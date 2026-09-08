from __future__ import annotations

import asyncio
import logging
import struct
import time
from datetime import datetime, timedelta
from typing import Any, Callable, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyS7.constants import ConnectionType
from pyS7.errors import S7CommunicationError, S7ConnectionError, S7ReadResponseError

from .plc.address import DataType, S7Tag, parse_tag
from .plc.connection_manager import S7ConnectionManager
from .plc.plans import StringPlan, TagPlan, build_plans
from .plc.read_executor import S7ReadError, S7ReadExecutor
from .write_manager import S7WriteManager

_LOGGER = logging.getLogger(__name__)


# Type variable for S7Client
S7ClientT = TypeVar("S7ClientT")


# -----------------------------
# Coordinator
# -----------------------------
class S7Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator handling pys7 connection, polling and writes."""

    _MIN_SCAN_INTERVAL = 0.05  # seconds

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
        enable_write_batching: bool = True,  # enable automatic write batching
        enable_metrics: bool = False,  # disable pyS7 performance metrics
        connection_enabled: bool = True,
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
        self._enable_write_batching = bool(enable_write_batching)
        self._enable_metrics = bool(enable_metrics)
        self._shutdown_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._async_lock = asyncio.Lock()
        self._connection = S7ConnectionManager(
            host=self._host,
            rack=self._rack,
            slot=self._slot,
            local_tsap=self._local_tsap,
            remote_tsap=self._remote_tsap,
            port=self._port,
            pys7_connection_type=self._pys7_connection_type,
            enable_metrics=self._enable_metrics,
            op_timeout=self._op_timeout,
            connection_enabled=bool(connection_enabled),
            error_type=HomeAssistantError,
        )

        # Address configuration: topic -> address string
        self._items: dict[str, str] = {}

        # Read plan cache
        self._plans_batch: dict[str, TagPlan] = {}
        self._plans_str: dict[str, StringPlan] = {}

        # Cache for parsed tags (shared by reads and writes)
        self._tag_cache: dict[str, S7Tag] = {}

        # Scan interval bookkeeping
        self._item_scan_intervals: dict[str, float] = {}
        self._item_next_read: dict[str, float] = {}

        # Precision for REAL items (topic -> decimals or None for full precision)
        self._item_real_precisions: dict[str, int | None] = {}

        # Store the latest values so entities keep their last state when a tag
        # is not due for polling in the current cycle.
        self._data_cache: dict[str, Any] = {}
        # Per-topic revisions distinguish a fresh PLC read from a coordinator
        # update that merely returns this topic's cached value.
        self._topic_read_revisions: dict[str, int] = {}

        # Health check bookkeeping (updated by normal read cycle)
        self._last_health_ok: bool | None = None
        self._last_health_latency: float | None = None
        self._last_health_time: datetime | None = None

        # Error tracking
        self._last_error_category: str | None = None
        self._last_error_message: str | None = None
        self._error_count_by_category: dict[str, int] = {}

        self._read_executor = S7ReadExecutor(
            read_tags=lambda tags: self._retry(
                lambda: self._connection.client.read(tags, optimize=self._optimize_read)
            ),
            optimize_read=self._optimize_read,
            op_timeout=self._op_timeout,
            monotonic=lambda: time.monotonic(),
        )

        self._write_manager = S7WriteManager(
            hass,
            host=self._host,
            op_timeout=self._op_timeout,
            state_lock=self._async_lock,
            write_multi=lambda writes: self.write_multi(writes),
            operation=self._connection.operation,
            check_connection=self._connection.check_available,
            get_generation=lambda: self._connection.generation,
        )

    @property
    def host(self) -> str:
        """IP/hostname of the associated PLC."""
        return self._host

    @property
    def pys7_connection_type_str(self) -> str:
        """Return the pyS7 connection type string (e.g. 'pg', 'op', 's7basic')."""
        return self._pys7_connection_type_str

    @property
    def enable_metrics(self) -> bool:
        """Return whether performance metrics are enabled."""
        return self._enable_metrics

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
    @property
    def connection_enabled(self) -> bool:
        """Return whether communication with this PLC is allowed."""
        return self._connection.enabled

    async def async_enable_connection(self) -> None:
        """Allow communication and immediately request a connection attempt."""
        async with self._lifecycle_lock:
            if not self._connection.enable():
                return
            self.async_set_updated_data(dict(self._data_cache))
        await self.async_request_refresh()

    async def async_disable_connection(self) -> None:
        """Stop retries, pending writes and the active PLC connection."""
        self._connection.disable()
        async with self._lifecycle_lock:
            # Reassert after acquiring the lock: an enable may have preceded us.
            self._connection.disable()
            await self._stop_io(
                HomeAssistantError("PLC connection is manually disabled")
            )
            self._last_health_ok = False
            self.async_set_updated_data(dict(self._data_cache))

    def is_connected(self) -> bool:
        """Check if the PLC connection is active."""
        return self._connection.is_connected()

    async def async_health_check(self) -> dict[str, Any]:
        """Run a lightweight health check against the PLC.

        Updates internal health bookkeeping and returns a summary dict.
        """
        async with self._connection.operation():
            start = time.monotonic()
            ok = False
            error: str | None = None
            try:
                await self._connection.ensure_connected()
                client = self._connection.client
                if client is None:
                    raise RuntimeError("Client not initialized")

                # Prefer a real PLC call if available;
                # otherwise rely on connection flag
                if hasattr(client, "get_cpu_info"):
                    try:
                        await self._connection.perform_io(
                            lambda: self._connection.client.get_cpu_info()
                        )
                    except Exception as err:
                        # Catch all exceptions from pyS7 library
                        # calls which may raise various undocumented exception types
                        # beyond the standard S7 errors
                        raise RuntimeError(f"CPU info probe failed: {err}") from err
                else:
                    # Fallback: ensure the driver reports connected
                    if not getattr(client, "is_connected", False):
                        raise RuntimeError("Client reports not connected")

                ok = True
            except (
                OSError,
                RuntimeError,
                S7CommunicationError,
                S7ConnectionError,
            ) as err:
                error = str(err)
            finally:
                latency = time.monotonic() - start

            # A probe completed during stop must not publish a healthy state.
            self._connection.check_available()
            # Record state
            self._last_health_ok = ok
            self._last_health_latency = round(latency, 2)
            self._last_health_time = datetime.now()

            return {
                "ok": ok,
                "latency": latency,
                "error": error,
            }

    @property
    def pys7_metrics(self) -> Any | None:
        """Return the pyS7 client metrics object, or None if unavailable.

        The metrics object exposes connection/operation/performance counters
        collected by the pyS7 library (requires pyS7 >= 2.7.0 with
        ``enable_metrics=True``, which is the default).
        """
        if self._connection.client is None:
            return None
        return getattr(self._connection.client, "metrics", None)

    @property
    def pys7_metrics_dict(self) -> dict[str, Any]:
        """Return pyS7 metrics as a plain dict (empty if unavailable)."""
        metrics = self.pys7_metrics
        if metrics is None:
            return {}
        try:
            return metrics.as_dict()
        except Exception:  # pragma: no cover - defensive
            return {}

    @property
    def last_health_ok(self) -> bool | None:
        return self._last_health_ok

    @property
    def last_health_latency(self) -> float | None:
        return self._last_health_latency

    @property
    def last_error_category(self) -> str | None:
        """Return the category of the last error encountered."""
        return self._last_error_category

    @property
    def last_error_message(self) -> str | None:
        """Return the message of the last error encountered."""
        return self._last_error_message

    @property
    def error_count_by_category(self) -> dict[str, int]:
        """Return error counts grouped by category."""
        return dict(self._error_count_by_category)

    def get_scan_interval(self, topic: str) -> float:
        """Return the effective scan interval for *topic*."""
        return self._item_scan_intervals.get(topic, self._default_scan_interval)

    def get_real_precision(self, topic: str) -> int | None:
        """Return the REAL precision configured for *topic*, or ``None``."""
        return self._item_real_precisions.get(topic)

    def is_string_plan(self, topic: str) -> bool:
        """Return ``True`` if *topic* is read as a string."""
        return topic in self._plans_str

    def get_batch_plan(self, topic: str):
        """Return the ``TagPlan`` for *topic*, or ``None``."""
        return self._plans_batch.get(topic)

    async def connect(self) -> None:
        """Establish the connection if needed."""
        await self._connection.ensure_connected()

    async def disconnect(self) -> None:
        """Close the PLC connection and cancel pending writes."""
        async with self._lifecycle_lock:
            await self._stop_io(HomeAssistantError("PLC connection was disconnected"))

    async def _stop_io(self, error: HomeAssistantError) -> None:
        """Coordinate batch cancellation and PLC draining under the lifecycle lock."""
        await self._connection.stop(
            state_lock=self._async_lock,
            cancel_batches=lambda: self._write_manager.cancel_batches(error),
            batch_tasks=lambda: self._write_manager.tasks,
        )

    async def async_shutdown(self) -> None:
        """Permanently stop communication, even if an unload caller is cancelled."""
        previous = self._shutdown_task
        if previous is None or (
            previous.done()
            and (previous.cancelled() or previous.exception() is not None)
        ):
            self._connection.begin_shutdown()
            self._shutdown_task = asyncio.create_task(self._finish_shutdown())
            self._shutdown_task.add_done_callback(self._consume_task_result)
        await asyncio.shield(self._shutdown_task)

    async def _finish_shutdown(self) -> None:
        async with self._lifecycle_lock:
            # Stop coordinator/debouncer scheduling before draining active PLC
            # operations. The permanent admission barrier is already set.
            await super().async_shutdown()
            await self._stop_io(HomeAssistantError("PLC coordinator is shut down"))
            self._last_health_ok = False
            # An already-running HA refresh can reschedule in its finally block.
            # Clear any such timer after its PLC operation has finished too.
            await super().async_shutdown()

    @staticmethod
    def _consume_task_result(task: asyncio.Task) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                _LOGGER.error("PLC background task failed: %s", error)

    # -------------------------
    # Address management
    # -------------------------
    async def add_item(
        self,
        topic: str,
        address: str,
        scan_interval: float | int | None = None,
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
            self._topic_read_revisions.pop(topic, None)
            self._invalidate_cache()
            self._update_min_interval_locked()

    def get_topic_read_revision(self, topic: str) -> int:
        """Return the number of successful PLC reads containing ``topic``."""
        return self._topic_read_revisions.get(topic, 0)

    def _invalidate_cache(self) -> None:
        """Clear read and write plan caches.

        Called when items are added or modified to ensure plans are rebuilt.
        """
        self._plans_batch.clear()
        self._plans_str.clear()
        self._tag_cache.clear()

    def _build_tag_cache(self) -> None:
        """Build read plans for scalar and string tags.

        Separates items into batch-readable scalars and strings that require
        individual handling. Stores results in _plans_batch and _plans_str.
        """
        plans_batch, plans_str = build_plans(
            self._items,
            precisions=self._item_real_precisions,
            tag_cache=self._tag_cache,
        )
        self._plans_batch = {plan.topic: plan for plan in plans_batch}
        self._plans_str = {plan.topic: plan for plan in plans_str}

    def _normalize_scan_interval(self, scan_interval: float | int | None) -> float:
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
    async def _retry(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` with retries using exponential backoff.

        Reconnects to the PLC between attempts on error.

        Args:
            func: The callable to execute with retries.  May return a
                  coroutine (async client) or a plain value (tests).
            *args: Positional arguments to pass to func.
            **kwargs: Keyword arguments to pass to func.

        Returns:
            The return value of func if successful.

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        async with self._connection.operation():
            attempt = 0
            last_exc: Exception | None = None
            error_category = "unknown"

            while attempt <= self._max_retries:
                self._connection.check_available()
                try:
                    return await self._connection.perform_io(func, *args, **kwargs)
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
                    await self._connection.drop_connection()
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
                    await self._connection.drop_connection()
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
                    await self._connection.drop_connection()
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
                    await self._connection.drop_connection()
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
                    await self._connection.drop_connection()
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
                    await self._connection.drop_connection()

                self._connection.check_available()
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
                await self._connection.sleep(backoff)
                attempt += 1

            # All attempts exhausted
            if last_exc is not None:
                # Track error for diagnostics
                self._last_error_category = error_category
                self._last_error_message = str(last_exc)
                self._error_count_by_category[error_category] = (
                    self._error_count_by_category.get(error_category, 0) + 1
                )

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
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from PLC (called by DataUpdateCoordinator).

        Determines which tags are due for reading based on their individual
        scan intervals, reads them via executor, and updates the cache.
        Updates health status based on read cycle outcome.

        Returns:
            Dictionary of all cached values (due and non-due items)

        Raises:
            UpdateFailed: On connection or read errors
        """
        if (
            self._connection.shutdown
            or not self._connection.enabled
            or self._connection.stopping
        ):
            return dict(self._data_cache)
        async with self._connection.operation():
            start_time = time.monotonic()
            now = start_time

            async with self._async_lock:
                self._connection.check_available()
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

            try:
                results = await self._read_all(plans_batch, plans_str)
                self._connection.check_available()
                # Update health: read succeeded
                latency = round(time.monotonic() - start_time, 2)
                self._last_health_ok = True
                self._last_health_latency = latency
                # Clear error info on success
                self._last_error_category = None
                self._last_error_message = None
            except UpdateFailed:
                # Update health: read failed
                latency = round(time.monotonic() - start_time, 2)
                self._last_health_ok = False
                self._last_health_latency = latency
                raise

            async with self._async_lock:
                self._connection.check_available()
                read_time = time.monotonic()
                for topic in due_topics:
                    interval = self._item_scan_intervals.get(
                        topic, self._default_scan_interval
                    )
                    interval = max(interval, self._MIN_SCAN_INTERVAL)
                    self._item_next_read[topic] = read_time + interval
                    if topic in results:
                        self._topic_read_revisions[topic] = (
                            self._topic_read_revisions.get(topic, 0) + 1
                        )
                self._data_cache.update(results)
                return dict(self._data_cache)

    async def _read_all(
        self, plans_batch: list[TagPlan], plans_str: list[StringPlan]
    ) -> dict[str, Any]:
        """Read all planned tags.

        Args:
            plans_batch: List of scalar tag plans to read
            plans_str: List of string plans to read

        Returns:
            Dictionary mapping all topic names to their values

        Raises:
            UpdateFailed: On connection or read failures
        """
        try:
            await self._connection.ensure_connected()
        except (OSError, RuntimeError) as err:
            _LOGGER.error("Connection failed: %s", err)
            raise UpdateFailed(f"Connection failed: {err}") from err

        start_ts = time.monotonic()
        deadline = start_ts + self._op_timeout

        results: dict[str, Any] = {}

        try:
            # ===== 1) Scalar batch with dedup & optimize =====
            if plans_batch:
                results.update(await self._read_executor.read_batch(plans_batch))

            # ===== 2) Strings (with deadline) =====
            if plans_str:
                results.update(
                    await self._read_executor.read_strings(plans_str, deadline)
                )

            # ===== 3) Timeout check after batch =====
            if time.monotonic() > deadline:
                _LOGGER.warning("Batch read timeout reached (%.2fs)", self._op_timeout)
                for plan in plans_str:
                    results.setdefault(plan.topic, None)
                return results

        except S7ReadError as err:
            # Preserve the reader's message and original cause without another
            # disconnect or the generic read-error prefix.
            raise UpdateFailed(str(err)) from err.__cause__
        except (
            OSError,
            RuntimeError,
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        ) as err:
            _LOGGER.exception("Read error")
            await self._connection.drop_connection()
            raise UpdateFailed(f"Read error: {err}") from err
        except HomeAssistantError:
            raise
        except Exception as err:  # pragma: no cover - catch unexpected errors
            _LOGGER.exception("Unexpected error during read")
            await self._connection.drop_connection()
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
        tag = self._tag_cache.get(address)
        if tag is None:
            tag = parse_tag(address)
            self._tag_cache[address] = tag
        return tag

    async def write_batched(
        self, address: str, value: bool | int | float | str | timedelta
    ) -> None:
        """Write value to PLC with optional automatic batching.

        If batching is enabled, writes are accumulated in a buffer and executed
        as a batch after a short delay (50ms by default). This dramatically
        improves performance when multiple entities are updated simultaneously.

        If batching is disabled, writes are executed immediately without delay.

        Raises:
            HomeAssistantError: If the write fails.

        Args:
            address: PLC address (e.g., 'DB1.DBX0.0', 'DB1.DBW10')
            value: Value to write (bool, int, float, or str)

        Example:
            >>> await coordinator.write_batched('DB1.DBX0.0', True)
            >>> await coordinator.write_batched('DB1.DBX0.1', True)
            # If batching enabled: both writes executed together in ~50ms
            # If batching disabled: each write executed immediately
        """
        self._connection.check_available()
        # If batching disabled, execute write immediately
        if not self._enable_write_batching:
            try:
                result = await self.write(address, value)
                if not result:
                    raise HomeAssistantError(f"S7 PLC write failed for {address}")
            except HomeAssistantError:
                raise
            except Exception as e:  # pragma: no cover
                _LOGGER.error("Write error for %s: %s", address, e)
                raise HomeAssistantError(
                    f"S7 PLC write failed for {address}: {e}"
                ) from e
            return

        await self._write_manager.write_batched(address, value)

    async def _write_with_retry(self, address: str, tag: S7Tag, payload: Any) -> bool:
        """Execute write with retry and error handling.

        Centralized error handling for PLC write operations.

        Args:
            address: PLC address string (for logging)
            tag: Parsed S7Tag object
            payload: Value to write

        Returns:
            True if write was successful, False otherwise
        """
        try:
            await self._connection.ensure_connected()
            await self._retry(lambda: self._connection.client.write([tag], [payload]))
            return True
        except HomeAssistantError:
            raise
        except (
            OSError,
            RuntimeError,
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        ):
            _LOGGER.exception("Write error %s", address)
            await self._connection.drop_connection()
            return False
        except Exception:  # pragma: no cover - catch unexpected errors
            _LOGGER.exception("Unexpected write error %s", address)
            await self._connection.drop_connection()
            return False

    async def _read_one(self, address: str) -> Any:
        """Read a single tag from PLC by address.

        Handles both strings and scalar values.

        Args:
            address: PLC address string (e.g., 'DB1.DBX0.0', 'DB1.DBW10')

        Returns:
            Value read from PLC (type depends on tag data type)

        Raises:
            RuntimeError: On connection or read failures
        """
        async with self._connection.operation():
            try:
                await self._connection.ensure_connected()
                tag = self._get_or_parse_tag(address)

                return await self._read_executor.read_one(tag, address)
            except (
                OSError,
                RuntimeError,
                S7CommunicationError,
                S7ConnectionError,
                S7ReadResponseError,
            ) as err:
                _LOGGER.error("Read error for %s: %s", address, err)
                await self._connection.drop_connection()
                raise RuntimeError(f"Failed to read {address}: {err}") from err
            except HomeAssistantError:
                raise
            except Exception as err:  # pragma: no cover - catch unexpected errors
                _LOGGER.exception("Unexpected read error for %s", address)
                await self._connection.drop_connection()
                raise RuntimeError(
                    f"Unexpected error reading {address}: {err}"
                ) from err

    async def write(
        self, address: str, value: bool | int | float | str | timedelta
    ) -> bool:
        """Write value to PLC with automatic type handling.

        Automatically determines the appropriate conversion based on the PLC
        data type and Python value type.

        Args:
            address: PLC address (e.g., 'DB1.DBX0.0', 'DB1.DBW10', 'DB1.S0.50')
            value: Value to write (bool, int, float, or str)

        Returns:
            True if write was successful, False otherwise

        Raises:
            ValueError: If value type doesn't match address data type
        """
        self._connection.check_available()
        tag = self._get_or_parse_tag(address)
        payload = self._prepare_payload(tag, value, address)
        async with self._connection.write_operation(serialize=True):
            return await self._write_with_retry(address, tag, payload)

    def _prepare_payload(
        self,
        tag: S7Tag,
        value: bool | int | float | str | timedelta,
        address: str = "",
    ) -> bool | int | float | str | timedelta:
        """Validate and convert a Python value to the appropriate PLC payload.

        Args:
            tag: Parsed S7Tag describing the target data type.
            value: Value to convert.
            address: PLC address (used only in error messages).

        Returns:
            Converted payload ready for the pyS7 write call.

        Raises:
            ValueError: If value type doesn't match the tag data type.
        """
        if tag.data_type == DataType.BIT:
            if not isinstance(value, bool):
                raise ValueError(
                    f"BIT address {address} requires bool value, "
                    f"got {type(value).__name__}"
                )
            return bool(value)

        if tag.data_type == getattr(DataType, "TIME", None):
            if not isinstance(value, timedelta):
                raise ValueError(
                    f"TIME address {address} requires timedelta value, "
                    f"got {type(value).__name__}"
                )
            return value

        if tag.data_type in (DataType.STRING, DataType.WSTRING):
            if not isinstance(value, str):
                raise ValueError(
                    f"STRING/WSTRING address {address} requires str value, "
                    f"got {type(value).__name__}"
                )
            return str(value)

        if tag.data_type in (DataType.REAL, DataType.LREAL):
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"{tag.data_type.name} address {address} requires numeric value, "
                    f"got {type(value).__name__}"
                )
            return float(value)

        if tag.data_type in (
            DataType.BYTE,
            DataType.WORD,
            DataType.DWORD,
            DataType.INT,
            DataType.DINT,
            DataType.USINT,
            DataType.SINT,
        ):
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"{tag.data_type.name} address {address} requires "
                    f"numeric value, got {type(value).__name__}"
                )
            return int(round(float(value)))

        if tag.data_type == DataType.CHAR:
            raise ValueError(
                f"CHAR arrays not supported for write at {address}, use STRING instead"
            )

        raise ValueError(
            f"Unsupported data type for write at {address}: {tag.data_type}"
        )

    async def write_multi(
        self, writes: list[tuple[str, bool | int | float | str | timedelta]]
    ) -> dict[str, bool]:
        """Write multiple values to PLC in a single batch operation.

        Optimizes multiple writes by grouping them into a single PLC request.
        This is significantly faster than individual write() calls when updating
        multiple tags at once.

        Args:
            writes: List of (address, value) tuples to write

        Returns:
            Dictionary mapping each address to its write success status (True/False)

        Example:
            >>> await coordinator.write_multi([
            ...     ('DB1.DBX0.0', True),
            ...     ('DB1.DBW10', 42),
            ...     ('DB1.DBD20', 3.14),
            ... ])
            {'DB1.DBX0.0': True, 'DB1.DBW10': True, 'DB1.DBD20': True}
        """
        self._connection.check_available()
        if not writes:
            return {}

        # Parse all addresses and prepare payloads
        tags = []
        payloads = []
        addresses = []
        results = {}

        for address, value in writes:
            try:
                tag = self._get_or_parse_tag(address)
                payload = self._prepare_payload(tag, value, address)
                addresses.append(address)
                tags.append(tag)
                payloads.append(payload)

            except (ValueError, Exception) as e:
                _LOGGER.error("Failed to prepare write for %s: %s", address, e)
                results[address] = False

        # Execute batch write
        if tags:
            async with self._connection.write_operation(serialize=True):
                try:
                    await self._connection.ensure_connected()
                    await self._retry(
                        lambda: self._connection.client.write(tags, payloads)
                    )
                    # Mark all as successful
                    for addr in addresses:
                        results[addr] = True
                except HomeAssistantError:
                    raise
                except (
                    OSError,
                    RuntimeError,
                    S7CommunicationError,
                    S7ConnectionError,
                    S7ReadResponseError,
                ):
                    _LOGGER.exception("Batch write error for %d tags", len(tags))
                    await self._connection.drop_connection()
                    # Mark all as failed
                    for addr in addresses:
                        results[addr] = False
                except Exception:  # pragma: no cover - catch unexpected errors
                    _LOGGER.exception("Unexpected batch write error")
                    await self._connection.drop_connection()
                    for addr in addresses:
                        results[addr] = False

        return results
