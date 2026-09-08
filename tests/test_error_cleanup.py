"""Error cleanup must preserve new sessions and retry failed closes."""

import asyncio

import pytest
import test_retry_behavior as retry_tests
from homeassistant.helpers.update_coordinator import UpdateFailed

pytestmark = pytest.mark.asyncio

# Reuse the controlled client fixture and operation entry points from the
# retry characterization suite; keep connection/lifecycle methods real.
rig = retry_tests.rig


async def assert_failed_operation(coord, operation):
    """Keep caller-visible outcomes in the cleanup scenarios explicit."""
    if operation in ("write", "write_multi"):
        result = await retry_tests.invoke(coord, operation)
        assert result == (False if operation == "write" else {"DB1,W0": False})
    else:
        expected = RuntimeError if operation == "read_one" else UpdateFailed
        with pytest.raises(expected, match="offline"):
            await retry_tests.invoke(coord, operation)


@pytest.mark.parametrize("operation", ["write", "write_multi", "read_one"])
@pytest.mark.parametrize("during_connect", [False, True])
async def test_outer_cleanup_retries_a_failed_inner_close(
    rig, operation, during_connect
):
    """A failed disconnect is swallowed internally; the outer close still helps."""
    if during_connect:
        rig.client.is_connected = False
        rig.connect_errors.append(OSError("offline"))
    else:
        rig.io_errors.append(OSError("offline"))
    disconnect = rig.client.disconnect.side_effect
    first = True

    async def failing_first_close():
        nonlocal first
        if first:
            first = False
            rig.events.append("disconnect-failed")
            raise OSError("close failed")
        await disconnect()

    rig.client.disconnect.side_effect = failing_first_close

    await assert_failed_operation(rig.coord, operation)

    initial_event = (
        "connect" if during_connect else "read" if operation == "read_one" else "write"
    )
    assert rig.events == [initial_event, "disconnect-failed", "disconnect"]
    assert rig.client.disconnect.await_count == 2
    assert not rig.coord.is_connected()
    retry_tests.assert_no_operations(rig.coord)


@pytest.mark.parametrize("operation", ["write", "write_multi", "read_one"])
async def test_outer_cleanup_handles_unexpected_handshake_failure(rig, operation):
    """Errors outside the handshake's handled classes still need adapter cleanup."""
    rig.client.is_connected = False
    rig.connect_errors.append(ValueError("offline"))

    await assert_failed_operation(rig.coord, operation)

    assert rig.events == ["connect", "disconnect"]
    assert rig.coord.error_count_by_category == {}
    retry_tests.assert_no_operations(rig.coord)


@pytest.mark.parametrize(
    "operation", ["write", "write_multi", "read_one", "scalar_poll", "string_poll"]
)
async def test_outer_cleanup_preserves_a_successfully_reconnected_transport(
    rig, operation, monkeypatch
):
    """Late cleanup must not close the session established by a queued read."""
    rig.io_errors.append(OSError("offline"))
    close_entered = asyncio.Event()
    release_close = asyncio.Event()
    handshake_queued = asyncio.Event()
    disconnect = rig.client.disconnect.side_effect
    connect = rig.coord._connection._connect
    first = True

    async def hold_first_close():
        nonlocal first
        await disconnect()
        if first:
            first = False
            close_entered.set()
            # Model an asynchronous driver close while the manager still
            # owns its transport lock. Reconnection must wait behind it.
            await release_close.wait()

    async def observe_handshake(generation):
        handshake_queued.set()
        await connect(generation)

    rig.client.disconnect.side_effect = hold_first_close
    monkeypatch.setattr(rig.coord._connection, "_connect", observe_handshake)
    tasks = [asyncio.create_task(assert_failed_operation(rig.coord, operation))]
    try:
        await asyncio.wait_for(close_entered.wait(), timeout=3)
        assert not rig.coord.is_connected()
        tasks.append(asyncio.create_task(rig.coord._read_one("DB1,W2")))
        await asyncio.wait_for(handshake_queued.wait(), timeout=3)
        rig.client.connect.assert_not_awaited()
        assert not tasks[1].done()
        release_close.set()
        _, value = await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        assert value == 7

        driver_call = "write" if operation in ("write", "write_multi") else "read"
        assert rig.events == [driver_call, "disconnect", "connect", "read"]
        assert rig.client.connect.await_count == 1
        assert rig.coord.is_connected()
        retry_tests.assert_no_operations(rig.coord)
    finally:
        release_close.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("close_outcome", ["raises_after_close", "returns_connected"])
async def test_outer_cleanup_requires_successful_disconnect(rig, close_outcome):
    """Neither a changed connection flag nor a normal return alone proves cleanup."""
    rig.io_errors.append(OSError("offline"))
    disconnect = rig.client.disconnect.side_effect
    first = True

    async def incomplete_close():
        nonlocal first
        if first:
            first = False
            if close_outcome == "raises_after_close":
                await disconnect()
                raise OSError("close failed after changing state")
            # Return without changing is_connected: the adapter must retry.
            return
        await disconnect()

    rig.client.disconnect.side_effect = incomplete_close
    assert await rig.coord.write("DB1,W0", 7) is False
    assert rig.client.disconnect.await_count == 2
    assert not rig.coord.is_connected()
    retry_tests.assert_no_operations(rig.coord)


async def test_error_cleanup_skips_old_session_but_explicit_disconnect_closes_new(rig):
    """Lifecycle disconnect is unconditional even after a successfully cleaned error."""
    rig.io_errors.append(OSError("offline"))
    with pytest.raises(RuntimeError) as caught:
        await rig.coord._retry(rig.client.read, [])

    assert await rig.coord._read_one("DB1,W0") == 7
    await rig.coord._connection.drop_connection(error=caught.value)
    assert rig.coord.is_connected()
    rig.client.disconnect.assert_awaited_once()
    await rig.coord.disconnect()
    assert not rig.coord.is_connected()
    assert rig.client.disconnect.await_count == 2
    retry_tests.assert_no_operations(rig.coord)


async def test_error_cleanup_rechecks_session_after_waiting_for_transport_lock(
    rig, monkeypatch
):
    """An uncleaned receipt cannot close a new session established ahead of it."""
    rig.io_errors.append(OSError("offline"))
    disconnect = rig.client.disconnect.side_effect
    rig.client.disconnect.side_effect = OSError("close failed")
    with pytest.raises(RuntimeError) as caught:
        await rig.coord._retry(rig.client.read, [])
    # The previous close failed. Simulate the peer subsequently closing so
    # a real handshake is needed before the next read.
    rig.client.is_connected = False
    handshake_queued = asyncio.Event()
    cleanup_queued = asyncio.Event()
    connect = rig.coord._connection._connect
    tasks = []

    async def observe_handshake(generation):
        handshake_queued.set()
        await connect(generation)

    async def late_cleanup():
        cleanup_queued.set()
        await rig.coord._connection.drop_connection(error=caught.value)

    monkeypatch.setattr(rig.coord._connection, "_connect", observe_handshake)
    try:
        async with rig.coord._connection._transport_lock:
            tasks.append(asyncio.create_task(rig.coord._read_one("DB1,W0")))
            await asyncio.wait_for(handshake_queued.wait(), timeout=3)
            tasks.append(asyncio.create_task(late_cleanup()))
            await asyncio.wait_for(cleanup_queued.wait(), timeout=3)
        value, _ = await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        assert value == 7
        assert rig.coord.is_connected()
        rig.client.connect.assert_awaited_once()
        # Only the original failed close was dispatched; the new session
        # must not be targeted, even though the old receipt was not cleaned.
        rig.client.disconnect.assert_awaited_once()
        retry_tests.assert_no_operations(rig.coord)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Allow fixture shutdown to close the healthy session normally.
        rig.client.disconnect.side_effect = disconnect


@pytest.mark.parametrize("first_close_fails", [False, True])
async def test_shared_handshake_waiters_share_cleanup_success(rig, first_close_fails):
    """Both callers see the failure; only unfinished cleanup is retried."""
    rig.client.is_connected = False
    connect_entered = asyncio.Event()
    release_connect = asyncio.Event()
    second_waiter = asyncio.Event()
    ensure = rig.coord._connection.ensure_connected
    disconnect = rig.client.disconnect.side_effect
    ensure_calls = 0
    closes = 0
    tasks = []

    async def failing_connect():
        connect_entered.set()
        await release_connect.wait()
        raise OSError("offline")

    async def observe_waiter():
        nonlocal ensure_calls
        ensure_calls += 1
        if ensure_calls == 2:
            second_waiter.set()
        await ensure()

    async def close():
        nonlocal closes
        closes += 1
        if first_close_fails and closes == 1:
            raise OSError("close failed")
        await disconnect()

    rig.client.connect.side_effect = failing_connect
    rig.client.disconnect.side_effect = close
    rig.coord._connection.ensure_connected = observe_waiter
    try:
        tasks.append(asyncio.create_task(assert_failed_operation(rig.coord, "write")))
        await asyncio.wait_for(connect_entered.wait(), timeout=3)
        tasks.append(
            asyncio.create_task(assert_failed_operation(rig.coord, "read_one"))
        )
        await asyncio.wait_for(second_waiter.wait(), timeout=3)
        release_connect.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        rig.client.connect.assert_awaited_once()
        assert rig.client.disconnect.await_count == (2 if first_close_fails else 1)
        assert not rig.coord.is_connected()
        assert rig.coord.error_count_by_category == {}
        retry_tests.assert_no_operations(rig.coord)
    finally:
        release_connect.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
