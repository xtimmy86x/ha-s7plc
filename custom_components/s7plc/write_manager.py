"""Batch PLC writes while leaving transport and I/O lifecycle to the coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

WriteValue = bool | int | float | str | timedelta


class S7WriteManager:
    """Own batch queues, waiters, timers and flush tasks for a single PLC.

    The coordinator supplies write execution, admission checks and the shared
    I/O generation. It owns connection/retry/serialization and drains this
    manager's tasks alongside all other PLC operations during lifecycle changes.
    The shared state lock preserves atomic snapshots and batch invalidation.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        host: str,
        op_timeout: float,
        state_lock: asyncio.Lock,
        write_multi: Callable[
            [list[tuple[str, WriteValue]]], Awaitable[dict[str, bool]]
        ],
        operation: Callable[[], AbstractAsyncContextManager[None]],
        check_connection: Callable[[], None],
        get_generation: Callable[[], int],
    ) -> None:
        self.hass = hass
        self._host = host
        self._op_timeout = op_timeout
        self._state_lock = state_lock
        self._write_multi = write_multi
        self._operation = operation
        self._check_connection = check_connection
        self._get_generation = get_generation
        self._buffer: dict[str, WriteValue] = {}
        self._waiters: dict[str, list[asyncio.Future[bool]]] = {}
        self._inflight_waiters: dict[int, dict[str, list[asyncio.Future[bool]]]] = {}
        self._flush_id = 0
        self._timer: asyncio.TimerHandle | None = None
        self._delay: float = 0.05
        self._flush_tasks: set[asyncio.Task] = set()
        self._last_write_error_notification: float | None = None
        self._write_error_notification_interval: float = 300.0

    @property
    def tasks(self) -> set[asyncio.Task]:
        """Snapshot owned flush tasks, including those not yet started."""
        return set(self._flush_tasks)

    async def write_batched(self, address: str, value: WriteValue) -> None:
        """Queue a PLC-domain value and await this caller's shared batch result."""
        self._check_connection()
        # Batching enabled: accumulate writes
        waiter: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        async with self._state_lock:
            self._check_connection()
            # Add to buffer
            self._buffer[address] = value
            self._waiters.setdefault(address, []).append(waiter)

            # Cancel existing timer if any
            if self._timer is not None:
                self._timer.cancel()

            # Schedule flush after delay (check loop exists for shutdown safety)
            if self.hass.loop is not None:
                generation = self._get_generation()
                self._timer = self.hass.loop.call_later(
                    self._delay,
                    lambda generation=generation: self._start_flush(generation),
                )
            else:
                # Fallback: execute immediately if loop unavailable (shutdown)
                _LOGGER.debug("Event loop unavailable, executing write immediately")
                self._start_flush(self._get_generation())

        try:
            success = await asyncio.wait_for(
                waiter, timeout=self._op_timeout + self._delay + 1.0
            )
        except asyncio.TimeoutError as err:
            raise HomeAssistantError(f"S7 PLC write timed out for {address}") from err
        finally:
            # Remove only this caller; never cancel a shared write on timeout.
            for groups in (
                self._waiters,
                *self._inflight_waiters.values(),
            ):
                address_waiters = groups.get(address, [])
                if waiter in address_waiters:
                    address_waiters.remove(waiter)
        if not success:
            raise HomeAssistantError(f"S7 PLC write failed for {address}")

    def _start_flush(self, generation: int) -> None:
        """Own the task before it can run, including cancelled-before-start tasks."""
        if generation != self._get_generation():
            return
        try:
            self._check_connection()
        except HomeAssistantError:
            return
        started = False

        async def run():
            nonlocal started
            started = True
            # A queued task may start after disconnect and a subsequent enable.
            if generation == self._get_generation():
                await self._flush()

        def done(task):
            self._flush_tasks.discard(task)
            if not started and task.cancelled():
                self._fail_queued_flush(generation)
            if not task.cancelled():
                error = task.exception()
                if error is not None:
                    _LOGGER.error("PLC background task failed: %s", error)

        task = self.hass.async_create_background_task(
            run(), name=f"s7plc_flush_batch_{self._host}"
        )
        self._flush_tasks.add(task)
        task.add_done_callback(done)

    def _fail_queued_flush(self, generation: int) -> None:
        """Fail only queued work if its flush was cancelled before snapshotting.

        No awaits: state mutations are atomic on the HA event loop, like the
        snapshot's critical section. Other in-flight batches are unaffected.
        """
        if generation != self._get_generation():
            return
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        waiters = self._waiters
        self._waiters = {}
        self._buffer.clear()
        self._fail_write_waiters(waiters)

    @staticmethod
    def _fail_write_waiters(waiters) -> None:
        for group in waiters.values():
            for waiter in group:
                if not waiter.done():
                    waiter.set_exception(HomeAssistantError("PLC write was cancelled"))

    async def _flush(self) -> None:
        """Flush accumulated writes to PLC using write_multi."""
        generation = self._get_generation()
        queued_waiters = self._waiters
        try:
            async with self._operation():
                await self._flush_impl()
        except asyncio.CancelledError:
            # Covers cancellation while waiting for the snapshot lock, too.
            if queued_waiters is self._waiters:
                self._fail_queued_flush(generation)
            raise
        except HomeAssistantError:
            # A stop already resolved the callers; no shutdown notification.
            return

    async def _flush_impl(self) -> None:
        async with self._state_lock:
            if not self._buffer:
                return

            # Get buffered writes
            writes = list(self._buffer.items())
            waiters = self._waiters
            generation = self._get_generation()
            self._flush_id += 1
            flush_id = self._flush_id
            self._buffer.clear()
            self._waiters = {}
            self._inflight_waiters[flush_id] = waiters
            if self._timer is not None:
                self._timer.cancel()
            self._timer = None

        results: dict[str, bool] = {}
        # Execute batch write
        try:
            if generation != self._get_generation():
                return
            results = await self._write_multi(writes)

            # A manual disable/disconnect may have happened while pyS7 was
            # already performing the write.  Let that operation finish so the
            # client is not left half-way through protocol I/O, but discard its
            # outcome: cancellation has already failed all of this flush's
            # callers and a later result must not revive the old generation.
            if generation != self._get_generation():
                return

            # Log results
            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)

            if success_count == total_count:
                _LOGGER.debug(
                    "Batched write: %d/%d addresses successful",
                    success_count,
                    total_count,
                )
            else:
                failed_addresses = [
                    addr for addr, success in results.items() if not success
                ]
                error_msg = (
                    f"S7 PLC write failed for {len(failed_addresses)} address(es): "
                    f"{', '.join(failed_addresses[:5])}"
                )
                if len(failed_addresses) > 5:
                    error_msg += f" (and {len(failed_addresses) - 5} more)"

                _LOGGER.error(error_msg)

                current_time = time.monotonic()

                if (
                    self._last_write_error_notification is None
                    or current_time - self._last_write_error_notification
                    >= self._write_error_notification_interval
                ):
                    self._last_write_error_notification = current_time
                    notification_id = (
                        f"s7plc_write_error_{self._host.replace('.', '_')}"
                    )
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "S7 PLC Write Error",
                            "message": error_msg,
                            "notification_id": notification_id,
                        },
                        blocking=False,
                    )
                else:
                    _LOGGER.debug(
                        "Suppressing notification (last sent %.0fs ago)",
                        current_time - self._last_write_error_notification,
                    )

        except asyncio.CancelledError:
            self._fail_write_waiters(waiters)
            raise
        except HomeAssistantError:
            # Manual disable/disconnect already completed pending callers with
            # the precise error and must not produce a notification or retry.
            results = {address: False for address, _ in writes}
        except Exception as e:  # pragma: no cover
            if generation != self._get_generation():
                return
            error_msg = f"S7 PLC batch write failed: {e}"
            _LOGGER.exception(error_msg)

            # Create persistent notification for critical errors
            try:
                notification_id = f"s7plc_write_error_{self._host.replace('.', '_')}"
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "S7 PLC Write Error",
                        "message": error_msg,
                        "notification_id": notification_id,
                    },
                    blocking=False,
                )
            except Exception:  # pragma: no cover
                # Don't fail if notification fails
                pass
            results = {address: False for address, _ in writes}

        finally:
            self._inflight_waiters.pop(flush_id, None)

        for address, address_waiters in waiters.items():
            success = bool(results.get(address, False))
            for waiter in address_waiters:
                if not waiter.done() and not waiter.cancelled():
                    waiter.set_result(success)

    def cancel_batches(self, error: HomeAssistantError) -> None:
        """Cancel queued and in-flight callers; the shared state lock must be held."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        self._buffer.clear()
        waiter_groups = (
            *self._waiters.values(),
            *(
                waiters
                for flush_waiters in self._inflight_waiters.values()
                for waiters in flush_waiters.values()
            ),
        )
        self._waiters.clear()
        self._inflight_waiters.clear()
        for waiters in waiter_groups:
            for waiter in waiters:
                if not waiter.done() and not waiter.cancelled():
                    waiter.set_exception(error)
