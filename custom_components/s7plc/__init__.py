from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_NAME,
    CONF_HOST,
    CONF_RACK,
    CONF_SLOT,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_RACK,
    DEFAULT_SLOT,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up S7 PLC from a config entry."""
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

    await hass.async_add_executor_job(coordinator.connect)

    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    device_id = f"s7plc-{_slug(str(host))}-{rack}-{slot}"

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "name": name,
        "host": host,
        "device_id": device_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data["coordinator"].disconnect)
    return unload_ok
