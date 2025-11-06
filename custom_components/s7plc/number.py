from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .address import get_numeric_limits, parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_SCAN_INTERVAL,
    CONF_STEP,
    DOMAIN,
)
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    device_id = data["device_id"]
    device_name = data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
    )

    entities: list[S7Number] = []
    for item in entry.options.get(CONF_NUMBERS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME, "S7 Number")
        topic = f"number:{address}"
        unique_id = f"{device_id}:{topic}"
        command_address = item.get(CONF_COMMAND_ADDRESS) or address
        min_value = item.get(CONF_MIN_VALUE)
        max_value = item.get(CONF_MAX_VALUE)
        step = item.get(CONF_STEP)

        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await hass.async_add_executor_job(coord.add_item, topic, address, scan_interval)
        entities.append(
            S7Number(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                command_address,
                min_value,
                max_value,
                step,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Number(S7BaseEntity, NumberEntity):
    """Number entity representing a numeric PLC address."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        command_address: str | None,
        min_value: float | None,
        max_value: float | None,
        step: float | None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )
        self._command_address = command_address

        # Always initialize native attributes to avoid AttributeError
        self._attr_native_min_value = None
        self._attr_native_max_value = None
        self._attr_native_step = 1.0

        numeric_limits: tuple[float, float] | None = None
        try:
            tag = parse_tag(address)
        except (RuntimeError, ValueError):
            tag = None
        if tag is not None:
            numeric_limits = get_numeric_limits(tag.data_type)

        def _clamp(value: float | None) -> float | None:
            if value is None:
                return None
            clamped = float(value)
            if numeric_limits is not None:
                limit_min, limit_max = numeric_limits
                clamped = min(max(clamped, limit_min), limit_max)
            return clamped

        min_value_clamped = _clamp(min_value)
        max_value_clamped = _clamp(max_value)

        # If the user provided min/max, use them (clamped).
        # Otherwise, if available, use the native limits of the PLC data type.
        if min_value_clamped is not None:
            self._attr_native_min_value = min_value_clamped
        elif numeric_limits is not None:
            self._attr_native_min_value = float(numeric_limits[0])

        if max_value_clamped is not None:
            self._attr_native_max_value = max_value_clamped
        elif numeric_limits is not None:
            self._attr_native_max_value = float(numeric_limits[1])

        if step is not None:
            self._attr_native_step = float(step)

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._topic)

    async def async_set_native_value(self, value: float) -> None:
        await self._ensure_connected()
        if not self._command_address:
            raise HomeAssistantError("No command address configured for this entity.")

        success = await self.hass.async_add_executor_job(
            self._coord.write_number, self._command_address, float(value)
        )
        if not success:
            _LOGGER.error(
                "Failed to write %.3f to PLC address %s", value, self._command_address
            )
            raise HomeAssistantError(
                f"Failed to send command to PLC: {self._command_address}."
            )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        # Avoid exceptions if any attr remains None
        return {
            "min_value": getattr(self, "_attr_native_min_value", None),
            "max_value": getattr(self, "_attr_native_max_value", None),
            "step": getattr(self, "_attr_native_step", None),
        }
