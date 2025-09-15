from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .plans import StringPlan, TagPlan, apply_postprocess, build_plans

_LOGGER = logging.getLogger(__name__)

try:
    from .address import DataType, MemoryArea, S7Tag, parse_tag, pyS7
except ImportError as err:
    _LOGGER.error("Failed to import S7 address helpers: %s", err)
    raise
except RuntimeError as err:  # pragma: no cover
    _LOGGER.error("Unexpected error importing S7 helpers: %s", err)
    raise


S7ClientT = "pyS7.S7Client"


# -----------------------------
# Coordinator
# -----------------------------
class S7Coordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator handling Snap7 connection, polling and writes."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        rack: int = 0,
        slot: int = 1,
        port: int = 102,
        scan_interval: float = 0.5,
        # Timeout/Retry configuration
        op_timeout: float = 5.0,  # max time for a read/write cycle
        max_retries: int = 3,  # number of retries per operation
        backoff_initial: float = 0.5,  # initial backoff
        backoff_max: float = 2.0,  # max backoff between retries
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="s7plc_coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._host = host
        self._rack = rack
        self._slot = slot
        self._port = port

        # Timeout/retry settings
        self._op_timeout = float(op_timeout)
        self._max_retries = int(max_retries)
        self._backoff_initial = float(backoff_initial)
        self._backoff_max = float(backoff_max)

        self._lock = threading.RLock()
        self._client: Optional[Any] = None  # S7Client when available

        # Address configuration: topic -> address string
        self._items: Dict[str, str] = {}

        # Read plan cache
        self._plans_batch: list[TagPlan] = []
        self._plans_str: list[StringPlan] = []

        # Cache for parsed tags used by writes
        self._write_tags: dict[str, S7Tag] = {}

    @property
    def host(self) -> str:
        """IP/hostname of the associated PLC."""
        return self._host

    # -------------------------
    # Connection handling
    # -------------------------
    def _drop_connection(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except (OSError, RuntimeError) as err:  # pragma: no cover
                _LOGGER.debug("Error during disconnection: %s", err)
        # Do not reset the instance; only the socket will reconnect

    def _ensure_connected(self) -> None:
        if self._client is None:
            if pyS7 is None:
                raise RuntimeError("pyS7 not available")
            self._client = pyS7.S7Client(
                self._host, self._rack, self._slot, port=self._port
            )
        if not getattr(self._client, "socket", None):
            try:
                self._client.connect()
                _LOGGER.info(
                    "Connected to S7 PLC %s (rack=%s slot=%s)",
                    self._host,
                    self._rack,
                    self._slot,
                )
            except (OSError, RuntimeError) as err:
                raise RuntimeError(f"Connection to PLC {self._host} failed: {err}")

    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._client and getattr(self._client, "socket", None))

    def connect(self) -> None:
        """Establish the connection if needed (thread-safe)."""
        with self._lock:
            self._ensure_connected()

    def disconnect(self) -> None:
        """Close the PLC connection (thread-safe)."""
        with self._lock:
            self._drop_connection()

    # -------------------------
    # Address management
    # -------------------------
    def add_item(self, topic: str, address: str) -> None:
        """Map a topic to a PLC address and invalidate caches."""
        with self._lock:
            self._items[topic] = address
            self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Clear read and write plan caches."""
        self._plans_batch.clear()
        self._plans_str.clear()
        self._write_tags.clear()

    def _build_tag_cache(self) -> None:
        """Build read plans for scalar and string tags."""
        self._plans_batch, self._plans_str = build_plans(self._items)

    # -------------------------
    # Retry/timeout helpers
    # -------------------------
    def _sleep(self, seconds: float) -> None:
        try:
            time.sleep(max(0.0, seconds))
        except OSError:
            pass

    def _retry(self, func, *args, **kwargs):
        """Execute ``func`` with retries using exponential backoff.
        Reconnects to the PLC between attempts on error.
        """
        attempt = 0
        last_exc = None
        while attempt <= self._max_retries:
            try:
                # Ensure connection before each attempt
                self._ensure_connected()
                return func(*args, **kwargs)
            except (OSError, RuntimeError) as e:  # log, drop connection and retry
                last_exc = e
                _LOGGER.debug("Attempt %s failed: %s", attempt + 1, e)
                self._drop_connection()
                if attempt == self._max_retries:
                    break
                backoff = min(self._backoff_initial * (2**attempt), self._backoff_max)
                self._sleep(backoff)
                attempt += 1
        # Attempts exhausted
        raise (
            last_exc
            if last_exc
            else RuntimeError("Operation failed without specific exception")
        )

    # -------------------------
    # Update loop
    # -------------------------
    async def _async_update_data(self) -> Dict[str, Any]:
        if not self._plans_batch and not self._plans_str:
            with self._lock:
                self._build_tag_cache()
        return await self.hass.async_add_executor_job(self._read_all)

    def _get_pdu_limit(self) -> int:
        # payload < PDU to leave space for headers (snap7 reserves ~18B)
        size = getattr(
            self._client, "pdu_length", getattr(self._client, "pdu_size", 240)
        )
        return max(1, int(size) - 30)

    def _read_s7_string(self, db: int, start: int) -> str:
        # Header: max_len, cur_len
        hdr_tag = S7Tag(MemoryArea.DB, db, DataType.BYTE, start, 0, 2)
        max_len, cur_len = self._client.read([hdr_tag], optimize=False)[0]
        # Type safety
        max_len = int(max_len)
        cur_len = int(cur_len)
        target = max(0, min(max_len, cur_len))
        if target == 0:
            return ""

        data = bytearray()
        pdu_limit = self._get_pdu_limit()
        offset = 0
        while offset < target:
            chunk_len = min(target - offset, pdu_limit)
            data_tag = S7Tag(
                MemoryArea.DB, db, DataType.BYTE, start + 2 + offset, 0, chunk_len
            )
            chunk = self._retry(lambda: self._client.read([data_tag], optimize=False))[
                0
            ]
            data.extend(chunk)
            offset += chunk_len

        return bytes(data).decode("latin-1", errors="ignore")

    def _tag_key(self, tag) -> tuple:
        return (
            tag.memory_area,
            tag.db_number,
            tag.data_type,
            tag.start,
            tag.bit_offset,
            tag.length,
        )

    def _read_batch(self, plans_batch: list[TagPlan]) -> Dict[str, Any]:
        """Read scalar tags in batch handling deduplication and post-processing."""
        results: Dict[str, Any] = {}
        if not plans_batch:
            return results

        groups: dict[tuple, list[TagPlan]] = {}
        order: list[tuple] = []
        for plan in plans_batch:
            k = self._tag_key(plan.tag)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(plan)

        try:
            tags = [groups[k][0].tag for k in order]
            values = self._retry(lambda: self._client.read(tags, optimize=False))
            for k, v in zip(order, values):
                for plan in groups[k]:
                    results[plan.topic] = plan.postprocess(v) if plan.postprocess else v
        except (OSError, RuntimeError):
            _LOGGER.exception("Batch read error")
            for plan in plans_batch:
                results.setdefault(plan.topic, None)
        return results

    def _read_strings(
        self, plans_str: list[StringPlan], deadline: float
    ) -> Dict[str, Any]:
        """Read strings respecting an absolute deadline."""
        results: Dict[str, Any] = {}
        for plan in plans_str:
            if time.monotonic() > deadline:
                _LOGGER.warning("String read timeout reached (%.2fs)", self._op_timeout)
                results.setdefault(plan.topic, None)
                continue
            try:
                results[plan.topic] = self._read_s7_string(plan.db, plan.start)
            except (OSError, RuntimeError):
                _LOGGER.exception("String read error %s", plan.topic)
                results.setdefault(plan.topic, None)
        return results

    def _read_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                self._ensure_connected()
            except (OSError, RuntimeError) as e:
                _LOGGER.error("Connection failed: %s", e)
                return {}
            plans_batch = list(self._plans_batch)
            plans_str = list(self._plans_str)

        start_ts = time.monotonic()
        deadline = start_ts + self._op_timeout

        results: Dict[str, Any] = {}

        try:
            # ===== 1) Scalar batch with dedup & optimize=False =====
            if plans_batch:
                results.update(self._read_batch(plans_batch))

            # ===== 2) Strings (with deadline) =====
            if plans_str:
                results.update(self._read_strings(plans_str, deadline))

            # ===== 3) Timeout check after batch =====
            if time.monotonic() > deadline:
                _LOGGER.warning("Batch read timeout reached (%.2fs)", self._op_timeout)
                for plan in plans_str:
                    results.setdefault(plan.topic, None)
                return results

        except (OSError, RuntimeError):
            _LOGGER.exception("Read error")
            for plan in plans_batch:
                results.setdefault(plan.topic, None)
            for plan in plans_str:
                results.setdefault(plan.topic, None)
            self._drop_connection()

        return results

    # -------------------------
    # Ad-hoc reads/writes
    # -------------------------
    def _read_one(self, address: str) -> Any:
        tag = parse_tag(address)
        if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
            return self._read_s7_string(tag.db_number, tag.start)

        value = self._retry(lambda: self._client.read([tag], optimize=False))[0]
        # Normalize BIT to bool
        if tag.data_type == DataType.BIT:
            return bool(value)
        return apply_postprocess(tag.data_type, value)

    def write_bool(self, address: str, value: bool) -> bool:
        tag = self._write_tags.get(address)
        if tag is None:
            tag = parse_tag(address)
            self._write_tags[address] = tag
        if tag.data_type != DataType.BIT:
            raise ValueError("write_bool supports only bit addresses")
        with self._lock:
            try:
                self._ensure_connected()
                self._retry(lambda: self._client.write([tag], [bool(value)]))
                return True
            except (OSError, RuntimeError):
                _LOGGER.exception("Write error %s", address)
                self._drop_connection()
                return False
