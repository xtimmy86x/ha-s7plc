"""Mixed batches must retain failures for values rejected before dispatch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.exceptions import HomeAssistantError
from pyS7.errors import S7AddressError
from support.write_batching import enqueue, install_scheduler, make_batch_coordinator

from custom_components.s7plc.plc.address import parse_tag

pytestmark = pytest.mark.asyncio

BAD_ADDRESS = "DB1,X0.0"
GOOD_ADDRESS = "DB1,W10"


@pytest_asyncio.fixture
async def writer():
    coord = make_batch_coordinator()
    client = SimpleNamespace(is_connected=True, write=AsyncMock())

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    coord._connection.client = client
    coord.hass.services.async_call = AsyncMock()
    yield coord, client
    await coord.async_shutdown()


@pytest.mark.parametrize("invalid_first", [True, False])
@pytest.mark.parametrize("driver_fails", [False, True])
async def test_mixed_batch_reports_only_dispatched_values_as_successful(
    writer, invalid_first, driver_fails
):
    coord, client = writer
    writes = [(BAD_ADDRESS, 42), (GOOD_ADDRESS, 7)]
    if not invalid_first:
        writes.reverse()
    if driver_fails:
        client.write.side_effect = OSError("PLC write failed")

    result = await coord.write_multi(writes)

    assert result == {BAD_ADDRESS: False, GOOD_ADDRESS: not driver_fails}
    client.write.assert_awaited_once_with([parse_tag(GOOD_ADDRESS)], [7])
    assert not coord._connection._io_tasks


@pytest.mark.parametrize("invalid_first", [True, False])
async def test_unencodable_string_does_not_block_other_batch_values(
    writer, invalid_first
):
    coord, client = writer
    writes = [("DB1,S0.12", "10 €"), ("DB1,S20.12", "25°C kühl")]
    if not invalid_first:
        writes.reverse()

    assert await coord.write_multi(writes) == {"DB1,S0.12": False, "DB1,S20.12": True}
    client.write.assert_awaited_once_with([parse_tag("DB1,S20.12")], ["25°C kühl"])
    client.disconnect.assert_not_awaited()
    assert client.is_connected


async def test_unencodable_single_string_is_rejected_before_io(writer):
    coord, client = writer
    with pytest.raises(ValueError, match="only supports Latin-1"):
        await coord.write("DB1,S0.12", "🌡")

    client.write.assert_not_awaited()
    client.disconnect.assert_not_awaited()
    assert await coord.write("DB1,S0.12", "25°C") is True
    client.write.assert_awaited_once_with([parse_tag("DB1,S0.12")], ["25°C"])


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize(
    "error",
    [
        S7AddressError("Invalid string value"),
        UnicodeEncodeError("utf-16-be", "\ud800", 0, 1, "surrogates not allowed"),
    ],
)
async def test_driver_validation_error_does_not_disconnect(writer, batch, error):
    coord, client = writer
    client.write.side_effect = error
    if batch:
        assert await coord.write_multi([("DB1,WS0.12", "text")]) == {
            "DB1,WS0.12": False
        }
    else:
        assert await coord.write("DB1,WS0.12", "text") is False
    client.write.assert_awaited_once()
    client.disconnect.assert_not_awaited()
    assert client.is_connected
    client.write.side_effect = None
    assert await coord.write(GOOD_ADDRESS, 7) is True


@pytest.mark.parametrize("invalid_first", [True, False])
@pytest.mark.parametrize("notification_error", [None, HomeAssistantError, RuntimeError])
async def test_mixed_flush_preserves_results_when_notifying(
    writer, invalid_first, notification_error, caplog
):
    coord, client = writer
    if notification_error is not None:
        coord.hass.services.async_call.side_effect = notification_error(
            "Notification unavailable"
        )
    scheduler, background_tasks = install_scheduler(coord)
    writes = [(BAD_ADDRESS, 42), (GOOD_ADDRESS, 7)]
    if not invalid_first:
        writes.reverse()
    callers = {}
    try:
        for address, value in writes:
            callers[address] = await enqueue(coord, address, value)
        scheduler.timers[-1].fire()
        results = await asyncio.wait_for(
            asyncio.gather(*callers.values(), return_exceptions=True), timeout=3
        )
        await asyncio.gather(*background_tasks)

        outcomes = dict(zip(callers, results, strict=True))
        assert isinstance(outcomes[BAD_ADDRESS], HomeAssistantError)
        assert str(outcomes[BAD_ADDRESS]) == f"S7 PLC write failed for {BAD_ADDRESS}"
        assert outcomes[GOOD_ADDRESS] is None
        client.write.assert_awaited_once_with([parse_tag(GOOD_ADDRESS)], [7])
        coord.hass.services.async_call.assert_awaited_once()
        notification = coord.hass.services.async_call.await_args
        assert notification.args[:2] == ("persistent_notification", "create")
        assert notification.args[2]["message"] == (
            f"S7 PLC write failed for 1 address(es): {BAD_ADDRESS}"
        )
        if notification_error is not None:
            assert "Failed to create S7 PLC write error notification" in caplog.text
        assert not coord._write_manager._buffer
        assert not coord._write_manager._waiters
        assert not coord._write_manager._inflight_waiters
        assert not coord._connection._io_tasks
    finally:
        for task in callers.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*callers.values(), return_exceptions=True)
        await asyncio.gather(*background_tasks, return_exceptions=True)


async def test_cancelling_flush_during_notification_fails_pending_callers(writer):
    coord, client = writer
    scheduler, background_tasks = install_scheduler(coord)
    notifying = asyncio.Event()

    async def notify(*args, **kwargs):
        notifying.set()
        await asyncio.Future()

    coord.hass.services.async_call.side_effect = notify
    callers = []
    try:
        for address, value in [(BAD_ADDRESS, 42), (GOOD_ADDRESS, 7)]:
            callers.append(await enqueue(coord, address, value))
        scheduler.timers[-1].fire()
        await asyncio.wait_for(notifying.wait(), timeout=3)
        (flush,) = background_tasks
        flush.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flush
        outcomes = await asyncio.wait_for(
            asyncio.gather(*callers, return_exceptions=True), timeout=3
        )
        assert all(isinstance(outcome, HomeAssistantError) for outcome in outcomes)
        assert all(str(outcome) == "PLC write was cancelled" for outcome in outcomes)
        client.write.assert_awaited_once_with([parse_tag(GOOD_ADDRESS)], [7])
        coord.hass.services.async_call.assert_awaited_once()
        assert not coord._write_manager._inflight_waiters
        assert not coord._connection._io_tasks
    finally:
        for task in [*callers, *background_tasks]:
            if not task.done():
                task.cancel()
        await asyncio.gather(*callers, *background_tasks, return_exceptions=True)
