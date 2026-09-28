"""Restore displayed PLC readings through HA's real storage and entity lifecycle."""

from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state

from custom_components.s7plc.const import DOMAIN


@pytest.mark.parametrize(
    ("platform", "category", "item", "value"),
    [
        ("sensor", "sensors", {"address": "DB1,REAL0"}, 21.5),
        ("sensor", "sensors", {"address": "DB1,TIME0"}, timedelta(seconds=3.5)),
        ("number", "numbers", {"address": "DB1,INT0"}, 0),
        (
            "number",
            "numbers",
            {
                "address": "DB1,WORD0",
                "value_conversions": {"value": {"type": "logo_time_bcd"}},
            },
            0x1234,
        ),
        (
            "binary_sensor",
            "binary_sensors",
            {"address": "DB1,X0.0", "invert_state": True},
            False,
        ),
        (
            "switch",
            "switches",
            {
                "state_address": "DB1,X0.0",
                "command_address": "DB1,X0.1",
                "sync_state": True,
            },
            False,
        ),
        ("text", "texts", {"address": "DB1,STRING0.20"}, ""),
        (
            "select",
            "selects",
            {
                "address": "DB1,INT0",
                "options_map": "0:Off;21:Heating",
                "sync_state": True,
                "command_address": "DB1,INT2",
            },
            21,
        ),
        (
            "light",
            "lights",
            {"state_address": "DB1,X0.0", "brightness_state_address": "DB1,BYTE2"},
            80,
        ),
        (
            "cover",
            "covers",
            {"position_state_address": "DB1,INT0", "tilt_state_address": "DB1,INT2"},
            40,
        ),
        (
            "cover",
            "covers",
            {
                "open_command_address": "DB1,X0.0",
                "close_command_address": "DB1,X0.1",
                "position_feedback": "both",
                "opening_state_address": "DB1,X0.2",
                "closing_state_address": "DB1,X0.3",
            },
            False,
        ),
        (
            "cover",
            "covers",
            {
                "open_command_address": "DB1,X0.0",
                "close_command_address": "DB1,X0.1",
                "position_feedback": "timed",
            },
            False,
        ),
        (
            "climate",
            "climates",
            {
                "control_mode": "direct",
                "current_temperature_address": "DB1,REAL0",
                "heating_output_address": "DB1,X4.0",
            },
            21,
        ),
        (
            "climate",
            "climates",
            {
                "control_mode": "setpoint",
                "current_temperature_address": "DB1,REAL0",
                "target_temperature_address": "DB1,REAL4",
            },
            21,
        ),
    ],
)
async def test_restore_while_connection_disabled(
    hass, config_entry, plc_client, hass_storage, platform, category, item, value
):
    """JSON roundtrip, two offline starts and fresh feedback across entity types."""
    item = {
        **item,
        "uid": "restore-test",
        "name": "Restore test",
        "availability_mode": "always",
    }
    hass.config_entries.async_update_entry(config_entry, options={category: [item]})
    plc_client.read.side_effect = lambda tags, **kwargs: [value] * len(tags)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, "restore-test")
    assert entity_id is not None
    restore_data = restore_state.async_get(hass)
    entity = restore_data.entities[entity_id]
    if platform == "cover" and item.get("position_feedback") == "timed":
        entity._assumed_closed = True
        entity.async_write_ha_state()
    original = hass.states.get(entity_id)
    # A between-end-stops cover is legitimately unknown.
    if not (platform == "cover" and item.get("position_feedback") == "both"):
        assert original.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)

    control_id = registry.async_get_entity_id(
        "switch", DOMAIN, f"{config_entry.runtime_data.device_id}:connection_enable"
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": control_id}, blocking=True
    )
    await hass.async_block_till_done()
    reads = plc_client.read.await_count
    connects = plc_client.connect.await_count

    for _ in range(2):
        await restore_data.async_dump_states()
        assert "core.restore_state" in hass_storage
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
        # Discard in-memory snapshots and load the JSON storage, as on restart.
        restore_data.last_states.clear()
        await restore_data.async_load()
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        coordinator = config_entry.runtime_data.coordinator
        assert coordinator.data == {}
        assert coordinator._data_cache == {}
        restored = hass.states.get(entity_id)
        assert restored.state == original.state
        assert restored.attributes == original.attributes
        assert plc_client.read.await_count == reads
        assert plc_client.connect.await_count == connects
        plc_client.write.assert_not_awaited()

    if platform == "select":
        new_value = 0
    elif isinstance(value, bool):
        new_value = not value
    elif isinstance(value, str):
        new_value = "Updated"
    elif isinstance(value, timedelta):
        new_value = value + timedelta(seconds=1)
    else:
        new_value = value + 1
    plc_client.read.side_effect = lambda tags, **kwargs: [new_value] * len(tags)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": control_id}, blocking=True
    )
    await hass.async_block_till_done()
    entity = restore_data.entities[entity_id]
    if entity._restorable_topics:
        assert plc_client.read.await_count > reads
        for topic in entity._restored_values:
            assert entity._state_data[topic] == coordinator.data[topic]
    assert not entity._has_restored_feedback
    plc_client.write.assert_not_awaited()


async def test_restore_when_enabled_plc_is_unreachable(
    hass, config_entry, plc_client, hass_storage
):
    """A failed read must not hide the saved value of an always-available sensor."""
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "sensors": [
                {
                    "uid": "offline",
                    "address": "DB1,REAL0",
                    "availability_mode": "always",
                }
            ]
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, "offline")
    original = hass.states.get(entity_id).state
    assert original == "21"
    restore_data = restore_state.async_get(hass)
    await restore_data.async_dump_states()
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    restore_data.last_states.clear()
    await restore_data.async_load()
    plc_client.connect.side_effect = OSError("PLC offline")
    plc_client.read.side_effect = OSError("PLC offline")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not config_entry.runtime_data.coordinator.last_update_success
    assert hass.states.get(entity_id).state == original
    plc_client.write.assert_not_awaited()
