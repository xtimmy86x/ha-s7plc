from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .address import get_numeric_limits, parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_COMMAND_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_REAL_PRECISION,
    CONF_SCALE_RAW_MAX,
    CONF_SCALE_RAW_MIN,
    CONF_SCAN_INTERVAL,
    CONF_STEP,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_MULTIPLIER,
)
from .entity import S7BaseEntity
from .helpers import (
    DEVICE_CLASS_DEFAULT_UNITS,
    default_entity_name,
    get_coordinator_and_device_info,
    inverse_scale_value,
    scale_value,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Device class → default unit mapping (shared from helpers)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities: list[S7Number] = []
    for item in entry.options.get(CONF_NUMBERS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(address)
        area = item.get(CONF_AREA)
        topic = f"number:{address}"
        unique_id = f"{device_id}:{topic}"
        command_address = item.get(CONF_COMMAND_ADDRESS) or address
        min_value = item.get(CONF_MIN_VALUE)
        max_value = item.get(CONF_MAX_VALUE)
        step = item.get(CONF_STEP)
        device_class = item.get(CONF_DEVICE_CLASS)
        unit_of_measurement = item.get(CONF_UNIT_OF_MEASUREMENT)
        real_precision = item.get(CONF_REAL_PRECISION)
        value_multiplier = item.get(CONF_VALUE_MULTIPLIER)
        scale_raw_min = item.get(CONF_SCALE_RAW_MIN)
        scale_raw_max = item.get(CONF_SCALE_RAW_MAX)

        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, address, scan_interval, real_precision)
        entities.append(
            S7Number(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                command_address,
                min_value,
                max_value,
                step,
                device_class,
                unit_of_measurement,
                area,
                value_multiplier=value_multiplier,
                scale_raw_min=scale_raw_min,
                scale_raw_max=scale_raw_max,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Number(S7BaseEntity, NumberEntity):
    """Number entity representing a numeric PLC address."""

    _address_attr_name = "s7_state_address"

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        command_address: str | None,
        min_value: float | None,
        max_value: float | None,
        step: float | None,
        device_class: str | None = None,
        unit_of_measurement: str | None = None,
        suggested_area_id: str | None = None,
        value_multiplier: float | None = None,
        scale_raw_min: float | None = None,
        scale_raw_max: float | None = None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
            suggested_area_id=suggested_area_id,
        )
        self._command_address = command_address

        # Parse value_multiplier with defensive validation
        self._value_multiplier: float | None = None
        if value_multiplier not in (None, ""):
            try:
                self._value_multiplier = float(value_multiplier)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Invalid value_multiplier '%s' for number %s: %s. Ignoring.",
                    value_multiplier,
                    name,
                    err,
                )

        # Parse linear-scale parameters (all four must be present to activate).
        # When active, scale takes precedence over value_multiplier.
        self._scale_params: tuple[float, float, float, float] | None = None
        _sp = (scale_raw_min, scale_raw_max, min_value, max_value)
        if all(v not in (None, "") for v in _sp):
            try:
                rn, rx, sn, sx = (float(v) for v in _sp)  # type: ignore[arg-type]
                self._scale_params = (rn, rx, sn, sx)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Invalid scale parameters for number %s: %s. Ignoring.",
                    name,
                    err,
                )

        # Set device_class if provided
        if device_class:
            self._attr_device_class = device_class

            # Derive unit from device_class if not explicitly provided
            if not unit_of_measurement:
                dc_upper = device_class.upper()
                if dc_upper in DEVICE_CLASS_DEFAULT_UNITS:
                    unit = DEVICE_CLASS_DEFAULT_UNITS[dc_upper]
                    if unit is not None:
                        self._attr_native_unit_of_measurement = unit

        # Override with custom unit if provided
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement

        # Always initialize native attributes to avoid AttributeError
        self._attr_native_min_value = None
        self._attr_native_max_value = None
        self._attr_native_step = 1.0

        numeric_limits: tuple[float, float] | None = None
        try:
            tag = parse_tag(address)
        except (RuntimeError, ValueError):
            tag = None
        if tag is not None:
            numeric_limits = get_numeric_limits(tag.data_type)

        def _clamp(value: float | None) -> float | None:
            if value is None:
                return None
            clamped = float(value)
            if numeric_limits is not None:
                limit_min, limit_max = numeric_limits
                clamped = min(max(clamped, limit_min), limit_max)
            return clamped

        min_value_clamped = _clamp(min_value)
        max_value_clamped = _clamp(max_value)

        # If the user provided min/max, use them (clamped).
        # Otherwise, if available, use the native limits of the PLC data type.
        if min_value_clamped is not None:
            self._attr_native_min_value = min_value_clamped
        elif numeric_limits is not None:
            self._attr_native_min_value = float(numeric_limits[0])

        if max_value_clamped is not None:
            self._attr_native_max_value = max_value_clamped
        elif numeric_limits is not None:
            self._attr_native_max_value = float(numeric_limits[1])

        if step is not None:
            self._attr_native_step = float(step)

        # Scale min/max/step by multiplier so the UI works in display units.
        # The PLC raw value is always divided back when writing.
        # If scale_params are active, the UI range is simply [scale_min, scale_max].
        if self._scale_params is not None:
            rn, rx, sn, sx = self._scale_params
            self._attr_native_min_value = min(sn, sx)
            self._attr_native_max_value = max(sn, sx)
        elif self._value_multiplier is not None:
            if self._attr_native_min_value is not None:
                self._attr_native_min_value = (
                    self._attr_native_min_value * self._value_multiplier
                )
            if self._attr_native_max_value is not None:
                self._attr_native_max_value = (
                    self._attr_native_max_value * self._value_multiplier
                )
            self._attr_native_step = self._attr_native_step * self._value_multiplier

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self._topic)
        if value is None:
            return value
        # Linear scaling takes precedence over multiplier
        if self._scale_params is not None:
            try:
                rn, rx, sn, sx = self._scale_params
                return scale_value(float(value), rn, rx, sn, sx)
            except (TypeError, ValueError):
                return value
        if self._value_multiplier is None:
            return value
        try:
            return float(value) * self._value_multiplier
        except (TypeError, ValueError):
            return value

    async def async_set_native_value(self, value: float) -> None:
        await self._ensure_connected()
        if not self._command_address:
            raise HomeAssistantError("No command address configured for this entity.")

        # Convert display-unit value back to PLC raw value
        if self._scale_params is not None:
            rn, rx, sn, sx = self._scale_params
            plc_value = inverse_scale_value(float(value), rn, rx, sn, sx)
        elif self._value_multiplier is not None and self._value_multiplier != 0:
            plc_value = float(value) / self._value_multiplier
        else:
            plc_value = float(value)

        await self.coordinator.write_batched(self._command_address, plc_value)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._command_address:
            attrs["s7_command_address"] = self._command_address.upper()
        attrs["step"] = self._attr_native_step
        # min and max are exposed automatically by NumberEntity
        if self._scale_params is not None:
            rn, rx, sn, sx = self._scale_params
            attrs["scale_raw_min"] = rn
            attrs["scale_raw_max"] = rx
        elif self._value_multiplier is not None:
            attrs["value_multiplier"] = self._value_multiplier

        return attrs
