from __future__ import annotations

import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_SWITCHES,
    CONF_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_SYNC_STATE,
)
from .entity import S7BaseEntity

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
    for item in entry.options.get(CONF_SWITCHES, []):
        state_address = (
            item.get(CONF_STATE_ADDRESS)
            or item.get(CONF_ADDRESS)
        )
        if not state_address:
            continue
        command_address = item.get(CONF_COMMAND_ADDRESS, state_address)
        sync_state = bool(item.get(CONF_SYNC_STATE, False))
        name = item.get(CONF_NAME, "S7 Switch")
        topic = f"switch:{state_address}"
        unique_id = f"{device_id}:{topic}"
        await hass.async_add_executor_job(coord.add_item, topic, state_address)
        entities.append(
            S7Switch(
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


class S7Switch(S7BaseEntity, SwitchEntity):
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
            address=state_address,
        )
        self._command_address = command_address
        self._sync_state = sync_state
        self._last_state: bool | None = None
        self._pending_command: bool | None = None

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._topic)
        return None if val is None else bool(val)

    async def _ensure_connected(self):
        if not self.available:
            raise HomeAssistantError("PLC non connesso: impossibile eseguire il comando.")

    async def async_turn_on(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = True
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._ensure_connected()
        self._pending_command = False
        await self.hass.async_add_executor_job(
            self._coord.write_bool, self._command_address, False
        )
        await self.coordinator.async_request_refresh()

    @callback
    def async_write_ha_state(self) -> None:
        new_state = self.is_on

        # Se il cambio stato arriva da HA (pending) e ciò che leggo dal PLC
        # coincide con quanto comandato, NON rimando il comando (evito eco).
        if (
            self._sync_state
            and new_state is not None
            and self.available
        ):
            if self._pending_command is not None:
                if new_state == self._pending_command:
                    # cambio interno completato -> aggiorno solo i registri interni e pulisco
                    self._last_state = new_state
                    self._pending_command = None
                    super().async_write_ha_state()
                    return
                else:
                    # il PLC ha risposto diversamente da quanto atteso:
                    # non reinviare subito; azzera il pending e lascia alla logica
                    # sottostante decidere se risincronizzare.
                    self._pending_command = None

            # Qui arrivano SOLO cambi esterni (o mismatch): sincronizzo il PLC
            if new_state != self._last_state:
                self._last_state = new_state
                self.hass.async_create_task(
                    self.hass.async_add_executor_job(
                        self._coord.write_bool, self._command_address, new_state
                    )
                )

        super().async_write_ha_state()