"""Live metadata edits through real HA registries, states and number services."""

from copy import deepcopy
from datetime import timedelta

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.helpers import (
    DEVICE_CLASS_DEFAULT_UNITS,
    device_class_values,
)
from custom_components.s7plc.plc.address import parse_tag


def test_default_numeric_metadata_is_compatible_with_home_assistant():
    """Every provided numeric default must pass upstream unit/class rules."""
    for entity_type in ("sensors", "numbers"):
        for device_class in device_class_values(entity_type):
            if device_class in {"enum", "date", "timestamp"}:
                continue
            if device_class.upper() not in DEVICE_CLASS_DEFAULT_UNITS:
                continue
            item, errors = build_entity_item(
                entity_type,
                {"address": "DB1,INT0", "device_class": device_class},
                options={},
            )
            assert not errors, (entity_type, device_class, errors)
            assert item["device_class"] == device_class


@pytest.mark.parametrize(
    "entity_type,item,error",
    [
        (
            "numbers",
            {
                "address": "DB1,INT0",
                "device_class": "temperature",
                "unit_of_measurement": "bar",
            },
            "invalid_unit_of_measurement",
        ),
        (
            "numbers",
            {"address": "DB1,TIME0", "unit_of_measurement": "min"},
            "invalid_unit_of_measurement",
        ),
        (
            "sensors",
            {"address": "DB1,TIME0", "device_class": "temperature"},
            "invalid_device_class",
        ),
        (
            "sensors",
            {"address": "DB1,C0", "state_class": "measurement"},
            "invalid_state_class",
        ),
        (
            "sensors",
            {"address": "DB1,C0", "unit_of_measurement": "°C"},
            "invalid_unit_of_measurement",
        ),
        (
            "sensors",
            {"address": "DB1,C0", "device_class": "temperature"},
            "invalid_device_class",
        ),
        (
            "sensors",
            {"address": "DB1,INT0", "state_class": "invalid"},
            "invalid_state_class",
        ),
        (
            "binary_sensors",
            {"address": "DB1,X0.0", "device_class": "temperature"},
            "invalid_device_class",
        ),
    ],
)
def test_metadata_validation_checks_the_plc_and_entity_type(entity_type, item, error):
    result, errors = build_entity_item(entity_type, item, options={})
    assert result is None
    assert errors == {"base": error}


async def test_sensor_metadata_and_unit_preferences_update_without_reload(
    hass, loaded_entry, plc_client, hass_ws_client
):
    entry = loaded_entry
    runtime = entry.runtime_data
    coord = runtime.coordinator
    entity = coord.config_entities["temperature"]
    original = dict(entry.options["sensors"][0])
    registry = er.async_get(hass)
    preferences = {"unit_of_measurement": "°F", "display_precision": 2}
    registry.async_update_entity_options(entity.entity_id, "sensor", preferences)
    await hass.async_block_till_done()
    reads = plc_client.read.await_count
    revision = coord.get_topic_read_revision(entity._topic)
    ws = await hass_ws_client(hass)
    for msg_id, (metadata, expected_value, expected_unit, expected_class) in enumerate(
        [
            ({"device_class": "temperature"}, 69.8, "°F", "measurement"),
            (
                {"device_class": "temperature", "unit_of_measurement": "°F"},
                21,
                "°F",
                "measurement",
            ),
            (
                {
                    "device_class": "pressure",
                    "unit_of_measurement": "kPa",
                    "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
                },
                42,
                "kPa",
                "measurement",
            ),
            ({"device_class": "temperature", "state_class": "none"}, 69.8, "°F", None),
            ({"device_class": "temperature"}, 69.8, "°F", "measurement"),
            ({"device_class": "energy"}, 21, "kWh", "total_increasing"),
            ({"device_class": "energy_storage"}, 21, "kWh", "measurement"),
            (
                {"unit_of_measurement": "RPM", "state_class": "measurement"},
                21,
                "RPM",
                "measurement",
            ),
            ({}, 21, None, None),
        ],
        start=1,
    ):
        await ws.send_json(
            {
                "id": msg_id,
                "type": "s7plc/config/save_entity",
                "entry_id": entry.entry_id,
                "entity_type": "sensors",
                "index": 0,
                "entity": {**original, **metadata},
            }
        )
        assert (await ws.receive_json())["success"]
        await hass.async_block_till_done()
        state = hass.states.get(entity.entity_id)
        assert float(state.state) == pytest.approx(expected_value)
        assert state.attributes.get("unit_of_measurement") == expected_unit
        assert state.attributes.get("state_class") == expected_class
        assert state.attributes.get("device_class") == metadata.get("device_class")
        registered = registry.async_get(entity.entity_id)
        assert registered.original_device_class == metadata.get("device_class")
        assert {
            key: registered.options["sensor"][key] for key in preferences
        } == preferences
        assert (registered.capabilities or {}).get("state_class") == expected_class
        assert entry.runtime_data is runtime
        assert coord.config_entities["temperature"] is entity
    assert plc_client.read.await_count == reads
    assert coord.get_topic_read_revision(entity._topic) == revision
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()
    plc_client.write.assert_not_awaited()


async def test_number_metadata_refreshes_display_bounds_and_command_units(
    hass, config_entry, plc_client
):
    item = {
        "uid": "setpoint",
        "name": "Setpoint",
        "address": "DB1,INT0",
        "min_value": 0,
        "max_value": 100,
        "step": 1,
    }
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, "enable_write_batching": False},
        options={"numbers": [item]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    await runtime.coordinator.async_refresh()
    entity = runtime.coordinator.config_entities["setpoint"]
    registry = er.async_get(hass)
    preferences = {"unit_of_measurement": "°F"}
    registry.async_update_entity_options(entity.entity_id, "number", preferences)
    await hass.async_block_till_done()
    for metadata, unit, bounds, command, raw in [
        ({"device_class": "temperature"}, "°F", (32, 212), 95, 35),
        (
            {"device_class": "pressure", "unit_of_measurement": "bar"},
            "bar",
            (0, 100),
            2,
            2,
        ),
        ({"device_class": "temperature"}, "°F", (32, 212), 68, 20),
        ({}, None, (0, 100), 3, 3),
    ]:
        reads, writes = plc_client.read.await_count, plc_client.write.await_count
        hass.config_entries.async_update_entry(
            config_entry, options={"numbers": [{**item, **metadata}]}
        )
        await hass.async_block_till_done()
        state = hass.states.get(entity.entity_id)
        assert state.attributes.get("unit_of_measurement") == unit
        assert (state.attributes["min"], state.attributes["max"]) == bounds
        assert plc_client.read.await_count == reads
        assert plc_client.write.await_count == writes
        assert registry.async_get(entity.entity_id).options["number"] == preferences
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity.entity_id, "value": command},
            blocking=True,
        )
        plc_client.write.assert_awaited_with([parse_tag("DB1,INT0")], [raw])
        assert config_entry.runtime_data is runtime
        assert runtime.coordinator.config_entities["setpoint"] is entity
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()


@pytest.mark.parametrize(
    "entity_type,item,device_class",
    [
        ("binary_sensors", {"address": "DB1,X0.0"}, "door"),
        ("covers", {"position_state_address": "DB1,INT0"}, "blind"),
        (
            "covers",
            {
                "open_command_address": "DB1,X0.0",
                "close_command_address": "DB1,X0.1",
                "position_feedback": "both",
                "opening_state_address": "DB1,X0.2",
                "closing_state_address": "DB1,X0.3",
            },
            "shutter",
        ),
    ],
)
async def test_device_class_changes_preserve_other_platforms(
    hass, config_entry, plc_client, entity_type, item, device_class
):
    item = {"uid": "entity", "name": "Test", **item}
    hass.config_entries.async_update_entry(config_entry, options={entity_type: [item]})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    await runtime.coordinator.async_refresh()
    entity = runtime.coordinator.config_entities["entity"]
    initial_state = hass.states.get(entity.entity_id).state
    reads = plc_client.read.await_count
    for metadata in ({"device_class": device_class}, {}):
        hass.config_entries.async_update_entry(
            config_entry, options={entity_type: [{**item, **metadata}]}
        )
        await hass.async_block_till_done()
        state = hass.states.get(entity.entity_id)
        assert state.state == initial_state
        assert state.attributes.get("device_class") == metadata.get("device_class")
        assert config_entry.runtime_data is runtime
        assert runtime.coordinator.config_entities["entity"] is entity
    assert plc_client.read.await_count == reads
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()
    plc_client.write.assert_not_awaited()


async def test_time_state_class_none_preserves_seconds(hass, config_entry, plc_client):
    item = {"uid": "timer", "address": "DB1,TIME0"}
    plc_client.read.side_effect = lambda tags, **kwargs: [timedelta(seconds=21)] * len(
        tags
    )
    hass.config_entries.async_update_entry(config_entry, options={"sensors": [item]})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    await runtime.coordinator.async_refresh()
    entity = runtime.coordinator.config_entities["timer"]
    hass.config_entries.async_update_entry(
        config_entry, options={"sensors": [{**item, "state_class": "none"}]}
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert float(state.state) == 21
    assert state.attributes["unit_of_measurement"] == "s"
    assert state.attributes["device_class"] == "duration"
    assert "state_class" not in state.attributes
    assert config_entry.runtime_data is runtime


@pytest.mark.parametrize("whole_configuration", [False, True])
@pytest.mark.parametrize(
    "metadata,error",
    [
        ({"device_class": "unknown"}, "invalid_device_class"),
        (
            {"device_class": "temperature", "unit_of_measurement": "bar"},
            "invalid_unit_of_measurement",
        ),
        (
            {"device_class": "temperature", "state_class": "total_increasing"},
            "invalid_state_class",
        ),
        ({"device_class": "enum"}, "invalid_device_class"),
        ({"device_class": "timestamp"}, "invalid_device_class"),
    ],
)
async def test_invalid_metadata_is_rejected_before_saving(
    hass,
    loaded_entry,
    hass_ws_client,
    plc_client,
    whole_configuration,
    metadata,
    error,
):
    import json

    entry = loaded_entry
    runtime = entry.runtime_data
    original = deepcopy(dict(entry.options))
    item = {**original["sensors"][0], **metadata}
    ws = await hass_ws_client(hass)
    message = {"id": 1, "entry_id": entry.entry_id}
    if whole_configuration:
        # A valid edit before an invalid entity must not be partially persisted.
        valid = {**original["sensors"][0], "state_class": "measurement"}
        invalid = {**item, "uid": "other", "address": "DB1,INT2"}
        message.update(
            {
                "type": "s7plc/config/save_configuration",
                "configuration_yaml": json.dumps({"sensors": [valid, invalid]}),
            }
        )
    else:
        message.update(
            {
                "type": "s7plc/config/save_entity",
                "entity_type": "sensors",
                "index": 0,
                "entity": item,
            }
        )
    await ws.send_json(message)
    response = await ws.receive_json()
    assert not response["success"]
    assert error in response["error"]["message"]
    await hass.async_block_till_done()
    assert entry.options == original
    assert entry.runtime_data is runtime
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()
    plc_client.write.assert_not_awaited()
