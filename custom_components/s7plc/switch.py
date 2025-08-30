from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
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
        vol.Optional(CONF_NAME, default="S7 Switch"): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info: DiscoveryInfoType | None = None
):
    client = hass.data[DOMAIN]["client"]
    coordinator = hass.data[DOMAIN]["coordinator"]

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]

    topic = f"switch:{address}"
    await hass.async_add_executor_job(client.add_item, topic, address)

    ent = S7Switch(coordinator, client, name, topic, address)
    async_add_entities([ent])


class S7Switch(CoordinatorEntity, SwitchEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, client, name: str, topic: str, address: str):
        super().__init__(coordinator)
        self._client = client
        self._attr_name = name
        self._topic = topic
        self._address = address
        self._attr_unique_id = topic

    @property
    def available(self) -> bool:
        """Entity disponibile solo se il PLC è connesso."""
        try:
            return bool(self._client.is_connected())
        except Exception:
            return False

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        val = data.get(self._topic)
        if val is None:
            return None
        return bool(val)

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC non connesso: impossibile eseguire il comando.")

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._client.write_bool, self._address, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._client.write_bool, self._address, False)
        await self.coordinator.async_request_refresh()
