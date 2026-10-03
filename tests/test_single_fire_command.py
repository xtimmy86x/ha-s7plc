"""Single-fire commands preserve pulse guards without timing or a reset write."""

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.light import S7Light
from custom_components.s7plc.switch import S7Switch

STATE = "DB1,X0.0"
COMMAND = "DB1,X0.1"
TOPIC = "command-state"


@pytest.fixture(params=[S7Switch, S7Light], ids=["switch", "light"])
def entity(request, mock_coordinator, fake_hass):
    result = request.param(
        mock_coordinator,
        name="Single fire",
        unique_id="single-fire",
        device_info={"identifiers": {("s7plc", "test")}},
        topic=TOPIC,
        state_address=STATE,
        command_address=COMMAND,
        sync_state=False,
        pulse_command=False,
        pulse_duration=0.5,
        single_fire_command=True,
    )
    result.hass = fake_hass
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "action", "fires"),
    [
        (False, "on", True),
        (True, "off", True),
        (True, "on", False),
        (False, "off", False),
    ],
)
async def test_single_fire_state_guard(entity, mock_coordinator, state, action, fires):
    mock_coordinator.data = {TOPIC: state}
    with patch(
        "custom_components.s7plc.entity.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await getattr(entity, f"async_turn_{action}")()
        sleep.assert_not_awaited()
    assert mock_coordinator.write_calls == (
        [("write_batched", COMMAND, True)] if fires else []
    )
    assert mock_coordinator.refresh_count == int(fires)
    # State comes from PLC feedback, never from the command bit or an optimistic flip.
    assert entity.is_on is state
    assert entity.extra_state_attributes["single_fire_command"] is True
    assert "pulse_duration" not in entity.extra_state_attributes
    assert "sync_state" not in entity.extra_state_attributes


@pytest.mark.asyncio
async def test_single_fire_write_failure_propagates(entity, mock_coordinator):
    mock_coordinator.data = {TOPIC: False}
    mock_coordinator.set_write_queue(False)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    assert mock_coordinator.write_calls == [("write_batched", COMMAND, True)]
    assert mock_coordinator.refresh_count == 0


@pytest.mark.asyncio
async def test_single_fire_disabled_connection_rejects_command(
    entity, mock_coordinator
):
    mock_coordinator.data = {TOPIC: False}
    mock_coordinator.set_connected(False)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", ["switches", "lights"])
async def test_setup_loads_single_fire(entity_type, mock_coordinator, fake_hass):
    module = "switch" if entity_type == "switches" else "light"
    config = {
        "uid": "single-fire",
        "state_address": STATE,
        "command_address": COMMAND,
        "single_fire_command": True,
    }
    entry = MagicMock()
    entry.data = {}
    entry.options = {entity_type: [config]}
    add_entities = MagicMock()
    with patch(
        f"custom_components.s7plc.{module}.get_coordinator_and_device_info"
    ) as get:
        get.return_value = (
            mock_coordinator,
            {"identifiers": {("s7plc", "test")}},
            "test",
        )
        if module == "switch":
            from custom_components.s7plc.switch import async_setup_entry
        else:
            from custom_components.s7plc.light import async_setup_entry
        await async_setup_entry(fake_hass, entry, add_entities)
    loaded = add_entities.call_args.args[0][0]
    loaded.hass = fake_hass
    mock_coordinator.data = {loaded._topic: False}
    mock_coordinator.write_calls.clear()
    await loaded.async_turn_on()
    assert mock_coordinator.write_calls == [("write_batched", COMMAND, True)]
    assert config == {
        "uid": "single-fire",
        "state_address": STATE,
        "command_address": COMMAND,
        "single_fire_command": True,
    }


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
def test_single_fire_configuration_round_trip(entity_type):
    config = {
        "uid": "stable",
        "state_address": STATE,
        "command_address": COMMAND,
        "single_fire_command": True,
        "pulse_duration": 0.8,
    }
    original = copy.deepcopy(config)
    item, errors = build_entity_item(entity_type, config, options={})
    assert not errors
    assert item["single_fire_command"] is True
    assert not item["pulse_command"] and not item["sync_state"]
    assert "pulse_duration" not in item
    assert build_entity_item(entity_type, item, options={}) == (item, {})
    assert config == original


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize("other", ["sync_state", "pulse_command"])
def test_single_fire_rejects_conflicting_modes(entity_type, other):
    item, errors = build_entity_item(
        entity_type,
        {
            "state_address": STATE,
            "command_address": COMMAND,
            "single_fire_command": True,
            other: True,
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "single_fire_conflict"}


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize(
    "flags", [{}, {"sync_state": True}, {"pulse_command": True, "pulse_duration": 0.3}]
)
def test_existing_configurations_do_not_gain_single_fire(entity_type, flags):
    config = {"state_address": STATE, "command_address": COMMAND, **flags}
    original = copy.deepcopy(config)
    item, errors = build_entity_item(entity_type, config, options={})
    assert not errors
    assert "single_fire_command" not in item
    assert config == original
    for key, value in flags.items():
        assert item[key] == value
