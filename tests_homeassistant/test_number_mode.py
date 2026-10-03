"""Display mode metadata is exposed by real HA without changing PLC writes."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import CONF_ENABLE_WRITE_BATCHING, DOMAIN
from custom_components.s7plc.plc.address import parse_tag


@pytest.mark.parametrize("mode", [None, "auto", "box", "slider"])
async def test_number_mode_state_and_write(hass, config_entry, plc_client, mode):
    item = {
        "name": "Setpoint",
        "uid": "setpoint",
        "address": "DB1,INT4",
        "min_value": 0,
        "max_value": 30,
        "step": 1,
    }
    if mode is not None:
        item["mode"] = mode
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ENABLE_WRITE_BATCHING: False},
        options={"numbers": [item]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, "setpoint")
    state = hass.states.get(entity_id)
    assert state.attributes["mode"] == (mode or "auto")
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == 30
    assert state.attributes["step"] == 1
    plc_client.write.assert_not_awaited()
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 7}, blocking=True
    )
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,INT4")], [7.0])
