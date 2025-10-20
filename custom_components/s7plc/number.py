from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
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

        await hass.async_add_executor_job(coord.add_item, topic, address)
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
        if min_value is not None:
            self._attr_native_min_value = float(min_value)
        if max_value is not None:
            self._attr_native_max_value = float(max_value)
        if step is not None:
            self._attr_native_step = float(step)

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._topic)

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC not connected: cannot execute command.")

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