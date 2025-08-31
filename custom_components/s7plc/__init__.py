from __future__ import annotations

import logging
import voluptuous as vol
import re

import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, CONF_NAME,
    CONF_HOST, CONF_RACK, CONF_SLOT, CONF_PORT, CONF_SCAN_INTERVAL,
    DEFAULT_PORT, DEFAULT_RACK, DEFAULT_SLOT, DEFAULT_SCAN_INTERVAL,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_NAME, default="PLC"): cv.string,
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
    """Setup integration via YAML (s7plc:)."""
    if DOMAIN not in config:
        return True

    cfg = config[DOMAIN]
    name = cfg[CONF_NAME]
    host = cfg[CONF_HOST]
    rack = cfg[CONF_RACK]
    slot = cfg[CONF_SLOT]
    port = cfg[CONF_PORT]
    scan_s = float(cfg[CONF_SCAN_INTERVAL])

    coordinator = S7Coordinator(
        hass,
        host=host,
        rack=rack,
        slot=slot,
        port=port,
        scan_interval=scan_s,
    )

    # Connessione iniziale
    await hass.async_add_executor_job(coordinator.connect)

    # Salviamo il coordinator in hass.data
    name = cfg.get(CONF_NAME, "S7 PLC")

    # device_id stabile e unico: s7plc-<host>-<rack>-<slot>
    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    device_id = f"s7plc-{_slug(str(host))}-{rack}-{slot}"

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator
    hass.data[DOMAIN]["name"] = name
    hass.data[DOMAIN]["host"] = host
    hass.data[DOMAIN]["device_id"] = device_id

    return True
