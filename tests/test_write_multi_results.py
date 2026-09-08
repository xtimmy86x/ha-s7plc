"""Mixed batches must retain failures for values rejected before dispatch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.exceptions import HomeAssistantError
from test_write_batching import _enqueue, _install_scheduler, _make_coordinator

from custom_components.s7plc.plc.address import parse_tag

pytestmark = pytest.mark.asyncio

BAD_ADDRESS = "DB1,X0.0"
GOOD_ADDRESS = "DB1,W10"


@pytest_asyncio.fixture
async def writer():
    coord = _make_coordinator()
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
async def test_mixed_flush_fails_rejected_caller_and_notifies(writer, invalid_first):
    coord, client = writer
    scheduler, background_tasks = _install_scheduler(coord)
    writes = [(BAD_ADDRESS, 42), (GOOD_ADDRESS, 7)]
    if not invalid_first:
        writes.reverse()
    callers = {}
    try:
        for address, value in writes:
            callers[address] = await _enqueue(coord, address, value)
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
