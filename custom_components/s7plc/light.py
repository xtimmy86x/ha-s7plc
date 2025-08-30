from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    LightEntity,
    ColorMode,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default="S7 Light"): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities,
    discovery_info: DiscoveryInfoType | None = None,
):
    coordinator = hass.data[DOMAIN]["coordinator"]

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]

    topic = f"light:{address}"
    await hass.async_add_executor_job(coordinator.add_item, topic, address)

    ent = S7Light(coordinator, name, topic, address)
    async_add_entities([ent])


class S7Light(CoordinatorEntity, LightEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, name: str, topic: str, address: str):
        super().__init__(coordinator)
        self._coord = coordinator
        self._attr_name = name
        self._topic = topic
        self._address = address
        self._attr_unique_id = topic

        # luce on/off
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF

    @property
    def available(self) -> bool:
        return self._coord.is_connected()

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.ONOFF

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC non connesso: impossibile eseguire il comando.")

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._coord.write_bool, self._address, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._coord.write_bool, self._address, False)
        await self.coordinator.async_request_refresh()
