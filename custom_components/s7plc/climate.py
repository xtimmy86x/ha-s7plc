from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import restore_state
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_AREA,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_COOLING_ACTION_ADDRESS,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_HEATING_ACTION_ADDRESS,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_HVAC_STATUS_ADDRESS,
    CONF_HVAC_STATUS_COOLING_VALUES,
    CONF_HVAC_STATUS_DRYING_VALUES,
    CONF_HVAC_STATUS_FAN_VALUES,
    CONF_HVAC_STATUS_HEATING_VALUES,
    CONF_HVAC_STATUS_IDLE_VALUES,
    CONF_HVAC_STATUS_OFF_VALUES,
    CONF_HVAC_STATUS_PREHEATING_VALUES,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_ON_OFF_ADDRESS,
    CONF_PRESET_MODE_ADDRESS,
    CONF_PRESET_MODE_AUTO_VALUE,
    CONF_PRESET_MODE_COOL_VALUE,
    CONF_PRESET_MODE_DRY_VALUE,
    CONF_PRESET_MODE_FAN_ONLY_VALUE,
    CONF_PRESET_MODE_HEAT_COOL_VALUE,
    CONF_PRESET_MODE_HEAT_VALUE,
    CONF_PRESET_MODE_OFF_VALUE,
    CONF_SCAN_INTERVAL,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONF_UID,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_HVAC_STATUS_COOLING_VALUES,
    DEFAULT_HVAC_STATUS_DRYING_VALUES,
    DEFAULT_HVAC_STATUS_FAN_VALUES,
    DEFAULT_HVAC_STATUS_HEATING_VALUES,
    DEFAULT_HVAC_STATUS_IDLE_VALUES,
    DEFAULT_HVAC_STATUS_OFF_VALUES,
    DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_PRESET_MODE_AUTO_VALUE,
    DEFAULT_PRESET_MODE_COOL_VALUE,
    DEFAULT_PRESET_MODE_DRY_VALUE,
    DEFAULT_PRESET_MODE_FAN_ONLY_VALUE,
    DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
    DEFAULT_PRESET_MODE_HEAT_VALUE,
    DEFAULT_PRESET_MODE_OFF_VALUE,
    DEFAULT_TEMP_STEP,
    MODE_VALUE_DISABLED,
)
from .address import parse_address_and_scale
from .entity import S7BaseEntity
from .helpers import (
    default_entity_name,
    get_coordinator_and_device_info,
    inverse_scale_value,
    make_unique_topic,
    scale_value,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up S7 climate entities."""
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    seen_topics: set[str] = set()
    for item in entry.options.get(CONF_CLIMATES, []):
        raw_current_temp_address = item.get(CONF_CURRENT_TEMPERATURE_ADDRESS)
        if not raw_current_temp_address:
            _LOGGER.warning(
                "Climate entity requires current_temperature_address, "
                "skipping item: %s",
                item,
            )
            continue
        try:
            current_temp_address, current_temp_scale = parse_address_and_scale(
                raw_current_temp_address
            )
        except ValueError:
            _LOGGER.warning(
                "Invalid Scale(...) syntax for climate current_temperature_address"
                " '%s', skipping",
                raw_current_temp_address,
            )
            continue

        control_mode = item.get(CONF_CLIMATE_CONTROL_MODE, CONTROL_MODE_SETPOINT)
        name = item.get(CONF_NAME) or default_entity_name(current_temp_address)
        area = item.get(CONF_AREA)

        # Common configuration
        min_temp = item.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        max_temp = item.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
        temp_step = item.get(CONF_TEMP_STEP, DEFAULT_TEMP_STEP)
        scan_interval = item.get(CONF_SCAN_INTERVAL)

        if control_mode == CONTROL_MODE_DIRECT:
            # Mode 1: Direct control - HA controls heating/cooling outputs
            heating_output = item.get(CONF_HEATING_OUTPUT_ADDRESS)
            cooling_output = item.get(CONF_COOLING_OUTPUT_ADDRESS)
            if not heating_output and not cooling_output:
                _LOGGER.debug(
                    "Skipping direct control climate with missing outputs: "
                    "heating=%s cooling=%s",
                    heating_output,
                    cooling_output,
                )
                continue

            # Optional: read heating/cooling action states from PLC
            heating_action = item.get(CONF_HEATING_ACTION_ADDRESS)
            cooling_action = item.get(CONF_COOLING_ACTION_ADDRESS)

            topic = make_unique_topic(
                seen_topics, f"climate_direct:{current_temp_address}"
            )
            unique_id = f"{device_id}:{item[CONF_UID]}"

            # Register current temperature for reading
            await coord.add_item(
                f"{topic}:current_temp", current_temp_address, scan_interval
            )

            # Register heating/cooling action states if specified
            if heating_action:
                await coord.add_item(
                    f"{topic}:heating_action", heating_action, scan_interval
                )
            if cooling_action:
                await coord.add_item(
                    f"{topic}:cooling_action", cooling_action, scan_interval
                )

            entities.append(
                S7ClimateDirectControl(
                    coord,
                    name,
                    unique_id,
                    device_info,
                    topic,
                    current_temp_address,
                    heating_output,
                    cooling_output,
                    heating_action,
                    cooling_action,
                    min_temp,
                    max_temp,
                    temp_step,
                    area,
                    current_temp_scale=current_temp_scale,
                )
            )

        elif control_mode == CONTROL_MODE_SETPOINT:
            # Mode 2: Setpoint control - PLC manages heating/cooling autonomously
            raw_target_temp_address = item.get(CONF_TARGET_TEMPERATURE_ADDRESS)
            if not raw_target_temp_address:
                _LOGGER.debug(
                    "Skipping setpoint control climate "
                    "without target_temperature_address"
                )
                continue
            try:
                target_temp_address, target_temp_scale = parse_address_and_scale(
                    raw_target_temp_address
                )
            except ValueError:
                _LOGGER.warning(
                    "Invalid Scale(...) syntax for climate"
                    " target_temperature_address '%s', skipping",
                    raw_target_temp_address,
                )
                continue

            topic = make_unique_topic(
                seen_topics, f"climate_setpoint:{current_temp_address}"
            )
            unique_id = f"{device_id}:{item[CONF_UID]}"

            # Register current and target temperature for reading
            await coord.add_item(
                f"{topic}:current_temp", current_temp_address, scan_interval
            )
            await coord.add_item(
                f"{topic}:target_temp", target_temp_address, scan_interval
            )

            # Optional: preset mode address
            preset_mode_address = item.get(CONF_PRESET_MODE_ADDRESS)
            if preset_mode_address:
                await coord.add_item(
                    f"{topic}:preset_mode", preset_mode_address, scan_interval
                )

            # Optional: boolean on/off address, for thermostats without a
            # native OFF mode. Writes False when target mode is OFF, True
            # for any other mode.
            on_off_address = item.get(CONF_ON_OFF_ADDRESS)
            if on_off_address:
                await coord.add_item(
                    f"{topic}:on_off", on_off_address, scan_interval
                )

            # Optional: HVAC status address (mapping configured below)
            hvac_status_address = item.get(CONF_HVAC_STATUS_ADDRESS)
            if hvac_status_address:
                await coord.add_item(
                    f"{topic}:hvac_status", hvac_status_address, scan_interval
                )

            # Current status mapping (hvac_status_address -> HVAC action).
            # Each field may hold multiple comma-separated PLC values, e.g.
            # "2,3", so several PLC codes can mean the same status.
            hvac_status_off_values = item.get(
                CONF_HVAC_STATUS_OFF_VALUES, DEFAULT_HVAC_STATUS_OFF_VALUES
            )
            hvac_status_heating_values = item.get(
                CONF_HVAC_STATUS_HEATING_VALUES, DEFAULT_HVAC_STATUS_HEATING_VALUES
            )
            hvac_status_cooling_values = item.get(
                CONF_HVAC_STATUS_COOLING_VALUES, DEFAULT_HVAC_STATUS_COOLING_VALUES
            )
            hvac_status_idle_values = item.get(
                CONF_HVAC_STATUS_IDLE_VALUES, DEFAULT_HVAC_STATUS_IDLE_VALUES
            )
            hvac_status_drying_values = item.get(
                CONF_HVAC_STATUS_DRYING_VALUES, DEFAULT_HVAC_STATUS_DRYING_VALUES
            )
            hvac_status_fan_values = item.get(
                CONF_HVAC_STATUS_FAN_VALUES, DEFAULT_HVAC_STATUS_FAN_VALUES
            )
            hvac_status_preheating_values = item.get(
                CONF_HVAC_STATUS_PREHEATING_VALUES,
                DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
            )

            # Target mode mapping (HVAC mode -> value written to
            # preset_mode_address). Independent from the status mapping above
            # since the PLC may use different codes for command vs. status.
            preset_mode_off_value = item.get(
                CONF_PRESET_MODE_OFF_VALUE, DEFAULT_PRESET_MODE_OFF_VALUE
            )
            preset_mode_heat_value = item.get(
                CONF_PRESET_MODE_HEAT_VALUE, DEFAULT_PRESET_MODE_HEAT_VALUE
            )
            preset_mode_cool_value = item.get(
                CONF_PRESET_MODE_COOL_VALUE, DEFAULT_PRESET_MODE_COOL_VALUE
            )
            preset_mode_heat_cool_value = item.get(
                CONF_PRESET_MODE_HEAT_COOL_VALUE,
                DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
            )
            preset_mode_auto_value = item.get(
                CONF_PRESET_MODE_AUTO_VALUE, DEFAULT_PRESET_MODE_AUTO_VALUE
            )
            preset_mode_dry_value = item.get(
                CONF_PRESET_MODE_DRY_VALUE, DEFAULT_PRESET_MODE_DRY_VALUE
            )
            preset_mode_fan_only_value = item.get(
                CONF_PRESET_MODE_FAN_ONLY_VALUE, DEFAULT_PRESET_MODE_FAN_ONLY_VALUE
            )

            entities.append(
                S7ClimateSetpointControl(
                    coord,
                    name,
                    unique_id,
                    device_info,
                    topic,
                    current_temp_address,
                    target_temp_address,
                    preset_mode_address,
                    hvac_status_address,
                    min_temp,
                    max_temp,
                    temp_step,
                    area,
                    hvac_status_off_values=hvac_status_off_values,
                    hvac_status_heating_values=hvac_status_heating_values,
                    hvac_status_cooling_values=hvac_status_cooling_values,
                    hvac_status_idle_values=hvac_status_idle_values,
                    hvac_status_drying_values=hvac_status_drying_values,
                    hvac_status_fan_values=hvac_status_fan_values,
                    hvac_status_preheating_values=hvac_status_preheating_values,
                    preset_mode_off_value=preset_mode_off_value,
                    preset_mode_heat_value=preset_mode_heat_value,
                    preset_mode_cool_value=preset_mode_cool_value,
                    preset_mode_heat_cool_value=preset_mode_heat_cool_value,
                    preset_mode_auto_value=preset_mode_auto_value,
                    preset_mode_dry_value=preset_mode_dry_value,
                    preset_mode_fan_only_value=preset_mode_fan_only_value,
                    on_off_address=on_off_address,
                    current_temp_scale=current_temp_scale,
                    target_temp_scale=target_temp_scale,
                )
            )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7ClimateDirectControl(S7BaseEntity, restore_state.RestoreEntity, ClimateEntity):
    """Climate entity with direct heating/cooling output control.

    This mode allows Home Assistant to directly control PLC outputs for
    heating and cooling. The PLC only provides the current temperature reading.
    HA manages the control logic based on the target temperature.
    """

    _address_attr_name = "s7_current_temp_address"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        current_temp_address: str,
        heating_output_address: str | None,
        cooling_output_address: str | None,
        heating_action_address: str | None,
        cooling_action_address: str | None,
        min_temp: float,
        max_temp: float,
        temp_step: float,
        suggested_area_id: str | None = None,
        current_temp_scale: tuple[float, float, float, float] | None = None,
    ):
        """Initialize direct control climate entity."""
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=current_temp_address,
            suggested_area_id=suggested_area_id,
        )
        self._current_temp_address = current_temp_address
        self._current_temp_scale = current_temp_scale
        self._heating_output_address = heating_output_address
        self._cooling_output_address = cooling_output_address
        self._heating_action_address = heating_action_address
        self._cooling_action_address = cooling_action_address

        self._attr_min_temp = float(min_temp)
        self._attr_max_temp = float(max_temp)
        self._attr_target_temperature_step = float(temp_step)

        # Internal state - initialize target temperature to midpoint of range
        default_target = (self._attr_min_temp + self._attr_max_temp) / 2
        self._target_temperature: float = default_target
        self._hvac_mode = HVACMode.OFF

        # Last values commanded to the PLC outputs. Used to write only on
        # transitions and avoid pointless traffic/wear on every coordinator
        # update (which fires every scan_interval regardless of changes).
        self._last_heating_cmd: bool | None = None
        self._last_cooling_cmd: bool | None = None

        # Available HVAC modes based on configured outputs
        self._attr_hvac_modes = [HVACMode.OFF]
        if heating_output_address:
            self._attr_hvac_modes.append(HVACMode.HEAT)
        if cooling_output_address:
            self._attr_hvac_modes.append(HVACMode.COOL)
        if heating_output_address and cooling_output_address:
            self._attr_hvac_modes.append(HVACMode.HEAT_COOL)

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) is not None:
            # Restore HVAC mode
            try:
                hvac_mode = HVACMode(last_state.state)
                if hvac_mode in self._attr_hvac_modes:
                    self._hvac_mode = hvac_mode
            except ValueError:
                # Invalid mode, keep default
                pass

            # Restore target temperature
            if (target_temp := last_state.attributes.get("temperature")) is not None:
                try:
                    self._target_temperature = float(target_temp)
                except (ValueError, TypeError):
                    pass

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.is_connected():
            return False
        # Check if current temperature reading is available
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:current_temp"
        return temp_topic in data and data[temp_topic] is not None

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature from PLC."""
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:current_temp"
        value = data.get(temp_topic)
        if value is not None and isinstance(value, (int, float)):
            if self._current_temp_scale is not None:
                rn, rx, sn, sx = self._current_temp_scale
                return scale_value(float(value), rn, rx, sn, sx)
            return float(value)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return self._target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action based on PLC state."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        data = self.coordinator.data or {}

        # Check heating action if address is specified
        if self._heating_action_address:
            heating_topic = f"{self._topic}:heating_action"
            heating_active = data.get(heating_topic)
            if heating_active:
                return HVACAction.HEATING

        # Check cooling action if address is specified
        if self._cooling_action_address:
            cooling_topic = f"{self._topic}:cooling_action"
            cooling_active = data.get(cooling_topic)
            if cooling_active:
                return HVACAction.COOLING

        # If no action addresses specified, infer from mode
        if self._hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        elif self._hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["climate_type"] = "Direct Control"
        if self._heating_output_address:
            attrs["s7_heating_output_address"] = self._heating_output_address.upper()
        if self._cooling_output_address:
            attrs["s7_cooling_output_address"] = self._cooling_output_address.upper()
        if self._heating_action_address:
            attrs["s7_heating_action_address"] = self._heating_action_address.upper()
        if self._cooling_action_address:
            attrs["s7_cooling_action_address"] = self._cooling_action_address.upper()
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._target_temperature = float(temperature)

        # If a mode is specified, set it first
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        else:
            # Update outputs based on current mode and new target
            await self._update_outputs()

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode not in self._attr_hvac_modes:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        self._hvac_mode = hvac_mode

        # Update outputs based on new mode
        await self._update_outputs()
        self.async_write_ha_state()

    async def _write_heating(self, value: bool) -> None:
        """Write the heating output only when the commanded value changes."""
        if self._heating_output_address and value != self._last_heating_cmd:
            await self.coordinator.write_batched(self._heating_output_address, value)
            self._last_heating_cmd = value

    async def _write_cooling(self, value: bool) -> None:
        """Write the cooling output only when the commanded value changes."""
        if self._cooling_output_address and value != self._last_cooling_cmd:
            await self.coordinator.write_batched(self._cooling_output_address, value)
            self._last_cooling_cmd = value

    async def _update_outputs(self) -> None:
        """Update PLC heating/cooling outputs based on mode and target temperature.

        Outputs are written only on transitions (see _write_heating/_write_cooling),
        so a coordinator update without a relevant change produces no PLC traffic.
        """
        if self._hvac_mode == HVACMode.OFF:
            # Turn off all outputs
            await self._write_heating(False)
            await self._write_cooling(False)
            return

        if self._target_temperature is None:
            return

        current_temp = self.current_temperature
        if current_temp is None:
            return

        # Simple hysteresis: 0.5°C
        hysteresis = 0.5
        heating_needed = current_temp < (self._target_temperature - hysteresis)
        cooling_needed = current_temp > (self._target_temperature + hysteresis)

        # Control heating output
        if self._hvac_mode in (HVACMode.HEAT, HVACMode.HEAT_COOL):
            await self._write_heating(heating_needed)
        else:
            await self._write_heating(False)

        # Control cooling output
        if self._hvac_mode in (HVACMode.COOL, HVACMode.HEAT_COOL):
            await self._write_cooling(cooling_needed)
        else:
            await self._write_cooling(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.is_connected():
            # Forget the cached commands so outputs are re-asserted on the
            # next update once the PLC is reachable again (the PLC state may
            # have drifted while disconnected).
            self._last_heating_cmd = None
            self._last_cooling_cmd = None
        elif self._hvac_mode != HVACMode.OFF and self._target_temperature is not None:
            # Re-evaluate outputs when temperature changes
            self.hass.async_create_task(self._update_outputs())
        super()._handle_coordinator_update()


class S7ClimateSetpointControl(
    S7BaseEntity, restore_state.RestoreEntity, ClimateEntity
):
    """Climate entity with PLC-managed setpoint control.

    This mode allows the PLC to manage heating/cooling autonomously.
    Home Assistant only writes the target temperature setpoint and reads
    the current temperature. The PLC handles all control logic.
    """

    _address_attr_name = "s7_current_temp_address"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        current_temp_address: str,
        target_temp_address: str,
        preset_mode_address: str | None,
        hvac_status_address: str | None = None,
        min_temp: float = DEFAULT_MIN_TEMP,
        max_temp: float = DEFAULT_MAX_TEMP,
        temp_step: float = DEFAULT_TEMP_STEP,
        suggested_area_id: str | None = None,
        hvac_status_off_values: str = DEFAULT_HVAC_STATUS_OFF_VALUES,
        hvac_status_heating_values: str = DEFAULT_HVAC_STATUS_HEATING_VALUES,
        hvac_status_cooling_values: str = DEFAULT_HVAC_STATUS_COOLING_VALUES,
        hvac_status_idle_values: str = DEFAULT_HVAC_STATUS_IDLE_VALUES,
        hvac_status_drying_values: str = DEFAULT_HVAC_STATUS_DRYING_VALUES,
        hvac_status_fan_values: str = DEFAULT_HVAC_STATUS_FAN_VALUES,
        hvac_status_preheating_values: str = DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
        preset_mode_off_value: int = DEFAULT_PRESET_MODE_OFF_VALUE,
        preset_mode_heat_value: int = DEFAULT_PRESET_MODE_HEAT_VALUE,
        preset_mode_cool_value: int = DEFAULT_PRESET_MODE_COOL_VALUE,
        preset_mode_heat_cool_value: int = DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
        preset_mode_auto_value: int = DEFAULT_PRESET_MODE_AUTO_VALUE,
        preset_mode_dry_value: int = DEFAULT_PRESET_MODE_DRY_VALUE,
        preset_mode_fan_only_value: int = DEFAULT_PRESET_MODE_FAN_ONLY_VALUE,
        on_off_address: str | None = None,
        current_temp_scale: tuple[float, float, float, float] | None = None,
        target_temp_scale: tuple[float, float, float, float] | None = None,
    ):
        """Initialize setpoint control climate entity."""
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=current_temp_address,
            suggested_area_id=suggested_area_id,
        )
        self._current_temp_address = current_temp_address
        self._current_temp_scale = current_temp_scale
        self._target_temp_address = target_temp_address
        self._target_temp_scale = target_temp_scale
        self._preset_mode_address = preset_mode_address
        self._hvac_status_address = hvac_status_address
        self._on_off_address = on_off_address

        self._attr_min_temp = float(min_temp)
        self._attr_max_temp = float(max_temp)
        self._attr_target_temperature_step = float(temp_step)

        # Current status mapping: PLC value(s) read from hvac_status_address
        # that are recognized as each HVAC action. Independent from the
        # target mapping below since the PLC may report status using
        # different codes than it accepts as a command. Priority order when
        # matching a status value is the dict's key order below.
        self._hvac_status_values: dict[HVACAction, list[int]] = {
            HVACAction.OFF: self._parse_mode_values(hvac_status_off_values),
            HVACAction.HEATING: self._parse_mode_values(hvac_status_heating_values),
            HVACAction.COOLING: self._parse_mode_values(hvac_status_cooling_values),
            HVACAction.DRYING: self._parse_mode_values(hvac_status_drying_values),
            HVACAction.FAN: self._parse_mode_values(hvac_status_fan_values),
            HVACAction.PREHEATING: self._parse_mode_values(
                hvac_status_preheating_values
            ),
            HVACAction.IDLE: self._parse_mode_values(hvac_status_idle_values),
        }

        # Target mode mapping: single PLC value written to
        # preset_mode_address when a given HVAC mode is selected. A mode
        # whose value is MODE_VALUE_DISABLED (-1) is removed from the
        # thermostat's selectable HVAC mode list entirely - except OFF when
        # on_off_address is configured, since that address is then always
        # able to turn the device off regardless of preset_mode_off_value.
        self._preset_mode_values: dict[HVACMode, int] = {
            HVACMode.OFF: int(preset_mode_off_value),
            HVACMode.HEAT: int(preset_mode_heat_value),
            HVACMode.COOL: int(preset_mode_cool_value),
            HVACMode.HEAT_COOL: int(preset_mode_heat_cool_value),
            HVACMode.AUTO: int(preset_mode_auto_value),
            HVACMode.DRY: int(preset_mode_dry_value),
            HVACMode.FAN_ONLY: int(preset_mode_fan_only_value),
        }

        self._attr_hvac_modes = [
            mode
            for mode in (
                HVACMode.HEAT,
                HVACMode.COOL,
                HVACMode.HEAT_COOL,
                HVACMode.AUTO,
                HVACMode.DRY,
                HVACMode.FAN_ONLY,
            )
            if self._preset_mode_values[mode] != MODE_VALUE_DISABLED
        ]
        # OFF is only removable when on_off_address isn't configured: if it
        # is, OFF is always reachable that way regardless of
        # preset_mode_off_value, so it must stay selectable (otherwise the
        # thermostat could never be turned off).
        if on_off_address or self._preset_mode_values[HVACMode.OFF] != MODE_VALUE_DISABLED:
            self._attr_hvac_modes.insert(0, HVACMode.OFF)
        if not self._attr_hvac_modes:
            _LOGGER.warning(
                "All HVAC modes disabled for %s; falling back to OFF only", name
            )
            self._attr_hvac_modes = [HVACMode.OFF]

        # Reverse lookup used to read the mode back from PLC: only modes
        # with a real (non-disabled) preset value are included, so a stray
        # MODE_VALUE_DISABLED (-1) shared by several disabled modes -
        # including OFF when it's actually handled via on_off_address -
        # can't be mistaken for a real one.
        self._preset_value_to_mode: dict[int, HVACMode] = {}
        for mode in self._attr_hvac_modes:
            value = self._preset_mode_values[mode]
            if value == MODE_VALUE_DISABLED:
                continue
            if value in self._preset_value_to_mode:
                _LOGGER.warning(
                    "Duplicate preset mode value %s for %s (modes %s and %s); "
                    "reading the mode back from PLC may be ambiguous",
                    value,
                    name,
                    self._preset_value_to_mode[value].value,
                    mode.value,
                )
            self._preset_value_to_mode[value] = mode

        # Internal state: used as a fallback when live PLC feedback (via
        # on_off_address / preset_mode_address) isn't available or doesn't
        # map to a known mode, and restored on startup by RestoreEntity.
        self._hvac_mode = (
            HVACMode.HEAT_COOL
            if HVACMode.HEAT_COOL in self._attr_hvac_modes
            else self._attr_hvac_modes[0]
        )

    @staticmethod
    def _parse_mode_values(raw: str | None) -> list[int]:
        """Parse a comma-separated list of PLC integer values for a mode.

        MODE_VALUE_DISABLED (-1) is dropped from the result: it means this
        status should never be matched, effectively skipping it (e.g. an
        "off status" field of "-1" means no PLC value is ever read as OFF).
        """
        if not raw:
            return []
        values: list[int] = []
        for token in str(raw).split(","):
            token = token.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError:
                _LOGGER.warning("Ignoring invalid mode value %r", token)
                continue
            if value == MODE_VALUE_DISABLED:
                continue
            values.append(value)
        return values

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) is not None:
            # Restore HVAC mode
            try:
                hvac_mode = HVACMode(last_state.state)
                if hvac_mode in self._attr_hvac_modes:
                    self._hvac_mode = hvac_mode
            except ValueError:
                # Invalid mode, keep default
                pass

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.is_connected():
            return False
        # Check if current temperature reading is available
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:current_temp"
        return temp_topic in data and data[temp_topic] is not None

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature from PLC."""
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:current_temp"
        value = data.get(temp_topic)
        if value is not None and isinstance(value, (int, float)):
            if self._current_temp_scale is not None:
                rn, rx, sn, sx = self._current_temp_scale
                return scale_value(float(value), rn, rx, sn, sx)
            return float(value)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature read from PLC."""
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:target_temp"
        value = data.get(temp_topic)
        if value is not None and isinstance(value, (int, float)):
            if self._target_temp_scale is not None:
                rn, rx, sn, sx = self._target_temp_scale
                return scale_value(float(value), rn, rx, sn, sx)
            return float(value)
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode.

        Communication is bidirectional when the corresponding PLC address is
        configured: on_off_address (if False, the mode is always OFF) takes
        priority, then preset_mode_address is mapped back to a mode using
        the same values configured for writing it. Falls back to the last
        mode commanded from HA (or restored on startup) when neither is
        configured or the PLC value doesn't match a known mode.
        """
        data = self.coordinator.data or {}

        if self._on_off_address:
            on_off_value = data.get(f"{self._topic}:on_off")
            if on_off_value is not None and not bool(on_off_value):
                return HVACMode.OFF

        if self._preset_mode_address:
            preset_value = data.get(f"{self._topic}:preset_mode")
            if preset_value is not None:
                try:
                    mode = self._preset_value_to_mode.get(int(preset_value))
                except (TypeError, ValueError):
                    mode = None
                if mode is not None:
                    return mode

        if (
            self._on_off_address
            and data.get(f"{self._topic}:on_off")
            and self._hvac_mode == HVACMode.OFF
            and len(self._attr_hvac_modes) > 1
        ):
            # Device reports "on" but we have no more specific mode source
            # and our last known mode was OFF: assume some active mode
            # rather than showing OFF while the device is actually running.
            return (
                HVACMode.HEAT_COOL
                if HVACMode.HEAT_COOL in self._attr_hvac_modes
                else next(m for m in self._attr_hvac_modes if m != HVACMode.OFF)
            )

        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action.

        If hvac_status_address is configured, read the actual status from PLC
        and match it against the configured status value lists (see
        hvac_status_off_values/hvac_status_heating_values/
        hvac_status_cooling_values/hvac_status_drying_values/
        hvac_status_fan_values/hvac_status_preheating_values/
        hvac_status_idle_values). Otherwise infer from target vs current
        temperature comparison.
        """
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        # Use PLC status address if configured
        if self._hvac_status_address:
            data = self.coordinator.data or {}
            status_topic = f"{self._topic}:hvac_status"
            status = data.get(status_topic)
            if status is not None:
                status = int(status)
                for action, values in self._hvac_status_values.items():
                    if status in values:
                        return action
            # Any other value (including unconfigured/unmatched status)
            # is treated as IDLE.
            return HVACAction.IDLE

        # Fallback: infer from temperature comparison
        if self.target_temperature is not None and self.current_temperature is not None:
            if self.target_temperature > self.current_temperature:
                return HVACAction.HEATING
            elif self.target_temperature < self.current_temperature:
                return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["climate_type"] = "Setpoint Control"
        attrs["s7_target_temp_address"] = self._target_temp_address.upper()
        if self._preset_mode_address:
            attrs["s7_preset_mode_address"] = self._preset_mode_address.upper()
            attrs["s7_preset_mode_values"] = {
                mode.value: value for mode, value in self._preset_mode_values.items()
            }
        if self._hvac_status_address:
            attrs["s7_hvac_status_address"] = self._hvac_status_address.upper()
            attrs["s7_hvac_status_values"] = {
                action.value: values
                for action, values in self._hvac_status_values.items()
            }
        if self._on_off_address:
            attrs["s7_on_off_address"] = self._on_off_address.upper()
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature on PLC."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Clamp temperature to valid range (engineering units, unaffected by
        # any raw-PLC scaling)
        temperature = max(self._attr_min_temp, min(self._attr_max_temp, temperature))

        # Write target temperature to PLC
        if self._target_temp_scale is not None:
            rn, rx, sn, sx = self._target_temp_scale
            plc_value = inverse_scale_value(float(temperature), rn, rx, sn, sx)
        else:
            plc_value = float(temperature)
        await self.coordinator.write_batched(self._target_temp_address, plc_value)

        # If a mode is specified, set it first
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode not in self._attr_hvac_modes:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        self._hvac_mode = hvac_mode

        # Optionally write mode to PLC if preset_mode_address is configured.
        # Uses the target value configured for this mode (see
        # preset_mode_off_value/preset_mode_heat_value/
        # preset_mode_cool_value/preset_mode_heat_cool_value/
        # preset_mode_auto_value/preset_mode_dry_value/
        # preset_mode_fan_only_value). Skipped if that mode's value is
        # MODE_VALUE_DISABLED (-1): this happens for OFF when it's only
        # selectable thanks to on_off_address, in which case there is no
        # real PLC value to write here.
        if self._preset_mode_address:
            mode_value = self._preset_mode_values.get(hvac_mode)
            if mode_value is not None and mode_value != MODE_VALUE_DISABLED:
                await self.coordinator.write_batched(
                    self._preset_mode_address, mode_value
                )

        # Optionally write a simple on/off signal, for thermostats that have
        # no native OFF mode and are switched on/off by a separate output:
        # False when OFF is selected, True for any other mode.
        if self._on_off_address:
            await self.coordinator.write_batched(
                self._on_off_address, hvac_mode != HVACMode.OFF
            )

        self.async_write_ha_state()
