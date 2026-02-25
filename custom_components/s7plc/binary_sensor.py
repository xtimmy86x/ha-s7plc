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
    CONF_AREA,
    CONF_BINARY_SENSORS,
    CONF_DEVICE_CLASS,
    CONF_INVERT_STATE,
    CONF_SCAN_INTERVAL,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

# Coordinator is used to centralize data updates
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up binary sensor entities from a config entry."""
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

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
        area = item.get(CONF_AREA)
        topic = f"binary_sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        invert_state = item.get(CONF_INVERT_STATE, False)
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
                invert_state,
                area,
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
        invert_state: bool = False,
        suggested_area_id: str | None = None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
            suggested_area_id=suggested_area_id,
        )
        self._invert_state = invert_state
        if device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        if val is None:
            return None
        result = bool(val)
        return not result if self._invert_state else result


class PlcConnectionBinarySensor(S7BaseEntity, BinarySensorEntity):
    """Binary sensor reporting the PLC connection status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "plc_connection"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        return self.coordinator.is_connected()

    @property
    def extra_state_attributes(self):
        attrs = {}
        attrs["s7_ip"] = self.coordinator.host
        attrs["pys7_connection_type"] = self.coordinator._pys7_connection_type_str
        if self.coordinator.connection_type == "rack_slot":
            attrs["connection_type"] = "Rack/Slot"
            attrs["rack"] = self.coordinator.rack
            attrs["slot"] = self.coordinator.slot
        else:
            attrs["connection_type"] = "TSAP"
            attrs["local_tsap"] = self.coordinator.local_tsap
            attrs["remote_tsap"] = self.coordinator.remote_tsap

        # Health probe results
        attrs["last_health_ok"] = self.coordinator.last_health_ok
        attrs["last_health_latency_s"] = self.coordinator.last_health_latency

        # Error diagnostics
        if self.coordinator.last_error_category:
            attrs["last_error_category"] = self.coordinator.last_error_category
            attrs["last_error_message"] = self.coordinator.last_error_message

        error_counts = self.coordinator.error_count_by_category
        if error_counts:
            attrs["error_counts"] = error_counts
            attrs["total_errors"] = sum(error_counts.values())

        return attrs

    @property
    def available(self) -> bool:
        return True
