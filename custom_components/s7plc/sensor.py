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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.event import async_track_state_change_event

from .address import DataType, parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_SYNC,
    CONF_REAL_PRECISION,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SOURCE_ENTITY,
    CONF_STATE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_MULTIPLIER,
)
from .entity import S7BaseEntity
from .helpers import default_entity_name, get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)

# Coordinator is used to centralize data updates
PARALLEL_UPDATES = 0


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
    coord, device_info, device_id = get_coordinator_and_device_info(entry)

    entities = []
    for item in entry.options.get(CONF_SENSORS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), address
        )
        area = item.get(CONF_AREA)
        topic = f"sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        value_multiplier = item.get(CONF_VALUE_MULTIPLIER)
        unit_of_measurement = item.get(CONF_UNIT_OF_MEASUREMENT)
        state_class = item.get(CONF_STATE_CLASS)
        real_precision = item.get(CONF_REAL_PRECISION)
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await coord.add_item(topic, address, scan_interval, real_precision)
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
                unit_of_measurement,
                state_class,
                area,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()

    # Setup Entity Syncs
    sync_entities = []
    for item in entry.options.get(CONF_ENTITY_SYNC, []):
        address = item.get(CONF_ADDRESS)
        source_entity = item.get(CONF_SOURCE_ENTITY)

        if not address or not source_entity:
            _LOGGER.debug(
                "Skipping entity sync with missing address or source entity: "
                "address=%s, source=%s",
                address,
                source_entity,
            )
            continue

        name = item.get(CONF_NAME) or default_entity_name(
            device_info.get("name"), f"Entity Sync {address}"
        )
        area = item.get(CONF_AREA)
        unique_id = f"{device_id}:entity_sync:{address}"

        sync_entities.append(
            S7EntitySync(
                coord,
                name,
                unique_id,
                device_info,
                address,
                source_entity,
                area,
            )
        )

    if sync_entities:
        async_add_entities(sync_entities)


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
        unit_of_measurement: str | None = None,
        state_class: str | None = None,
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

        # Parse value_multiplier with defensive validation
        self._value_multiplier = None
        if value_multiplier not in (None, ""):
            try:
                self._value_multiplier = float(value_multiplier)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Invalid value_multiplier '%s' for sensor %s: %s. Ignoring.",
                    value_multiplier,
                    name,
                    err,
                )

        self._custom_unit = unit_of_measurement if unit_of_measurement else None

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

        # Override with custom unit if provided
        if self._custom_unit:
            self._attr_native_unit_of_measurement = self._custom_unit

        # Set state_class: user config takes precedence,
        # otherwise derive from device_class
        if state_class and state_class != "none":
            # User explicitly configured state_class
            self._attr_state_class = state_class
        elif not is_string_or_char and sensor_device_class is not None:
            # Auto-derive state_class from device_class
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


class S7EntitySync(S7BaseEntity, SensorEntity):
    """Entity sync that sends HA entity values to PLC."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    # State class is set to MEASUREMENT for numeric syncs,
    # but left as None for binary syncs to allow on/off states.

    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        address: str,
        source_entity: str,
        suggested_area_id: str | None = None,
    ) -> None:
        """Initialize the entity sync."""
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=None,
            suggested_area_id=suggested_area_id,
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

        # Detect if this is a binary entity sync (BIT address)
        from .address import DataType

        self._is_binary = self._data_type == DataType.BIT

        if not self._is_binary:
            self._attr_state_class = SensorStateClass.MEASUREMENT

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
            self.hass.async_create_task(self._async_write_to_plc(new_state))

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
        state_str = (
            source_state.state.lower()
            if isinstance(source_state.state, str)
            else str(source_state.state)
        )

        # Check if this is a BIT address
        from .address import DataType

        is_bit_address = self._data_type == DataType.BIT

        if is_bit_address:
            # Handle boolean/binary states for BIT addresses
            bool_value = None

            # Try to parse as boolean
            if state_str in ("on", "true", "1", "yes"):
                bool_value = True
            elif state_str in ("off", "false", "0", "no"):
                bool_value = False
            else:
                # Try numeric conversion for BIT (0 or 1)
                try:
                    num_value = float(source_state.state)
                    bool_value = bool(num_value)
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        "Cannot convert source entity %s state '%s' to "
                        "boolean value for BIT address",
                        self._source_entity,
                        source_state.state,
                    )
                    self._error_count += 1
                    self.async_write_ha_state()
                    return

            # Check if coordinator is connected
            if not self._coord.is_connected():
                _LOGGER.debug(
                    "EntitySync %s: Cannot write, coordinator not connected", self.name
                )
                self._error_count += 1
                self.async_write_ha_state()
                return

            # Write boolean to PLC
            try:
                await self._coord.write_batched(self._address, bool_value)
                success = True
            except HomeAssistantError:
                success = False

            _LOGGER.debug(
                "EntitySync %s: Write attempt of boolean value %s to %s returned %s",
                self.name,
                bool_value,
                self._address,
                success,
            )

            if success:
                self._last_written_value = 1.0 if bool_value else 0.0
                self._write_count += 1
                _LOGGER.debug(
                    "EntitySync %s: Successfully wrote boolean value %s to %s",
                    self.name,
                    bool_value,
                    self._address,
                )
            else:
                self._error_count += 1
                _LOGGER.error(
                    "EntitySync %s: Failed to write boolean value %s to %s",
                    self.name,
                    bool_value,
                    self._address,
                )
        else:
            # Handle numeric values for non-BIT addresses
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
                    "EntitySync %s: Cannot write, coordinator not connected", self.name
                )
                self._error_count += 1
                self.async_write_ha_state()
                return

            # Write to PLC
            try:
                await self._coord.write_batched(self._address, value)
                success = True
            except HomeAssistantError:
                success = False

            _LOGGER.debug(
                "EntitySync %s: Write attempt of value %.2f to %s returned %s",
                self.name,
                value,
                self._address,
                success,
            )

            if success:
                self._last_written_value = value
                self._write_count += 1
                _LOGGER.debug(
                    "EntitySync %s: Successfully wrote value %.2f to %s",
                    self.name,
                    value,
                    self._address,
                )
            else:
                self._error_count += 1
                _LOGGER.error(
                    "EntitySync %s: Failed to write value %.2f to %s",
                    self.name,
                    value,
                    self._address,
                )

        self.async_write_ha_state()

    @property
    def native_value(self) -> str | float | None:
        """Return the last written value."""
        if self._last_written_value is None:
            return None

        # For binary entity syncs, return on/off string
        if self._is_binary:
            return "on" if self._last_written_value else "off"

        return self._last_written_value

    @property
    def icon(self) -> str:
        """Return icon based on entity sync type."""
        if self._is_binary:
            # Use toggle icon for binary entity syncs
            if self._last_written_value:
                return "mdi:toggle-switch"
            return "mdi:toggle-switch-off-outline"
        return "mdi:upload"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        attrs = {
            "s7_address": self._address.upper(),
            "source_entity": self._source_entity,
            "write_count": self._write_count,
            "error_count": self._error_count,
            "entity_sync_type": "binary" if self._is_binary else "numeric",
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
