from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_ADDRESS, CONF_BUTTONS, DOMAIN
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
        topic = f"button:{address}"
        unique_id = f"{device_id}:{topic}"
        await hass.async_add_executor_job(coord.add_item, topic, address)
        entities.append(
            S7Button(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
            )
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
        topic: str,
        address: str,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )

    async def _ensure_connected(self):
        """Raise if the PLC is not available."""
        if not self.available:
            raise HomeAssistantError("PLC not connected: cannot execute command.")

    async def async_press(self) -> None:
        await self._ensure_connected()
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._address, True
        )
        await asyncio.sleep(1)
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._address, False
        )
