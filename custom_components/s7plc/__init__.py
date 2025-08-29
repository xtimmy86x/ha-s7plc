from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN, PLATFORMS, CONF_HOST, CONF_RACK, CONF_SLOT, CONF_PORT, CONF_SCAN_INTERVAL,
    DEFAULT_PORT, DEFAULT_RACK, DEFAULT_SLOT, DEFAULT_SCAN_INTERVAL
)
from .plc_client import PlcClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_RACK, default=DEFAULT_RACK): vol.Coerce(int),
                vol.Optional(CONF_SLOT, default=DEFAULT_SLOT): vol.Coerce(int),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(float),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Setup via YAML."""
    if DOMAIN not in config:
        return True

    cfg = config[DOMAIN]
    host = cfg[CONF_HOST]
    rack = cfg[CONF_RACK]
    slot = cfg[CONF_SLOT]
    port = cfg[CONF_PORT]
    scan_s = float(cfg.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    scan_s = max(0.05, scan_s)

    client = PlcClient(host=host, rack=rack, slot=slot, port=port)
    await hass.async_add_executor_job(client.connect)

    # Coordinator: un unico poll periodico -> read_all() in executor
    async def _async_update():
        return await hass.async_add_executor_job(client.read_all)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="s7plc_coordinator",
        update_method=_async_update,
        update_interval=timedelta(seconds=scan_s),
    )

    # primo fetch per popolarsi
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["client"] = client
    hass.data[DOMAIN]["coordinator"] = coordinator

    # Carica le piattaforme dichiarate nel configuration.yaml
    for platform in PLATFORMS:
        hass.helpers.discovery.load_platform(platform, DOMAIN, {}, config)

    return True
