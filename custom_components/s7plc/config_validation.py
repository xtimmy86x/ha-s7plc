from __future__ import annotations

import math
from typing import Any

from homeassistant.const import CONF_NAME

from .address import DataType, get_numeric_limits, parse_tag
from .const import (
    AVAILABILITY_MODE_BIT,
    AVAILABILITY_MODE_CONNECTION,
    AVAILABILITY_MODES,
    CONF_ADDRESS,
    CONF_AREA,
    CONF_AVAILABILITY_ADDRESS,
    CONF_AVAILABILITY_MODE,
    CONF_BINARY_SENSORS,
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_SCALE,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_COOLING_ACTION_ADDRESS,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_POSITION_FEEDBACK,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVER_STATUS_CLOSED_VALUES,
    CONF_COVER_STATUS_CLOSING_VALUES,
    CONF_COVER_STATUS_OPEN_VALUES,
    CONF_COVER_STATUS_OPENING_VALUES,
    CONF_COVER_STATUS_STOPPED_VALUES,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_SYNC,
    CONF_HEATING_ACTION_ADDRESS,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_HVAC_STATUS_ADDRESS,
    CONF_HVAC_STATUS_COOLING_VALUES,
    CONF_HVAC_STATUS_DEFROSTING_VALUES,
    CONF_HVAC_STATUS_DRYING_VALUES,
    CONF_HVAC_STATUS_FAN_VALUES,
    CONF_HVAC_STATUS_HEATING_VALUES,
    CONF_HVAC_STATUS_IDLE_VALUES,
    CONF_HVAC_STATUS_OFF_VALUES,
    CONF_HVAC_STATUS_PREHEATING_VALUES,
    CONF_INVERT_POSITION,
    CONF_INVERT_STATE,
    CONF_INVERT_TILT,
    CONF_LIGHTS,
    CONF_MAX_TEMP,
    CONF_MAX_VALUE,
    CONF_MIN_TEMP,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_ON_OFF_ADDRESS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_PATTERN,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_PRESET_MODE_ADDRESS,
    CONF_PRESET_MODE_AUTO_VALUE,
    CONF_PRESET_MODE_BIDIRECTIONAL,
    CONF_PRESET_MODE_COOL_VALUE,
    CONF_PRESET_MODE_DRY_VALUE,
    CONF_PRESET_MODE_FAN_ONLY_VALUE,
    CONF_PRESET_MODE_HEAT_COOL_VALUE,
    CONF_PRESET_MODE_HEAT_VALUE,
    CONF_PRESET_MODE_OFF_VALUE,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_REAL_PRECISION,
    CONF_SCALE_RAW_MAX,
    CONF_SCALE_RAW_MIN,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SOURCE_ENTITY,
    CONF_STATE_ADDRESS,
    CONF_STATE_CLASS,
    CONF_STEP,
    CONF_STOP_COMMAND_ADDRESS,
    CONF_STOP_PULSE_DURATION,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONF_TEXTS,
    CONF_TILT_COMMAND_ADDRESS,
    CONF_TILT_STATE_ADDRESS,
    CONF_TOGGLE_MODE,
    CONF_TOGGLE_PULSE_DURATION,
    CONF_UID,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USE_STATE_TOPICS,
    CONF_VALUE_MULTIPLIER,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_BRIGHTNESS_SCALE,
    DEFAULT_COVER_STATUS_CLOSED_VALUES,
    DEFAULT_COVER_STATUS_CLOSING_VALUES,
    DEFAULT_COVER_STATUS_OPEN_VALUES,
    DEFAULT_COVER_STATUS_OPENING_VALUES,
    DEFAULT_COVER_STATUS_STOPPED_VALUES,
    DEFAULT_HVAC_STATUS_COOLING_VALUES,
    DEFAULT_HVAC_STATUS_DEFROSTING_VALUES,
    DEFAULT_HVAC_STATUS_DRYING_VALUES,
    DEFAULT_HVAC_STATUS_FAN_VALUES,
    DEFAULT_HVAC_STATUS_HEATING_VALUES,
    DEFAULT_HVAC_STATUS_IDLE_VALUES,
    DEFAULT_HVAC_STATUS_OFF_VALUES,
    DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_OPERATE_TIME,
    DEFAULT_PRESET_MODE_AUTO_VALUE,
    DEFAULT_PRESET_MODE_BIDIRECTIONAL,
    DEFAULT_PRESET_MODE_COOL_VALUE,
    DEFAULT_PRESET_MODE_DRY_VALUE,
    DEFAULT_PRESET_MODE_FAN_ONLY_VALUE,
    DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
    DEFAULT_PRESET_MODE_HEAT_VALUE,
    DEFAULT_PRESET_MODE_OFF_VALUE,
    DEFAULT_PULSE_DURATION,
    DEFAULT_TEMP_STEP,
    DEFAULT_TOGGLE_MODE,
)
from .helpers import parse_pulse_duration

# Fields accepted by each entity configuration.  This catalog describes only
# the shape of an entity; semantic and duplicate-address checks remain the
# responsibility of ``EntityConfigBuilder``.
_COMMON_FIELDS = frozenset(
    {
        CONF_NAME,
        CONF_AREA,
        CONF_SCAN_INTERVAL,
        CONF_UID,
        CONF_AVAILABILITY_MODE,
        CONF_AVAILABILITY_ADDRESS,
    }
)
_NUMERIC_SCALE_FIELDS = frozenset(
    {
        CONF_VALUE_MULTIPLIER,
        CONF_MIN_VALUE,
        CONF_MAX_VALUE,
        CONF_SCALE_RAW_MIN,
        CONF_SCALE_RAW_MAX,
        CONF_REAL_PRECISION,
    }
)

ENTITY_ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    CONF_SENSORS: _COMMON_FIELDS
    | _NUMERIC_SCALE_FIELDS
    | {CONF_ADDRESS, CONF_DEVICE_CLASS, CONF_UNIT_OF_MEASUREMENT, CONF_STATE_CLASS},
    CONF_BINARY_SENSORS: _COMMON_FIELDS
    | {CONF_ADDRESS, CONF_DEVICE_CLASS, CONF_INVERT_STATE},
    CONF_SWITCHES: _COMMON_FIELDS
    | {
        CONF_ADDRESS,
        CONF_STATE_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_SYNC_STATE,
        CONF_PULSE_COMMAND,
        CONF_PULSE_DURATION,
    },
    CONF_COVERS: _COMMON_FIELDS
    | {
        CONF_OPEN_COMMAND_ADDRESS,
        CONF_CLOSE_COMMAND_ADDRESS,
        CONF_OPENING_STATE_ADDRESS,
        CONF_CLOSING_STATE_ADDRESS,
        CONF_COVER_OPENING_ADDRESS,
        CONF_COVER_CLOSING_ADDRESS,
        CONF_COVER_STOPPED_ADDRESS,
        CONF_COVER_STATUS_ADDRESS,
        CONF_COVER_STATUS_OPEN_VALUES,
        CONF_COVER_STATUS_CLOSED_VALUES,
        CONF_COVER_STATUS_OPENING_VALUES,
        CONF_COVER_STATUS_CLOSING_VALUES,
        CONF_COVER_STATUS_STOPPED_VALUES,
        CONF_COVER_POSITION_FEEDBACK,
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_STOP_COMMAND_ADDRESS,
        CONF_STOP_PULSE_DURATION,
        CONF_TILT_STATE_ADDRESS,
        CONF_TILT_COMMAND_ADDRESS,
        CONF_INVERT_TILT,
        CONF_OPERATE_TIME,
        CONF_USE_STATE_TOPICS,
        CONF_TOGGLE_MODE,
        CONF_TOGGLE_PULSE_DURATION,
        CONF_INVERT_POSITION,
        CONF_DEVICE_CLASS,
    },
    CONF_LIGHTS: _COMMON_FIELDS
    | {
        CONF_ADDRESS,
        CONF_STATE_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_SYNC_STATE,
        CONF_PULSE_COMMAND,
        CONF_PULSE_DURATION,
        CONF_BRIGHTNESS_STATE_ADDRESS,
        CONF_BRIGHTNESS_COMMAND_ADDRESS,
        CONF_BRIGHTNESS_SCALE,
    },
    CONF_BUTTONS: _COMMON_FIELDS | {CONF_ADDRESS, CONF_BUTTON_PULSE},
    CONF_NUMBERS: _COMMON_FIELDS
    | _NUMERIC_SCALE_FIELDS
    | {
        CONF_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_DEVICE_CLASS,
        CONF_UNIT_OF_MEASUREMENT,
        CONF_STEP,
    },
    CONF_TEXTS: _COMMON_FIELDS | {CONF_ADDRESS, CONF_COMMAND_ADDRESS, CONF_PATTERN},
    CONF_CLIMATES: _COMMON_FIELDS
    | {
        CONF_CLIMATE_CONTROL_MODE,
        CONF_CURRENT_TEMPERATURE_ADDRESS,
        CONF_TARGET_TEMPERATURE_ADDRESS,
        CONF_HEATING_OUTPUT_ADDRESS,
        CONF_COOLING_OUTPUT_ADDRESS,
        CONF_HEATING_ACTION_ADDRESS,
        CONF_COOLING_ACTION_ADDRESS,
        CONF_PRESET_MODE_ADDRESS,
        CONF_PRESET_MODE_BIDIRECTIONAL,
        CONF_ON_OFF_ADDRESS,
        CONF_PRESET_MODE_OFF_VALUE,
        CONF_PRESET_MODE_HEAT_VALUE,
        CONF_PRESET_MODE_COOL_VALUE,
        CONF_PRESET_MODE_HEAT_COOL_VALUE,
        CONF_PRESET_MODE_AUTO_VALUE,
        CONF_PRESET_MODE_DRY_VALUE,
        CONF_PRESET_MODE_FAN_ONLY_VALUE,
        CONF_HVAC_STATUS_ADDRESS,
        CONF_HVAC_STATUS_OFF_VALUES,
        CONF_HVAC_STATUS_HEATING_VALUES,
        CONF_HVAC_STATUS_COOLING_VALUES,
        CONF_HVAC_STATUS_IDLE_VALUES,
        CONF_HVAC_STATUS_DRYING_VALUES,
        CONF_HVAC_STATUS_FAN_VALUES,
        CONF_HVAC_STATUS_PREHEATING_VALUES,
        CONF_HVAC_STATUS_DEFROSTING_VALUES,
        CONF_MIN_TEMP,
        CONF_MAX_TEMP,
        CONF_TEMP_STEP,
    },
    CONF_ENTITY_SYNC: _COMMON_FIELDS
    | {CONF_SOURCE_ENTITY, CONF_ADDRESS, CONF_INVERT_STATE},
}


def validate_entity_fields(entity_type: str, entity: dict[str, Any]) -> None:
    """Reject entity types and fields that are not part of the public schema."""
    allowed = ENTITY_ALLOWED_FIELDS.get(entity_type)
    if allowed is None:
        raise ValueError(f"Unknown entity type: {entity_type}")
    unknown = sorted(set(entity) - allowed)
    if unknown:
        raise ValueError(f"Unknown field(s) for {entity_type}: {', '.join(unknown)}")


class EntityConfigBuilder:
    """Normalize, validate, and build entity configuration items."""

    _MIN_ITEM_SCAN_INTERVAL = 0.05
    _MAX_ITEM_SCAN_INTERVAL = 3600.0

    def __init__(self, options: dict[str, list[dict[str, Any]]]) -> None:
        """Initialize the builder with the current entity options."""
        self._options = options

    @staticmethod
    def _sanitize_address(address: Any | None) -> str | None:
        """Return a trimmed string representation of an address."""

        if address is None:
            return None

        if not isinstance(address, str):
            address = str(address)

        address = address.strip()
        return address or None

    @staticmethod
    def _normalized_address(address: Any | None) -> str | None:
        """Return a normalized representation used for comparisons."""

        sanitized = EntityConfigBuilder._sanitize_address(address)
        if sanitized is None:
            return None

        return sanitized.upper()

    @staticmethod
    def _normalize_scan_interval_value(value: Any | None) -> float | None:
        if value in (None, ""):
            return None
        try:
            interval = float(value)
        except (TypeError, ValueError):
            return None
        if interval <= 0:
            return None
        return min(
            max(interval, EntityConfigBuilder._MIN_ITEM_SCAN_INTERVAL),
            EntityConfigBuilder._MAX_ITEM_SCAN_INTERVAL,
        )

    @staticmethod
    def _sanitize_operate_time(value: Any | None) -> float:
        if value in (None, ""):
            return float(DEFAULT_OPERATE_TIME)
        try:
            operate_time = float(value)
        except (TypeError, ValueError):
            return float(DEFAULT_OPERATE_TIME)
        if operate_time < 0:
            return float(DEFAULT_OPERATE_TIME)
        return operate_time

    @staticmethod
    def _normalize_real_precision(value: Any | None) -> int | None:
        if value in (None, ""):
            return None

        candidate = value
        if isinstance(candidate, str):
            candidate = candidate.strip()
            if not candidate:
                return None

        try:
            precision = int(candidate)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid precision") from exc

        if precision < 0 or precision > 6:
            raise ValueError("invalid precision")

        return precision

    @staticmethod
    def _apply_real_precision(item: dict[str, Any], value: Any | None) -> None:
        normalized = EntityConfigBuilder._normalize_real_precision(value)
        if normalized is None:
            item.pop(CONF_REAL_PRECISION, None)
        else:
            item[CONF_REAL_PRECISION] = normalized

    @staticmethod
    def _apply_scan_interval(item: dict[str, Any], value: Any | None) -> None:
        normalized = EntityConfigBuilder._normalize_scan_interval_value(value)
        if normalized is None:
            item.pop(CONF_SCAN_INTERVAL, None)
        else:
            item[CONF_SCAN_INTERVAL] = normalized

    @staticmethod
    def _normalize_numeric_value(value: Any | None) -> float | None:
        """Normalize a numeric value, handling comma decimal separator."""
        if value in (None, ""):
            return None

        candidate = value
        if isinstance(candidate, str):
            candidate = candidate.strip()
            if not candidate:
                return None
            candidate = candidate.replace(",", ".")

        try:
            result = float(candidate)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid numeric value") from exc

        if not math.isfinite(result):
            raise ValueError("invalid numeric value")

        return result

    @staticmethod
    def _apply_value_multiplier(item: dict[str, Any], value: Any | None) -> None:
        normalized = EntityConfigBuilder._normalize_numeric_value(value)
        if normalized is None:
            item.pop(CONF_VALUE_MULTIPLIER, None)
        else:
            item[CONF_VALUE_MULTIPLIER] = normalized

    @staticmethod
    def _apply_value_scale(
        item: dict[str, Any],
        raw_min: Any | None,
        raw_max: Any | None,
    ) -> None:
        """Store or remove the raw-range scale parameters from *item*.

        Both values must be valid numbers for the scale to be saved.
        If either is missing/invalid the raw-range keys are cleared from the item.
        """
        _normalize = EntityConfigBuilder._normalize_numeric_value
        rn = _normalize(raw_min)
        rx = _normalize(raw_max)

        if rn is not None and rx is not None:
            item[CONF_SCALE_RAW_MIN] = rn
            item[CONF_SCALE_RAW_MAX] = rx
        else:
            for key in (CONF_SCALE_RAW_MIN, CONF_SCALE_RAW_MAX):
                item.pop(key, None)

    def _has_duplicate(
        self,
        option_key: str,
        address: str,
        *,
        keys: tuple[str, ...] = (CONF_ADDRESS,),
        skip_idx: int | None = None,
    ) -> bool:
        """Return ``True`` if ``address`` already exists in the options."""

        normalized = self._normalized_address(address)
        if normalized is None:
            return False

        for idx, item in enumerate(self._options.get(option_key, [])):
            if skip_idx is not None and idx == skip_idx:
                continue
            for key in keys:
                if self._normalized_address(item.get(key)) == normalized:
                    return True

        return False

    def _validate_address_field(
        self, address: str | None
    ) -> tuple[str | None, dict[str, str]]:
        """Validate and sanitize an address field.

        Returns:
            Tuple of (sanitized_address, errors_dict)
        """
        errors: dict[str, str] = {}

        sanitized = self._sanitize_address(address)
        if not sanitized:
            errors["base"] = "invalid_address"
            return None, errors

        try:
            parse_tag(sanitized)
        except (RuntimeError, ValueError):
            errors["base"] = "invalid_address"
            return None, errors

        return sanitized, errors

    def _validate_mode_values_field(
        self, raw: str | None
    ) -> tuple[str | None, dict[str, str]]:
        """Validate a comma-separated list of PLC integer values for a mode.

        Returns:
            Tuple of (normalized_value_string, errors_dict)
        """
        errors: dict[str, str] = {}

        if raw is None or str(raw).strip() == "":
            return None, errors

        tokens = [token.strip() for token in str(raw).split(",")]
        tokens = [token for token in tokens if token]
        if not tokens:
            errors["base"] = "invalid_mode_values"
            return None, errors

        values: list[int] = []
        for token in tokens:
            try:
                values.append(int(token))
            except ValueError:
                errors["base"] = "invalid_mode_values"
                return None, errors

        return ",".join(str(v) for v in values), errors

    def _validate_preset_mode_value_field(
        self, raw: Any
    ) -> tuple[int | None, dict[str, str]]:
        """Validate a single PLC integer value to write for a HVAC mode.

        Rejects decimal input (e.g. "2.7") instead of silently truncating
        it, since this is a PLC integer mode code, not an engineering value.

        Returns:
            Tuple of (value, errors_dict)
        """
        errors: dict[str, str] = {}

        if raw is None or str(raw).strip() == "":
            return None, errors

        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            errors["base"] = "invalid_number"
            return None, errors
        if not numeric.is_integer():
            errors["base"] = "invalid_integer"
            return None, errors
        value = int(numeric)

        return value, errors

    @staticmethod
    def _validate_no_duplicate_preset_values(
        values: dict[str, int | None],
    ) -> dict[str, str]:
        """Reject preset_mode_*_value fields sharing the same PLC value.

        Two enabled modes mapped to the same value would make reading the
        mode back from preset_mode_address ambiguous. Disabled modes (None)
        are skipped - there's nothing to compare.
        """
        seen: dict[int, str] = {}
        for field, value in values.items():
            if value is None:
                continue
            if value in seen and seen[value] != field:
                return {"base": "duplicate_preset_value"}
            seen[value] = field
        return {}

    @staticmethod
    def _validate_no_duplicate_status_values(
        values: dict[str, str],
    ) -> dict[str, str]:
        """Reject hvac_status_*_values fields whose value lists overlap.

        The same PLC status value assigned to two different HVAC actions
        would otherwise make the match ambiguous, silently resolved by dict
        order instead of being flagged as a configuration error.
        """
        seen: dict[int, str] = {}
        for field, raw in values.items():
            if not raw:
                continue
            for token in raw.split(","):
                value = int(token)
                if value in seen and seen[value] != field:
                    return {"base": "duplicate_status_value"}
                seen[value] = field
        return {}

    def _validate_cover_status_fields(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Validate cover_status_address and its per-status value mappings.

        Shared by traditional and position covers. Returns only the fields
        that ended up set (address and/or non-empty value lists) to merge
        into the item, plus an errors dict.
        """
        fields: dict[str, Any] = {}

        if user_input.get(CONF_COVER_STATUS_ADDRESS):
            cover_status_addr, errors = self._validate_address_field(
                user_input.get(CONF_COVER_STATUS_ADDRESS)
            )
            if errors:
                return {}, errors
            fields[CONF_COVER_STATUS_ADDRESS] = cover_status_addr

        status_values: dict[str, str | None] = {}
        for conf_key, default in (
            (CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES),
            (CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES),
            (CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES),
            (CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES),
            (CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES),
        ):
            value, errors = self._validate_mode_values_field(
                user_input.get(conf_key, default)
            )
            if errors:
                return {}, errors
            status_values[conf_key] = value

        errors = self._validate_no_duplicate_status_values(status_values)
        if errors:
            return {}, errors

        for conf_key, value in status_values.items():
            if value:
                fields[conf_key] = value

        return fields, {}

    def _copy_optional_fields(
        self,
        item: dict[str, Any],
        user_input: dict[str, Any],
        *fields: str,
    ) -> None:
        """Copy optional fields from user_input to item if they exist.

        Empty strings and '__none__' are treated as removal signals,
        allowing users to remove previously set optional values.
        """
        for field in fields:
            if field in user_input:
                value = user_input[field]
                # Treat empty strings and __none__
                # as removal (explicitly remove from item)
                if value is None or value == "" or value == "__none__":
                    item.pop(field, None)  # Remove field if present
                else:
                    item[field] = value

    def _build_base_item(
        self,
        address: str,
        user_input: dict[str, Any],
        *optional_fields: str,
    ) -> dict[str, Any]:
        """Build a base item with address and optional fields.

        Args:
            address: The primary address (already validated)
            user_input: User input dictionary
            *optional_fields: Field names to copy if present

        Returns:
            Dictionary with address and optional fields
        """
        item: dict[str, Any] = {CONF_ADDRESS: address}
        self._copy_optional_fields(item, user_input, *optional_fields)
        return item

    def _build_sensor_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(CONF_SENSORS, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Build item with optional fields
        item = self._build_base_item(
            address,
            user_input,
            CONF_NAME,
            CONF_AREA,
            CONF_DEVICE_CLASS,
            CONF_UNIT_OF_MEASUREMENT,
            CONF_STATE_CLASS,
        )

        # Store display range + scale only when all 4 params are provided
        min_v = self._normalize_numeric_value(user_input.get(CONF_MIN_VALUE))
        max_v = self._normalize_numeric_value(user_input.get(CONF_MAX_VALUE))
        raw_min_v = self._normalize_numeric_value(user_input.get(CONF_SCALE_RAW_MIN))
        raw_max_v = self._normalize_numeric_value(user_input.get(CONF_SCALE_RAW_MAX))

        scale_values = (min_v, max_v, raw_min_v, raw_max_v)
        any_scale_set = any(v is not None for v in scale_values)
        all_scale_set = all(v is not None for v in scale_values)

        if any_scale_set and not all_scale_set:
            return None, {"base": "scale_requires_all_four"}

        if all_scale_set:
            item[CONF_MIN_VALUE] = min_v
            item[CONF_MAX_VALUE] = max_v
            item[CONF_SCALE_RAW_MIN] = raw_min_v
            item[CONF_SCALE_RAW_MAX] = raw_max_v
        else:
            for key in (
                CONF_MIN_VALUE,
                CONF_MAX_VALUE,
                CONF_SCALE_RAW_MIN,
                CONF_SCALE_RAW_MAX,
            ):
                item.pop(key, None)

        # Apply specific transformations
        self._apply_value_multiplier(item, user_input.get(CONF_VALUE_MULTIPLIER))
        self._apply_real_precision(item, user_input.get(CONF_REAL_PRECISION))
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, errors

    def _build_binary_sensor_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(CONF_BINARY_SENSORS, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Build item with optional fields
        item = self._build_base_item(
            address,
            user_input,
            CONF_NAME,
            CONF_AREA,
            CONF_DEVICE_CLASS,
            CONF_INVERT_STATE,
        )

        # Apply specific transformations
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_switch_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # Validate state address (try CONF_STATE_ADDRESS first, then CONF_ADDRESS)
        state_address, errors = self._validate_address_field(
            user_input.get(CONF_STATE_ADDRESS) or user_input.get(CONF_ADDRESS)
        )
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(
            CONF_SWITCHES,
            state_address,
            keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
            skip_idx=skip_idx,
        ):
            return None, {"base": "duplicate_entry"}

        # Validate optional command address
        command_address = None
        if user_input.get(CONF_COMMAND_ADDRESS):
            command_address, cmd_errors = self._validate_address_field(
                user_input.get(CONF_COMMAND_ADDRESS)
            )
            if cmd_errors:
                return None, cmd_errors

        # Build item
        item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
        if command_address:
            item[CONF_COMMAND_ADDRESS] = command_address

        # Copy optional fields
        self._copy_optional_fields(item, user_input, CONF_NAME, CONF_AREA)

        # Add boolean flags — mutually exclusive
        sync_state = bool(user_input.get(CONF_SYNC_STATE, False))
        pulse_command = bool(user_input.get(CONF_PULSE_COMMAND, False))
        if sync_state and pulse_command:
            return None, {"base": "sync_pulse_conflict"}
        if sync_state and (not command_address or command_address == state_address):
            return None, {"base": "sync_same_address"}
        item[CONF_SYNC_STATE] = sync_state
        item[CONF_PULSE_COMMAND] = pulse_command

        # Add pulse duration only if pulse command is enabled
        if pulse_command:
            pulse_duration = parse_pulse_duration(user_input.get(CONF_PULSE_DURATION))

            if pulse_duration is not None:
                item[CONF_PULSE_DURATION] = pulse_duration

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_cover_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        open_command, open_errors = self._validate_address_field(
            user_input.get(CONF_OPEN_COMMAND_ADDRESS)
        )
        if open_errors:
            return None, open_errors

        toggle_mode = bool(user_input.get(CONF_TOGGLE_MODE, DEFAULT_TOGGLE_MODE))

        # In toggle_mode, open_command_address is the single PLC pulse
        # output; close_command_address has no meaning and is ignored even
        # if supplied (a cover is either two-address or toggle, not both).
        if toggle_mode:
            close_command = None
        else:
            close_command, close_errors = self._validate_address_field(
                user_input.get(CONF_CLOSE_COMMAND_ADDRESS)
            )
            if close_errors:
                return None, close_errors

        feedback_mode = user_input.get(CONF_COVER_POSITION_FEEDBACK)
        explicit_feedback = feedback_mode in {
            "timed",
            "opening",
            "closing",
            "both",
            "status",
        }
        if not explicit_feedback:
            # Legacy entries did not persist a selector.  Preserve their exact
            # shape, including configurations with only one limit switch.
            use_state_topics = user_input.get(CONF_USE_STATE_TOPICS)
            if use_state_topics is False:
                feedback_mode = "timed"
            elif user_input.get(CONF_OPENING_STATE_ADDRESS) and user_input.get(
                CONF_CLOSING_STATE_ADDRESS
            ):
                feedback_mode = "both"
            elif user_input.get(CONF_OPENING_STATE_ADDRESS):
                feedback_mode = "opening"
            elif user_input.get(CONF_CLOSING_STATE_ADDRESS):
                feedback_mode = "closing"
            else:
                feedback_mode = "timed"

        # Get optional state addresses
        opening_state = self._sanitize_address(
            user_input.get(CONF_OPENING_STATE_ADDRESS)
        )
        closing_state = self._sanitize_address(
            user_input.get(CONF_CLOSING_STATE_ADDRESS)
        )

        # Get optional real-time movement status addresses (separate from
        # the opened/closed end-stops above: each is a boolean address for
        # "currently opening"/"currently closing"/"stopped", not a limit
        # switch)
        cover_opening_addr = self._sanitize_address(
            user_input.get(CONF_COVER_OPENING_ADDRESS)
        )
        cover_closing_addr = self._sanitize_address(
            user_input.get(CONF_COVER_CLOSING_ADDRESS)
        )
        cover_stopped_addr = self._sanitize_address(
            user_input.get(CONF_COVER_STOPPED_ADDRESS)
        )

        # Get other parameters
        operate_time = self._sanitize_operate_time(user_input.get(CONF_OPERATE_TIME))
        use_state_topics = feedback_mode in {"opening", "closing", "both"}
        if feedback_mode in {"opening", "both"} and not opening_state:
            return None, {"base": "state_addresses_required"}
        if feedback_mode in {"closing", "both"} and not closing_state:
            return None, {"base": "state_addresses_required"}

        # Validate optional state addresses if present
        for candidate in (
            opening_state,
            closing_state,
            cover_opening_addr,
            cover_closing_addr,
            cover_stopped_addr,
        ):
            if candidate:
                _, addr_errors = self._validate_address_field(candidate)
                if addr_errors:
                    return None, addr_errors

        # Check for duplicates
        if self._has_duplicate(
            CONF_COVERS,
            open_command,
            keys=(CONF_OPEN_COMMAND_ADDRESS,),
            skip_idx=skip_idx,
        ):
            return None, {"base": "duplicate_entry"}

        # Validate optional real-time movement status (cover_status_address
        # and its per-status value mappings)
        status_keys = (
            CONF_COVER_STATUS_ADDRESS,
            CONF_COVER_STATUS_OPEN_VALUES,
            CONF_COVER_STATUS_CLOSED_VALUES,
            CONF_COVER_STATUS_OPENING_VALUES,
            CONF_COVER_STATUS_CLOSING_VALUES,
            CONF_COVER_STATUS_STOPPED_VALUES,
        )
        status_input = (
            user_input if any(key in user_input for key in status_keys) else {}
        )
        cover_status_fields, cover_status_errors = self._validate_cover_status_fields(
            status_input
        )
        if cover_status_errors:
            return None, cover_status_errors
        if any(
            cover_status_fields.get(key) for key in status_keys[1:]
        ) and not cover_status_fields.get(CONF_COVER_STATUS_ADDRESS):
            return None, {"base": "cover_status_required"}
        if feedback_mode == "status" and (
            not cover_status_fields.get(CONF_COVER_STATUS_ADDRESS)
            or not any(
                cover_status_fields.get(key)
                for key in (
                    CONF_COVER_STATUS_OPEN_VALUES,
                    CONF_COVER_STATUS_CLOSED_VALUES,
                    CONF_COVER_STATUS_OPENING_VALUES,
                    CONF_COVER_STATUS_CLOSING_VALUES,
                    CONF_COVER_STATUS_STOPPED_VALUES,
                )
            )
        ):
            return None, {"base": "cover_status_required"}

        if toggle_mode:
            # toggle_mode's correctness depends entirely on knowing the
            # PLC's real state - it can't fall back to a simulated timer
            # like the two-address mode does. Require two independent
            # feedback sources: motion (is_opening/is_closing) and settled
            # state (is_closed), each satisfiable via cover_status_address
            # alone or via the boolean/end-stop alternatives.
            # The status word is the selected *motion* source only when it
            # has opening+closing values mapped - matches S7Cover's runtime
            # _toggle_movement() priority (status wins over bits only when
            # it actually carries motion values), so this validation stays
            # tied to the source the entity will really use, not merely to
            # cover_status_address's presence.
            status_is_motion_source = bool(
                cover_status_fields.get(CONF_COVER_STATUS_OPENING_VALUES)
                and cover_status_fields.get(CONF_COVER_STATUS_CLOSING_VALUES)
            )
            has_motion_feedback = status_is_motion_source or bool(
                cover_opening_addr and cover_closing_addr
            )
            has_settled_feedback = bool(
                cover_status_fields.get(CONF_COVER_STATUS_OPEN_VALUES)
                and cover_status_fields.get(CONF_COVER_STATUS_CLOSED_VALUES)
            ) or bool(use_state_topics and opening_state and closing_state)
            if not (has_motion_feedback and has_settled_feedback):
                return None, {"base": "toggle_mode_requires_feedback"}
            # A status-word setup must also map "stopped" explicitly, so a
            # genuine mid-travel stop can be told apart from a missing or
            # unmatched status value (see S7Cover._toggle_state) - but only
            # when the status word is actually the selected motion source;
            # a status word used purely for position (with bits driving
            # motion) has no need to also carry a "stopped" mapping.
            if status_is_motion_source and not cover_status_fields.get(
                CONF_COVER_STATUS_STOPPED_VALUES
            ):
                return None, {"base": "toggle_mode_requires_stopped_mapping"}

        # Build item
        item: dict[str, Any] = {
            CONF_OPEN_COMMAND_ADDRESS: open_command,
        }
        if close_command:
            item[CONF_CLOSE_COMMAND_ADDRESS] = close_command

        # Add optional state addresses
        if (
            feedback_mode in {"opening", "both"} or not explicit_feedback
        ) and opening_state:
            item[CONF_OPENING_STATE_ADDRESS] = opening_state
        if (
            feedback_mode in {"closing", "both"} or not explicit_feedback
        ) and closing_state:
            item[CONF_CLOSING_STATE_ADDRESS] = closing_state

        # Add optional real-time movement status addresses. toggle_mode
        # treats position and movement feedback as independent sources, so
        # a status word chosen for position does not discard separately
        # configured movement bits there; plain traditional covers keep the
        # pre-existing coupling (status word supplies both, stale bit
        # fields are dropped) since their runtime still implements that
        # precedence - out of this PR's scope to change.
        keep_movement_bits = toggle_mode or feedback_mode != "status"
        if keep_movement_bits and cover_opening_addr:
            item[CONF_COVER_OPENING_ADDRESS] = cover_opening_addr
        if keep_movement_bits and cover_closing_addr:
            item[CONF_COVER_CLOSING_ADDRESS] = cover_closing_addr
        if keep_movement_bits and cover_stopped_addr:
            item[CONF_COVER_STOPPED_ADDRESS] = cover_stopped_addr

        # Copy optional fields
        self._copy_optional_fields(
            item, user_input, CONF_NAME, CONF_AREA, CONF_DEVICE_CLASS
        )

        # Add cover-specific fields
        item[CONF_OPERATE_TIME] = operate_time
        if explicit_feedback:
            item[CONF_USE_STATE_TOPICS] = use_state_topics
            item[CONF_COVER_POSITION_FEEDBACK] = feedback_mode
        elif CONF_USE_STATE_TOPICS in user_input:
            item[CONF_USE_STATE_TOPICS] = bool(user_input[CONF_USE_STATE_TOPICS])
        if toggle_mode:
            item[CONF_TOGGLE_MODE] = True
            item[CONF_TOGGLE_PULSE_DURATION] = parse_pulse_duration(
                user_input.get(CONF_TOGGLE_PULSE_DURATION)
            )
        item.update(cover_status_fields)

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_cover_position_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # Validate required position state address
        position_state, state_errors = self._validate_address_field(
            user_input.get(CONF_POSITION_STATE_ADDRESS)
        )
        if state_errors:
            return None, state_errors

        # Get optional position command address
        position_command = self._sanitize_address(
            user_input.get(CONF_POSITION_COMMAND_ADDRESS)
        )

        # Validate optional command address if present
        if position_command:
            _, cmd_errors = self._validate_address_field(position_command)
            if cmd_errors:
                return None, cmd_errors

        # Get optional tilt state/command addresses; symmetric to position
        # above.
        tilt_state_addr = None
        tilt_command_addr = None
        if user_input.get(CONF_TILT_STATE_ADDRESS):
            tilt_state_addr, tilt_state_errors = self._validate_address_field(
                user_input.get(CONF_TILT_STATE_ADDRESS)
            )
            if tilt_state_errors:
                return None, tilt_state_errors

            if self._sanitize_address(user_input.get(CONF_TILT_COMMAND_ADDRESS)):
                tilt_command_addr, tilt_cmd_errors = self._validate_address_field(
                    user_input.get(CONF_TILT_COMMAND_ADDRESS)
                )
                if tilt_cmd_errors:
                    return None, tilt_cmd_errors

        # Check for duplicates
        if self._has_duplicate(
            CONF_COVERS,
            position_state,
            keys=(CONF_POSITION_STATE_ADDRESS,),
            skip_idx=skip_idx,
        ):
            return None, {"base": "duplicate_entry"}

        # Validate optional real-time movement status (cover_status_address
        # and its per-status value mappings)
        cover_status_fields, cover_status_errors = self._validate_cover_status_fields(
            user_input
        )
        if cover_status_errors:
            return None, cover_status_errors

        # Build item
        item: dict[str, Any] = {
            CONF_POSITION_STATE_ADDRESS: position_state,
        }

        # Add optional command address
        if position_command:
            item[CONF_POSITION_COMMAND_ADDRESS] = position_command

        # Add optional stop command address and pulse duration
        stop_command = self._sanitize_address(user_input.get(CONF_STOP_COMMAND_ADDRESS))
        if stop_command:
            _, stop_errors = self._validate_address_field(stop_command)
            if stop_errors:
                return None, stop_errors
            item[CONF_STOP_COMMAND_ADDRESS] = stop_command
            stop_pulse = user_input.get(
                CONF_STOP_PULSE_DURATION, DEFAULT_PULSE_DURATION
            )
            item[CONF_STOP_PULSE_DURATION] = float(stop_pulse)

        # Add optional tilt addresses and invert flag
        if tilt_state_addr:
            item[CONF_TILT_STATE_ADDRESS] = tilt_state_addr
            if tilt_command_addr:
                item[CONF_TILT_COMMAND_ADDRESS] = tilt_command_addr
            if user_input.get(CONF_INVERT_TILT, False):
                item[CONF_INVERT_TILT] = True

        item.update(cover_status_fields)

        # Copy optional fields
        self._copy_optional_fields(
            item, user_input, CONF_NAME, CONF_AREA, CONF_DEVICE_CLASS
        )

        # Add invert_position flag
        if user_input.get(CONF_INVERT_POSITION, False):
            item[CONF_INVERT_POSITION] = True

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_button_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(CONF_BUTTONS, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Build item with optional fields
        item = self._build_base_item(address, user_input, CONF_NAME, CONF_AREA)

        # Add button-specific fields
        button_pulse = parse_pulse_duration(user_input.get(CONF_BUTTON_PULSE))
        item[CONF_BUTTON_PULSE] = button_pulse

        return item, {}

    def _build_light_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build a light item from user input (supports both on/off and dimmer)."""
        # Validate state address (try CONF_STATE_ADDRESS first, then CONF_ADDRESS)
        state_address, errors = self._validate_address_field(
            user_input.get(CONF_STATE_ADDRESS) or user_input.get(CONF_ADDRESS)
        )
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(
            CONF_LIGHTS,
            state_address,
            keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
            skip_idx=skip_idx,
        ):
            return None, {"base": "duplicate_entry"}

        # Validate optional command address
        command_address = None
        if user_input.get(CONF_COMMAND_ADDRESS):
            command_address, cmd_errors = self._validate_address_field(
                user_input.get(CONF_COMMAND_ADDRESS)
            )
            if cmd_errors:
                return None, cmd_errors

        # Build item
        item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
        if command_address:
            item[CONF_COMMAND_ADDRESS] = command_address

        # Copy optional fields
        self._copy_optional_fields(item, user_input, CONF_NAME, CONF_AREA)

        # Add boolean flags — mutually exclusive
        sync_state = bool(user_input.get(CONF_SYNC_STATE, False))
        pulse_command = bool(user_input.get(CONF_PULSE_COMMAND, False))
        if sync_state and pulse_command:
            return None, {"base": "sync_pulse_conflict"}
        if sync_state and (not command_address or command_address == state_address):
            return None, {"base": "sync_same_address"}
        item[CONF_SYNC_STATE] = sync_state
        item[CONF_PULSE_COMMAND] = pulse_command

        # Add pulse duration only if pulse command is enabled
        if pulse_command:
            pulse_duration = parse_pulse_duration(user_input.get(CONF_PULSE_DURATION))

            if pulse_duration is not None:
                item[CONF_PULSE_DURATION] = pulse_duration

        # Brightness / dimmer fields (optional)
        bri_state_addr = user_input.get(CONF_BRIGHTNESS_STATE_ADDRESS)
        if bri_state_addr:
            bri_state_addr_val, bri_errors = self._validate_address_field(
                bri_state_addr
            )
            if bri_errors:
                return None, bri_errors
            item[CONF_BRIGHTNESS_STATE_ADDRESS] = bri_state_addr_val

            # Brightness command address (defaults to state address)
            bri_cmd_addr = user_input.get(CONF_BRIGHTNESS_COMMAND_ADDRESS)
            if bri_cmd_addr:
                bri_cmd_val, bri_cmd_errors = self._validate_address_field(bri_cmd_addr)
                if bri_cmd_errors:
                    return None, bri_cmd_errors
                item[CONF_BRIGHTNESS_COMMAND_ADDRESS] = bri_cmd_val

            # Brightness scale
            raw_brightness = user_input.get(CONF_BRIGHTNESS_SCALE)
            if raw_brightness is not None:
                try:
                    brightness_scale = int(raw_brightness)
                except (TypeError, ValueError):
                    brightness_scale = DEFAULT_BRIGHTNESS_SCALE
                if brightness_scale < 1 or brightness_scale > 65535:
                    brightness_scale = DEFAULT_BRIGHTNESS_SCALE
                item[CONF_BRIGHTNESS_SCALE] = brightness_scale
            else:
                item[CONF_BRIGHTNESS_SCALE] = DEFAULT_BRIGHTNESS_SCALE

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_number_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build a 'number' item from user input.

        Returns (item, errors). If there is an error,
        item is None and errors["base"] is set.
        """
        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Parse tag to get type information
        address_tag = parse_tag(address)

        # Check for duplicates
        if self._has_duplicate(CONF_NUMBERS, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Validate optional command address
        command_address = None
        if user_input.get(CONF_COMMAND_ADDRESS):
            command_address, cmd_errors = self._validate_address_field(
                user_input.get(CONF_COMMAND_ADDRESS)
            )
            if cmd_errors:
                return None, cmd_errors

        # Parse numeric values
        min_value: float | None = None
        max_value: float | None = None
        step_value: float | None = None

        try:
            min_value = self._normalize_numeric_value(user_input.get(CONF_MIN_VALUE))
            max_value = self._normalize_numeric_value(user_input.get(CONF_MAX_VALUE))
            step_value = self._normalize_numeric_value(user_input.get(CONF_STEP))
            if step_value is not None and step_value <= 0:
                return None, {"base": "invalid_number"}
        except ValueError:
            return None, {"base": "invalid_number"}

        # If either raw-range scale param is set, both min and max are required
        raw_min_set = (
            self._normalize_numeric_value(user_input.get(CONF_SCALE_RAW_MIN))
            is not None
        )
        raw_max_set = (
            self._normalize_numeric_value(user_input.get(CONF_SCALE_RAW_MAX))
            is not None
        )
        if (raw_min_set or raw_max_set) and (min_value is None or max_value is None):
            return None, {"base": "scale_raw_requires_min_max"}

        # Check if REAL or LREAL type requires min/max
        from .address import DataType

        real_type = getattr(DataType, "REAL", None)
        lreal_type = getattr(DataType, "LREAL", None)

        if address_tag.data_type in (real_type, lreal_type):
            if min_value is None or max_value is None:
                return None, {"base": "min_max_required_for_real"}

        # PLC data-type limits
        limits = get_numeric_limits(address_tag.data_type)
        if limits is not None:
            dtype_min, dtype_max = limits
            if min_value is not None:
                min_value = min(max(min_value, dtype_min), dtype_max)
            if max_value is not None:
                max_value = min(max(max_value, dtype_min), dtype_max)

        # Range consistency (min/max)
        if min_value is not None and max_value is not None and min_value > max_value:
            return None, {"base": "invalid_range"}

        # Build item
        item = self._build_base_item(
            address,
            user_input,
            CONF_NAME,
            CONF_AREA,
            CONF_DEVICE_CLASS,
            CONF_UNIT_OF_MEASUREMENT,
        )

        # Add command address if present
        if command_address:
            item[CONF_COMMAND_ADDRESS] = command_address

        # Add numeric constraints
        if min_value is not None:
            item[CONF_MIN_VALUE] = min_value
        if max_value is not None:
            item[CONF_MAX_VALUE] = max_value
        if step_value is not None:
            item[CONF_STEP] = step_value

        # Apply transformations
        self._apply_value_multiplier(item, user_input.get(CONF_VALUE_MULTIPLIER))
        self._apply_value_scale(
            item,
            user_input.get(CONF_SCALE_RAW_MIN),
            user_input.get(CONF_SCALE_RAW_MAX),
        )
        self._apply_real_precision(item, user_input.get(CONF_REAL_PRECISION))
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_text_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build a 'text' item from user input.

        Returns (item, errors). If there is an error,
        item is None and errors["base"] is set.
        """
        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Parse tag to validate it's a STRING or WSTRING type
        address_tag = parse_tag(address)
        from .address import DataType

        if address_tag.data_type not in (DataType.STRING, DataType.WSTRING):
            return None, {"base": "text_requires_string_type"}

        # Check for duplicates
        if self._has_duplicate(CONF_TEXTS, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Validate optional command address
        command_address = None
        if user_input.get(CONF_COMMAND_ADDRESS):
            command_address, cmd_errors = self._validate_address_field(
                user_input.get(CONF_COMMAND_ADDRESS)
            )
            if cmd_errors:
                return None, cmd_errors

        # Build item with optional fields
        item = self._build_base_item(
            address, user_input, CONF_NAME, CONF_AREA, CONF_PATTERN
        )

        # Add command address if present
        if command_address:
            item[CONF_COMMAND_ADDRESS] = command_address

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_writer_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build an 'entity_sync' item from user input."""
        # Validate source entity
        source_entity = user_input.get(CONF_SOURCE_ENTITY, "").strip()
        if not source_entity:
            return None, {"base": "invalid_source_entity"}

        # Validate address
        address, errors = self._validate_address_field(user_input.get(CONF_ADDRESS))
        if errors:
            return None, errors

        # Check for duplicates
        if self._has_duplicate(CONF_ENTITY_SYNC, address, skip_idx=skip_idx):
            return None, {"base": "duplicate_entry"}

        # Build item
        item: dict[str, Any] = {
            CONF_ADDRESS: address,
            CONF_SOURCE_ENTITY: source_entity,
        }

        # Copy optional fields
        self._copy_optional_fields(
            item, user_input, CONF_NAME, CONF_AREA, CONF_INVERT_STATE
        )

        return item, {}

    def _build_climate_direct_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build a 'climate_direct' item from user input."""
        # Validate current temperature address
        current_temp_addr, errors = self._validate_address_field(
            user_input.get(CONF_CURRENT_TEMPERATURE_ADDRESS)
        )
        if errors:
            return None, errors

        # At least one output address is required
        heating_output = user_input.get(CONF_HEATING_OUTPUT_ADDRESS)
        cooling_output = user_input.get(CONF_COOLING_OUTPUT_ADDRESS)

        if not heating_output and not cooling_output:
            return None, {
                "base": "At least one of heating or cooling output is required"
            }

        # Validate heating output if present
        heating_output_addr = None
        if heating_output:
            heating_output_addr, heat_errors = self._validate_address_field(
                heating_output
            )
            if heat_errors:
                return None, heat_errors

        # Validate cooling output if present
        cooling_output_addr = None
        if cooling_output:
            cooling_output_addr, cool_errors = self._validate_address_field(
                cooling_output
            )
            if cool_errors:
                return None, cool_errors

        # Validate optional action addresses
        heating_action_addr = None
        if user_input.get(CONF_HEATING_ACTION_ADDRESS):
            heating_action_addr, errors = self._validate_address_field(
                user_input.get(CONF_HEATING_ACTION_ADDRESS)
            )
            if errors:
                return None, errors

        cooling_action_addr = None
        if user_input.get(CONF_COOLING_ACTION_ADDRESS):
            cooling_action_addr, errors = self._validate_address_field(
                user_input.get(CONF_COOLING_ACTION_ADDRESS)
            )
            if errors:
                return None, errors

        # Build item
        item = {
            CONF_CLIMATE_CONTROL_MODE: CONTROL_MODE_DIRECT,
            CONF_CURRENT_TEMPERATURE_ADDRESS: current_temp_addr,
        }

        if heating_output_addr:
            item[CONF_HEATING_OUTPUT_ADDRESS] = heating_output_addr
        if cooling_output_addr:
            item[CONF_COOLING_OUTPUT_ADDRESS] = cooling_output_addr
        if heating_action_addr:
            item[CONF_HEATING_ACTION_ADDRESS] = heating_action_addr
        if cooling_action_addr:
            item[CONF_COOLING_ACTION_ADDRESS] = cooling_action_addr

        # Add temperature limits
        item[CONF_MIN_TEMP] = user_input.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        item[CONF_MAX_TEMP] = user_input.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
        item[CONF_TEMP_STEP] = user_input.get(CONF_TEMP_STEP, DEFAULT_TEMP_STEP)

        # Copy optional fields
        self._copy_optional_fields(item, user_input, CONF_NAME, CONF_AREA)

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        return item, {}

    def _build_climate_setpoint_item(
        self,
        user_input: dict[str, Any],
        *,
        skip_idx: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Build a 'climate_setpoint' item from user input."""
        # Validate current temperature address
        current_temp_addr, errors = self._validate_address_field(
            user_input.get(CONF_CURRENT_TEMPERATURE_ADDRESS)
        )
        if errors:
            return None, errors

        # Validate target temperature address
        target_temp_addr, errors = self._validate_address_field(
            user_input.get(CONF_TARGET_TEMPERATURE_ADDRESS)
        )
        if errors:
            return None, errors

        # Validate optional preset mode address
        preset_mode_addr = None
        if user_input.get(CONF_PRESET_MODE_ADDRESS):
            preset_mode_addr, errors = self._validate_address_field(
                user_input.get(CONF_PRESET_MODE_ADDRESS)
            )
            if errors:
                return None, errors

        # Validate optional on/off address
        on_off_addr = None
        if user_input.get(CONF_ON_OFF_ADDRESS):
            on_off_addr, errors = self._validate_address_field(
                user_input.get(CONF_ON_OFF_ADDRESS)
            )
            if errors:
                return None, errors

        # Validate optional HVAC status address
        hvac_status_addr = None
        if user_input.get(CONF_HVAC_STATUS_ADDRESS):
            hvac_status_addr, errors = self._validate_address_field(
                user_input.get(CONF_HVAC_STATUS_ADDRESS)
            )
            if errors:
                return None, errors

        # Validate current status mapping (each may hold several
        # comma-separated values, e.g. "2,3")
        hvac_status_off_values, errors = self._validate_mode_values_field(
            user_input.get(CONF_HVAC_STATUS_OFF_VALUES, DEFAULT_HVAC_STATUS_OFF_VALUES)
        )
        if errors:
            return None, errors

        hvac_status_heating_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_HEATING_VALUES, DEFAULT_HVAC_STATUS_HEATING_VALUES
            )
        )
        if errors:
            return None, errors

        hvac_status_cooling_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_COOLING_VALUES, DEFAULT_HVAC_STATUS_COOLING_VALUES
            )
        )
        if errors:
            return None, errors

        hvac_status_idle_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_IDLE_VALUES, DEFAULT_HVAC_STATUS_IDLE_VALUES
            )
        )
        if errors:
            return None, errors

        hvac_status_drying_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_DRYING_VALUES, DEFAULT_HVAC_STATUS_DRYING_VALUES
            )
        )
        if errors:
            return None, errors

        hvac_status_fan_values, errors = self._validate_mode_values_field(
            user_input.get(CONF_HVAC_STATUS_FAN_VALUES, DEFAULT_HVAC_STATUS_FAN_VALUES)
        )
        if errors:
            return None, errors

        hvac_status_preheating_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_PREHEATING_VALUES,
                DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
            )
        )
        if errors:
            return None, errors

        hvac_status_defrosting_values, errors = self._validate_mode_values_field(
            user_input.get(
                CONF_HVAC_STATUS_DEFROSTING_VALUES,
                DEFAULT_HVAC_STATUS_DEFROSTING_VALUES,
            )
        )
        if errors:
            return None, errors

        # Validate target mode mapping (single value written per mode)
        preset_mode_off_value, errors = self._validate_preset_mode_value_field(
            user_input.get(CONF_PRESET_MODE_OFF_VALUE, DEFAULT_PRESET_MODE_OFF_VALUE)
        )
        if errors:
            return None, errors

        preset_mode_heat_value, errors = self._validate_preset_mode_value_field(
            user_input.get(CONF_PRESET_MODE_HEAT_VALUE, DEFAULT_PRESET_MODE_HEAT_VALUE)
        )
        if errors:
            return None, errors

        preset_mode_cool_value, errors = self._validate_preset_mode_value_field(
            user_input.get(CONF_PRESET_MODE_COOL_VALUE, DEFAULT_PRESET_MODE_COOL_VALUE)
        )
        if errors:
            return None, errors

        preset_mode_heat_cool_value, errors = self._validate_preset_mode_value_field(
            user_input.get(
                CONF_PRESET_MODE_HEAT_COOL_VALUE,
                DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
            )
        )
        if errors:
            return None, errors

        preset_mode_auto_value, errors = self._validate_preset_mode_value_field(
            user_input.get(CONF_PRESET_MODE_AUTO_VALUE, DEFAULT_PRESET_MODE_AUTO_VALUE)
        )
        if errors:
            return None, errors

        preset_mode_dry_value, errors = self._validate_preset_mode_value_field(
            user_input.get(CONF_PRESET_MODE_DRY_VALUE, DEFAULT_PRESET_MODE_DRY_VALUE)
        )
        if errors:
            return None, errors

        preset_mode_fan_only_value, errors = self._validate_preset_mode_value_field(
            user_input.get(
                CONF_PRESET_MODE_FAN_ONLY_VALUE, DEFAULT_PRESET_MODE_FAN_ONLY_VALUE
            )
        )
        if errors:
            return None, errors

        preset_mode_bidirectional = bool(
            user_input.get(
                CONF_PRESET_MODE_BIDIRECTIONAL, DEFAULT_PRESET_MODE_BIDIRECTIONAL
            )
        )

        # Build item
        item = {
            CONF_CLIMATE_CONTROL_MODE: CONTROL_MODE_SETPOINT,
            CONF_CURRENT_TEMPERATURE_ADDRESS: current_temp_addr,
            CONF_TARGET_TEMPERATURE_ADDRESS: target_temp_addr,
        }

        if preset_mode_addr:
            item[CONF_PRESET_MODE_ADDRESS] = preset_mode_addr
            item[CONF_PRESET_MODE_BIDIRECTIONAL] = preset_mode_bidirectional

        if on_off_addr:
            item[CONF_ON_OFF_ADDRESS] = on_off_addr

        if hvac_status_addr:
            item[CONF_HVAC_STATUS_ADDRESS] = hvac_status_addr

        # Store "" (not the field's non-empty historical default, where it
        # has one - OFF/HEATING/COOLING default to "0"/"1"/"2") when the
        # user explicitly cleared the field. Falling back to the non-empty
        # default here would silently re-enable status matching for a
        # value the user just tried to disable - same bug class fixed
        # above for preset_mode_*_value.
        item[CONF_HVAC_STATUS_OFF_VALUES] = hvac_status_off_values or ""
        item[CONF_HVAC_STATUS_HEATING_VALUES] = hvac_status_heating_values or ""
        item[CONF_HVAC_STATUS_COOLING_VALUES] = hvac_status_cooling_values or ""
        item[CONF_HVAC_STATUS_IDLE_VALUES] = hvac_status_idle_values or ""
        item[CONF_HVAC_STATUS_DRYING_VALUES] = hvac_status_drying_values or ""
        item[CONF_HVAC_STATUS_FAN_VALUES] = hvac_status_fan_values or ""
        item[CONF_HVAC_STATUS_PREHEATING_VALUES] = hvac_status_preheating_values or ""
        item[CONF_HVAC_STATUS_DEFROSTING_VALUES] = hvac_status_defrosting_values or ""

        # Store exactly what was validated above: an explicit int the user
        # typed, or None if they cleared the field (which disables that
        # mode - see the docstring on the preset mode mapping below). The
        # DEFAULT_* constants were already applied upstream, at validation
        # time, when the field was absent from user_input entirely; re-
        # applying them here on None would incorrectly re-enable a mode the
        # user just explicitly disabled by clearing its field.
        item[CONF_PRESET_MODE_OFF_VALUE] = preset_mode_off_value
        item[CONF_PRESET_MODE_HEAT_VALUE] = preset_mode_heat_value
        item[CONF_PRESET_MODE_COOL_VALUE] = preset_mode_cool_value
        item[CONF_PRESET_MODE_HEAT_COOL_VALUE] = preset_mode_heat_cool_value
        item[CONF_PRESET_MODE_AUTO_VALUE] = preset_mode_auto_value
        item[CONF_PRESET_MODE_DRY_VALUE] = preset_mode_dry_value
        item[CONF_PRESET_MODE_FAN_ONLY_VALUE] = preset_mode_fan_only_value

        # Add temperature limits
        item[CONF_MIN_TEMP] = user_input.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        item[CONF_MAX_TEMP] = user_input.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
        item[CONF_TEMP_STEP] = user_input.get(CONF_TEMP_STEP, DEFAULT_TEMP_STEP)

        # Copy optional fields
        self._copy_optional_fields(item, user_input, CONF_NAME, CONF_AREA)

        # Apply scan interval
        self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))

        # Duplicate values are ambiguous only when preset mode readback is
        # enabled. Write-only mappings may intentionally share PLC values.
        if preset_mode_addr and preset_mode_bidirectional:
            errors = self._validate_no_duplicate_preset_values(
                {
                    field: item[field]
                    for field in (
                        CONF_PRESET_MODE_OFF_VALUE,
                        CONF_PRESET_MODE_HEAT_VALUE,
                        CONF_PRESET_MODE_COOL_VALUE,
                        CONF_PRESET_MODE_HEAT_COOL_VALUE,
                        CONF_PRESET_MODE_AUTO_VALUE,
                        CONF_PRESET_MODE_DRY_VALUE,
                        CONF_PRESET_MODE_FAN_ONLY_VALUE,
                    )
                }
            )
            if errors:
                return None, errors

        # Reject the same PLC status value appearing under more than one
        # HVAC action - the match would otherwise silently depend on dict
        # order instead of being a configuration error.
        errors = self._validate_no_duplicate_status_values(
            {
                field: item[field]
                for field in (
                    CONF_HVAC_STATUS_OFF_VALUES,
                    CONF_HVAC_STATUS_HEATING_VALUES,
                    CONF_HVAC_STATUS_COOLING_VALUES,
                    CONF_HVAC_STATUS_IDLE_VALUES,
                    CONF_HVAC_STATUS_DRYING_VALUES,
                    CONF_HVAC_STATUS_FAN_VALUES,
                    CONF_HVAC_STATUS_PREHEATING_VALUES,
                    CONF_HVAC_STATUS_DEFROSTING_VALUES,
                )
            }
        )
        if errors:
            return None, errors

        return item, {}


def build_entity_item(
    entity_type: str,
    entity: dict[str, Any],
    *,
    options: dict[str, list[dict[str, Any]]],
    skip_idx: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Validate and normalize one entity using the appropriate builder."""
    validate_entity_fields(entity_type, entity)
    if entity_type not in (CONF_SENSORS, CONF_NUMBERS):
        for key, value in entity.items():
            if "address" not in key or not isinstance(value, str) or not value.strip():
                continue
            try:
                if parse_tag(value.strip()).data_type == getattr(
                    DataType, "TIME", None
                ):
                    return None, {"base": "time_unsupported_for_entity"}
            except (RuntimeError, ValueError):
                # The platform-specific builder supplies the established error.
                pass
    builder = EntityConfigBuilder(options)

    if entity_type == CONF_COVERS:
        method = (
            builder._build_cover_position_item
            if entity.get(CONF_POSITION_STATE_ADDRESS)
            else builder._build_cover_item
        )
    elif entity_type == CONF_CLIMATES:
        control_mode = entity.get(
            CONF_CLIMATE_CONTROL_MODE,
            CONTROL_MODE_SETPOINT,
        )

        if control_mode == CONTROL_MODE_DIRECT:
            method = builder._build_climate_direct_item
        elif control_mode == CONTROL_MODE_SETPOINT:
            method = builder._build_climate_setpoint_item
        else:
            return None, {"base": "invalid_control_mode"}
    else:
        method = {
            CONF_SENSORS: builder._build_sensor_item,
            CONF_BINARY_SENSORS: builder._build_binary_sensor_item,
            CONF_SWITCHES: builder._build_switch_item,
            CONF_LIGHTS: builder._build_light_item,
            CONF_BUTTONS: builder._build_button_item,
            CONF_NUMBERS: builder._build_number_item,
            CONF_TEXTS: builder._build_text_item,
            CONF_ENTITY_SYNC: builder._build_writer_item,
        }[entity_type]

    item, errors = method(entity, skip_idx=skip_idx)
    if errors or item is None:
        return item, errors

    mode = entity.get(CONF_AVAILABILITY_MODE) or AVAILABILITY_MODE_CONNECTION
    if mode not in AVAILABILITY_MODES:
        return None, {"base": "invalid_availability_mode"}
    if mode == AVAILABILITY_MODE_BIT:
        address = builder._sanitize_address(entity.get(CONF_AVAILABILITY_ADDRESS))
        if not address:
            return None, {"base": "availability_address_required"}
        try:
            tag = parse_tag(address)
        except (RuntimeError, ValueError):
            return None, {"base": "invalid_availability_address"}
        if tag.data_type != DataType.BIT:
            return None, {"base": "availability_address_must_be_bit"}
        item[CONF_AVAILABILITY_MODE] = mode
        item[CONF_AVAILABILITY_ADDRESS] = address.upper()
    else:
        item.pop(CONF_AVAILABILITY_ADDRESS, None)
        if mode == AVAILABILITY_MODE_CONNECTION:
            item.pop(CONF_AVAILABILITY_MODE, None)
        else:
            item[CONF_AVAILABILITY_MODE] = mode
    return item, {}
