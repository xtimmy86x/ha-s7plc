"""Connection control remains usable through HA when PLC reads fail."""

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import DOMAIN


async def test_offline_connection_can_be_disabled_and_stays_disabled_after_reload(
    hass, loaded_entry, plc_client, freezer, hass_storage
):
    """Dispatch a real switch service and persist its state across reload."""
    coordinator = loaded_entry.runtime_data.coordinator
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id("sensor", DOMAIN, "temperature")
    control_id = registry.async_get_entity_id(
        "switch", DOMAIN, f"{loaded_entry.runtime_data.device_id}:connection_enable"
    )
    assert hass.states.get(sensor_id).state == "21"
    assert hass.states.get(control_id).state == STATE_ON

    plc_client.read.side_effect = OSError("PLC offline")
    freezer.tick(3601)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert hass.states.get(sensor_id).state == STATE_UNAVAILABLE
    assert hass.states.get(control_id).state == STATE_ON

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": control_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(control_id).state == STATE_OFF
    assert not coordinator.connection_enabled
    assert not plc_client.is_connected
    storage_key = f"{DOMAIN}.connection_control.{loaded_entry.entry_id}"
    assert hass_storage[storage_key]["data"] == {"enabled": False}
    reads = plc_client.read.await_count
    connects = plc_client.connect.await_count

    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    await loaded_entry.runtime_data.coordinator.async_refresh()
    assert hass.states.get(control_id).state == STATE_OFF
    assert not loaded_entry.runtime_data.coordinator.connection_enabled
    assert plc_client.read.await_count == reads
    assert plc_client.connect.await_count == connects
