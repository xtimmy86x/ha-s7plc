from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, CONF_BINARY_SENSORS
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    device_id = data["device_id"]
    device_name = data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
        sw_version="snap7",
    )

    device_info_diagnostics = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
        sw_version="snap7",
        
    )

    entities = [PlcConnectionBinarySensor(coord, device_info, f"{device_id}:connection")]

    for item in entry.options.get(CONF_BINARY_SENSORS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME, "S7 Binary Sensor")
        topic = f"binary_sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        await hass.async_add_executor_job(coord.add_item, topic, address)

        entities.append(
            S7BinarySensor(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                device_class,
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
            except Exception:  # pylint: disable=broad-except
                _LOGGER.warning("Invalid device class %s", device_class)

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)


class PlcConnectionBinarySensor(S7BaseEntity, BinarySensorEntity):
    device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "plc_connection"
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info: DeviceInfo, unique_id: str):
        super().__init__(coordinator, name=None, unique_id=unique_id, device_info=device_info)
        self._plc_name = self.device_info.get("name", "")
    
    @property 
    def translation_placeholders(self) -> dict[str, str]:
        return {"plc_name": self._plc_name}

    @property
    def is_on(self) -> bool:
        return self._coord.is_connected()

    @property
    def available(self) -> bool:
        return True