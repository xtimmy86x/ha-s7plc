"""Behavioral contract tests for coordinator write batching."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc import coordinator as coordinator_module
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.number import S7Number


class _ControlledTimer:
    """Timer handle whose callback is fired explicitly by a test."""

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def fire(self):
        assert not self.cancelled
        self.callback()


class _ControlledScheduler:
    """Minimal deterministic replacement for loop.call_later."""

    def __init__(self):
        self.timers: list[_ControlledTimer] = []

    def call_later(self, delay, callback):
        timer = _ControlledTimer(delay, callback)
        self.timers.append(timer)
        return timer


def _make_coordinator(*, batching=True):
    hass = coordinator_module.HomeAssistant()
    coord = S7Coordinator(
        hass,
        host="plc.local",
        enable_write_batching=batching,
        max_retries=0,
    )
    return coord


def _install_scheduler(coord):
    scheduler = _ControlledScheduler()
    coord.hass.loop = scheduler
    background_tasks = []

    def create_background_task(coro, name=None):
        task = asyncio.create_task(coro, name=name)
        background_tasks.append(task)
        return task

    coord.hass.async_create_background_task = create_background_task
    return scheduler, background_tasks


async def _enqueue(coord, address, value):
    task = asyncio.create_task(coord.write_batched(address, value))
    await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_batching_disabled_writes_immediately_without_scheduling():
    """The non-batched path delegates once and does not wait for a timer."""
    coord = _make_coordinator(batching=False)
    scheduler, background_tasks = _install_scheduler(coord)
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
    coord = _make_coordinator(batching=False)
    scheduler, background_tasks = _install_scheduler(coord)
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
    coord = _make_coordinator()
    scheduler, background_tasks = _install_scheduler(coord)
    batches = []

    async def write_multi(writes):
        batches.append(writes)
        return {address: success for address, _ in writes}

    coord.write_multi = write_multi
    first = await _enqueue(coord, "DB1,W10", 10)
    first_timer = scheduler.timers[-1]
    second = await _enqueue(coord, "DB1,W10", 20)

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
    coord = _make_coordinator()
    scheduler, background_tasks = _install_scheduler(coord)
    coord.write_multi = AsyncMock(
        return_value={"DB1,W10": True, "DB1,W12": True}
    )

    first = await _enqueue(coord, "DB1,W10", 10)
    old_deadline = scheduler.timers[-1]
    second = await _enqueue(coord, "DB1,W12", 12)
    new_deadline = scheduler.timers[-1]

    assert old_deadline.cancelled
    assert old_deadline.delay == new_deadline.delay == 0.05
    await asyncio.sleep(0)
    coord.write_multi.assert_not_awaited()
    assert not first.done() and not second.done()

    new_deadline.fire()
    assert await asyncio.gather(first, second) == [None, None]
    await asyncio.gather(*background_tasks)
    coord.write_multi.assert_awaited_once_with(
        [("DB1,W10", 10), ("DB1,W12", 12)]
    )


@pytest.mark.asyncio
async def test_enqueue_during_flush_creates_a_second_generation():
    """Writes arriving after the flush snapshot are retained for the next flush."""
    coord = _make_coordinator()
    scheduler, background_tasks = _install_scheduler(coord)
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
    first = await _enqueue(coord, "DB1,W10", 10)
    scheduler.timers[-1].fire()
    await first_started.wait()

    second = await _enqueue(coord, "DB1,W12", 12)
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
    good = _make_coordinator()
    bad = _make_coordinator()
    good_scheduler, good_background = _install_scheduler(good)
    bad_scheduler, bad_background = _install_scheduler(bad)
    good.write_multi = AsyncMock(return_value={"DB1,W10": True})
    bad.write_multi = AsyncMock(return_value={"DB1,W10": False})

    good_write = await _enqueue(good, "DB1,W10", 10)
    bad_write = await _enqueue(bad, "DB1,W10", 99)
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
    coord = _make_coordinator(batching=False)
    written_payloads = []

    class Client:
        is_connected = True

        def write(self, tags, payloads):
            written_payloads.extend(payloads)

    coord._client = Client()

    async def no_op():
        return None

    async def retry_once(func):
        return func()

    coord._ensure_connected = no_op
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
