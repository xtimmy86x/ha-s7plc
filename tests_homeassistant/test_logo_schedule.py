"""An HHMM dashboard command reaches PLC transport as exactly one BCD WORD."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import CONF_ENABLE_WRITE_BATCHING, DOMAIN
from custom_components.s7plc.plc.address import parse_tag


async def test_logo_clock_ha_state_metadata_and_service(
    hass, config_entry, plc_client, freezer
):
    item, errors = build_entity_item(
        "numbers",
        {
            "name": "Schedule start",
            "address": "DB1,WORD4",
            "value_conversions": {"value": {"type": "logo_time_bcd"}},
        },
        options={},
    )
    assert not errors
    item["uid"] = "schedule-start"
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ENABLE_WRITE_BATCHING: False},
        options={"numbers": [item]},
    )
    clock = 0x0400
    plc_client.read.side_effect = lambda tags, **kwargs: [clock] * len(tags)

    async def write(tags, values):
        nonlocal clock
        clock = values[0]

    plc_client.write.side_effect = write
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, "schedule-start")
    state = hass.states.get(entity_id)
    assert float(state.state) == 400
    assert state.attributes["s7_time_format"] == "hhmm"
    assert state.attributes["s7_raw_word"] is False
    plc_client.write.assert_not_awaited()

    # The same numeric payload sent by the card in HHMM mode.
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 2359}, blocking=True
    )
    await hass.async_block_till_done()
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,WORD4")], [0x2359])
    freezer.tick(3601)
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == 2359

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": 1260}, blocking=True
        )
    assert plc_client.write.await_count == 1
