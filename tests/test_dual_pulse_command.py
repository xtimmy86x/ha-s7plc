"""Explicit SET/RESET pulses, including uncertain writes and concurrent services."""

import asyncio
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.config_validation import (
    build_entity_item,
    validate_entity_fields,
)
from custom_components.s7plc.helpers import build_expected_unique_ids
from custom_components.s7plc.light import S7Light
from custom_components.s7plc.switch import S7Switch

STATE, ON, OFF, TOPIC = "I1.3", "Q1.0", "Q1.1", "dual-state"


@pytest.fixture(params=[S7Switch, S7Light], ids=["switch", "light"])
def entity(request, mock_coordinator, fake_hass):
    result = request.param(
        mock_coordinator,
        name="Dual pulse",
        unique_id="dual-pulse",
        device_info={"identifiers": {("s7plc", "test")}},
        topic=TOPIC,
        state_address=STATE,
        command_address=ON,
        off_command_address=OFF,
        sync_state=False,
        pulse_command=False,
        pulse_duration=0,
    )
    result.hass = fake_hass
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("initial", [True, False, None])
@pytest.mark.parametrize("action,address", [("on", ON), ("off", OFF)])
async def test_explicit_pulses_never_use_stale_feedback_guard(
    entity, mock_coordinator, initial, action, address
):
    mock_coordinator.data = {TOPIC: initial}
    await getattr(entity, f"async_turn_{action}")()
    assert mock_coordinator.write_calls == [
        ("write", address, True),
        ("write", address, False),
    ]
    assert entity.is_on is initial
    assert mock_coordinator.refresh_count == 1
    assert entity.extra_state_attributes["dual_pulse_command"] is True
    assert entity.extra_state_attributes["s7_off_command_address"] == OFF
    assert "pulse_duration" in entity.extra_state_attributes


@pytest.mark.asyncio
async def test_opposite_requests_are_serialized(entity, mock_coordinator):
    started, release = asyncio.Event(), asyncio.Event()
    write = mock_coordinator.write

    async def blocked_write(address, value):
        result = await write(address, value)
        if address == ON and value:
            started.set()
            await release.wait()
        return result

    mock_coordinator.write = blocked_write
    mock_coordinator.data = {TOPIC: False}
    first = asyncio.create_task(entity.async_turn_on())
    await started.wait()
    second = asyncio.create_task(entity.async_turn_off())
    release.set()
    await asyncio.gather(first, second)
    assert mock_coordinator.write_calls == [
        ("write", ON, True),
        ("write", ON, False),
        ("write", OFF, True),
        ("write", OFF, False),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["activation", "delay", "reset"])
async def test_cancellation_waits_for_reset_before_next_pulse(
    entity, mock_coordinator, monkeypatch, phase
):
    started, release, resetting, release_reset = (asyncio.Event() for _ in range(4))
    write = mock_coordinator.write

    async def blocked_write(address, value):
        result = await write(address, value)
        if address == ON:
            if value and phase == "activation":
                started.set()
                await release.wait()
            if not value:
                resetting.set()
                if phase == "reset":
                    started.set()
                await release_reset.wait()
        return result

    async def delay(duration):
        if phase == "delay":
            started.set()
            await release.wait()

    mock_coordinator.write = blocked_write
    monkeypatch.setattr("custom_components.s7plc.entity.asyncio.sleep", delay)
    first = asyncio.create_task(entity.async_turn_on())
    await started.wait()
    first.cancel()
    release.set()
    await resetting.wait()
    second = asyncio.create_task(entity.async_turn_off())
    first.cancel()
    assert mock_coordinator.write_calls == [("write", ON, True), ("write", ON, False)]
    release_reset.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    await second
    assert mock_coordinator.write_calls[-2:] == [
        ("write", OFF, True),
        ("write", OFF, False),
    ]
    assert not entity._dual_pulse_lock.locked()


@pytest.mark.asyncio
async def test_failed_activation_still_releases_output(entity, mock_coordinator):
    mock_coordinator.set_write_queue(False, True)
    with pytest.raises(HomeAssistantError, match=ON):
        await entity.async_turn_on()
    assert mock_coordinator.write_calls == [("write", ON, True), ("write", ON, False)]
    assert mock_coordinator.refresh_count == 0


@pytest.mark.asyncio
async def test_failed_reset_blocks_next_activation_until_released(
    entity, mock_coordinator
):
    mock_coordinator.set_write_queue(True, False, False, True, True, True)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_off()
    assert mock_coordinator.write_calls == [
        ("write", ON, True),
        ("write", ON, False),
        ("write", ON, False),
    ]
    await entity.async_turn_off()
    assert mock_coordinator.write_calls[-3:] == [
        ("write", ON, False),
        ("write", OFF, True),
        ("write", OFF, False),
    ]


@pytest.mark.asyncio
async def test_connection_failure_does_not_start_pulse(entity, mock_coordinator):
    mock_coordinator.set_connected(False)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_assumed_state_only_changes_after_success(entity, mock_coordinator):
    entity._address = None
    entity._attr_assumed_state = True
    assert entity.is_on is None
    assert entity.available
    assert TOPIC not in entity._restorable_topics
    await entity.async_turn_on()
    assert entity.is_on is True
    assert entity.extra_state_attributes["s7_command_address"] == ON
    assert "s7_state_address" not in entity.extra_state_attributes
    mock_coordinator.set_write_queue(True, False)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_off()
    assert entity.is_on is None


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize("feedback", [True, False])
def test_config_round_trip_and_expected_entity(entity_type, feedback):
    config = {"uid": "dual", "command_address": ON, "off_command_address": OFF}
    if feedback:
        config["state_address"] = STATE
    original = deepcopy(config)
    validate_entity_fields(entity_type, config)
    item, errors = build_entity_item(entity_type, config, options={})
    assert not errors
    assert item["off_command_address"] == OFF
    assert bool(item.get("state_address")) is feedback
    assert build_entity_item(entity_type, item, options={}) == (item, {})
    assert "dual" in build_expected_unique_ids("test", {entity_type: [config]})
    assert config == original


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize(
    "fields,error",
    [
        ({"command_address": None}, "dual_pulse_requires_on_address"),
        ({"off_command_address": "q01.0"}, "dual_pulse_same_address"),
        ({"off_command_address": "QB1"}, "dual_pulse_requires_output_bits"),
        ({"command_address": "I1.0"}, "dual_pulse_requires_output_bits"),
        ({"off_command_address": "I1.1"}, "dual_pulse_requires_output_bits"),
        ({"state_address": ON}, "dual_pulse_invalid_feedback"),
        ({"state_address": OFF}, "dual_pulse_invalid_feedback"),
        ({"state_address": "IB1"}, "dual_pulse_invalid_feedback"),
        ({"sync_state": True}, "dual_pulse_conflict"),
        ({"pulse_command": True}, "dual_pulse_conflict"),
        ({"single_fire_command": True}, "dual_pulse_conflict"),
        ({"pulse_duration": -1}, "invalid_pulse_duration"),
        ({"pulse_duration": 61}, "invalid_pulse_duration"),
        ({"pulse_duration": float("nan")}, "invalid_pulse_duration"),
    ],
)
def test_invalid_dual_configuration(entity_type, fields, error):
    assert build_entity_item(
        entity_type,
        {
            "state_address": STATE,
            "command_address": ON,
            "off_command_address": OFF,
            **fields,
        },
        options={},
    ) == (None, {"base": error})


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
def test_command_only_duplicate_and_edit(entity_type):
    config = {"command_address": ON, "off_command_address": OFF}
    options = {entity_type: [config]}
    assert build_entity_item(entity_type, config, options=options)[1] == {
        "base": "duplicate_entry"
    }
    assert not build_entity_item(entity_type, config, options=options, skip_idx=0)[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type,module", [("switches", "switch"), ("lights", "light")]
)
@pytest.mark.parametrize("feedback", [True, False])
async def test_setup_dual_output(
    entity_type, module, feedback, mock_coordinator, fake_hass
):
    config = {
        "uid": "dual",
        "command_address": ON,
        "off_command_address": OFF,
        "pulse_duration": 0,
    }
    if feedback:
        config["state_address"] = STATE
    entry = MagicMock(data={}, options={entity_type: [config]})
    add = MagicMock()
    with patch(
        f"custom_components.s7plc.{module}.get_coordinator_and_device_info",
        return_value=(mock_coordinator, {}, "test"),
    ):
        if module == "light":
            from custom_components.s7plc.light import async_setup_entry
        else:
            from custom_components.s7plc.switch import async_setup_entry
        await async_setup_entry(fake_hass, entry, add)
    loaded = add.call_args.args[0][0]
    loaded.hass = fake_hass
    assert loaded._attr_assumed_state is not feedback
    assert len(mock_coordinator.add_item_calls) == int(feedback)
    await loaded.async_turn_off()
    assert mock_coordinator.write_calls == [("write", OFF, True), ("write", OFF, False)]
    assert loaded.is_on is (None if feedback else False)
