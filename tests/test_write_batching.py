"""Behavioral contract tests for coordinator write batching."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from support.write_batching import enqueue, install_scheduler, make_batch_coordinator

from custom_components.s7plc.number import S7Number


@pytest.mark.asyncio
async def test_batching_disabled_writes_immediately_without_scheduling():
    """The non-batched path delegates once and does not wait for a timer."""
    coord = make_batch_coordinator(batching=False)
    scheduler, background_tasks = install_scheduler(coord)
    coord.write = AsyncMock(return_value=True)

    result = await coord.write_batched("DB1,W10", 42.7)

    assert result is None
    coord.write.assert_awaited_once_with("DB1,W10", 42.7)
    assert scheduler.timers == []
    assert background_tasks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("write_result", "write_error"),
    [(False, None), (None, HomeAssistantError("already public"))],
)
async def test_batching_disabled_exposes_write_errors_without_flush_side_effects(
    write_result, write_error
):
    """Immediate failures keep the public error contract and create no batch work."""
    coord = make_batch_coordinator(batching=False)
    scheduler, background_tasks = install_scheduler(coord)
    coord.hass.services.async_call = AsyncMock()
    coord.write = AsyncMock(return_value=write_result, side_effect=write_error)

    with pytest.raises(HomeAssistantError):
        await coord.write_batched("DB1,W10", 42)

    coord.write.assert_awaited_once_with("DB1,W10", 42)
    coord.hass.services.async_call.assert_not_awaited()
    assert scheduler.timers == []
    assert background_tasks == []


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_same_address_last_value_wins_and_all_callers_share_outcome(success):
    """The superseded value is not written, but its caller gets the final outcome."""
    coord = make_batch_coordinator()
    scheduler, background_tasks = install_scheduler(coord)
    batches = []

    async def write_multi(writes):
        batches.append(writes)
        return {address: success for address, _ in writes}

    coord.write_multi = write_multi
    first = await enqueue(coord, "DB1,W10", 10)
    first_timer = scheduler.timers[-1]
    second = await enqueue(coord, "DB1,W10", 20)

    assert first_timer.cancelled
    scheduler.timers[-1].fire()
    results = await asyncio.gather(first, second, return_exceptions=True)
    await asyncio.gather(*background_tasks)

    assert batches == [[("DB1,W10", 20)]]
    if success:
        assert results == [None, None]
    else:
        assert all(isinstance(result, HomeAssistantError) for result in results)
    assert first.done() and second.done()
    assert all(task.done() for task in background_tasks)


@pytest.mark.asyncio
async def test_debounce_is_restarted_from_the_latest_enqueue():
    """A later enqueue cancels the old deadline and starts a fresh 50 ms delay."""
    coord = make_batch_coordinator()
    scheduler, background_tasks = install_scheduler(coord)
    coord.write_multi = AsyncMock(return_value={"DB1,W10": True, "DB1,W12": True})

    first = await enqueue(coord, "DB1,W10", 10)
    old_deadline = scheduler.timers[-1]
    second = await enqueue(coord, "DB1,W12", 12)
    new_deadline = scheduler.timers[-1]

    assert old_deadline.cancelled
    assert old_deadline.delay == new_deadline.delay == 0.05
    await asyncio.sleep(0)
    coord.write_multi.assert_not_awaited()
    assert not first.done() and not second.done()

    new_deadline.fire()
    assert await asyncio.gather(first, second) == [None, None]
    await asyncio.gather(*background_tasks)
    coord.write_multi.assert_awaited_once_with([("DB1,W10", 10), ("DB1,W12", 12)])


@pytest.mark.asyncio
async def test_enqueue_during_flush_creates_a_second_generation():
    """Writes arriving after the flush snapshot are retained for the next flush."""
    coord = make_batch_coordinator()
    scheduler, background_tasks = install_scheduler(coord)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    batches = []

    async def write_multi(writes):
        batches.append(writes)
        if len(batches) == 1:
            first_started.set()
            await release_first.wait()
        return {address: True for address, _ in writes}

    coord.write_multi = write_multi
    first = await enqueue(coord, "DB1,W10", 10)
    scheduler.timers[-1].fire()
    await first_started.wait()

    second = await enqueue(coord, "DB1,W12", 12)
    assert batches == [[("DB1,W10", 10)]]
    assert not second.done()
    second_timer = scheduler.timers[-1]

    release_first.set()
    assert await first is None
    second_timer.fire()
    assert await second is None
    await asyncio.gather(*background_tasks)

    assert batches == [[("DB1,W10", 10)], [("DB1,W12", 12)]]
    assert first.done() and second.done()


@pytest.mark.asyncio
async def test_coordinators_have_isolated_queues_waiters_and_failures():
    """Same-address batches on different coordinators never share state."""
    good = make_batch_coordinator()
    bad = make_batch_coordinator()
    good_scheduler, good_background = install_scheduler(good)
    bad_scheduler, bad_background = install_scheduler(bad)
    good.write_multi = AsyncMock(return_value={"DB1,W10": True})
    bad.write_multi = AsyncMock(return_value={"DB1,W10": False})

    good_write = await enqueue(good, "DB1,W10", 10)
    bad_write = await enqueue(bad, "DB1,W10", 99)
    good_scheduler.timers[-1].fire()
    assert await good_write is None
    assert not bad_write.done()

    bad_scheduler.timers[-1].fire()
    with pytest.raises(HomeAssistantError):
        await bad_write
    await asyncio.gather(*good_background, *bad_background)

    good.write_multi.assert_awaited_once_with([("DB1,W10", 10)])
    bad.write_multi.assert_awaited_once_with([("DB1,W10", 99)])


@pytest.mark.asyncio
async def test_number_conversion_precedes_batching_and_payload_normalization(
    monkeypatch,
):
    """Semantic scaling occurs once before coordinator datatype coercion."""
    coord = make_batch_coordinator(batching=False)
    written_payloads = []

    class Client:
        is_connected = True

        def write(self, tags, payloads):
            written_payloads.extend(payloads)

    coord._connection.client = Client()

    async def no_op():
        return None

    async def retry_once(func):
        return func()

    coord._connection.ensure_connected = no_op
    coord._retry = retry_once
    coord.async_request_refresh = AsyncMock()
    batched_inputs = []
    real_write_batched = coord.write_batched

    async def tracked_write_batched(address, value):
        batched_inputs.append((address, value))
        return await real_write_batched(address, value)

    coord.write_batched = tracked_write_batched

    from custom_components.s7plc import number as number_module

    real_convert = number_module.convert_to_plc
    conversion_inputs = []

    def tracked_convert(value, config, context):
        conversion_inputs.append(value)
        return real_convert(value, config, context)

    monkeypatch.setattr(number_module, "convert_to_plc", tracked_convert)
    entity = S7Number(
        coord,
        name="Scaled",
        unique_id="scaled",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w10",
        address="DB1,W10",
        command_address="DB1,W10",
        min_value=-50,
        max_value=50,
        step=1,
        value_conversion={
            "type": "linear_scale",
            "plc_min": 0,
            "plc_max": 1000,
            "ha_min": -50,
            "ha_max": 50,
        },
    )

    assert await entity.async_set_native_value(25) is None

    assert conversion_inputs == [25]
    assert batched_inputs == [("DB1,W10", 750)]
    assert written_payloads == [750]
    coord.async_request_refresh.assert_awaited_once()
