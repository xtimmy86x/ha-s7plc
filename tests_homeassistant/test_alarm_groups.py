"""Alarm groups on the M flag area through Home Assistant's real entity lifecycle."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import DOMAIN


async def test_last_alarm_sequence_publishes_attributes_and_cancels_on_unload(
    hass, config_entry, plc_client, merker_group, monkeypatch
):
    """Only the timer is controlled; HA entity writes and unloading are real."""
    timers = []

    def later(hass, delay, action):
        cancel = Mock()
        timers.append((delay, action, cancel))
        return cancel

    monkeypatch.setattr("custom_components.s7plc.sensor.async_call_later", later)
    plc_client.read.side_effect = lambda tags, **kwargs: [
        (7, 0) if tag.memory_area.name == "MERKER" and tag.length == 2 else 21
        for tag in tags
    ]
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "alarm_groups": [merker_group]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    count_id = registry.async_get_entity_id("sensor", DOMAIN, "flags")
    presence_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "flags:active")
    assert hass.states.get(count_id).attributes["last_alarm"] == "M8.0"
    assert "last_alarm" not in hass.states.get(presence_id).attributes
    for expected in ("Valve low", "M8.2"):
        delay, action, _ = timers[-1]
        assert delay == 2
        action(datetime.now(timezone.utc))
        await hass.async_block_till_done()
        state = hass.states.get(count_id)
        assert state.state == "3"
        assert state.attributes["last_alarm"] == expected

    assert len(timers) == 3
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    timers[-1][2].assert_called_once_with()


@pytest.fixture
def merker_group():
    return {
        "uid": "flags",
        "name": "Boiler flags",
        "start_address": "M8.0",
        "end_address": "M9.7",
        "active_value": 1,
        "alarms": [
            {"address": "M8.1", "description": "Valve low", "enabled": True},
            {"address": "M8.6", "description": "Reserved", "enabled": False},
        ],
    }


def _read_bytes(tags, **kwargs):
    """Answer M8 and M9 as one two byte block, other tags with a scalar."""
    values = []
    for tag in tags:
        if tag.memory_area.name == "MERKER" and tag.length == 2:
            # M8.1 and M8.6 set in MB8, M9.7 set in MB9.
            values.append((0b01000010, 0b10000000))
        else:
            values.append(21)
    return values


async def test_merker_alarm_group_entities_follow_plc_bits(
    hass, config_entry, plc_client, merker_group
):
    """Create both entities from an M range and report only included active bits."""
    plc_client.read.side_effect = _read_bytes
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "alarm_groups": [merker_group]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    count_id = registry.async_get_entity_id("sensor", DOMAIN, "flags")
    presence_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "flags:active")
    assert count_id is not None
    assert presence_id is not None

    count = hass.states.get(count_id)
    # M8.6 is excluded, so only M8.1 and M9.7 are counted.
    assert count.state == "2"
    assert count.attributes["start_address"] == "M8.0"
    assert count.attributes["end_address"] == "M9.7"
    assert count.attributes["active_alarms"] == [
        {"address": "M8.1", "description": "Valve low"},
        {"address": "M9.7", "description": "M9.7"},
    ]
    assert hass.states.get(presence_id).state == "on"

    # One shared block read of the merker area, not one read per bit.
    block_reads = [
        tag
        for call in plc_client.read.await_args_list
        for tag in call.args[0]
        if tag.memory_area.name == "MERKER" and tag.length == 2
    ]
    assert block_reads
    assert {(tag.start, tag.length) for tag in block_reads} == {(8, 2)}


async def test_merker_alarm_group_clears_when_bits_drop(
    hass, config_entry, plc_client, merker_group
):
    """Turn the presence sensor off again once every included bit is inactive."""
    plc_client.read.side_effect = _read_bytes
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "alarm_groups": [merker_group]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    count_id = registry.async_get_entity_id("sensor", DOMAIN, "flags")
    presence_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "flags:active")
    assert hass.states.get(presence_id).state == "on"

    def quiet(tags, **kwargs):
        return [
            (0, 0) if tag.memory_area.name == "MERKER" and tag.length == 2 else 21
            for tag in tags
        ]

    plc_client.read.side_effect = quiet
    for topic in list(coordinator._item_next_read):
        coordinator._item_next_read[topic] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count_id).state == "0"
    assert hass.states.get(count_id).attributes["active_alarms"] == []
    assert hass.states.get(presence_id).state == "off"


async def test_merker_alarm_group_entity_names(
    hass, config_entry, plc_client, merker_group
):
    """Name both entities after the configured group."""
    plc_client.read.side_effect = _read_bytes
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "alarm_groups": [merker_group]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    count_id = registry.async_get_entity_id("sensor", DOMAIN, "flags")
    presence_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "flags:active")
    assert registry.async_get(count_id).original_name == "Boiler flags"
    assert registry.async_get(presence_id).original_name == "Boiler flags"
    assert hass.states.get(count_id).name.endswith("Boiler flags")
    assert hass.states.get(presence_id).name.endswith("Boiler flags")


@pytest.mark.parametrize(
    "block",
    [
        21,
        (1,),
        (256, 0),
        (-1, 0),
        (True, False),
        ("a", "b"),
        None,
    ],
    ids=["scalar", "short", "above-byte", "negative", "bool", "text", "none"],
)
async def test_merker_alarm_group_unavailable_for_missing_or_invalid_block(
    hass, config_entry, plc_client, merker_group, block
):
    """Never report zero alarms or off when the sampled block cannot be decoded."""

    def invalid(tags, **kwargs):
        return [
            block if tag.memory_area.name == "MERKER" and tag.length == 2 else 21
            for tag in tags
        ]

    plc_client.read.side_effect = invalid
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "alarm_groups": [merker_group]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    count_id = registry.async_get_entity_id("sensor", DOMAIN, "flags")
    presence_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "flags:active")
    assert hass.states.get(count_id).state == "unavailable"
    assert hass.states.get(presence_id).state == "unavailable"
