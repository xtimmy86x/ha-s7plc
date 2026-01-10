from __future__ import annotations

import logging
import numbers

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_NAME,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .address import DataType, parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_REAL_PRECISION,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SOURCE_ENTITY,
    CONF_VALUE_MULTIPLIER,
    CONF_WRITERS,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)


_CANDIDATE_UNITS: dict[str, str | None] = {
    # Environmental
    "TEMPERATURE": UnitOfTemperature.CELSIUS,
    "TEMPERATURE_DELTA": UnitOfTemperature.CELSIUS,
    "HUMIDITY": PERCENTAGE,
    "MOISTURE": PERCENTAGE,
    "ILLUMINANCE": "lx",
    "IRRADIANCE": "W/m²",
    "ATMOSPHERIC_PRESSURE": UnitOfPressure.HPA,
    "PRESSURE": UnitOfPressure.HPA,
    "PRECIPITATION": "mm",
    "PRECIPITATION_INTENSITY": "mm/h",
    "WIND_SPEED": UnitOfSpeed.METERS_PER_SECOND,
    "SPEED": UnitOfSpeed.METERS_PER_SECOND,
    "WIND_DIRECTION": "°",
    # Electrical / energy
    "POWER": UnitOfPower.WATT,
    "APPARENT_POWER": "VA",
    "REACTIVE_POWER": "var",
    "POWER_FACTOR": None,  # unitless by default
    "ENERGY": UnitOfEnergy.KILO_WATT_HOUR,
    "ENERGY_STORAGE": UnitOfEnergy.KILO_WATT_HOUR,
    "REACTIVE_ENERGY": "varh",
    "VOLTAGE": UnitOfElectricPotential.VOLT,
    "CURRENT": UnitOfElectricCurrent.AMPERE,
    "FREQUENCY": UnitOfFrequency.HERTZ,
    # Air quality
    "AQI": None,
    "CO2": CONCENTRATION_PARTS_PER_MILLION,
    "CO": CONCENTRATION_PARTS_PER_MILLION,
    "OZONE": CONCENTRATION_PARTS_PER_BILLION,
    "NITROGEN_DIOXIDE": CONCENTRATION_PARTS_PER_BILLION,
    "PM1": "µg/m³",
    "PM25": "µg/m³",
    "PM4": "µg/m³",
    "PM10": "µg/m³",
    # Misc
    "BATTERY": PERCENTAGE,
    "SIGNAL_STRENGTH": "dBm",
    "SOUND_PRESSURE": "dB",
    "PH": None,
    "DURATION": "s",
    "DISTANCE": "m",
    "VOLUME": "m³",
    "VOLUME_STORAGE": "m³",
    "VOLUME_FLOW_RATE": "L/min",
    "WEIGHT": "kg",
    "WATER": "m³",
    "GAS": "m³",
    "DATA_RATE": "B/s",
    "DATA_SIZE": "B",
    # Non-numeric / special
    "DATE": None,
    "TIMESTAMP": None,
    "ENUM": None,
    "MONETARY": None,
}

TOTAL_INCREASING_CLASSES = {
    SensorDeviceClass.ENERGY,
    SensorDeviceClass.ENERGY_STORAGE,
    getattr(SensorDeviceClass, "REACTIVE_ENERGY", None),
}

NO_MEASUREMENT_CLASSES = {
    SensorDeviceClass.GAS,
    SensorDeviceClass.WATER,
    getattr(SensorDeviceClass, "DATE", None),
    getattr(SensorDeviceClass, "TIMESTAMP", None),
    getattr(SensorDeviceClass, "ENUM", None),
    getattr(SensorDeviceClass, "MONETARY", None),
    SensorDeviceClass.VOLUME,
    # Note: VOLUME_STORAGE is allowed as a device_class,
    # but treat it as "stored amount" and do not mark it as MEASUREMENT
    # to avoid "impossible state_class" warnings in some setups.
    getattr(SensorDeviceClass, "VOLUME_STORAGE", None),
}

# Build a mapping using only device classes that exist
DEVICE_CLASS_UNITS: dict[SensorDeviceClass, str | None] = {
    getattr(SensorDeviceClass, name): unit
    for name, unit in _CANDIDATE_UNITS.items()
    if hasattr(SensorDeviceClass, name)
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(hass, entry)

    entities = []
    for item in entry.options.get(CONF_SENSORS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), address
        )
        topic = f"sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        value_multiplier = item.get(CONF_VALUE_MULTIPLIER)
        real_precision = item.get(CONF_REAL_PRECISION)
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await hass.async_add_executor_job(
            coord.add_item, topic, address, scan_interval, real_precision
        )
        entities.append(
            S7Sensor(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                device_class,
                value_multiplier,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()

    # Setup Writers
    writer_entities = []
    for item in entry.options.get(CONF_WRITERS, []):
        address = item.get(CONF_ADDRESS)
        source_entity = item.get(CONF_SOURCE_ENTITY)

        if not address or not source_entity:
            _LOGGER.debug(
                "Skipping writer with missing address or source entity: "
                "address=%s, source=%s",
                address,
                source_entity,
            )
            continue

        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), f"Writer {address}"
        )
        unique_id = f"{device_id}:writer:{address}"

        writer_entities.append(
            S7Writer(
                coord,
                name,
                unique_id,
                device_info,
                address,
                source_entity,
            )
        )

    if writer_entities:
        async_add_entities(writer_entities)


class S7Sensor(S7BaseEntity, SensorEntity):
    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        device_class: str | None,
        value_multiplier: float | None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )
        self._value_multiplier = (
            float(value_multiplier) if value_multiplier not in (None, "") else None
        )

        # Check if this is a string or char sensor
        is_string_or_char = self._is_string_or_char_sensor()

        sensor_device_class = None

        # Don't set device_class or state_class for string/char sensors
        if not is_string_or_char and device_class:
            try:
                sensor_device_class = SensorDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)
            else:
                self._attr_device_class = sensor_device_class
                unit = DEVICE_CLASS_UNITS.get(sensor_device_class)
                if unit is not None:
                    self._attr_native_unit_of_measurement = unit

        # Assign the correct state_class.
        if not is_string_or_char and sensor_device_class is not None:
            if sensor_device_class in TOTAL_INCREASING_CLASSES:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING

            elif sensor_device_class in NO_MEASUREMENT_CLASSES:
                # Instantaneous tank level / stored volume -> no state_class
                # (HA disallows MEASUREMENT here)
                self._attr_state_class = None

            else:
                # Default for instantaneous numeric sensors
                if sensor_device_class not in (
                    getattr(SensorDeviceClass, "DATE", None),
                    getattr(SensorDeviceClass, "TIMESTAMP", None),
                    getattr(SensorDeviceClass, "ENUM", None),
                ):
                    self._attr_state_class = SensorStateClass.MEASUREMENT

    def _is_string_or_char_sensor(self) -> bool:
        """Check if this sensor is a string or char data type."""
        # Check if it's a string plan (multi-char)
        if self._topic in self.coordinator._plans_str:
            return True

        # Check if it's a char plan (single char)
        if self._topic in self.coordinator._plans_batch:
            plan = self.coordinator._plans_batch[self._topic]
            if plan.tag.data_type == DataType.CHAR:
                return True

        return False

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self._topic)
        if self._value_multiplier is None or value is None:
            return value
        if isinstance(value, bool):
            return value
        if isinstance(value, numbers.Number):
            return value * self._value_multiplier
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Cannot apply multiplier to non-numeric value for %s: %s",
                self._topic,
                value,
            )
            return value
        return numeric_value * self._value_multiplier

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._value_multiplier is not None:
            attrs["value_multiplier"] = self._value_multiplier
        return attrs


class S7Writer(S7BaseEntity, SensorEntity):
    """Writer entity that sends HA entity values to PLC."""

    _attr_icon = "mdi:upload"

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        address: str,
        source_entity: str,
    ) -> None:
        """Initialize the writer."""
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=None,
        )
        self._address = address
        self._source_entity = source_entity
        self._last_written_value: float | None = None
        self._write_count = 0
        self._error_count = 0

        # Parse address to get data type limits
        try:
            tag = parse_tag(address)
            self._data_type = tag.data_type
        except (RuntimeError, ValueError):
            _LOGGER.error("Invalid PLC address: %s", address)
            self._data_type = None

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()

        # Track state changes of the source entity
        @callback
        def state_changed(event: Event) -> None:
            """Handle state changes of source entity."""
            new_state: State | None = event.data.get("new_state")
            if new_state is None:
                return

            # Schedule write on next update cycle
            self.hass.create_task(self._async_write_to_plc(new_state))

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity], state_changed
            )
        )

        # Write initial value
        source_state = self.hass.states.get(self._source_entity)
        if source_state is not None:
            await self._async_write_to_plc(source_state)

    async def _async_write_to_plc(self, source_state: State) -> None:
        """Write value to PLC."""
        try:
            # Get numeric value from state
            value = float(source_state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Cannot convert source entity %s state '%s' to numeric value",
                self._source_entity,
                source_state.state,
            )
            self._error_count += 1
            self.async_write_ha_state()
            return

        # Check if coordinator is connected
        if not self._coord.is_connected():
            _LOGGER.debug(
                "Writer %s: Cannot write, coordinator not connected", self.name
            )
            self._error_count += 1
            self.async_write_ha_state()
            return

        # Write to PLC
        success = await self.hass.async_add_executor_job(
            self._coord.write_number, self._address, value
        )
        _LOGGER.debug(
            "Writer %s: Write attempt of value %.2f to %s returned %s",
            self.name,
            value,
            self._address,
            success,
        )

        if success:
            self._last_written_value = value
            self._write_count += 1
            _LOGGER.debug(
                "Writer %s: Successfully wrote value %.2f to %s",
                self.name,
                value,
                self._address,
            )
        else:
            self._error_count += 1
            _LOGGER.error(
                "Writer %s: Failed to write value %.2f to %s",
                self.name,
                value,
                self._address,
            )

        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the last written value."""
        return self._last_written_value

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        attrs = {
            "s7_address": self._address.upper(),
            "source_entity": self._source_entity,
            "write_count": self._write_count,
            "error_count": self._error_count,
        }

        # Get source entity current state
        source_state = self.hass.states.get(self._source_entity)
        if source_state:
            attrs["source_state"] = source_state.state
            attrs["source_last_updated"] = source_state.last_updated.isoformat()

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coord.is_connected()
