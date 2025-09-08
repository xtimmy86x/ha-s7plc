from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_RACK,
    CONF_SCAN_INTERVAL,
    CONF_SLOT,
    DEFAULT_PORT,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = entry.data
    host = data[CONF_HOST]
    rack = data.get(CONF_RACK, DEFAULT_RACK)
    slot = data.get(CONF_SLOT, DEFAULT_SLOT)
    port = data.get(CONF_PORT, DEFAULT_PORT)
    scan_s = float(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    name = data.get(CONF_NAME, "S7 PLC")

    coordinator = S7Coordinator(
        hass,
        host=host,
        rack=rack,
        slot=slot,
        port=port,
        scan_interval=scan_s,
    )

    # opzionale: puoi anche rimuovere questa connect
    # e lasciare che il first_refresh la gestisca
    await hass.async_add_executor_job(coordinator.connect)

    device_id = slugify(f"s7plc-{host}-{rack}-{slot}")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "name": name,
        "host": host,
        "device_id": device_id,
        "platforms_forwarded": False,  # 👈 guard flag
    }

    # 1) Primo refresh “ufficiale” del coordinator (avvia anche il timer periodico)
    await coordinator.async_config_entry_first_refresh()

    # 2) Forward piattaforme UNA SOLA VOLTA
    store = hass.data[DOMAIN][entry.entry_id]
    if not store["platforms_forwarded"]:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        store["platforms_forwarded"] = True

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data["coordinator"].disconnect)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
