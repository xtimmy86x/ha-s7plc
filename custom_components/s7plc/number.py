from __future__ import annotations

import logging
import math

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .address import (
    get_numeric_limits,
    is_time_data_type,
    parse_tag,
    seconds_to_time,
    time_to_seconds,
)
from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_COMMAND_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_REAL_PRECISION,
    CONF_SCAN_INTERVAL,
    CONF_STEP,
    CONF_UID,
    CONF_UNIT_OF_MEASUREMENT,
)
from .entity import S7BaseEntity, async_configure_entity_availability
from .helpers import (
    DEVICE_CLASS_DEFAULT_UNITS,
    default_entity_name,
    get_coordinator_and_device_info,
)
from .value_conversion import (
    ConversionContext,
    ValueConversionError,
    convert_from_plc,
    convert_to_plc,
    normalize_value_conversion,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Device class → default unit mapping (shared from helpers)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, _ = get_coordinator_and_device_info(entry)

    entities: list[S7Number] = []
    for item in entry.options.get(CONF_NUMBERS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(address)
        area = item.get(CONF_AREA)
        topic = f"number:{address}"
        unique_id = item[CONF_UID]
        command_address = item.get(CONF_COMMAND_ADDRESS) or address
        min_value = item.get(CONF_MIN_VALUE)
        max_value = item.get(CONF_MAX_VALUE)
        step = item.get(CONF_STEP)
        device_class = item.get(CONF_DEVICE_CLASS)
        unit_of_measurement = item.get(CONF_UNIT_OF_MEASUREMENT)
        real_precision = item.get(CONF_REAL_PRECISION)

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
                value_conversion=normalize_value_conversion(item, "value"),
            )
        )

    if entities:
        await async_configure_entity_availability(
            entities, entry.options.get(CONF_NUMBERS, [])
        )
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
        value_conversion: dict | None = None,
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
        self._value_conversion = value_conversion
        self._conversion_context = ConversionContext.from_address(
            "value", command_address or address, "bidirectional"
        )
        try:
            self._is_time = is_time_data_type(parse_tag(address).data_type)
        except (RuntimeError, ValueError):
            self._is_time = False

        # Set device_class if provided
        if self._is_time:
            self._attr_device_class = "duration"
            self._attr_native_unit_of_measurement = "s"
        elif device_class:
            self._attr_device_class = device_class

            # Derive unit from device_class if not explicitly provided
            if not unit_of_measurement:
                dc_upper = device_class.upper()
                if dc_upper in DEVICE_CLASS_DEFAULT_UNITS:
                    unit = DEVICE_CLASS_DEFAULT_UNITS[dc_upper]
                    if unit is not None:
                        self._attr_native_unit_of_measurement = unit

        # Override with custom unit if provided
        if unit_of_measurement and not self._is_time:
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
        elif self._is_time:
            self._attr_native_step = 0.001

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self._topic)
        if value is None:
            return value
        if self._is_time:
            try:
                value = time_to_seconds(value)
            except (TypeError, ValueError):
                _LOGGER.warning("Invalid TIME value for %s: %r", self._topic, value)
                return None
        if self._value_conversion:
            try:
                return convert_from_plc(
                    value, self._value_conversion, self._conversion_context
                )
            except ValueConversionError as err:
                _LOGGER.warning(
                    "Value conversion failed for number %s channel value: %s",
                    self.name,
                    err,
                )
                return None
        return value

    async def async_set_native_value(self, value: float) -> None:
        await self._ensure_connected()
        if not self._command_address:
            raise HomeAssistantError("No command address configured for this entity.")

        if self._is_time and not math.isfinite(float(value)):
            raise HomeAssistantError("TIME/number value must be finite.")

        if self._value_conversion:
            try:
                plc_value = convert_to_plc(
                    value, self._value_conversion, self._conversion_context
                )
            except ValueConversionError as err:
                raise HomeAssistantError(str(err)) from err
        # Convert display-unit value back to PLC raw value. TIME scaling and
        # multipliers operate in HA seconds; conversion to pyS7 timedelta is last.
        else:
            plc_value = float(value)

        if self._is_time:
            try:
                plc_value = seconds_to_time(plc_value)
            except (TypeError, ValueError) as err:
                raise HomeAssistantError(str(err)) from err

        await self.coordinator.write_batched(self._command_address, plc_value)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._command_address:
            attrs["s7_command_address"] = self._command_address.upper()
        attrs["step"] = self._attr_native_step
        # min and max are exposed automatically by NumberEntity
        return attrs
