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
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_PRESET_MODE_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_TEMP_STEP,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up S7 climate entities."""
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    for item in entry.options.get(CONF_CLIMATES, []):
        current_temp_address = item.get(CONF_CURRENT_TEMPERATURE_ADDRESS)
        if not current_temp_address:
            _LOGGER.warning(
                "Climate entity requires current_temperature_address, "
                "skipping item: %s",
                item,
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

            topic = f"climate_direct:{current_temp_address}"
            unique_id = f"{device_id}:{topic}"

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
                )
            )

        elif control_mode == CONTROL_MODE_SETPOINT:
            # Mode 2: Setpoint control - PLC manages heating/cooling autonomously
            target_temp_address = item.get(CONF_TARGET_TEMPERATURE_ADDRESS)
            if not target_temp_address:
                _LOGGER.debug(
                    "Skipping setpoint control climate "
                    "without target_temperature_address"
                )
                continue

            topic = f"climate_setpoint:{current_temp_address}"
            unique_id = f"{device_id}:{topic}"

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

            # Optional: HVAC status address (0=off, 1=heating, 2=cooling)
            hvac_status_address = item.get(CONF_HVAC_STATUS_ADDRESS)
            if hvac_status_address:
                await coord.add_item(
                    f"{topic}:hvac_status", hvac_status_address, scan_interval
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

    async def _update_outputs(self) -> None:
        """Update PLC heating/cooling outputs based on mode and target temperature."""
        if self._hvac_mode == HVACMode.OFF:
            # Turn off all outputs
            if self._heating_output_address:
                await self.coordinator.write_batched(
                    self._heating_output_address, False
                )
            if self._cooling_output_address:
                await self.coordinator.write_batched(
                    self._cooling_output_address, False
                )
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
        if self._heating_output_address:
            if self._hvac_mode in (HVACMode.HEAT, HVACMode.HEAT_COOL):
                await self.coordinator.write_batched(
                    self._heating_output_address, heating_needed
                )
            else:
                await self.coordinator.write_batched(
                    self._heating_output_address, False
                )

        # Control cooling output
        if self._cooling_output_address:
            if self._hvac_mode in (HVACMode.COOL, HVACMode.HEAT_COOL):
                await self.coordinator.write_batched(
                    self._cooling_output_address, cooling_needed
                )
            else:
                await self.coordinator.write_batched(
                    self._cooling_output_address, False
                )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Re-evaluate outputs when temperature changes
        if self._hvac_mode != HVACMode.OFF and self._target_temperature is not None:
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
        self._target_temp_address = target_temp_address
        self._preset_mode_address = preset_mode_address
        self._hvac_status_address = hvac_status_address

        self._attr_min_temp = float(min_temp)
        self._attr_max_temp = float(max_temp)
        self._attr_target_temperature_step = float(temp_step)

        # Internal state
        self._hvac_mode = HVACMode.HEAT_COOL

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
            return float(value)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature read from PLC."""
        data = self.coordinator.data or {}
        temp_topic = f"{self._topic}:target_temp"
        value = data.get(temp_topic)
        if value is not None and isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action.

        If hvac_status_address is configured, read the actual status from PLC
        (0=OFF, 1=HEATING, 2=COOLING). Otherwise infer from target vs current
        temperature comparison.
        """
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        # Use PLC status address if configured
        if self._hvac_status_address:
            data = self.coordinator.data or {}
            status_topic = f"{self._topic}:hvac_status"
            status = data.get(status_topic)
            if status is not None:
                status = int(status)
                if status == 0:
                    return HVACAction.OFF
                if status == 1:
                    return HVACAction.HEATING
                if status == 2:
                    return HVACAction.COOLING
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
        if self._hvac_status_address:
            attrs["s7_hvac_status_address"] = self._hvac_status_address.upper()
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature on PLC."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Clamp temperature to valid range
        temperature = max(self._attr_min_temp, min(self._attr_max_temp, temperature))

        # Write target temperature to PLC
        await self.coordinator.write_batched(
            self._target_temp_address, float(temperature)
        )

        # If a mode is specified, set it first
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode not in self._attr_hvac_modes:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        self._hvac_mode = hvac_mode

        # Optionally write mode to PLC if preset_mode_address is configured
        # OFF = 0, HEAT_COOL = 1 (or any other mapping you need)
        if self._preset_mode_address:
            match hvac_mode:
                case HVACMode.HEAT_COOL:
                    mode_value = 3
                case HVACMode.COOL:
                    mode_value = 2
                case HVACMode.HEAT:
                    mode_value = 1
                case _:
                    mode_value = 0
            await self.coordinator.write_batched(self._preset_mode_address, mode_value)

        self.async_write_ha_state()
