"""Cover feedback through the real Home Assistant entity lifecycle."""

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import DOMAIN


@pytest.mark.parametrize("kind", ["traditional", "position", "toggle"])
async def test_cover_status_transitions_and_reload(
    hass, config_entry, plc_client, freezer, kind
):
    item = {
        "uid": "cover-feedback",
        "name": "Feedback cover",
        "cover_position_feedback": "status",
        "cover_status_address": "DB1,W10",
        "cover_status_open_values": "0",
        "cover_status_closed_values": "1",
        "cover_status_opening_values": "2",
        "cover_status_closing_values": "3",
        "cover_status_stopped_values": "4",
        "value_conversions": {"status": {"type": "multiplier", "factor": 0.1}},
        "scan_interval": 0.25,
    }
    features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    if kind == "position":
        item["position_state_address"] = "DB1,W20"
        features |= CoverEntityFeature.SET_POSITION
    else:
        item["open_command_address"] = "DB1,X0.0"
        if kind == "toggle":
            item["toggle_mode"] = True
        else:
            item["close_command_address"] = "DB1,X0.1"
    hass.config_entries.async_update_entry(config_entry, options={"covers": [item]})
    status = 20
    plc_client.read.side_effect = lambda tags, **kwargs: [
        status if tag.start == 10 else 50 for tag in tags
    ]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "cover", DOMAIN, "cover-feedback"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "opening"
    assert hass.states.get(entity_id).attributes["supported_features"] == features

    for status, expected in [(30, "closing"), (10, "closed"), (0, "open")]:
        freezer.tick(1)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == expected
    plc_client.write.assert_not_awaited()

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "open"
    assert config_entry.options == {"covers": [item]}
    plc_client.write.assert_not_awaited()
