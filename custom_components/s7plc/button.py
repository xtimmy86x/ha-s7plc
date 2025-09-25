from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    DEFAULT_BUTTON_PULSE,
    DOMAIN,
)
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up button entities from a config entry."""
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

    entities = []
    for item in entry.options.get(CONF_BUTTONS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME, "S7 Button")
        unique_id = f"{device_id}:button:{address}"
        raw_pulse = item.get(CONF_BUTTON_PULSE)
        button_pulse = DEFAULT_BUTTON_PULSE
        if raw_pulse is not None:
            try:
                button_pulse = int(raw_pulse)
            except (TypeError, ValueError):
                button_pulse = DEFAULT_BUTTON_PULSE
            else:
                if button_pulse < 0:
                    button_pulse = DEFAULT_BUTTON_PULSE
        entities.append(
            S7Button(coord, name, unique_id, device_info, address, button_pulse)
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Button(S7BaseEntity, ButtonEntity):
    """Stateless button that pulses a PLC boolean address."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        address: str,
        button_pulse: int,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            address=address,
        )

        self._button_pulse = button_pulse

    async def _ensure_connected(self):
        """Raise if the PLC is not available."""
        if not self.available:
            raise HomeAssistantError("PLC not connected: cannot execute command.")

    async def async_press(self) -> None:
        await self._ensure_connected()
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._address, True
        )
        if not success:
            _LOGGER.error("Failed to press PLC button at %s", self._address)
            raise HomeAssistantError(f"Failed to send command to PLC: {self._address}.")
        await asyncio.sleep(self._button_pulse)
        success = await self.hass.async_add_executor_job(
            self._coord.write_bool, self._address, False
        )
        if not success:
            _LOGGER.error("Failed to release PLC button at %s", self._address)
            raise HomeAssistantError(f"Failed to send command to PLC: {self._address}.")

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._address:
            attrs["s7_address"] = self._address.upper()
        if self._button_pulse is not None:
            attrs["button_pulse"] = f"{self._button_pulse} s"
        return attrs
