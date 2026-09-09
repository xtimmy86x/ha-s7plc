"""Exercise config-entry lifecycle using the real HA loader and platforms."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.s7plc.const import DOMAIN


async def test_setup_reload_unload(hass, config_entry, plc_client, freezer):
    """Reload replaces runtime data without duplicating registered entities."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id("sensor", DOMAIN, "temperature")
    assert sensor_id is not None
    assert hass.states.get(sensor_id).state == "21"
    assert plc_client.connect.await_count == 1
    await hass.async_start()
    await hass.async_block_till_done()
    original_runtime = config_entry.runtime_data
    registered = {
        entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    assert hass.services.has_service(DOMAIN, "health_check")
    assert hass.services.has_service(DOMAIN, "write_multi")

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is not original_runtime
    assert plc_client.disconnect.await_count == 1
    assert plc_client.connect.await_count == 2
    assert hass.states.get(sensor_id).state == "21"
    assert {
        entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    } == registered

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(config_entry, "runtime_data")
    assert plc_client.disconnect.await_count == 2
    assert not plc_client.is_connected
    # HA retains registry-backed placeholders after platform unload.
    assert all(
        hass.states.get(entity_id).state == STATE_UNAVAILABLE
        for entity_id in registered
    )
    assert not hass.services.has_service(DOMAIN, "health_check")
    assert not hass.services.has_service(DOMAIN, "write_multi")

    reads = plc_client.read.await_count
    connects = plc_client.connect.await_count
    freezer.tick(3601)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert plc_client.read.await_count == reads
    assert plc_client.connect.await_count == connects
