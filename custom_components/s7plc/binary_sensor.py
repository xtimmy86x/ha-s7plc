from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity,
    BinarySensorDeviceClass,
    BinarySensorEntityDescription
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DOMAIN
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
    }
)

async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info: DiscoveryInfoType | None = None
):
    coord = hass.data[DOMAIN]["coordinator"]
    data = hass.data[DOMAIN]
    device_id = data["device_id"]
    device_name = data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
        sw_version="snap7",
    )

    entities = []

    if CONF_ADDRESS in config:
        name = config.get(CONF_NAME, "S7 Binary Sensor")
        address = config[CONF_ADDRESS]
        topic = f"binary_sensor:{address}"
        unique_id = f"{device_id}:{topic}"

        await hass.async_add_executor_job(coord.add_item, topic, address)
        entities.append(S7BinarySensor(coord, name, unique_id, device_info, topic, address, config.get(CONF_DEVICE_CLASS)))

    # plc connecction sensor (one time)
    if not discovery_info:
        entities.append(
            PlcConnectionBinarySensor(
                coord, device_info, f"{device_id}:connection"
            )
        )

    async_add_entities(entities)
    await coord.async_request_refresh()


class S7BinarySensor(S7BaseEntity, BinarySensorEntity):
    def __init__(self, coordinator, name: str, unique_id: str, device_info: DeviceInfo, topic: str, address: str, device_class: str | None):
        super().__init__(coordinator, name=name, unique_id=unique_id, device_info=device_info, topic=topic, address=address)
        if device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(device_class)
            except Exception:
                pass

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)


class PlcConnectionBinarySensor(S7BaseEntity, BinarySensorEntity):
    ENTITY_DESC = BinarySensorEntityDescription(
        key="plc_connection",
        translation_key="plc_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    )

    def __init__(self, coordinator, device_info: DeviceInfo, unique_id: str):
        super().__init__(coordinator, name=None, unique_id=unique_id, device_info=device_info)
        self.entity_description = self.ENTITY_DESC

    @property
    def is_on(self) -> bool:
        return self._coord.is_connected()

    @property
    def available(self) -> bool:
        """Always show the sensor as available.

        When the PLC is disconnected we still want the entity present
        with state ``False`` instead of ``unavailable``.
        """
        return True