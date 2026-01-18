from __future__ import annotations

import asyncio
import logging
import struct
import threading
import time
from datetime import timedelta
from typing import Any, Callable, Dict, List, TypeVar, Union

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

if pyS7 is not None:  # pragma: no cover - exercised only when library available
    try:
        from pyS7.constants import ConnectionType
        from pyS7.errors import (
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        )
    except (ImportError, AttributeError):  # pragma: no cover - defensive
        S7CommunicationError = S7ConnectionError = S7ReadResponseError = RuntimeError
        ConnectionType = None
else:  # pragma: no cover - library absent in tests
    S7CommunicationError = S7ConnectionError = S7ReadResponseError = RuntimeError
    ConnectionType = None


# Type variable for S7Client (pyS7.S7Client when available)
S7ClientT = TypeVar("S7ClientT")


# -----------------------------
# Coordinator
# -----------------------------
class S7Coordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator handling Snap7 connection, polling and writes."""

    _MIN_SCAN_INTERVAL = 0.05  # seconds

    # PDU (Protocol Data Unit) size constants
    _DEFAULT_PDU_SIZE = 240  # Default PDU size for S7 communication (bytes)
    _PDU_HEADER_RESERVED = (
        30  # Leave space in PDU for headers to avoid oversize read chunks
    )

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        connection_type: str = "rack_slot",
        rack: int | None = None,
        slot: int | None = None,
        local_tsap: str | None = None,
        remote_tsap: str | None = None,
        pys7_connection_type: str = "pg",  # PG, OP, or S7Basic
        port: int = 102,
        scan_interval: float = 0.5,
        # Timeout/Retry configuration
        op_timeout: float = 5.0,  # max time for a read/write cycle
        max_retries: int = 3,  # number of retries per operation
        backoff_initial: float = 0.5,  # initial backoff
        backoff_max: float = 2.0,  # max backoff between retries
        optimize_read: bool = True,  # enable optimized batch reads
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="s7plc_coordinator",
            update_interval=timedelta(
                seconds=max(scan_interval, self._MIN_SCAN_INTERVAL)
            ),
        )
        self._host = host
        self._connection_type = connection_type
        self._rack = rack
        self._slot = slot
        self._local_tsap = local_tsap
        self._remote_tsap = remote_tsap
        self._port = port

        # Map string to ConnectionType enum
        self._pys7_connection_type_str = pys7_connection_type
        self._pys7_connection_type = self._get_connection_type_enum(
            pys7_connection_type
        )

        self._default_scan_interval = max(float(scan_interval), self._MIN_SCAN_INTERVAL)

        # Timeout/retry settings
        self._op_timeout = float(op_timeout)
        self._max_retries = int(max_retries)
        self._backoff_initial = float(backoff_initial)
        self._backoff_max = float(backoff_max)
        self._optimize_read = bool(optimize_read)

        # Lock for async operations (state management)
        self._async_lock = asyncio.Lock()
        # Lock for sync operations in executor (PLC communication)
        self._sync_lock = threading.RLock()
        self._client: Any | None = None  # pyS7.S7Client when available

        # Address configuration: topic -> address string
        self._items: Dict[str, str] = {}

        # Read plan cache
        self._plans_batch: Dict[str, TagPlan] = {}
        self._plans_str: Dict[str, StringPlan] = {}

        # Cache for parsed tags used by writes
        self._write_tags: Dict[str, S7Tag] = {}

        # Scan interval bookkeeping
        self._item_scan_intervals: Dict[str, float] = {}
        self._item_next_read: Dict[str, float] = {}

        # Precision for REAL items (topic -> decimals or None for full precision)
        self._item_real_precisions: Dict[str, int | None] = {}

        # Store the latest values so entities keep their last state when a tag
        # is not due for polling in the current cycle.
        self._data_cache: Dict[str, Any] = {}

        # Performance: Cache PDU limit to avoid repeated attribute lookups
        self._pdu_limit_cache: int | None = None

    @property
    def host(self) -> str:
        """IP/hostname of the associated PLC."""
        return self._host

    def _get_connection_type_enum(self, connection_type_str: str) -> Any | None:
        """Convert string connection type to pyS7 ConnectionType enum.

        Args:
            connection_type_str: String identifier ('pg', 'op', or 's7basic')

        Returns:
            Corresponding ConnectionType enum value, or None if library unavailable
        """
        if ConnectionType is None:
            return None

        connection_type_map = {
            "pg": ConnectionType.PG,
            "op": ConnectionType.OP,
            "s7basic": ConnectionType.S7Basic,
        }
        return connection_type_map.get(connection_type_str.lower(), ConnectionType.PG)

    @property
    def connection_type(self) -> str:
        """Return connection type: 'rack_slot' or 'tsap'."""
        return self._connection_type

    @property
    def rack(self) -> int | None:
        """Return rack number for rack/slot connection."""
        return self._rack

    @property
    def slot(self) -> int | None:
        """Return slot number for rack/slot connection."""
        return self._slot

    @property
    def local_tsap(self) -> str | None:
        """Return local TSAP for TSAP connection."""
        return self._local_tsap

    @property
    def remote_tsap(self) -> str | None:
        """Return remote TSAP for TSAP connection."""
        return self._remote_tsap

    # -------------------------
    # Connection handling
    # -------------------------
    def _drop_connection(self) -> None:
        """Safely close PLC connection, ensuring socket cleanup even on errors.

        Uses multi-level cleanup strategy:
        1. Call disconnect() on client
        2. On failure, attempt direct socket.close()
        3. Clear socket reference to enable reconnection
        """
        # Invalidate PDU cache immediately - must happen regardless of client state
        self._pdu_limit_cache = None

        if self._client and self._client.is_connected:
            try:
                self._client.disconnect()
            except (OSError, RuntimeError) as err:  # pragma: no cover
                _LOGGER.debug("Error during disconnect call: %s", err)
                # Fallback: try to close socket directly if disconnect() failed
                try:
                    socket = getattr(self._client, "socket", None)
                    if socket:
                        socket.close()
                        _LOGGER.debug("Socket closed directly after disconnect failure")
                except Exception as socket_err:  # pragma: no cover
                    _LOGGER.debug("Failed to close socket directly: %s", socket_err)
            finally:
                # Clear socket reference to ensure reconnection
                try:
                    if hasattr(self._client, "socket"):
                        self._client.socket = None
                except Exception:  # pragma: no cover
                    pass

    def _ensure_connected(self) -> None:
        """Ensure PLC connection is established, with proper cleanup on failure.

        Creates S7Client if needed and establishes connection using either
        TSAP or rack/slot addressing.

        Raises:
            RuntimeError: If pyS7 unavailable or connection fails
        """
        if self._client is None:
            if pyS7 is None:
                raise RuntimeError("pyS7 not available")

            # Create client based on connection type
            if self._local_tsap and self._remote_tsap:
                self._client = pyS7.S7Client(
                    address=self._host,
                    local_tsap=self._local_tsap,
                    remote_tsap=self._remote_tsap,
                    port=self._port,
                    connection_type=self._pys7_connection_type,
                )
            else:
                self._client = pyS7.S7Client(
                    self._host,
                    self._rack,
                    self._slot,
                    port=self._port,
                    connection_type=self._pys7_connection_type,
                )

        if not getattr(self._client, "socket", None):
            try:
                self._client.connect()
                if self._local_tsap and self._remote_tsap:
                    _LOGGER.info(
                        "Connected to S7 PLC %s (TSAP %s/%s)",
                        self._host,
                        self._local_tsap,
                        self._remote_tsap,
                    )
                else:
                    _LOGGER.info(
                        "Connected to S7 PLC %s (rack=%s slot=%s)",
                        self._host,
                        self._rack,
                        self._slot,
                    )
            except (
                OSError,
                RuntimeError,
                S7CommunicationError,
                S7ConnectionError,
            ) as err:
                # Ensure cleanup if connection failed
                self._drop_connection()
                raise RuntimeError(f"Connection to PLC {self._host} failed: {err}")

    def is_connected(self) -> bool:
        """Check if PLC connection is active.

        Thread-safe check using S7Client's is_connected property.

        Note:
            Requires pyS7 >= 2.3.0 for is_connected property support.

        Returns:
            True if client exists and is connected
        """
        with self._sync_lock:
            return bool(self._client and self._client.is_connected)

    def connect(self) -> None:
        """Establish the connection if needed (thread-safe).

        Wrapper around _ensure_connected with thread synchronization.
        """
        with self._sync_lock:
            self._ensure_connected()

    def disconnect(self) -> None:
        """Close the PLC connection (thread-safe).

        Wrapper around _drop_connection with thread synchronization.
        """
        with self._sync_lock:
            self._drop_connection()

    # -------------------------
    # Address management
    # -------------------------
    async def add_item(
        self,
        topic: str,
        address: str,
        scan_interval: Union[float, int, None] = None,
        real_precision: int | None = None,
    ) -> None:
        """Map a topic to a PLC address and invalidate caches.

        Args:
            topic: Unique identifier for this data point
            address: PLC address string (e.g., 'DB1.DBX0.0')
            scan_interval: Custom scan interval (seconds), None for default
            real_precision: Decimal places for REAL values, None for full precision
        """
        async with self._async_lock:
            self._items[topic] = address
            self._item_scan_intervals[topic] = self._normalize_scan_interval(
                scan_interval
            )
            if real_precision is None:
                self._item_real_precisions.pop(topic, None)
            else:
                self._item_real_precisions[topic] = real_precision
            self._item_next_read[topic] = time.monotonic()
            self._invalidate_cache()
            self._update_min_interval_locked()

    def _invalidate_cache(self) -> None:
        """Clear read and write plan caches.

        Called when items are added or modified to ensure plans are rebuilt.
        """
        self._plans_batch.clear()
        self._plans_str.clear()
        self._write_tags.clear()

    def _build_tag_cache(self) -> None:
        """Build read plans for scalar and string tags.

        Separates items into batch-readable scalars and strings that require
        individual handling. Stores results in _plans_batch and _plans_str.
        """
        plans_batch, plans_str = build_plans(
            self._items, precisions=self._item_real_precisions
        )
        self._plans_batch = {plan.topic: plan for plan in plans_batch}
        self._plans_str = {plan.topic: plan for plan in plans_str}

    def _normalize_scan_interval(self, scan_interval: Union[float, int, None]) -> float:
        """Return a sanitized scan interval for an item.

        Args:
            scan_interval: Requested scan interval (seconds) or None for default

        Returns:
            Validated scan interval, enforcing minimum and default values
        """

        if scan_interval is None:
            return self._default_scan_interval
        try:
            interval = float(scan_interval)
        except (TypeError, ValueError):
            interval = self._default_scan_interval
        else:
            if interval <= 0:
                interval = self._default_scan_interval
        return max(interval, self._MIN_SCAN_INTERVAL)

    def _update_min_interval_locked(self) -> None:
        """Update the coordinator polling interval based on registered tags.

        Sets update_interval to the minimum of all item scan intervals,
        ensuring it doesn't go below _MIN_SCAN_INTERVAL.
        """

        if self._item_scan_intervals:
            min_interval = min(self._item_scan_intervals.values())
        else:
            min_interval = self._default_scan_interval

        min_interval = max(min_interval, self._MIN_SCAN_INTERVAL)
        self.update_interval = timedelta(seconds=min_interval)

    # -------------------------
    # Retry/timeout helpers
    # -------------------------
    def _sleep(self, seconds: float) -> None:
        """Sleep for the specified duration, handling interruptions gracefully.

        Args:
            seconds: Duration to sleep (seconds), negative values are clamped to 0
        """
        try:
            time.sleep(max(0.0, seconds))
        except OSError as err:
            _LOGGER.debug("Sleep interrupted: %s", err)

    def _retry(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` with retries using exponential backoff.

        Reconnects to the PLC between attempts on error.

        Note: This method uses synchronous time.sleep() for backoff delays.
        It must be called via hass.async_add_executor_job() to avoid blocking
        the Home Assistant event loop.

        Args:
            func: The callable to execute with retries.
            *args: Positional arguments to pass to func.
            **kwargs: Keyword arguments to pass to func.

        Returns:
            The return value of func if successful.

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        attempt = 0
        last_exc: Exception | None = None
        error_category = "unknown"

        while attempt <= self._max_retries:
            try:
                # Ensure connection before each attempt
                self._ensure_connected()
                return func(*args, **kwargs)
            except (S7CommunicationError, S7ConnectionError) as e:
                # S7-specific communication errors (most common)
                last_exc = e
                error_category = "s7_communication"
                _LOGGER.debug(
                    "S7 communication error on attempt %s/%s: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
                self._drop_connection()
            except S7ReadResponseError as e:
                # S7 response parsing errors
                last_exc = e
                error_category = "s7_response"
                _LOGGER.debug(
                    "S7 response error on attempt %s/%s: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
                self._drop_connection()
            except OSError as e:
                # Network/socket errors
                last_exc = e
                error_category = "network"
                _LOGGER.debug(
                    "Network error on attempt %s/%s: %s (errno: %s)",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                    getattr(e, "errno", "unknown"),
                )
                self._drop_connection()
            except struct.error as e:
                # Data parsing errors (usually indicates protocol mismatch)
                last_exc = e
                error_category = "data_parsing"
                _LOGGER.warning(
                    "Data parsing error on attempt %s/%s: %s (check PLC data type)",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
                self._drop_connection()
            except IndexError as e:
                # Array access errors (unexpected response size)
                last_exc = e
                error_category = "unexpected_response"
                _LOGGER.warning(
                    "Unexpected response size on attempt %s/%s: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                    exc_info=True,
                )
                self._drop_connection()
            except RuntimeError as e:
                # Generic runtime errors (catch-all for pyS7 issues)
                last_exc = e
                error_category = "runtime"
                _LOGGER.debug(
                    "Runtime error on attempt %s/%s: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
                self._drop_connection()

            # Check if we should retry
            if attempt == self._max_retries:
                break

            # Exponential backoff
            backoff = min(self._backoff_initial * (2**attempt), self._backoff_max)
            _LOGGER.debug(
                "Retrying after %.2fs backoff (attempt %s/%s, error: %s)",
                backoff,
                attempt + 1,
                self._max_retries,
                error_category,
            )
            self._sleep(backoff)
            attempt += 1

        # All attempts exhausted
        if last_exc is not None:
            _LOGGER.error(
                "Operation failed after %s attempts (category: %s): %s",
                self._max_retries + 1,
                error_category,
                last_exc,
            )
            raise RuntimeError(
                f"Operation failed after {self._max_retries + 1} attempts "
                f"({error_category}): {last_exc}"
            ) from last_exc
        raise RuntimeError("Operation failed without specific exception")

    # -------------------------
    # Update loop
    # -------------------------
    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from PLC (called by DataUpdateCoordinator).

        Determines which tags are due for reading based on their individual
        scan intervals, reads them via executor, and updates the cache.

        Returns:
            Dictionary of all cached values (due and non-due items)

        Raises:
            UpdateFailed: On connection or read errors
        """
        now = time.monotonic()

        async with self._async_lock:
            if not self._plans_batch and not self._plans_str:
                self._build_tag_cache()
            due_topics = [
                topic for topic, due in self._item_next_read.items() if due <= now
            ]

            if not due_topics and not self._data_cache:
                # First refresh without cached data: read all topics once.
                due_topics = list(self._items.keys())
                now = time.monotonic()
                for topic in due_topics:
                    self._item_next_read[topic] = now

            plans_batch = [
                self._plans_batch[topic]
                for topic in due_topics
                if topic in self._plans_batch
            ]
            plans_str = [
                self._plans_str[topic]
                for topic in due_topics
                if topic in self._plans_str
            ]

        if not plans_batch and not plans_str:
            async with self._async_lock:
                return dict(self._data_cache)

        results = await self.hass.async_add_executor_job(
            self._read_all, plans_batch, plans_str
        )

        async with self._async_lock:
            read_time = time.monotonic()
            for topic in due_topics:
                interval = self._item_scan_intervals.get(
                    topic, self._default_scan_interval
                )
                interval = max(interval, self._MIN_SCAN_INTERVAL)
                self._item_next_read[topic] = read_time + interval
            self._data_cache.update(results)
            return dict(self._data_cache)

    def _get_pdu_limit(self) -> int:
        """Calculate usable PDU size for payload, accounting for protocol headers.

        Uses cached value if available to avoid repeated attribute lookups.
        Cache is invalidated when connection is dropped.

        Returns:
            Maximum payload size in bytes (PDU size minus reserved header space),
            minimum value of 1 byte
        """
        # Return cached value if available
        if self._pdu_limit_cache is not None:
            return self._pdu_limit_cache

        # Calculate and cache the PDU limit
        size = getattr(
            self._client,
            "pdu_length",
            getattr(self._client, "pdu_size", self._DEFAULT_PDU_SIZE),
        )
        self._pdu_limit_cache = max(1, int(size) - self._PDU_HEADER_RESERVED)
        return self._pdu_limit_cache

    def _read_s7_string(self, db: int, start: int, is_wstring: bool = False) -> str:
        """Read S7 STRING or WSTRING from PLC memory.

        Handles both STRING (Latin-1, max 254 chars)
        and WSTRING (UTF-16, max 16382 chars).
        Reads in chunks if string exceeds PDU limit.

        Args:
            db: Data block number
            start: Starting byte address in the data block
            is_wstring: True for WSTRING (UTF-16), False for STRING (Latin-1)

        Returns:
            Decoded string content
        """
        # WSTRING: 4-byte header (2 bytes max_len, 2 bytes cur_len), UTF-16 data
        # STRING: 2-byte header (1 byte max_len, 1 byte cur_len), Latin-1 data
        header_size = 4 if is_wstring else 2
        hdr_tag = S7Tag(MemoryArea.DB, db, DataType.BYTE, start, 0, header_size)
        # Changed in pyS7 1.5.0 optimized=True by default
        header_bytes = self._retry(
            lambda: self._client.read([hdr_tag], optimize=self._optimize_read)
        )[0]

        if is_wstring:
            # WSTRING: 2-byte words for max_len and cur_len
            max_len = int.from_bytes(header_bytes[0:2], byteorder="big")
            cur_len = int.from_bytes(header_bytes[2:4], byteorder="big")
            bytes_per_char = 2  # UTF-16
        else:
            # STRING: 1-byte for max_len and cur_len
            max_len = int(header_bytes[0])
            cur_len = int(header_bytes[1])
            bytes_per_char = 1  # Latin-1

        _LOGGER.debug(
            "Reading S7 %s DB%d.%d max_len=%d cur_len=%d optimize=%s",
            "WSTRING" if is_wstring else "STRING",
            db,
            start,
            max_len,
            cur_len,
            self._optimize_read,
        )

        target_chars = max(0, min(max_len, cur_len))
        if target_chars == 0:
            return ""

        target_bytes = target_chars * bytes_per_char
        data = bytearray()
        pdu_limit = self._get_pdu_limit()
        offset = 0

        while offset < target_bytes:
            chunk_len = min(target_bytes - offset, pdu_limit)
            data_tag = S7Tag(
                MemoryArea.DB,
                db,
                DataType.BYTE,
                start + header_size + offset,
                0,
                chunk_len,
            )
            # Changed in pyS7 1.5.0 optimized=True by default
            chunk = self._retry(
                lambda: self._client.read([data_tag], optimize=self._optimize_read)
            )[0]
            _LOGGER.debug(
                "Read S7 %s chunk DB%d.%d len=%d optimize=%s",
                "WSTRING" if is_wstring else "STRING",
                db,
                start + header_size + offset,
                chunk_len,
                self._optimize_read,
            )
            data.extend(chunk)
            offset += chunk_len

        if is_wstring:
            return bytes(data).decode("utf-16-be", errors="ignore")
        else:
            return bytes(data).decode("latin-1", errors="ignore")

    def _tag_key(self, tag: S7Tag) -> tuple[Any, ...]:
        """Generate a unique key for tag deduplication.

        Args:
            tag: S7Tag instance to generate key for

        Returns:
            Tuple of tag attributes that uniquely identify it
        """
        return (
            tag.memory_area,
            tag.db_number,
            tag.data_type,
            tag.start,
            tag.bit_offset,
            tag.length,
        )

    def _read_batch(self, plans_batch: List[TagPlan]) -> Dict[str, Any]:
        """Read scalar tags in batch handling deduplication and post-processing.

        Args:
            plans_batch: List of TagPlan objects for scalar reads

        Returns:
            Dictionary mapping topic names to their read values

        Raises:
            OSError, RuntimeError, S7 errors: On communication failures
        """
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
            # Changed in pyS7 1.5.0 optimized=True by default
            values = self._retry(
                lambda: self._client.read(tags, optimize=self._optimize_read)
            )
            _LOGGER.debug(
                "Batch read %d tags optimize=%s", len(tags), self._optimize_read
            )
            for k, v in zip(order, values):
                for plan in groups[k]:
                    results[plan.topic] = plan.postprocess(v) if plan.postprocess else v
        except (OSError, RuntimeError) as err:
            _LOGGER.error("Batch read failed for %d tags: %s", len(plans_batch), err)
            raise
        except (
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        ) as err:
            _LOGGER.error(
                "S7 communication error during batch read of %d tags: %s",
                len(plans_batch),
                err,
            )
            raise
        return results

    def _read_strings(
        self, plans_str: List[StringPlan], deadline: float
    ) -> Dict[str, Any]:
        """Read strings respecting an absolute deadline.

        Args:
            plans_str: List of StringPlan objects for string reads
            deadline: Absolute monotonic timestamp to stop reading

        Returns:
            Dictionary mapping topic names to their string values

        Raises:
            UpdateFailed: On timeout or communication failures
        """
        results: Dict[str, Any] = {}
        for plan in plans_str:
            if time.monotonic() > deadline:
                _LOGGER.warning("String read timeout reached (%.2fs)", self._op_timeout)
                raise UpdateFailed(
                    f"String read timeout reached ({self._op_timeout:.2f}s)"
                )
            try:
                results[plan.topic] = self._read_s7_string(
                    plan.db, plan.start, plan.is_wstring
                )
            except (
                S7CommunicationError,
                S7ConnectionError,
                S7ReadResponseError,
            ) as err:
                _LOGGER.error(
                    "String read error: "
                    "S7 communication error reading %s (DB%d.%d): %s",
                    plan.topic,
                    plan.db,
                    plan.start,
                    err,
                )
                raise UpdateFailed(
                    f"S7 error reading string {plan.topic}: {err}"
                ) from err
            except (OSError, RuntimeError) as err:
                _LOGGER.error(
                    "String read error: Network/runtime error reading %s (DB%d.%d): %s",
                    plan.topic,
                    plan.db,
                    plan.start,
                    err,
                )
                raise UpdateFailed(f"Error reading string {plan.topic}: {err}") from err
        return results

    def _read_all(
        self, plans_batch: List[TagPlan], plans_str: List[StringPlan]
    ) -> Dict[str, Any]:
        """Read all planned tags with proper resource cleanup.

        Executed in executor thread pool to avoid blocking async event loop.

        Args:
            plans_batch: List of scalar tag plans to read
            plans_str: List of string plans to read

        Returns:
            Dictionary mapping all topic names to their values

        Raises:
            UpdateFailed: On connection or read failures
        """
        with self._sync_lock:
            try:
                self._ensure_connected()
            except (OSError, RuntimeError) as err:
                _LOGGER.error("Connection failed: %s", err)
                raise UpdateFailed(f"Connection failed: {err}") from err

        start_ts = time.monotonic()
        deadline = start_ts + self._op_timeout

        results: Dict[str, Any] = {}

        try:
            # ===== 1) Scalar batch with dedup & optimize =====
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

        except (
            OSError,
            RuntimeError,
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        ) as err:
            _LOGGER.exception("Read error")
            self._drop_connection()
            raise UpdateFailed(f"Read error: {err}") from err
        except Exception as err:  # pragma: no cover - catch unexpected errors
            _LOGGER.exception("Unexpected error during read")
            self._drop_connection()
            raise UpdateFailed(f"Unexpected read error: {err}") from err

        return results

    # -------------------------
    # Ad-hoc reads/writes
    # -------------------------
    def _get_or_parse_tag(self, address: str) -> S7Tag:
        """Get tag from cache or parse and cache it.

        Args:
            address: PLC address string

        Returns:
            Parsed S7Tag object
        """
        tag = self._write_tags.get(address)
        if tag is None:
            tag = parse_tag(address)
            self._write_tags[address] = tag
        return tag

    def _write_with_retry(self, address: str, tag: S7Tag, payload: Any) -> bool:
        """Execute write with retry and error handling.

        Centralized error handling for PLC write operations.

        Args:
            address: PLC address string (for logging)
            tag: Parsed S7Tag object
            payload: Value to write

        Returns:
            True if write was successful, False otherwise
        """
        with self._sync_lock:
            try:
                self._ensure_connected()
                self._retry(lambda: self._client.write([tag], [payload]))
                return True
            except (
                OSError,
                RuntimeError,
                S7CommunicationError,
                S7ConnectionError,
                S7ReadResponseError,
            ):
                _LOGGER.exception("Write error %s", address)
                self._drop_connection()
                return False
            except Exception:  # pragma: no cover - catch unexpected errors
                _LOGGER.exception("Unexpected write error %s", address)
                self._drop_connection()
                return False

    def _read_one(self, address: str) -> Any:
        """Read a single tag from PLC by address.

        Handles both strings and scalar values. Thread-safe via sync_lock.

        Args:
            address: PLC address string (e.g., 'DB1.DBX0.0', 'DB1.DBW10')

        Returns:
            Value read from PLC (type depends on tag data type)

        Raises:
            RuntimeError: On connection or read failures
        """
        with self._sync_lock:
            try:
                self._ensure_connected()
                tag = parse_tag(address)

                # Handle STRING types (CHAR array, STRING, WSTRING)
                if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
                    return self._read_s7_string(
                        tag.db_number, tag.start, is_wstring=False
                    )
                elif tag.data_type == DataType.STRING:
                    return self._read_s7_string(
                        tag.db_number, tag.start, is_wstring=False
                    )
                elif tag.data_type == DataType.WSTRING:
                    return self._read_s7_string(
                        tag.db_number, tag.start, is_wstring=True
                    )

                # Changed in pyS7 1.5.0 optimized=True by default
                value = self._retry(
                    lambda: self._client.read([tag], optimize=self._optimize_read)
                )[0]
                _LOGGER.debug(
                    "Read single tag %s optimize=%s", address, self._optimize_read
                )
                # Normalize BIT to bool
                if tag.data_type == DataType.BIT:
                    return bool(value)
                return apply_postprocess(tag.data_type, value)
            except (
                OSError,
                RuntimeError,
                S7CommunicationError,
                S7ConnectionError,
                S7ReadResponseError,
            ) as err:
                _LOGGER.error("Read error for %s: %s", address, err)
                self._drop_connection()
                raise RuntimeError(f"Failed to read {address}: {err}") from err
            except Exception as err:  # pragma: no cover - catch unexpected errors
                _LOGGER.exception("Unexpected read error for %s", address)
                self._drop_connection()
                raise RuntimeError(
                    f"Unexpected error reading {address}: {err}"
                ) from err

    def write_bool(self, address: str, value: bool) -> bool:
        """Write boolean value to PLC with proper error handling and cleanup.

        Args:
            address: PLC address for the boolean tag
            value: Boolean value to write

        Returns:
            True if write was successful, False otherwise
        """
        tag = self._get_or_parse_tag(address)
        if tag.data_type != DataType.BIT:
            raise ValueError("write_bool supports only bit addresses")
        return self._write_with_retry(address, tag, bool(value))

    def write_number(self, address: str, value: float) -> bool:
        """Write numeric value to PLC with proper error handling and cleanup.

        Args:
            address: PLC address for the numeric tag
            value: Numeric value to write (converted to int or float based on data type)

        Returns:
            True if write was successful, False otherwise
        """

        tag = self._get_or_parse_tag(address)

        if tag.data_type in (
            DataType.BIT,
            DataType.CHAR,
            DataType.STRING,
            DataType.WSTRING,
        ):
            raise ValueError("write_number requires a numeric address")

        if tag.data_type == DataType.REAL:
            payload = float(value)
        elif tag.data_type in (
            DataType.BYTE,
            DataType.WORD,
            DataType.DWORD,
            DataType.INT,
            DataType.DINT,
        ):
            payload = int(round(float(value)))
        else:  # pragma: no cover - defensive for unexpected future types
            raise ValueError("Unsupported data type for write_number")

        return self._write_with_retry(address, tag, payload)
