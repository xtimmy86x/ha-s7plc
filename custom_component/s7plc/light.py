"""Light platform for the S7 integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.light import PLATFORM_SCHEMA, LightEntity
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv

from plc_client import PlcClient

CONF_ADDRESS = "address"
CONF_PLC = "plc"
DEFAULT_NAME = "S7 Light"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PLC, default={}): dict,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up S7 light platform."""
    plc = PlcClient(config.get(CONF_PLC, {}))
    async_add_entities([S7Light(config[CONF_NAME], config[CONF_ADDRESS], plc)], True)


class S7Light(LightEntity):
    """Representation of an S7 light entity."""

    def __init__(self, name: str, address: str, plc: PlcClient):
        self._name = name
        self._address = address
        self._plc = plc
        self._state = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self._plc.write_address, self._address, True)
        self._state = True

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self._plc.write_address, self._address, False)
        self._state = False

    async def async_update(self) -> None:
        value = await self.hass.async_add_executor_job(self._plc.read_address, self._address)
        self._state = bool(value)