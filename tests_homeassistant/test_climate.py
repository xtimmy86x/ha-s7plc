"""Climate temperatures through Home Assistant's state and service conversion."""

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

from custom_components.s7plc.const import DOMAIN
from custom_components.s7plc.plc.address import parse_tag


@pytest.mark.parametrize("control_mode", ["direct", "setpoint"])
@pytest.mark.parametrize(
    ("units", "current", "target", "requested"),
    [(METRIC_SYSTEM, 20, 21, 25), (IMPERIAL_SYSTEM, 68, 70, 77)],
)
async def test_climate_temperature_state_and_service(
    hass,
    config_entry,
    plc_client,
    caplog,
    control_mode,
    units,
    current,
    target,
    requested,
):
    """Publish converted temperatures and pass native Celsius values to the PLC."""
    hass.config.units = units
    item = {
        "uid": "climate-native",
        "name": "Climate native",
        "control_mode": control_mode,
        "current_temperature_address": "DB1,REAL0",
        "min_temp": 7,
        "max_temp": 35,
    }
    if control_mode == "direct":
        item["heating_output_address"] = "DB1,X8.0"
    else:
        item["target_temperature_address"] = "DB1,REAL4"
    hass.config_entries.async_update_entry(config_entry, options={"climates": [item]})
    values = {parse_tag("DB1,REAL0"): 20.0, parse_tag("DB1,REAL4"): 21.0}
    plc_client.read.side_effect = lambda tags, **kwargs: [values[tag] for tag in tags]

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("climate", DOMAIN, item["uid"])
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.attributes["current_temperature"] == current
    assert state.attributes["temperature"] == target
    if "temperature_unit" in state.attributes:
        assert state.attributes["temperature_unit"] == units.temperature_unit

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, "temperature": requested},
        blocking=True,
    )
    await hass.async_block_till_done()
    if control_mode == "setpoint":
        plc_client.write.assert_awaited_once_with([parse_tag("DB1,REAL4")], [25.0])
    else:
        assert hass.states.get(entity_id).attributes["temperature"] == requested
        plc_client.write.assert_awaited_once_with([parse_tag("DB1,X8.0")], [False])
        plc_client.write.reset_mock()
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": "heat"},
            blocking=True,
        )
        await hass.async_block_till_done()
        plc_client.write.assert_awaited_once_with([parse_tag("DB1,X8.0")], [True])

    assert not [
        record
        for record in caplog.records
        if "deprecated" in record.message.lower() and "S7Climate" in record.message
    ]
