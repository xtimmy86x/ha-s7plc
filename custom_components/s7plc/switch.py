from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_COMMAND_ADDRESS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BoolSyncEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(hass, entry)

    entities = []
    for item in entry.options.get(CONF_SWITCHES, []):
        state_address = item.get(CONF_STATE_ADDRESS)
        if not state_address:
            continue
        command_address = item.get(CONF_COMMAND_ADDRESS, state_address)
        sync_state = bool(item.get(CONF_SYNC_STATE, False))
        pulse_command = bool(item.get(CONF_PULSE_COMMAND, False))
        raw_pulse = item.get(CONF_PULSE_DURATION)
        pulse_duration = DEFAULT_PULSE_DURATION
        if raw_pulse is not None:
            try:
                pulse_duration = float(raw_pulse)
            except (TypeError, ValueError):
                pulse_duration = DEFAULT_PULSE_DURATION
            else:
                if pulse_duration < 0.1 or pulse_duration > 60:
                    pulse_duration = DEFAULT_PULSE_DURATION
        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), state_address
        )
        topic = f"switch:{state_address}"
        unique_id = f"{device_id}:{topic}"
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
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


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
        pulse_command: bool = False,
        pulse_duration: float = DEFAULT_PULSE_DURATION,
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
        )
