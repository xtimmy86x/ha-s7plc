from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
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
        vol.Optional(CONF_NAME, default="S7 Sensor"): cv.string,
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

    topic = f"sensor:{address}"
    await hass.async_add_executor_job(coordinator.add_item, topic, address)

    ent = S7Sensor(coordinator, name, topic, address)
    async_add_entities([ent])


class S7Sensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, name: str, topic: str, address: str):
        super().__init__(coordinator)
        self._coord = coordinator
        self._attr_name = name
        self._topic = topic
        self._address = address
        self._attr_unique_id = topic

    @property
    def available(self) -> bool:
        """Disponibile solo se il PLC è connesso."""
        return self._coord.is_connected()

    @property
    def native_value(self):
        """Restituisce il valore numerico letto dal PLC."""
        val = (self.coordinator.data or {}).get(self._topic)
        return val
