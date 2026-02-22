from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
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
    CONF_SCAN_INTERVAL,
    CONF_STEP,
    CONF_UNIT_OF_MEASUREMENT,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Map NumberDeviceClass to default units
NUMBER_DEVICE_CLASS_UNITS: dict[str, str | None] = {
    "APPARENT_POWER": "VA",
    "AQI": None,
    "ATMOSPHERIC_PRESSURE": "hPa",
    "BATTERY": PERCENTAGE,
    "CO": "ppm",
    "CO2": "ppm",
    "CURRENT": UnitOfElectricCurrent.AMPERE,
    "DATA_RATE": "B/s",
    "DATA_SIZE": "B",
    "DISTANCE": "m",
    "DURATION": "s",
    "ENERGY": "kWh",
    "ENERGY_STORAGE": "kWh",
    "FREQUENCY": "Hz",
    "GAS": "m³",
    "HUMIDITY": PERCENTAGE,
    "ILLUMINANCE": "lx",
    "IRRADIANCE": "W/m²",
    "MOISTURE": PERCENTAGE,
    "MONETARY": None,
    "NITROGEN_DIOXIDE": "ppb",
    "NITROUS_OXIDE": "ppb",
    "OZONE": "ppb",
    "PH": None,
    "PM1": "µg/m³",
    "PM10": "µg/m³",
    "PM25": "µg/m³",
    "POWER": UnitOfPower.WATT,
    "POWER_FACTOR": None,
    "PRECIPITATION": "mm",
    "PRECIPITATION_INTENSITY": "mm/h",
    "PRESSURE": "hPa",
    "REACTIVE_POWER": "var",
    "SIGNAL_STRENGTH": "dBm",
    "SOUND_PRESSURE": "dB",
    "SPEED": "m/s",
    "SULPHUR_DIOXIDE": "ppb",
    "TEMPERATURE": UnitOfTemperature.CELSIUS,
    "VOLATILE_ORGANIC_COMPOUNDS": "ppb",
    "VOLATILE_ORGANIC_COMPOUNDS_PARTS": "ppm",
    "VOLTAGE": UnitOfElectricPotential.VOLT,
    "VOLUME": "m³",
    "VOLUME_FLOW_RATE": "L/min",
    "VOLUME_STORAGE": "m³",
    "WATER": "m³",
    "WEIGHT": "kg",
    "WIND_SPEED": "m/s",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities: list[S7Number] = []
    for item in entry.options.get(CONF_NUMBERS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), address
        )
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
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Number(S7BaseEntity, NumberEntity):
    """Number entity representing a numeric PLC address."""

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

        # Set device_class if provided
        if device_class:
            self._attr_device_class = device_class

            # Derive unit from device_class if not explicitly provided
            if not unit_of_measurement:
                dc_upper = device_class.upper()
                if dc_upper in NUMBER_DEVICE_CLASS_UNITS:
                    unit = NUMBER_DEVICE_CLASS_UNITS[dc_upper]
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

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._topic)

    async def async_set_native_value(self, value: float) -> None:
        await self._ensure_connected()
        if not self._command_address:
            raise HomeAssistantError("No command address configured for this entity.")

        await self._async_write(
            self._command_address,
            float(value),
            error_msg=(
                f"Failed to write {value:.3f} to PLC address {self._command_address}"
            ),
        )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        attrs = dict(super().extra_state_attributes or {})
        attrs["min_value"] = self.min_value
        attrs["max_value"] = self.max_value
        attrs["step"] = self.step

        return attrs
