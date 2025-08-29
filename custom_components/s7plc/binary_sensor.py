from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default="S7 Binary Sensor"): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
    }
)

async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info: DiscoveryInfoType | None = None):
    client = hass.data[DOMAIN]["client"]
    coordinator = hass.data[DOMAIN]["coordinator"]

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]
    device_class = config.get(CONF_DEVICE_CLASS)

    topic = f"binary_sensor:{address}"
    await hass.async_add_executor_job(client.add_item, topic, address)

    ent = S7BinarySensor(coordinator, name, topic, device_class)
    async_add_entities([ent])

class S7BinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, name: str, topic: str, device_class: str | None):
        super().__init__(coordinator)
        self._attr_name = name
        self._topic = topic
        self._attr_unique_id = topic
        if device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(device_class)
            except Exception:
                # se non è tra quelli previsti, lo omettiamo senza rompere
                pass

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        val = data.get(self._topic)
        if val is None:
            return None
        # assicuriamoci di restituire proprio un bool
        return bool(val)
