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

from .const import (
    CONF_ADDRESS,
    CONF_BINARY_SENSORS,
    CONF_DEVICE_CLASS,
    CONF_SCAN_INTERVAL,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up binary sensor entities from a config entry."""
    coord, device_info, device_id = get_coordinator_and_device_info(hass, entry)

    entities = [
        PlcConnectionBinarySensor(coord, device_info, f"{device_id}:connection")
    ]

    for item in entry.options.get(CONF_BINARY_SENSORS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), address
        )
        topic = f"binary_sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, address, scan_interval)

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
    """Binary sensor reading a boolean value from the PLC."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        device_class: str | None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )
        if device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)


class PlcConnectionBinarySensor(S7BaseEntity, BinarySensorEntity):
    """Binary sensor reporting the PLC connection status."""

    device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "plc_connection"
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info: DeviceInfo, unique_id: str):
        super().__init__(
            coordinator, name=None, unique_id=unique_id, device_info=device_info
        )
        self._plc_name = self._attr_device_info.get("name", "")

    @property
    def translation_placeholders(self) -> dict[str, str]:
        return {"plc_name": self._plc_name}

    @property
    def is_on(self) -> bool:
        return self._coord.is_connected()

    @property
    def extra_state_attributes(self):
        attrs = {}
        attrs["s7_ip"] = self._coord.host
        attrs["pys7_connection_type"] = self._coord._pys7_connection_type_str
        if self._coord.connection_type == "rack_slot":
            attrs["connection_type"] = "Rack/Slot"
            attrs["rack"] = self._coord.rack
            attrs["slot"] = self._coord.slot
        else:
            attrs["connection_type"] = "TSAP"
            attrs["local_tsap"] = self._coord.local_tsap
            attrs["remote_tsap"] = self._coord.remote_tsap
        return attrs

    @property
    def available(self) -> bool:
        return True
