from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_AREA,
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_SCALE,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_LIGHTS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
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
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    for item in entry.options.get(CONF_LIGHTS, []):
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

        brightness_scale = item.get(CONF_BRIGHTNESS_SCALE)
        brightness_state_address = item.get(CONF_BRIGHTNESS_STATE_ADDRESS)
        brightness_command_address = item.get(
            CONF_BRIGHTNESS_COMMAND_ADDRESS, brightness_state_address
        )

        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), state_address
        )
        area = item.get(CONF_AREA)
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        topic = f"light:{state_address}"
        unique_id = f"{device_id}:{topic}"

        # Always register the boolean on/off topic
        await coord.add_item(topic, state_address, scan_interval)

        # If dimmer, also register the brightness topic
        is_dimmer = (
            brightness_scale is not None and brightness_state_address is not None
        )
        if is_dimmer:
            await coord.add_item(
                f"{topic}:brightness", brightness_state_address, scan_interval
            )

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
                brightness_scale,
                brightness_state_address,
                brightness_command_address,
                area,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Light(S7BoolSyncEntity, LightEntity):
    """Unified light entity supporting ON/OFF and optional dimmer mode.

    Inherits boolean ON/OFF state management, sync and pulse modes from
    :class:`S7BoolSyncEntity`.  When *brightness_state_address* and
    *brightness_scale* are set, the entity additionally supports
    ``ColorMode.BRIGHTNESS`` and reads/writes brightness through the
    separate brightness addresses.
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
        sync_state: bool = False,
        pulse_command: bool = False,
        pulse_duration: float = DEFAULT_PULSE_DURATION,
        brightness_scale: int | None = None,
        brightness_state_address: str | None = None,
        brightness_command_address: str | None = None,
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
        self._brightness_scale = (
            max(1, brightness_scale) if brightness_scale is not None else None
        )
        self._brightness_state_address = brightness_state_address
        self._brightness_command_address = (
            brightness_command_address or brightness_state_address
        )

        if self._is_dimmer:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    # ------------------------------------------------------------------
    # Mode helpers
    # ------------------------------------------------------------------

    @property
    def _is_dimmer(self) -> bool:
        return (
            self._brightness_scale is not None
            and self._brightness_state_address is not None
        )

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.BRIGHTNESS if self._is_dimmer else ColorMode.ONOFF

    # ------------------------------------------------------------------
    # Availability (extends parent with brightness topic check)
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self._is_dimmer:
            data = self.coordinator.data or {}
            bri_key = f"{self._topic}:brightness"
            if bri_key not in data or data[bri_key] is None:
                return False
        return True

    # ------------------------------------------------------------------
    # Brightness helpers (dimmer mode)
    # ------------------------------------------------------------------

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
        """Return the current brightness (0-255) or None if not a dimmer."""
        if not self._is_dimmer:
            return None
        data = self.coordinator.data or {}
        value = data.get(f"{self._topic}:brightness")
        if value is None:
            return None
        return self._plc_to_ha_brightness(value)

    # ------------------------------------------------------------------
    # State attributes (extends parent with brightness info)
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        if self._is_dimmer:
            attrs["s7_brightness_state_address"] = (
                self._brightness_state_address.upper()
            )
            attrs["s7_brightness_command_address"] = (
                self._brightness_command_address.upper()
            )
            attrs["brightness_scale"] = self._brightness_scale
        return attrs

    # ------------------------------------------------------------------
    # Turn on (extends parent with optional brightness write)
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Write brightness before boolean on so PLC has the value ready
        if self._is_dimmer and "brightness" in kwargs:
            await self._ensure_connected()
            plc_value = self._ha_to_plc_brightness(kwargs["brightness"])
            await self.coordinator.write_batched(
                self._brightness_command_address, plc_value
            )
        # Delegate boolean on/off + sync/pulse + refresh to parent
        await super().async_turn_on(**kwargs)

    # async_turn_off — inherited from S7BoolSyncEntity
    # is_on — inherited from S7BoolSyncEntity
    # async_write_ha_state — inherited from S7BoolSyncEntity


# Backward-compatible alias for existing imports
S7DimmerLight = S7Light
