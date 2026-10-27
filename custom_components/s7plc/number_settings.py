"""Number UI limits shared by validation, previews and runtime updates."""

from __future__ import annotations

import math

from .plc.address import DataType, get_numeric_limits, is_time_data_type
from .value_conversion import LOGO_TIME_HHMM_LIMITS

NUMBER_SETTINGS_FIELDS = frozenset({"min_value", "max_value", "step", "mode"})
DEFAULT_NUMBER_STEP = 1.0
TIME_NUMBER_STEP = 0.001


def number_value_settings(data_type, item: dict, conversion: dict | None) -> dict:
    """Resolve HA limits without treating them as conversion endpoints."""
    limits = get_numeric_limits(data_type)
    if conversion and conversion.get("type") == "logo_time_bcd":
        limits = LOGO_TIME_HHMM_LIMITS
    defaults = {
        "min_value": limits[0] if limits is not None else None,
        "max_value": limits[1] if limits is not None else None,
        "step": (
            TIME_NUMBER_STEP if is_time_data_type(data_type) else DEFAULT_NUMBER_STEP
        ),
    }
    return {
        key: float(item[key]) if item.get(key) is not None else value
        for key, value in defaults.items()
    }


def number_settings_error(data_type, item: dict, conversion: dict | None) -> str | None:
    """Validate the final interval, including any retained or automatic bounds."""
    try:
        settings = number_value_settings(data_type, item, conversion)
    except (TypeError, ValueError, OverflowError):
        return "invalid_number"
    if any(
        value is not None and not math.isfinite(value) for value in settings.values()
    ):
        return "invalid_number"
    if settings["step"] <= 0:
        return "invalid_number"
    if data_type in {DataType.REAL, DataType.LREAL} and (
        item.get("min_value") is None or item.get("max_value") is None
    ):
        return "min_max_required_for_real"
    minimum, maximum = settings["min_value"], settings["max_value"]
    if minimum is not None and maximum is not None and minimum > maximum:
        return "invalid_range"
    return None
