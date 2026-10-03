"""Single-fire mode through HA platforms and service dispatch, with the real coordinator."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import CONF_ENABLE_WRITE_BATCHING, DOMAIN
from custom_components.s7plc.plc.address import parse_tag


@pytest.mark.parametrize("platform", ["switch", "light"])
@pytest.mark.parametrize("initial", [False, True], ids=["turn-on", "turn-off"])
async def test_single_fire_service_and_reload(
    hass, config_entry, plc_client, freezer, platform, initial
):
    config = {
        "uid": "single-fire",
        "name": "Single fire",
        "state_address": "DB1,X4.0",
        "command_address": "DB1,X4.1",
        "single_fire_command": True,
    }
    entity_type = "lights" if platform == "light" else "switches"
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ENABLE_WRITE_BATCHING: False},
        options={entity_type: [config]},
    )
    plc_client.read.side_effect = lambda tags, **kwargs: [int(initial)] * len(tags)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, "single-fire")
    assert hass.states.get(entity_id).state == (STATE_ON if initial else STATE_OFF)
    assert hass.states.get(entity_id).attributes["single_fire_command"] is True
    plc_client.write.reset_mock()

    # An already satisfied request must never toggle the PLC.
    await hass.services.async_call(
        platform,
        "turn_on" if initial else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    plc_client.write.assert_not_awaited()
    await hass.services.async_call(
        platform,
        "turn_off" if initial else "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,X4.1")], [True])

    # PLC feedback changes the displayed state; config reload retains the mode.
    plc_client.read.side_effect = lambda tags, **kwargs: [int(not initial)] * len(tags)
    freezer.tick(3601)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == (STATE_OFF if initial else STATE_ON)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    plc_client.write.reset_mock()
    await hass.services.async_call(
        platform,
        "turn_on" if initial else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    plc_client.write.assert_awaited_once_with([parse_tag("DB1,X4.1")], [True])
    assert config_entry.options == {
        f"{platform}s" if platform == "light" else "switches": [config]
    }
