from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AREA,
    CONF_COMMAND_ADDRESS,
    CONF_MANUAL_CONNECTION_CONTROL,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    CONF_UID,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BoolSyncEntity, async_configure_entity_availability
from .helpers import default_entity_name, get_coordinator_and_device_info

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    if entry.data.get(CONF_MANUAL_CONNECTION_CONTROL, False) is True:
        entities.append(
            S7ConnectionControlSwitch(
                coord,
                device_info,
                f"{device_id}:connection_enable",
                entry.runtime_data.connection_state_store,
            )
        )
    for item in entry.options.get(CONF_SWITCHES, []):
        state_address = item.get(CONF_STATE_ADDRESS)
        if not state_address:
            continue
        command_address = item.get(CONF_COMMAND_ADDRESS, state_address)
        sync_state = bool(item.get(CONF_SYNC_STATE, False))
        pulse_command = bool(item.get(CONF_PULSE_COMMAND, False))
        pulse_duration = item.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)
        name = item.get(CONF_NAME) or default_entity_name(state_address)
        area = item.get(CONF_AREA)
        topic = f"switch:{state_address}"
        unique_id = item[CONF_UID]
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, state_address, scan_interval)
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
                pulse_command,
                pulse_duration,
                area,
            )
        )

    if entities:
        await async_configure_entity_availability(
            [entity for entity in entities if isinstance(entity, S7Switch)],
            entry.options.get(CONF_SWITCHES, []),
        )
        async_add_entities(entities)
        if entry.options.get(CONF_SWITCHES):
            await coord.async_request_refresh()


class S7ConnectionControlSwitch(CoordinatorEntity, SwitchEntity):
    """Always-available, persisted control for all PLC communication."""

    _attr_has_entity_name = True
    _attr_translation_key = "connection_enable"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_available = True
    _attr_should_poll = False

    def __init__(self, coordinator, device_info: DeviceInfo, unique_id: str, store):
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._store = store

    @property
    def is_on(self) -> bool:
        return self.coordinator.connection_enabled

    async def _async_save(self) -> None:
        if self._store is not None:
            await self._store.async_save({"enabled": self.is_on})

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_enable_connection()
        await self._async_save()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_disable_connection()
        await self._async_save()


class S7Switch(S7BoolSyncEntity, SwitchEntity):
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
        pulse_command: bool,
        pulse_duration: float,
        suggested_area_id: str | None = None,
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
            pulse_command=pulse_command,
            pulse_duration=pulse_duration,
            suggested_area_id=suggested_area_id,
        )
