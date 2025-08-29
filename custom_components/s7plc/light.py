from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    LightEntity,
    ColorMode,          # <— importa ColorMode
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default="S7 Light"): cv.string,
    }
)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info: DiscoveryInfoType | None = None):
    client = hass.data[DOMAIN]["client"]
    coordinator = hass.data[DOMAIN]["coordinator"]

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]

    topic = f"light:{address}"
    await hass.async_add_executor_job(client.add_item, topic, address)

    ent = S7Light(coordinator, client, name, topic, address)
    async_add_entities([ent])


class S7Light(CoordinatorEntity, LightEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, client, name: str, topic: str, address: str):
        super().__init__(coordinator)
        self._client = client
        self._attr_name = name
        self._topic = topic
        self._address = address
        self._attr_unique_id = f"{topic}"

        # >>>> fix richiesto da HA: dichiara i color modes supportati
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        # (nessuna feature extra)
        self._attr_supported_features = 0

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        if val is None:
            return None
        return bool(val)

    @property
    def color_mode(self) -> ColorMode | None:
        # fisso: è una luce on/off
        return ColorMode.ONOFF

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._client.write_bool, self._address, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._client.write_bool, self._address, False)
        await self.coordinator.async_request_refresh()
