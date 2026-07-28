from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .address import parse_address_and_scale
from .const import (
    CONF_AREA,
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_LIGHTS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SYNC_STATE,
    CONF_UID,
    DEFAULT_PULSE_DURATION,
)
from .entity import S7BoolSyncEntity
from .helpers import (
    default_entity_name,
    get_coordinator_and_device_info,
    inverse_scale_value,
    scale_value,
)

# Identity scale used when brightness_state_address/brightness_command_address
# has no inline Scale(...): a plain 0-255 PLC brightness value passes through
# unchanged, matching the old default brightness_scale == 255 behavior.
_IDENTITY_BRIGHTNESS_SCALE = (0.0, 255.0, 0.0, 255.0)

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
        pulse_duration = item.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)

        raw_brightness_state_address = item.get(CONF_BRIGHTNESS_STATE_ADDRESS)
        brightness_state_address = None
        brightness_state_scale = None
        brightness_command_address = None
        brightness_command_scale = None
        if raw_brightness_state_address:
            try:
                brightness_state_address, brightness_state_scale = (
                    parse_address_and_scale(raw_brightness_state_address)
                )
            except ValueError:
                _LOGGER.warning(
                    "Invalid Scale(...) syntax for light"
                    " brightness_state_address '%s', skipping",
                    raw_brightness_state_address,
                )
                continue

            raw_brightness_command_address = item.get(
                CONF_BRIGHTNESS_COMMAND_ADDRESS
            )
            if raw_brightness_command_address:
                try:
                    brightness_command_address, brightness_command_scale = (
                        parse_address_and_scale(raw_brightness_command_address)
                    )
                except ValueError:
                    _LOGGER.warning(
                        "Invalid Scale(...) syntax for light"
                        " brightness_command_address '%s', skipping",
                        raw_brightness_command_address,
                    )
                    continue
            else:
                brightness_command_address = brightness_state_address
                brightness_command_scale = brightness_state_scale

        name = item.get(CONF_NAME) or default_entity_name(state_address)
        area = item.get(CONF_AREA)
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        topic = f"light:{state_address}"
        unique_id = f"{device_id}:{item[CONF_UID]}"

        # Always register the boolean on/off topic
        await coord.add_item(topic, state_address, scan_interval)

        # If dimmer, also register the brightness topic
        is_dimmer = brightness_state_address is not None
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
                brightness_state_address,
                brightness_command_address,
                area,
                brightness_state_scale=brightness_state_scale,
                brightness_command_scale=brightness_command_scale,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Light(S7BoolSyncEntity, LightEntity):
    """Unified light entity supporting ON/OFF and optional dimmer mode.

    Inherits boolean ON/OFF state management, sync and pulse modes from
    :class:`S7BoolSyncEntity`.  When *brightness_state_address* is set, the
    entity additionally supports ``ColorMode.BRIGHTNESS`` and reads/writes
    brightness through the separate brightness addresses, linearly scaled
    via an inline ``Scale(...)`` suffix on the address (identity 0-255 when
    absent).
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
        brightness_state_address: str | None = None,
        brightness_command_address: str | None = None,
        suggested_area_id: str | None = None,
        brightness_state_scale: tuple[float, float, float, float] | None = None,
        brightness_command_scale: tuple[float, float, float, float] | None = None,
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
        self._brightness_state_address = brightness_state_address
        self._brightness_command_address = (
            brightness_command_address or brightness_state_address
        )
        self._brightness_state_scale = (
            brightness_state_scale or _IDENTITY_BRIGHTNESS_SCALE
        )
        self._brightness_command_scale = (
            brightness_command_scale or _IDENTITY_BRIGHTNESS_SCALE
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
        return self._brightness_state_address is not None

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

    @property
    def brightness(self) -> int | None:
        """Return the current brightness (0-255) or None if not a dimmer."""
        if not self._is_dimmer:
            return None
        data = self.coordinator.data or {}
        value = data.get(f"{self._topic}:brightness")
        if value is None:
            return None
        rn, rx, sn, sx = self._brightness_state_scale
        return max(0, min(255, round(scale_value(float(value), rn, rx, sn, sx))))

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
        return attrs

    # ------------------------------------------------------------------
    # Turn on (extends parent with optional brightness write)
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Write brightness before boolean on so PLC has the value ready
        if self._is_dimmer and "brightness" in kwargs:
            await self._ensure_connected()
            rn, rx, sn, sx = self._brightness_command_scale
            plc_value = round(
                inverse_scale_value(float(kwargs["brightness"]), rn, rx, sn, sx)
            )
            await self.coordinator.write_batched(
                self._brightness_command_address, plc_value
            )
        # Delegate boolean on/off + sync/pulse + refresh to parent
        await super().async_turn_on(**kwargs)

    # async_turn_off — inherited from S7BoolSyncEntity
    # is_on — inherited from S7BoolSyncEntity
    # async_write_ha_state — inherited from S7BoolSyncEntity
