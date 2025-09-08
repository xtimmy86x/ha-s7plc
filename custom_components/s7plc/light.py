from __future__ import annotations

import logging
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_LIGHTS,
    CONF_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_SYNC_STATE,
)
from .entity import S7BoolSyncEntity

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"


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
    )

    entities = []
    for item in entry.options.get(CONF_LIGHTS, []):
        state_address = (
            item.get(CONF_STATE_ADDRESS)
            or item.get(CONF_ADDRESS)
        )
        if not state_address:
            continue
        command_address = item.get(CONF_COMMAND_ADDRESS, state_address)
        sync_state = bool(item.get(CONF_SYNC_STATE, False))
        name = item.get(CONF_NAME, "S7 Light")
        topic = f"light:{state_address}"
        unique_id = f"{device_id}:{topic}"
        await hass.async_add_executor_job(coord.add_item, topic, state_address)
        entities.append(
            S7Light(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                state_address,
                command_address,
                sync_state,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Light(S7BoolSyncEntity, LightEntity):
    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        state_address: str,
        command_address: str,
        sync_state: bool,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            state_address=state_address,
            command_address=command_address,
            sync_state=sync_state,
        )
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.ONOFF
