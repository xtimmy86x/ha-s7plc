"""Own one PLC connection, transport admission and active I/O lifetimes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pyS7
from pyS7.errors import S7CommunicationError, S7ConnectionError

_LOGGER = logging.getLogger(__name__)


@dataclass(eq=False)
class _TransportCleanup:
    """Identity and successful cleanup of one client session/handshake."""

    client: Any
    closed: bool = False


class S7ConnectionManager:
    """Manage PLC I/O without Home Assistant scheduling or entity state.

    Each instance owns its client, shared handshake, transport reset, locks and
    operation generations. The adapter supplies its lifecycle exception type
    to preserve the public error contract without importing Home Assistant.
    It serializes enable/disable/stop with its lifecycle lock and supplies batch
    cancellation under the shared state lock. Retry policy stays in the adapter.
    """

    def __init__(
        self,
        *,
        host: str,
        rack: int | None,
        slot: int | None,
        local_tsap: str | None,
        remote_tsap: str | None,
        port: int,
        pys7_connection_type: Any,
        enable_metrics: bool,
        op_timeout: float,
        connection_enabled: bool,
        error_type: type[Exception],
    ) -> None:
        self._host = host
        self._rack = rack
        self._slot = slot
        self._local_tsap = local_tsap
        self._remote_tsap = remote_tsap
        self._port = port
        self._pys7_connection_type = pys7_connection_type
        self._enable_metrics = enable_metrics
        self._op_timeout = op_timeout
        self._error_type = error_type
        self._connection_enabled = connection_enabled
        self._shutdown = False
        self._connection_lock = asyncio.Lock()
        # Claim admission before pyS7's packet lock, including stream cleanup.
        self._transport_lock = asyncio.Lock()
        self._transport_generation = 0
        self._transport_cleanup: _TransportCleanup | None = None
        self._transport_reset_task: asyncio.Task[None] | None = None
        self._transport_reset_failed = False
        self._connect_task: asyncio.Task[None] | None = None
        # Serialize the entire write/retry scope, not just individual packets.
        self._write_io_lock = asyncio.Lock()
        self._io_stopping = False
        self._io_tasks: dict[asyncio.Task, int] = {}
        self._io_completions: dict[asyncio.Task, asyncio.Future[None]] = {}
        self._io_generation = 0
        self._connection_state_changed = asyncio.Event()
        self.client: Any | None = None

    @property
    def enabled(self) -> bool:
        """Whether the user allows PLC communication."""
        return self._connection_enabled

    @property
    def shutdown(self) -> bool:
        """Whether this instance has permanently stopped accepting work."""
        return self._shutdown

    @property
    def stopping(self) -> bool:
        """Whether cleanup still prevents admission of new PLC work."""
        return self._io_stopping

    @property
    def generation(self) -> int:
        """Current operation generation shared with queued writes."""
        return self._io_generation

    def enable(self) -> bool:
        """Enable communication; return whether the adapter should refresh."""
        if self._shutdown:
            raise self._error_type("PLC coordinator is shut down")
        if self._io_stopping:
            raise self._error_type("PLC I/O has not finished stopping")
        if self._connection_enabled:
            return False
        self._connection_enabled = True
        self._connection_state_changed.set()
        self._connection_state_changed.clear()
        return True

    def disable(self) -> None:
        """Close admission and wake retries before awaiting the lifecycle lock."""
        self._connection_enabled = False
        self._connection_state_changed.set()

    def begin_shutdown(self) -> None:
        """Permanently close admission before adapter scheduling is stopped."""
        self._shutdown = True
        self.disable()

    def check_available(self) -> None:
        """Reject PLC I/O without allowing it to reconnect."""
        if self._shutdown:
            raise self._error_type("PLC coordinator is shut down")
        if not self._connection_enabled:
            raise self._error_type("PLC connection is manually disabled")
        if (
            self._io_stopping
            or self._io_tasks.get(asyncio.current_task(), self._io_generation)
            != self._io_generation
        ):
            raise self._error_type("PLC connection was disconnected")

    def _capture_transport(self) -> _TransportCleanup:
        """Capture the current session, including injected/replaced clients."""
        transport = self._transport_cleanup
        if transport is None or transport.client is not self.client:
            transport = self._transport_cleanup = _TransportCleanup(self.client)
        return transport

    def _mark_failed_transport(
        self, error: Exception, transport: _TransportCleanup
    ) -> None:
        """Carry cleanup ownership through existing exception cause chains."""
        error._s7plc_cleanup = (self, transport)

    def _failed_transport(self, error: Exception | None) -> _TransportCleanup | None:
        """Find this manager's receipt without changing public exception types."""
        seen = set()
        while error is not None and id(error) not in seen:
            seen.add(id(error))
            receipt = getattr(error, "_s7plc_cleanup", None)
            if receipt is not None and receipt[0] is self:
                return receipt[1]
            error = error.__cause__
        return None

    async def drop_connection(
        self, *, strict: bool = False, error: Exception | None = None
    ) -> None:
        """Safely close PLC connection, tolerant of concurrent disconnects.

        The pyS7 library may concurrently set socket=None when the peer closes
        the connection (race condition in _recv_exact / __send), so we catch
        AttributeError alongside OSError/RuntimeError.  We skip the
        is_connected guard because pyS7.disconnect() already returns early
        when the state is DISCONNECTED.

        Error cleanup only closes the session that failed. Explicit lifecycle
        closes omit error and remain unconditional, including strict resets.
        """
        failed_transport = self._failed_transport(error)
        async with self._transport_lock, self._connection_lock:
            if failed_transport is not None and (
                failed_transport.closed
                or failed_transport is not self._transport_cleanup
                or failed_transport.client is not self.client
            ):
                return
            await self._disconnect_client(
                self.client, strict=strict or self._transport_reset_failed
            )

    async def _disconnect_client(
        self, client: Any | None, *, strict: bool = False
    ) -> None:
        """Close a captured client while the caller owns the connection lock."""
        transport = self._transport_cleanup
        self._transport_generation += 1
        if client is not None:
            try:
                await client.disconnect()
                if strict and client.is_connected:
                    raise RuntimeError("PLC client remained connected after cleanup")
            except (OSError, RuntimeError, AttributeError) as err:
                _LOGGER.debug("Error during PLC disconnect: %s", err)
                if strict:
                    raise
            else:
                if transport is not None and transport.client is client:
                    transport.closed = not getattr(client, "is_connected", False)

    async def ensure_connected(self) -> None:
        """Await the shared handshake without transferring ownership to callers."""
        async with self.operation():
            await self._wait_for_transport_reset()
            if self.client is None:
                # Create client based on connection type
                if self._local_tsap and self._remote_tsap:
                    self.client = pyS7.AsyncS7Client(
                        address=self._host,
                        local_tsap=self._local_tsap,
                        remote_tsap=self._remote_tsap,
                        port=self._port,
                        connection_type=self._pys7_connection_type,
                        enable_metrics=self._enable_metrics,
                    )
                else:
                    self.client = pyS7.AsyncS7Client(
                        self._host,
                        self._rack,
                        self._slot,
                        port=self._port,
                        connection_type=self._pys7_connection_type,
                        enable_metrics=self._enable_metrics,
                    )

            task = self._connect_task
            if task is None or task.done():
                if self.is_connected():
                    return
                # Own the task from scheduling, including before its first turn.
                # The lifecycle drain includes it even if all waiters cancel.
                task = asyncio.create_task(self._connect(self._io_generation))
                self._connect_task = task
                task.add_done_callback(self._connection_task_done)
            await asyncio.shield(task)
            self.check_available()

    def _connection_task_done(self, task: asyncio.Task[None]) -> None:
        """Consume orphaned failures and allow a later attempt after completion."""
        if self._connect_task is task:
            self._connect_task = None
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                _LOGGER.debug("PLC connection attempt finished with error: %s", error)

    async def _connect(self, generation: int) -> None:
        """Own one handshake and its cleanup, serialized with transport closes."""
        async with self.operation():
            if generation != self._io_generation:
                raise self._error_type("PLC connection was disconnected")
            while True:
                await self._wait_for_transport_reset()
                async with self._transport_lock, self._connection_lock:
                    if self._transport_reset_task is not None:
                        continue
                    self.check_available()
                    client = self.client
                    transport = self._transport_cleanup = _TransportCleanup(client)
                    try:
                        await client.connect()
                        self.check_available()
                        if not client.is_connected:
                            raise RuntimeError(
                                "PLC handshake did not establish a connection"
                            )
                    except asyncio.CancelledError:
                        # Stop drains all I/O owners before disconnecting. Otherwise
                        # Direct cancellation of the owned task needs cleanup.
                        if not self._io_stopping:
                            try:
                                await asyncio.wait_for(
                                    self._disconnect_client(client), self._op_timeout
                                )
                            except TimeoutError:
                                self._io_stopping = True
                                _LOGGER.error(
                                    "PLC disconnect timed out "
                                    "after connect cancellation"
                                )
                        raise
                    except self._error_type:
                        # The lifecycle barrier owns cleanup after active I/O drains.
                        raise
                    except (
                        OSError,
                        RuntimeError,
                        S7CommunicationError,
                        S7ConnectionError,
                    ) as err:
                        self._mark_failed_transport(err, transport)
                        await self._disconnect_client(client)
                        raise RuntimeError(
                            f"Connection to PLC {self._host} failed: {err}"
                        ) from err
                    except Exception as err:
                        self._mark_failed_transport(err, transport)
                        raise

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
                return

    def is_connected(self) -> bool:
        """Check if PLC connection is active.

        Note:
            Requires pyS7 >= 2.3.0 for is_connected property support.

        Returns:
            True if client exists and is connected
        """
        return bool(self.client and self.client.is_connected)

    async def stop(
        self,
        *,
        state_lock: asyncio.Lock,
        cancel_batches: Callable[[], None],
        batch_tasks: Callable[[], set[asyncio.Task]],
    ) -> None:
        """Drain invalidated PLC operations; caller holds only the lifecycle lock."""
        self._io_stopping = True
        self._connection_state_changed.set()
        async with state_lock:
            self._io_generation += 1
            cancel_batches()
        operations = {
            task: done
            for task, done in self._io_completions.items()
            if task is not asyncio.current_task()
        }
        # For entity/service callers, wait for the I/O scope, not their whole
        # task: a caller may continue unrelated work after handling a write error.
        owned_tasks = batch_tasks()
        if self._connect_task is not None:
            owned_tasks.add(self._connect_task)
        if self._transport_reset_task is not None:
            owned_tasks.add(self._transport_reset_task)
        owned_tasks.discard(asyncio.current_task())
        completions = set(operations.values()) | owned_tasks
        completions = {done for done in completions if not done.done()}
        if completions:
            _, pending = await asyncio.wait(completions, timeout=self._op_timeout)
            if pending:
                # pyS7.disconnect also needs the I/O lock. Cancel and drain its
                # owners before trying to close the connection.
                cancellable = owned_tasks | {
                    task for task, done in operations.items() if not done.done()
                }
                for task in cancellable:
                    if not task.done():
                        task.cancel()
                _, pending = await asyncio.wait(pending, timeout=self._op_timeout)
                if pending:
                    # Do not reopen or report successful unload with live I/O.
                    raise self._error_type("PLC I/O tasks did not stop")
            await asyncio.gather(*completions, return_exceptions=True)
        await asyncio.wait_for(self.drop_connection(), self._op_timeout)
        self._transport_reset_failed = False
        self._io_stopping = False
        if self._connection_enabled and not self._shutdown:
            self._connection_state_changed.clear()

    @asynccontextmanager
    async def operation(self) -> AsyncIterator[None]:
        """Track active PLC work without owning the caller's later work."""
        self.check_available()
        task = asyncio.current_task()
        owner = task not in self._io_tasks
        if owner:
            self._io_tasks[task] = self._io_generation
            self._io_completions[task] = asyncio.get_running_loop().create_future()
        try:
            yield
        finally:
            if owner:
                self._io_tasks.pop(task, None)
                self._io_completions.pop(task).set_result(None)

    @asynccontextmanager
    async def write_operation(self, *, serialize: bool = False) -> AsyncIterator[None]:
        """Serialize complete writes, including retry and cancellation cleanup."""
        async with self.operation():
            if serialize:
                async with self._write_io_lock:
                    self.check_available()
                    yield
            else:
                yield

    async def sleep(self, seconds: float) -> None:
        """Async sleep for the specified duration.

        Args:
            seconds: Duration to sleep (seconds), negative values are clamped to 0
        """
        try:
            await asyncio.wait_for(
                self._connection_state_changed.wait(), timeout=max(0.0, seconds)
            )
        except TimeoutError:
            return
        self.check_available()

    async def _wait_for_transport_reset(self) -> None:
        """Wait outside transport locks; cancelling a waiter cannot cancel cleanup."""
        task = self._transport_reset_task
        if task is not None:
            await asyncio.shield(task)

    def _start_transport_reset(self) -> asyncio.Task[None]:
        """Mark the stream unusable synchronously before releasing its gate."""
        task = self._transport_reset_task
        if task is None:
            task = asyncio.create_task(self._reset_transport())
            self._transport_reset_task = task
            task.add_done_callback(self._transport_reset_done)
        return task

    async def _reset_transport(self) -> None:
        """Own cleanup even if the cancelled caller is cancelled a second time."""
        try:
            await asyncio.wait_for(self.drop_connection(strict=True), self._op_timeout)
        except BaseException:
            # A failed/cancelled close must not reopen admission on an uncertain
            # stream. An explicit lifecycle stop can retry and finish cleanup.
            self._io_stopping = True
            self._transport_reset_failed = True
            self._connection_state_changed.set()
            raise

    def _transport_reset_done(self, task: asyncio.Task[None]) -> None:
        if self._transport_reset_task is task:
            self._transport_reset_task = None
        self._consume_task_result(task)

    async def perform_io(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Dispatch one driver call and quarantine its stream on cancellation.

        Connection waits, transport-gate waits and retry backoffs send no packet
        and need no reset. All reads, writes and CPU probes use this boundary.
        """
        reset = None
        try:
            while True:
                await self.ensure_connected()
                generation = self._transport_generation
                async with self._transport_lock:
                    # Already-queued callers may acquire the gate before the
                    # reset task. Yield it rather than using or waiting on it.
                    if (
                        self._transport_reset_task is not None
                        or generation != self._transport_generation
                    ):
                        continue
                    self.check_available()
                    transport = self._capture_transport()
                    try:
                        result = func(*args, **kwargs)
                        if asyncio.iscoroutine(result):
                            result = await result
                    except asyncio.CancelledError:
                        if not self._io_stopping:
                            reset = self._start_transport_reset()
                        raise
                    except Exception as err:
                        self._mark_failed_transport(err, transport)
                        raise
                    self.check_available()
                    return result
        except asyncio.CancelledError:
            if reset is not None:
                try:
                    # The gate is released before cleanup needs to acquire it.
                    await asyncio.shield(reset)
                except Exception:
                    # The owned task logs the failure and closes admission.
                    # Preserve the initiating caller's cancellation outcome.
                    pass
            raise

    @staticmethod
    def _consume_task_result(task: asyncio.Task) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                _LOGGER.error("PLC background task failed: %s", error)
