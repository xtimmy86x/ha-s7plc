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
CONF_DEVICE_CLASS = "device_class"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default="S7 Sensor"): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
    }
)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info: DiscoveryInfoType | None = None):
    client = hass.data[DOMAIN]["client"]
    coordinator = hass.data[DOMAIN]["coordinator"]

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]
    device_class = config.get(CONF_DEVICE_CLASS)

    topic = f"sensor:{address}"
    # registra l'item nel client
    await hass.async_add_executor_job(client.add_item, topic, address)

    ent = S7Sensor(coordinator, client, name, topic, device_class)
    async_add_entities([ent])


class S7Sensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, client, name: str, topic: str, device_class: str | None):
        super().__init__(coordinator)
        self._client = client
        self._attr_name = name
        self._topic = topic
        if device_class:
            self._attr_device_class = device_class
        self._attr_unique_id = f"{topic}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get(self._topic)
