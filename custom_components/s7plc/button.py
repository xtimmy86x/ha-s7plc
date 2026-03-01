from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up button entities from a config entry."""
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    for item in entry.options.get(CONF_BUTTONS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(address)
        area = item.get(CONF_AREA)
        unique_id = f"{device_id}:button:{address}"
        button_pulse = item.get(CONF_BUTTON_PULSE, DEFAULT_PULSE_DURATION)
        entities.append(
            S7Button(coord, name, unique_id, device_info, address, button_pulse, area)
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Button(S7BaseEntity, ButtonEntity):
    """Stateless button that pulses a PLC boolean address."""

    _address_attr_name = "s7_command_address"

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        address: str,
        button_pulse: float,
        suggested_area_id: str | None = None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            address=address,
            suggested_area_id=suggested_area_id,
        )

        self._button_pulse = button_pulse

    async def async_press(self) -> None:
        """Press button by toggling the PLC address."""
        await self._ensure_connected()
        await self.coordinator.write_batched(self._address, True)
        await asyncio.sleep(self._button_pulse)
        await self.coordinator.write_batched(self._address, False)

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._button_pulse is not None:
            attrs["button_pulse"] = f"{self._button_pulse} s"
        return attrs
