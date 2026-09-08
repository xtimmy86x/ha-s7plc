"""Characterize cleanup ownership before removing outer disconnects.

The reconnect test deliberately records the current stale-close behavior. It
must change when cleanup becomes scoped to the transport that actually failed.
"""

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
async def test_outer_cleanup_currently_closes_a_successfully_reconnected_transport(
    rig, operation, monkeypatch
):
    """Queue a real handshake behind the failing operation's first close.

    This is characterization of a defect, not a required cleanup policy:
    all adapters except planned string polling close the healthy new session.
    """
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
        stale_close = operation != "string_poll"
        assert rig.events == [driver_call, "disconnect", "connect"] + (
            ["disconnect", "connect"] if stale_close else []
        ) + ["read"]
        # The waiting read succeeds, but needs a second handshake after the
        # outer handler closes the connection that was just established.
        assert rig.client.connect.await_count == (2 if stale_close else 1)
        assert rig.coord.is_connected()
        retry_tests.assert_no_operations(rig.coord)
    finally:
        release_close.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
