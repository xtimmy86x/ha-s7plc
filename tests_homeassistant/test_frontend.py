"""The dashboard module is advertised by HA without navigating to the panel."""

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.s7plc.frontend import (
    SCHEDULE_CARD_MODULE,
    async_setup_dashboard,
)


async def test_schedule_card_loaded_on_setup_and_reload(hass, loaded_entry):
    modules = hass.data[DATA_EXTRA_MODULE_URL]
    assert SCHEDULE_CARD_MODULE in modules.urls
    await async_setup_dashboard(hass)
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert list(modules.urls).count(SCHEDULE_CARD_MODULE) == 1
