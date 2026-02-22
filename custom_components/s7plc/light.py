from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ACTUATOR_COMMAND_ADDRESS,
    CONF_AREA,
    CONF_BRIGHTNESS_SCALE,
    CONF_COMMAND_ADDRESS,
    CONF_LIGHTS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SYNC_STATE,
    DEFAULT_BRIGHTNESS_SCALE,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BaseEntity, S7BoolSyncEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    for item in entry.options.get(CONF_LIGHTS, []):
        state_address = item.get(CONF_STATE_ADDRESS)
        if not state_address:
            continue

        # Check if this is a dimmer light (has brightness_scale key)
        if CONF_BRIGHTNESS_SCALE in item:
            # Dimmer light
            command_address = item.get(CONF_COMMAND_ADDRESS, state_address)
            actuator_command_address = item.get(CONF_ACTUATOR_COMMAND_ADDRESS)
            brightness_scale = item.get(CONF_BRIGHTNESS_SCALE, DEFAULT_BRIGHTNESS_SCALE)
            name = item.get(CONF_NAME) or default_entity_name(
                device_info.get("name"), state_address
            )
            area = item.get(CONF_AREA)
            topic = f"dimmer_light:{state_address}"
            unique_id = f"{device_id}:{topic}"
            scan_interval = item.get(CONF_SCAN_INTERVAL)
            await coord.add_item(f"{topic}:brightness", state_address, scan_interval)
            entities.append(
                S7DimmerLight(
                    coord,
                    name,
                    unique_id,
                    device_info,
                    topic,
                    state_address,
                    command_address,
                    actuator_command_address,
                    brightness_scale,
                    area,
                )
            )
            continue

        # On/off light
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
        area = item.get(CONF_AREA)
        topic = f"light:{state_address}"
        unique_id = f"{device_id}:{topic}"
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, state_address, scan_interval)
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
                pulse_command,
                pulse_duration,
                area,
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
        pulse_command: bool = False,
        pulse_duration: float = DEFAULT_PULSE_DURATION,
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
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.ONOFF


class S7DimmerLight(S7BaseEntity, LightEntity):
    """Light entity with brightness (dimmer) control.

    Uses a numeric PLC address for brightness state/command and an optional
    boolean actuator command address that is set ON when brightness >= 1%
    and OFF when brightness is 0.
    """

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        state_address: str,
        command_address: str,
        actuator_command_address: str | None = None,
        brightness_scale: int = DEFAULT_BRIGHTNESS_SCALE,
        suggested_area_id: str | None = None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=state_address,
            suggested_area_id=suggested_area_id,
        )
        self._command_address = command_address
        self._actuator_command_address = actuator_command_address
        self._brightness_scale = max(1, brightness_scale)
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS

    @property
    def available(self) -> bool:
        """Return True when the coordinator has brightness data."""
        if not self._coord.is_connected():
            return False
        data = self.coordinator.data or {}
        key = f"{self._topic}:brightness"
        return (key in data) and (data[key] is not None)

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.BRIGHTNESS

    def _plc_to_ha_brightness(self, plc_value: int | float) -> int:
        """Convert PLC brightness value to HA 0-255 range."""
        if self._brightness_scale == 255:
            return max(0, min(255, int(plc_value)))
        return max(0, min(255, round(plc_value * 255 / self._brightness_scale)))

    def _ha_to_plc_brightness(self, ha_brightness: int) -> int | float:
        """Convert HA 0-255 brightness to PLC value range."""
        if self._brightness_scale == 255:
            return max(0, min(255, int(ha_brightness)))
        return max(
            0,
            min(
                self._brightness_scale,
                round(ha_brightness * self._brightness_scale / 255),
            ),
        )

    @property
    def brightness(self) -> int | None:
        """Return the current brightness (0-255)."""
        data = self.coordinator.data or {}
        value = data.get(f"{self._topic}:brightness")
        if value is None:
            return None
        return self._plc_to_ha_brightness(value)

    @property
    def is_on(self) -> bool | None:
        """Return True if brightness > 0."""
        bri = self.brightness
        if bri is None:
            return None
        return bri > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity state attributes."""
        attrs: dict[str, Any] = {}
        if self._address:
            attrs["s7_state_address"] = self._address.upper()
            attrs["s7_command_address"] = self._command_address.upper()
        if self._actuator_command_address:
            attrs["s7_actuator_command_address"] = (
                self._actuator_command_address.upper()
            )
        attrs["brightness_scale"] = self._brightness_scale
        interval = self._coord._item_scan_intervals.get(
            f"{self._topic}:brightness", self._coord._default_scan_interval
        )
        attrs["scan_interval"] = f"{interval} s"
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally with brightness."""
        await self._ensure_connected()
        ha_brightness = kwargs.get("brightness", 255)
        plc_value = self._ha_to_plc_brightness(ha_brightness)
        await self._async_write(self._command_address, plc_value)
        if self._actuator_command_address:
            await self._async_write(self._actuator_command_address, plc_value > 0)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off (brightness 0)."""
        await self._ensure_connected()
        await self._async_write(self._command_address, 0)
        if self._actuator_command_address:
            await self._async_write(self._actuator_command_address, False)
        await self.coordinator.async_request_refresh()
