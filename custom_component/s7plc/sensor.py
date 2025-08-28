"""Sensor platform for the S7 integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv

from custom_component.s7plc.plc_client import PlcClient

CONF_ADDRESS = "address"
CONF_UNIT = "unit_of_measurement"
CONF_PLC = "plc"
DEFAULT_NAME = "S7 Sensor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIT): cv.string,
        vol.Optional(CONF_PLC, default={}): dict,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up S7 sensor platform."""
    plc = PlcClient(config.get(CONF_PLC, {}))
    async_add_entities(
        [S7Sensor(config[CONF_NAME], config[CONF_ADDRESS], plc, config.get(CONF_UNIT))],
        True,
    )


class S7Sensor(SensorEntity):
    """Representation of an S7 sensor entity."""

    def __init__(self, name: str, address: str, plc: PlcClient, unit: str | None):
        self._name = name
        self._address = address
        self._plc = plc
        self._unit = unit
        self._state = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def native_value(self):
        return self._state

    @property
    def native_unit_of_measurement(self):
        return self._unit

    async def async_update(self) -> None:
        value = await self.hass.async_add_executor_job(self._plc.read_address, self._address)
        self._state = value