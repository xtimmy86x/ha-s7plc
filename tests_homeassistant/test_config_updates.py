"""Configuration edits preserve real HA entities and the live PLC session."""

from copy import deepcopy

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.s7plc.plc.address import parse_tag


async def test_panel_multiplier_updates_state_without_reload(
    hass, loaded_entry, plc_client, hass_ws_client
):
    entry = loaded_entry
    runtime = entry.runtime_data
    coord = runtime.coordinator
    entity = coord.config_entities["temperature"]
    revision = coord.get_topic_read_revision("sensor:DB1,INT0")
    reads = plc_client.read.await_count
    ws = await hass_ws_client(hass)
    original = dict(entry.options["sensors"][0])
    for msg_id, conversion, expected in (
        (1, {"value": {"type": "multiplier", "factor": 0.1}}, "2.1"),
        (2, {}, "21"),
    ):
        await ws.send_json(
            {
                "id": msg_id,
                "type": "s7plc/config/save_entity",
                "entry_id": entry.entry_id,
                "entity_type": "sensors",
                "index": 0,
                "entity": {**original, "value_conversions": conversion},
            }
        )
        assert (await ws.receive_json())["success"]
        await hass.async_block_till_done()
        assert entry.runtime_data is runtime
        assert coord.config_entities["temperature"] is entity
        assert hass.states.get(entity.entity_id).state == expected
    assert plc_client.read.await_count == reads
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()
    plc_client.write.assert_not_awaited()
    assert coord.get_topic_read_revision("sensor:DB1,INT0") == revision


async def test_number_conversion_metadata_and_writes_update_together(
    hass, config_entry, plc_client
):
    item = {"uid": "setpoint", "name": "Setpoint", "address": "DB1,W4"}
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
    assert hass.states.get(entity.entity_id).attributes["s7_raw_word"] is True
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "numbers": [
                {
                    **item,
                    "value_conversions": {
                        "value": {"type": "multiplier", "factor": 0.1}
                    },
                    "min_value": 0,
                    "max_value": 100,
                    "step": 0.5,
                    "mode": "box",
                }
            ]
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "2.1"
    assert {key: state.attributes[key] for key in ("min", "max", "step", "mode")} == {
        "min": 0,
        "max": 100,
        "step": 0.5,
        "mode": "box",
    }
    assert state.attributes["s7_raw_word"] is False
    plc_client.write.assert_not_awaited()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity.entity_id, "value": 7},
        blocking=True,
    )
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,W4")], [70.0])
    # Removing options must restore defaults, including HA's cached metadata.
    hass.config_entries.async_update_entry(config_entry, options={"numbers": [item]})
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.attributes["max"] == 65535
    assert state.attributes["step"] == 1
    assert state.attributes["mode"] == "auto"
    assert state.attributes["s7_raw_word"] is True
    assert config_entry.runtime_data is runtime
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()


async def test_polling_and_precision_reschedule_without_resetting_feedback(
    hass, config_entry, plc_client, freezer
):
    item = {"uid": "real", "name": "Real", "address": "DB1,R0"}
    plc_client.read.side_effect = lambda tags, **kwargs: [1.234567] * len(tags)
    hass.config_entries.async_update_entry(config_entry, options={"sensors": [item]})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    coord = runtime.coordinator
    await coord.async_refresh()
    await hass.async_start()
    await hass.async_block_till_done()
    revision = coord.get_topic_read_revision("sensor:DB1,R0")
    sample = dict(coord.data)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "sensors": [
                {
                    **item,
                    "scan_interval": 1,
                    "real_precision": 2,
                }
            ]
        },
    )
    await hass.async_block_till_done()
    assert config_entry.runtime_data is runtime
    assert coord.get_topic_read_revision("sensor:DB1,R0") == revision
    assert coord.data == sample
    assert coord.update_interval.total_seconds() == 1
    freezer.tick(2)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert coord.get_topic_read_revision("sensor:DB1,R0") > revision
    assert coord.data["sensor:DB1,R0"] == 1.23
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()


async def test_live_options_keep_disabled_connection_off(
    hass, loaded_entry, plc_client
):
    runtime = loaded_entry.runtime_data
    await runtime.coordinator.async_disable_connection()
    reads = plc_client.read.await_count
    item = loaded_entry.options["sensors"][0]
    hass.config_entries.async_update_entry(
        loaded_entry,
        options={
            "sensors": [
                {
                    **item,
                    "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
                    "scan_interval": 30,
                }
            ]
        },
    )
    await hass.async_block_till_done()
    assert loaded_entry.runtime_data is runtime
    assert not runtime.coordinator.connection_enabled
    assert plc_client.connect.await_count == 1
    assert plc_client.disconnect.await_count == 1
    assert plc_client.read.await_count == reads
    plc_client.write.assert_not_awaited()


async def test_area_assignment_updates_registry_without_reload(hass, loaded_entry):
    runtime = loaded_entry.runtime_data
    area = ar.async_get(hass).async_create("Boiler room")
    item = loaded_entry.options["sensors"][0]
    hass.config_entries.async_update_entry(
        loaded_entry, options={"sensors": [{**item, "area": area.id}]}
    )
    await hass.async_block_till_done()
    entity_id = runtime.coordinator.config_entities["temperature"].entity_id
    assert er.async_get(hass).async_get(entity_id).area_id == area.id
    assert loaded_entry.runtime_data is runtime


async def test_rapid_edits_apply_latest_configuration(hass, loaded_entry, plc_client):
    runtime = loaded_entry.runtime_data
    item = loaded_entry.options["sensors"][0]
    for factor in (2, 3):
        hass.config_entries.async_update_entry(
            loaded_entry,
            options={
                "sensors": [
                    {
                        **item,
                        "value_conversions": {
                            "value": {"type": "multiplier", "factor": factor}
                        },
                    }
                ]
            },
        )
    await hass.async_block_till_done()
    entity = runtime.coordinator.config_entities["temperature"]
    assert float(hass.states.get(entity.entity_id).state) == 63
    assert loaded_entry.runtime_data is runtime
    assert runtime.applied_options == loaded_entry.options
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()


@pytest.mark.parametrize("change", ["address", "add", "host", "enum", "mixed"])
async def test_structural_changes_reload_once(hass, loaded_entry, plc_client, change):
    runtime = loaded_entry.runtime_data
    original_entity = runtime.coordinator.config_entities["temperature"]
    options = deepcopy(dict(loaded_entry.options))
    data = dict(loaded_entry.data)
    if change == "host":
        data["host"] = "192.0.2.20"
    elif change == "address":
        options["sensors"][0]["address"] = "DB1,INT2"
    elif change == "enum":
        options["sensors"][0]["value_conversions"] = {
            "value": {"type": "enum_map", "mappings": [{"value": 21, "label": "On"}]}
        }
    elif change == "add":
        options["sensors"].append({"uid": "added", "address": "DB1,INT2"})
    else:
        options["sensors"][0]["value_conversions"] = {
            "value": {"type": "multiplier", "factor": 2}
        }
        options["numbers"] = [{"uid": "added", "address": "DB1,INT2"}]
    hass.config_entries.async_update_entry(loaded_entry, options=options, data=data)
    await hass.async_block_till_done()
    assert loaded_entry.runtime_data is not runtime
    await loaded_entry.runtime_data.coordinator.async_refresh()
    assert plc_client.connect.await_count == 2
    assert plc_client.disconnect.await_count == 1
    assert not runtime.coordinator.config_entities
    assert original_entity._value_conversion is None
