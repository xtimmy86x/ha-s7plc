"""Deterministic regression tests for write ownership and lifecycle barriers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from support.write_batching import enqueue, install_scheduler, make_batch_coordinator

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc.const import DOMAIN


def make_coordinator():
    coord = make_batch_coordinator()
    scheduler, tasks = install_scheduler(coord)
    client = SimpleNamespace(is_connected=True)

    async def connect():
        client.is_connected = True

    async def disconnect():
        client.is_connected = False

    client.connect = AsyncMock(side_effect=connect)
    client.disconnect = AsyncMock(side_effect=disconnect)
    client.write = AsyncMock()
    coord._connection.client = client
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    coord.hass.services.async_call = AsyncMock()
    return coord, scheduler, tasks, client


def assert_clean(coord):
    assert not coord._connection._io_tasks
    assert not coord._connection._io_completions
    assert not coord._write_manager._flush_tasks
    assert not coord._write_manager._buffer
    assert not coord._write_manager._inflight_waiters
    assert not coord._write_manager._waiters
    assert coord._write_manager._timer is None


@pytest.mark.asyncio
async def test_shutdown_is_permanent_and_concurrently_idempotent():
    coord, _, _, client = make_coordinator()
    coord._data_cache = {"temperature": 21}
    await asyncio.gather(coord.async_shutdown(), coord.async_shutdown())
    await coord.async_shutdown()
    client.disconnect.assert_awaited_once()
    for operation in (
        coord.async_enable_connection,
        coord.connect,
        coord.async_health_check,
        lambda: coord.write_batched("DB1,W0", 1),
        lambda: coord.write("DB1,W0", 1),
        lambda: coord.write_multi([("DB1,W0", 1)]),
        lambda: coord._retry(lambda: None),
    ):
        with pytest.raises(HomeAssistantError, match="shut down"):
            await operation()
    assert await coord._async_update_data() == {"temperature": 21}
    client.connect.assert_not_awaited()
    client.write.assert_not_awaited()
    coord.async_request_refresh.assert_not_awaited()
    assert_clean(coord)


@pytest.mark.asyncio
async def test_shutdown_does_not_wait_for_unrelated_work_in_service_caller():
    coord, _, _, client = make_coordinator()
    entered, release = asyncio.Event(), asyncio.Event()
    after_write, finish_caller = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    async def caller():
        with pytest.raises(HomeAssistantError):
            await coord.write("DB1,W0", 1)
        after_write.set()
        await finish_caller.wait()

    client.write.side_effect = write
    service = asyncio.create_task(caller())
    await entered.wait()
    shutdown = asyncio.create_task(coord.async_shutdown())
    await asyncio.sleep(0)
    release.set()
    try:
        await after_write.wait()
        await shutdown
        assert not service.done()
        assert not service.cancelling()
        assert_clean(coord)
    finally:
        finish_caller.set()
        await service


@pytest.mark.asyncio
async def test_disconnect_cancels_pending_and_obsolete_timer_callback():
    coord, scheduler, tasks, client = make_coordinator()
    caller = await enqueue(coord, "DB1,W0", 1)
    timer = scheduler.timers[-1]
    await coord.disconnect()
    with pytest.raises(HomeAssistantError, match="disconnected"):
        await caller
    assert timer.cancelled
    # Simulate a callback already dispatched by the event loop before cancel().
    timer.callback()
    assert tasks == []
    assert coord.connection_enabled
    client.write.assert_not_awaited()
    assert_clean(coord)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop", ["disconnect", "async_disable_connection", "async_shutdown"]
)
async def test_stop_waits_for_natural_io_completion_without_late_success(stop):
    coord, scheduler, tasks, client = make_coordinator()
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    client.write.side_effect = write
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    stopping = asyncio.create_task(getattr(coord, stop)())
    try:
        with pytest.raises(HomeAssistantError):
            await caller
        assert not stopping.done()
        assert not tasks[0].done()
        client.disconnect.assert_not_awaited()
    finally:
        release.set()
        await stopping
        await asyncio.gather(*tasks, return_exceptions=True)
    assert not tasks[0].cancelled()
    client.connect.assert_not_awaited()
    coord.hass.services.async_call.assert_not_awaited()
    assert_clean(coord)
    if stop != "async_shutdown":
        await coord.async_enable_connection()
        await coord.write("DB1,W2", 2)
        assert client.write.await_count == 2
        client.connect.assert_awaited_once()
        await coord.async_shutdown()


@pytest.mark.asyncio
async def test_shutdown_deadline_cancels_and_drains_before_disconnect(monkeypatch):
    coord, scheduler, tasks, client = make_coordinator()
    entered = asyncio.Event()
    order = []

    async def write(*_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            order.append("write-ended")

    async def disconnect():
        order.append("disconnect")
        client.is_connected = False

    client.write.side_effect = write
    client.disconnect.side_effect = disconnect
    real_wait = asyncio.wait
    waits = 0

    async def controlled_wait(fs, *, timeout):
        nonlocal waits
        waits += 1
        assert timeout == coord._op_timeout
        if waits == 1:
            return set(), set(fs)  # deterministic drain deadline, no wall clock
        return await real_wait(fs, timeout=timeout)

    monkeypatch.setattr(asyncio, "wait", controlled_wait)
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    await coord.async_shutdown()
    with pytest.raises(HomeAssistantError, match="shut down"):
        await caller
    assert tasks[0].cancelled()
    assert order == ["write-ended", "disconnect"]
    assert_clean(coord)


@pytest.mark.asyncio
async def test_shutdown_drains_direct_multi_write_error_cleanup(monkeypatch):
    coord, _, _, client = make_coordinator()
    entered, released = asyncio.Event(), asyncio.Event()
    finished = asyncio.Event()
    disconnects = 0

    async def disconnect():
        nonlocal disconnects
        disconnects += 1
        if disconnects == 1:
            entered.set()
            try:
                await released.wait()
            finally:
                finished.set()
        client.is_connected = False

    # An unexpected driver error reaches write_multi's final cleanup handler.
    client.write.side_effect = ValueError("invalid driver response")
    client.disconnect.side_effect = disconnect
    real_wait = asyncio.wait
    expired = False

    async def controlled_wait(fs, *, timeout):
        nonlocal expired
        if not expired:
            expired = True
            return set(), set(fs)
        return await real_wait(fs, timeout=timeout)

    monkeypatch.setattr(asyncio, "wait", controlled_wait)
    caller = asyncio.create_task(coord.write_multi([("DB1,W0", 1)]))
    await entered.wait()
    try:
        await coord.async_shutdown()
        assert finished.is_set()
        assert caller.cancelled()
        assert disconnects == 2
        assert_clean(coord)
    finally:
        released.set()
        await asyncio.gather(caller, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelling_shutdown_caller_does_not_abandon_cleanup():
    coord, scheduler, tasks, client = make_coordinator()
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    client.write.side_effect = write
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    shutdown_caller = asyncio.create_task(coord.async_shutdown())
    try:
        with pytest.raises(HomeAssistantError):
            await caller
        shutdown_caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await shutdown_caller
        assert not coord._shutdown_task.done()
    finally:
        release.set()
        await coord.async_shutdown()
        await asyncio.gather(*tasks)
    assert_clean(coord)


@pytest.mark.asyncio
async def test_started_timer_task_cannot_capture_batch_after_disconnect():
    coord, scheduler, tasks, client = make_coordinator()
    old = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    # No yield between scheduling and disconnect: the old task has not started.
    await coord.disconnect()
    with pytest.raises(HomeAssistantError):
        await old
    new = await enqueue(coord, "DB1,W0", 2)
    assert not new.done()
    client.write.assert_not_awaited()
    scheduler.timers[-1].fire()
    assert await new is None
    await asyncio.gather(*tasks)
    client.write.assert_awaited_once()
    assert client.write.await_args.args[1] == [2]
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("batching", [False, True])
async def test_shutdown_drains_nonbatched_and_service_writes(batching):
    coord, _, _, client = make_coordinator()
    coord._enable_write_batching = batching
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    client.write.side_effect = write
    operation = (
        coord.write_multi([("DB1,W0", 1)])
        if batching
        else coord.write_batched("DB1,W0", 1)
    )
    caller = asyncio.create_task(operation)
    await entered.wait()
    shutdown = asyncio.create_task(coord.async_shutdown())
    # A deterministic event at the drain boundary proves shutdown is waiting.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    try:
        assert coord._connection.shutdown
        assert not shutdown.done()
        assert caller in coord._connection._io_tasks
    finally:
        release.set()
        with pytest.raises(HomeAssistantError, match="shut down"):
            await caller
        await shutdown
    assert_clean(coord)


@pytest.mark.asyncio
async def test_shutdown_rechecks_state_after_connect_before_sending():
    coord, scheduler, tasks, client = make_coordinator()
    client.is_connected = False
    entered, release = asyncio.Event(), asyncio.Event()

    async def connect():
        entered.set()
        await release.wait()
        client.is_connected = True

    client.connect.side_effect = connect
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    shutdown = asyncio.create_task(coord.async_shutdown())
    try:
        with pytest.raises(HomeAssistantError):
            await caller
    finally:
        release.set()
        await shutdown
        await asyncio.gather(*tasks)
    client.write.assert_not_awaited()
    assert not client.is_connected
    assert_clean(coord)


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
async def test_cancel_before_snapshot_completes_queued_callers(started):
    coord, scheduler, tasks, client = make_coordinator()
    caller = await enqueue(coord, "DB1,W0", 1)
    async with coord._async_lock:
        scheduler.timers[-1].fire()
        if started:
            await asyncio.sleep(0)  # task now waits for snapshot lock
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
    with pytest.raises(HomeAssistantError, match="cancelled"):
        await caller
    client.write.assert_not_awaited()
    assert_clean(coord)


@pytest.mark.asyncio
async def test_cancel_inflight_resolves_its_waiters_not_the_next_batch():
    coord, scheduler, tasks, client = make_coordinator()
    entered = asyncio.Event()
    payloads = []

    async def write(_, values):
        payloads.append(values)
        if len(payloads) == 1:
            entered.set()
            await asyncio.Event().wait()

    client.write.side_effect = write
    first = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    second = await enqueue(coord, "DB1,W2", 2)
    tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    with pytest.raises(HomeAssistantError, match="cancelled"):
        await first
    assert not second.done()
    assert coord._write_manager._buffer == {"DB1,W2": 2}
    client.disconnect.assert_awaited_once()
    scheduler.timers[-1].fire()
    assert await second is None
    await asyncio.gather(*tasks, return_exceptions=True)
    assert payloads == [[1], [2]]
    client.connect.assert_awaited_once()
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_stop_or_cancel_during_retry_backoff_prevents_reconnect(cancel):
    coord, scheduler, tasks, client = make_coordinator()
    coord._max_retries = 2
    client.write.side_effect = OSError("offline")
    entered = asyncio.Event()
    real_sleep = coord._connection.sleep

    async def backoff(_):
        entered.set()
        await real_sleep(60)

    coord._connection.sleep = backoff
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    if cancel:
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
    else:
        await coord.disconnect()
    with pytest.raises(HomeAssistantError):
        await caller
    await asyncio.gather(*tasks, return_exceptions=True)
    assert client.write.await_count == 1
    client.connect.assert_not_awaited()
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
async def test_disconnect_during_failing_write_does_not_retry_stale_epoch():
    coord, scheduler, tasks, client = make_coordinator()
    coord._max_retries = 2
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()
        raise OSError("connection dropped during write")

    client.write.side_effect = write
    caller = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    stopping = asyncio.create_task(coord.disconnect())
    try:
        with pytest.raises(HomeAssistantError):
            await caller
    finally:
        release.set()
        await stopping
        await asyncio.gather(*tasks)
    assert client.write.await_count == 1
    client.connect.assert_not_awaited()
    assert_clean(coord)


@pytest.mark.asyncio
async def test_normal_write_failure_still_reconnects_and_retries():
    coord, _, _, client = make_coordinator()
    coord._max_retries = 1
    coord._connection.sleep = AsyncMock()
    client.write.side_effect = [OSError("temporary"), None]
    assert await coord.write_multi([("DB1,W0", 1)]) == {"DB1,W0": True}
    assert client.write.await_count == 2
    client.connect.assert_awaited_once()
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
async def test_serialization_covers_complete_writes_and_waiting_epoch():
    coord, scheduler, tasks, client = make_coordinator()
    entered, release = asyncio.Event(), asyncio.Event()
    payloads = []

    async def write(_, values):
        payloads.append(values)
        if len(payloads) == 1:
            entered.set()
            await release.wait()

    client.write.side_effect = write
    first = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    second = await enqueue(coord, "DB1,W2", 2)
    scheduler.timers[-1].fire()
    await asyncio.sleep(0)
    try:
        assert len(coord._write_manager._inflight_waiters) == 2
        assert payloads == [[1]]
    finally:
        release.set()
        assert await asyncio.gather(first, second) == [None, None]
        await asyncio.gather(*tasks)
    assert payloads == [[1], [2]]
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("inflight", [False, True])
async def test_timeout_removes_only_its_waiter_and_keeps_shared_write(
    monkeypatch, inflight
):
    coord, scheduler, tasks, client = make_coordinator()
    expire = asyncio.Event()
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    client.write.side_effect = write
    real_wait_for = asyncio.wait_for
    first_wait = True

    async def controlled_wait_for(awaitable, timeout):
        nonlocal first_wait
        if first_wait and isinstance(awaitable, asyncio.Future):
            first_wait = False
            await expire.wait()
            awaitable.cancel()
            raise TimeoutError
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr(asyncio, "wait_for", controlled_wait_for)
    first = await enqueue(coord, "DB1,W0", 1)
    expired_waiter = coord._write_manager._waiters["DB1,W0"][0]
    second = await enqueue(coord, "DB1,W0", 2)
    if inflight:
        scheduler.timers[-1].fire()
        await entered.wait()
    expire.set()
    with pytest.raises(HomeAssistantError, match="timed out"):
        await first
    groups = (
        next(iter(coord._write_manager._inflight_waiters.values()))
        if inflight
        else coord._write_manager._waiters
    )
    assert expired_waiter not in groups["DB1,W0"]
    assert not second.done()
    if not inflight:
        scheduler.timers[-1].fire()
    release.set()
    assert await second is None
    await asyncio.gather(*tasks)
    assert client.write.await_args.args[1] == [2]
    assert_clean(coord)
    await coord.async_shutdown()


@pytest.mark.asyncio
async def test_queued_io_does_not_start_after_shutdown_invalidates_epoch():
    coord, scheduler, tasks, client = make_coordinator()
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*_):
        entered.set()
        await release.wait()

    client.write.side_effect = write
    first = await enqueue(coord, "DB1,W0", 1)
    scheduler.timers[-1].fire()
    await entered.wait()
    second = await enqueue(coord, "DB1,W2", 2)
    scheduler.timers[-1].fire()
    await asyncio.sleep(0)
    assert len(coord._write_manager._inflight_waiters) == 2
    shutdown = asyncio.create_task(coord.async_shutdown())
    try:
        for caller in (first, second):
            with pytest.raises(HomeAssistantError):
                await caller
    finally:
        release.set()
        await shutdown
        await asyncio.gather(*tasks)
    client.write.assert_awaited_once()
    assert_clean(coord)


@pytest.mark.asyncio
async def test_shutdown_of_one_coordinator_does_not_affect_another():
    first, first_scheduler, first_tasks, first_client = make_coordinator()
    second, second_scheduler, second_tasks, second_client = make_coordinator()
    first_caller = await enqueue(first, "DB1,W0", 1)
    second_caller = await enqueue(second, "DB1,W0", 2)
    generation = second._connection.generation
    await first.async_shutdown()
    with pytest.raises(HomeAssistantError):
        await first_caller
    assert not second_caller.done()
    assert not second_scheduler.timers[-1].cancelled
    assert second._connection.generation == generation
    assert second.connection_enabled
    second_scheduler.timers[-1].fire()
    assert await second_caller is None
    await asyncio.gather(*second_tasks)
    first_client.write.assert_not_awaited()
    assert not first_tasks
    assert first_scheduler.timers[-1].cancelled
    assert second_client.write.await_args.args[1] == [2]
    assert_clean(first)
    assert_clean(second)
    await second.async_shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("unload_ok", [False, True])
async def test_real_coordinator_unload_only_stops_after_platform_success(unload_ok):
    coord, _, _, client = make_coordinator()
    entry = SimpleNamespace(
        entry_id="lifecycle", runtime_data=SimpleNamespace(coordinator=coord)
    )
    hass = coord.hass
    hass.data[DOMAIN] = {}

    async def unload(*_):
        assert not coord._connection.shutdown
        assert await coord.write("DB1,W0", 1)
        return unload_ok

    hass.config_entries.async_unload_platforms = unload
    hass.config_entries.async_entries = lambda _: [entry]
    assert await s7init.async_unload_entry(hass, entry) is unload_ok
    assert coord._connection.shutdown is unload_ok
    if unload_ok:
        client.disconnect.assert_awaited_once()
    else:
        client.disconnect.assert_not_awaited()
        assert await coord.write("DB1,W0", 2)
        await coord.async_shutdown()
    assert_clean(coord)
