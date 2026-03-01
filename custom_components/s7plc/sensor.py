from __future__ import annotations

import logging
import numbers

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
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
from .helpers import (
    DEVICE_CLASS_DEFAULT_UNITS,
    default_entity_name,
    get_coordinator_and_device_info,
)

_LOGGER = logging.getLogger(__name__)

# Boolean-like states used by EntitySync to map HA entity states to BIT values.
# Covers many HA domains: switch, light, cover, lock, alarm, person, vacuum, etc.
_TRUE_STATES = frozenset(
    {
        "on",
        "true",
        "1",
        "yes",
        "open",
        "opening",  # cover
        "unlocked",
        "unlocking",  # lock
        "home",  # person / device_tracker
        "armed_home",
        "armed_away",  # alarm_control_panel
        "armed_night",
        "armed_vacation",
        "armed_custom_bypass",
        "arming",
        "triggered",
        "pending",
        "cleaning",
        "returning",  # vacuum
        "playing",
        "buffering",  # media_player
        "above_horizon",  # sun
        "active",  # generic active state
    }
)
_FALSE_STATES = frozenset(
    {
        "off",
        "false",
        "0",
        "no",
        "closed",
        "closing",  # cover
        "locked",
        "locking",
        "jammed",  # lock
        "not_home",  # person / device_tracker
        "disarmed",  # alarm_control_panel
        "docked",
        "idle",
        "paused",  # vacuum
        "error",  # vacuum / generic error
        "standby",  # media_player
        "below_horizon",  # sun
        "inactive",  # generic inactive state
    }
)

# Coordinator is used to centralize data updates
PARALLEL_UPDATES = 0


# Sensor-only candidate names not already in DEVICE_CLASS_DEFAULT_UNITS
# (currently all covered by the shared map)

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
    for name, unit in DEVICE_CLASS_DEFAULT_UNITS.items()
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
        name = item.get(CONF_NAME) or default_entity_name(address)
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

        name = item.get(CONF_NAME) or default_entity_name(f"Entity Sync {address}")
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

    _address_attr_name = "s7_state_address"

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
        if self.coordinator.is_string_plan(self._topic):
            return True

        plan = self.coordinator.get_batch_plan(self._topic)
        if plan is not None and plan.tag.data_type == DataType.CHAR:
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
        self._initial_write_pending: bool = False
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
        self._is_binary = self._data_type == DataType.BIT

        # State class is set to MEASUREMENT for numeric syncs,
        # but left as None for binary syncs to allow on/off states.
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """React to coordinator data updates.

        On each coordinator poll, if we never managed to write the initial
        source-entity value (e.g. PLC was not connected at startup), retry.
        Once _last_written_value is set this check becomes a no-op.

        _initial_write_pending prevents creating multiple concurrent tasks
        when the coordinator polls faster than the write coroutine completes.
        """
        if (
            self._last_written_value is None
            and not self._initial_write_pending
            and self.coordinator.is_connected()
        ):
            source_state = self.hass.states.get(self._source_entity)
            if source_state is not None and source_state.state not in (
                "unknown",
                "unavailable",
            ):
                self._initial_write_pending = True
                self.hass.async_create_task(self._async_write_to_plc(source_state))
        super()._handle_coordinator_update()

    async def _async_write_to_plc(self, source_state: State) -> None:
        """Write value to PLC."""
        # --- value conversion (only part that differs) ---
        if self._is_binary:
            value = self._parse_binary_value(source_state)
        else:
            value = self._parse_numeric_value(source_state)

        if value is None:
            self._error_count += 1
            self.async_write_ha_state()
            return

        # --- common write path ---
        if not self.coordinator.is_connected():
            _LOGGER.debug(
                "EntitySync %s: Cannot write, coordinator not connected", self.name
            )
            self._error_count += 1
            self.async_write_ha_state()
            return

        try:
            await self.coordinator.write_batched(self._address, value)
            success = True
        except HomeAssistantError:
            success = False

        _LOGGER.debug(
            "EntitySync %s: Write attempt of %s to %s returned %s",
            self.name,
            value,
            self._address,
            success,
        )

        if success:
            self._last_written_value = (
                (1.0 if value else 0.0) if self._is_binary else value
            )
            self._write_count += 1
            _LOGGER.debug(
                "EntitySync %s: Successfully wrote %s to %s",
                self.name,
                value,
                self._address,
            )
        else:
            self._error_count += 1
            _LOGGER.error(
                "EntitySync %s: Failed to write %s to %s",
                self.name,
                value,
                self._address,
            )

        # Allow the next coordinator poll to schedule a fresh retry if needed.
        self._initial_write_pending = False
        self.async_write_ha_state()

    def _parse_binary_value(self, source_state: State) -> bool | None:
        """Parse a HA state to boolean for BIT addresses.

        Returns None when the state cannot be converted.
        """
        state_str = (
            source_state.state.lower()
            if isinstance(source_state.state, str)
            else str(source_state.state)
        )

        if state_str in _TRUE_STATES:
            return True
        if state_str in _FALSE_STATES:
            return False

        # Try numeric conversion for BIT (0 or 1)
        try:
            return bool(float(source_state.state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Cannot convert source entity %s state '%s' to "
                "boolean value for BIT address",
                self._source_entity,
                source_state.state,
            )
            return None

    def _parse_numeric_value(self, source_state: State) -> float | None:
        """Parse a HA state to float for non-BIT addresses.

        Returns None when the state cannot be converted.
        """
        try:
            return float(source_state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Cannot convert source entity %s state '%s' to numeric value",
                self._source_entity,
                source_state.state,
            )
            return None

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
            "s7_write_address": self._address.upper(),
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
        return self.coordinator.is_connected()
