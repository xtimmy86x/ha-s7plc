from __future__ import annotations

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import S7BaseEntity

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default="S7 Switch"): cv.string,
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

    name = config.get(CONF_NAME)
    address = config[CONF_ADDRESS]
    topic = f"switch:{address}"
    unique_id = f"{device_id}:{topic}"

    await hass.async_add_executor_job(coord.add_item, topic, address)
    async_add_entities([S7Switch(coord, name, unique_id, device_info, topic, address)])
    await coord.async_request_refresh()


class S7Switch(S7BaseEntity, SwitchEntity):
    def __init__(self, coordinator, name: str, unique_id: str, device_info: DeviceInfo, topic: str, address: str):
        super().__init__(coordinator, name=name, unique_id=unique_id, device_info=device_info, topic=topic, address=address)

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC non connesso: impossibile eseguire il comando.")

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._coord.write_bool, self._address, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        await self.hass.async_add_executor_job(self._coord.write_bool, self._address, False)
        await self.coordinator.async_request_refresh()
