"""Regression tests for shutdown while reads hold the shared PLC I/O lock."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc.const import DOMAIN
from custom_components.s7plc.coordinator import S7Coordinator


class LockedClient:
    """Model pyS7's lock for connect negotiation, reads, probes and disconnect.

    A blocked operation has no wall-clock deadline in the fake: tests decide
    whether it completes naturally or the coordinator has to cancel it. This
    models a driver read outlasting the configured coordinator operation timeout.
    """

    def __init__(self, blocking="read"):
        self.is_connected = blocking != "connect"
        self.lock = asyncio.Lock()
        self.blocking = blocking
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
        self.disconnect_entered = asyncio.Event()
        self.disconnect_release = None
        self.calls = []
        self.cancelled = False

    async def _operation(self, kind):
        async with self.lock:
            self.calls.append(kind)
            if kind == self.blocking:
                self.entered.set()
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
                finally:
                    self.finished.set()

    async def read(self, tags, *, optimize=True):
        await self._operation("read")
        return [17] * len(tags)

    async def get_cpu_info(self):
        await self._operation("health")
        return {}

    async def connect(self):
        await self._operation("connect")
        self.is_connected = True

    async def disconnect(self):
        async with self.lock:
            self.calls.append("disconnect")
            self.disconnect_entered.set()
            if self.disconnect_release is not None:
                await self.disconnect_release.wait()
            self.is_connected = False


async def make_coordinator(blocking="read"):
    coord = S7Coordinator(
        HomeAssistant(), host="plc.local", op_timeout=0.5, max_retries=0
    )
    client = LockedClient(blocking)
    coord._connection.client = client
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    coord.hass.services.async_call = AsyncMock()
    await coord.add_item("temperature", "DB1,W0")
    coord._data_cache = {"temperature": 12}
    return coord, client


def run_operation(coord, kind):
    if kind == "poll":
        return coord._async_update_data()
    if kind == "health":
        return coord.async_health_check()
    if kind == "connect":
        return coord.connect()
    return coord._read_one("DB1,W0")


def expire_first_drain(monkeypatch):
    """Advance the first drain deadline without patching operation scheduling."""
    real_wait = asyncio.wait
    expired = False

    async def controlled_wait(fs, *, timeout):
        nonlocal expired
        if not expired and timeout == 0.5:
            expired = True
            return set(), set(fs)
        return await real_wait(fs, timeout=timeout)

    monkeypatch.setattr(asyncio, "wait", controlled_wait)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
@pytest.mark.parametrize("kind", ["poll", "health", "connect", "single_read"])
async def test_stop_drains_reads_probes_and_connect_holding_driver_lock(
    monkeypatch, stop, kind
):
    """A read longer than op_timeout must not poison cleanup or hold its lock."""
    blocking = kind if kind in {"health", "connect"} else "read"
    coord, client = await make_coordinator(blocking)
    expire_first_drain(monkeypatch)
    operation = asyncio.create_task(run_operation(coord, kind))
    await client.entered.wait()
    try:
        # This is a watchdog, not a timing assertion. Deadlines inside the
        # coordinator are 0.5 s, whereas this blocked driver never self-releases.
        await asyncio.wait_for(getattr(coord, stop)(), timeout=3)
        assert client.finished.is_set()
        assert not client.lock.locked()
        assert not client.is_connected
        assert "disconnect" in client.calls
        assert client.cancelled
        assert coord.last_health_ok is False
        assert coord._data_cache == {"temperature": 12}
        assert not coord._connection.stopping
        assert not coord._connection._io_tasks
        assert not coord._connection._io_completions

        if stop == "async_shutdown":
            await coord.async_shutdown()
            with pytest.raises(HomeAssistantError, match="shut down"):
                await coord.async_enable_connection()
        else:
            # Manual disable remains reversible after cancelling the old I/O.
            client.blocking = None
            await coord.async_enable_connection()
            assert await coord._async_update_data() == {"temperature": 17}
            assert client.is_connected
            await coord.async_shutdown()
    finally:
        client.release.set()
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
async def test_cleanup_barrier_rejects_new_reads_before_driver_disconnect_finishes(
    stop,
):
    coord, client = await make_coordinator(blocking=None)
    client.disconnect_release = asyncio.Event()
    stopping = asyncio.create_task(getattr(coord, stop)())
    await client.disconnect_entered.wait()
    try:
        calls = list(client.calls)
        assert await coord._async_update_data() == {"temperature": 12}
        for operation in (coord.async_health_check, coord.connect):
            with pytest.raises(HomeAssistantError):
                await operation()
        with pytest.raises((HomeAssistantError, RuntimeError)):
            await asyncio.wait_for(coord._read_one("DB1,W0"), timeout=1)
        assert client.calls == calls
    finally:
        client.disconnect_release.set()
        await stopping
    await coord.async_shutdown()


@pytest.mark.asyncio
async def test_shutdown_stops_ha_scheduling_before_attempting_disconnect(monkeypatch):
    coord, client = await make_coordinator(blocking=None)
    order = []

    async def stop_scheduling(_):
        order.append("stop-scheduling")

    real_disconnect = client.disconnect

    async def disconnect():
        order.append("disconnect")
        await real_disconnect()

    monkeypatch.setattr(DataUpdateCoordinator, "async_shutdown", stop_scheduling)
    client.disconnect = disconnect
    await coord.async_shutdown()
    assert order == ["stop-scheduling", "disconnect", "stop-scheduling"]


@pytest.mark.asyncio
async def test_shutdown_clears_timer_rescheduled_by_refresh_finally(monkeypatch):
    """HA's refresh finally may reschedule after the initial scheduling stop."""
    coord, client = await make_coordinator("read")
    loop = asyncio.get_running_loop()
    timers = []
    initially_stopped = asyncio.Event()
    callback = MagicMock()

    async def stop_scheduling(_):
        for timer in timers:
            timer.cancel()
        initially_stopped.set()

    async def refresh():
        try:
            await coord._async_update_data()
        except HomeAssistantError:
            pass
        finally:
            # Model DataUpdateCoordinator._async_refresh's final scheduling
            # while a listener still exists. No delay is awaited in this test.
            timers.append(loop.call_later(60, callback))

    monkeypatch.setattr(DataUpdateCoordinator, "async_shutdown", stop_scheduling)
    polling = asyncio.create_task(refresh())
    await client.entered.wait()
    stopping = asyncio.create_task(coord.async_shutdown())
    await initially_stopped.wait()
    assert timers == []
    client.release.set()
    try:
        await asyncio.wait_for(stopping, timeout=3)
        await polling
        assert len(timers) == 1
        assert timers[0].cancelled()
        callback.assert_not_called()
        assert not client.cancelled
        assert coord._data_cache == {"temperature": 12}
    finally:
        client.release.set()
        for timer in timers:
            timer.cancel()
        await asyncio.gather(polling, stopping, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_shutdown_cleanup_can_retry_without_reenabling_connection():
    coord, client = await make_coordinator(blocking=None)
    real_drop = coord._connection.drop_connection
    calls = 0

    async def drop():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("transient cleanup timeout")
        await real_drop()

    # Fail at the lifecycle boundary. A TimeoutError raised by the driver itself
    # is an OSError and is deliberately tolerated inside _drop_connection().
    coord._connection.drop_connection = drop
    with pytest.raises((HomeAssistantError, TimeoutError)):
        await coord.async_shutdown()
    with pytest.raises(HomeAssistantError, match="shut down"):
        await coord.async_enable_connection()
    with pytest.raises(HomeAssistantError, match="shut down"):
        await coord.connect()
    await coord.async_shutdown()
    await coord.async_shutdown()
    assert calls == 2
    assert not client.is_connected
    assert not coord._connection.stopping
    assert not coord._connection._io_tasks
    assert not coord._connection._io_completions


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["health", "poll"])
async def test_read_completion_does_not_make_shutdown_wait_for_caller_continuation(
    kind,
):
    coord, client = await make_coordinator("read" if kind == "poll" else "health")
    continued = asyncio.Event()
    finish_caller = asyncio.Event()

    async def caller():
        try:
            await run_operation(coord, kind)
        except HomeAssistantError:
            pass
        continued.set()
        await finish_caller.wait()

    service = asyncio.create_task(caller())
    await client.entered.wait()
    stopping = asyncio.create_task(coord.async_shutdown())
    # Let the lifecycle barrier run, then complete I/O naturally before its
    # deadline. The unrelated caller continuation remains intentionally blocked.
    await asyncio.sleep(0)
    client.release.set()
    try:
        await asyncio.wait_for(continued.wait(), timeout=3)
        await asyncio.wait_for(stopping, timeout=3)
        assert not service.done()
        assert not service.cancelling()
        assert not client.cancelled
        assert coord.last_health_ok is False
        assert coord._data_cache == {"temperature": 12}
    finally:
        client.release.set()
        finish_caller.set()
        await asyncio.gather(service, stopping, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("unload_ok", [False, True])
async def test_entry_unload_with_active_poll_then_new_coordinator_reload(
    monkeypatch, unload_ok
):
    coord, client = await make_coordinator()
    expire_first_drain(monkeypatch)
    entry = SimpleNamespace(
        entry_id="read-lifecycle", runtime_data=SimpleNamespace(coordinator=coord)
    )
    hass = coord.hass
    hass.data[DOMAIN] = {}

    async def unload_platforms(*_):
        assert not coord._connection.shutdown
        assert client.lock.locked()
        return unload_ok

    hass.config_entries.async_unload_platforms = unload_platforms
    hass.config_entries.async_entries = lambda _: [entry]
    polling = asyncio.create_task(coord._async_update_data())
    await client.entered.wait()
    try:
        assert await s7init.async_unload_entry(hass, entry) is unload_ok
        if unload_ok:
            assert not client.lock.locked()
            assert not client.is_connected
            assert client.cancelled
            assert await coord._async_update_data() == {"temperature": 12}
            # HA reload constructs a new coordinator instead of resurrecting the
            # permanently stopped one; its first real polling path must work.
            reloaded, next_client = await make_coordinator(blocking=None)
            entry.runtime_data = SimpleNamespace(coordinator=reloaded)
            assert await reloaded._async_update_data() == {"temperature": 17}
            assert next_client.calls == ["read"]
            await reloaded.async_shutdown()
        else:
            assert not coord._connection.shutdown
            assert not client.cancelled
            assert "disconnect" not in client.calls
            client.release.set()
            assert await polling == {"temperature": 17}
            await coord.async_shutdown()
    finally:
        client.release.set()
        if not polling.done():
            polling.cancel()
        await asyncio.gather(polling, return_exceptions=True)
