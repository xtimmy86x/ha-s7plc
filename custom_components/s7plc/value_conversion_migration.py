"""Persistent migration of legacy numeric conversion configuration.

This module deliberately has no Home Assistant or PLC dependencies.  Legacy
keys belong here (and at the 7.x configuration-input boundary), never in an
entity's runtime conversion pipeline.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .value_conversion import ValueConversionError

LEGACY_VALUE_FIELDS = ("value_multiplier", "scale_raw_min", "scale_raw_max")
LEGACY_BRIGHTNESS_FIELDS = ("brightness_scale",)


@dataclass(frozen=True)
class MigrationReport:
    """Result metadata for one entity migration."""

    changed: bool = False
    multipliers: int = 0
    linear_scales: int = 0
    brightness_scales: int = 0
    conflicts: tuple[str, ...] = ()


def _number(value: Any, field: str) -> int | float:
    if isinstance(value, bool):
        raise ValueConversionError(f"legacy {field} must be numeric")
    if isinstance(value, str):
        try:
            value = float(value.strip().replace(",", "."))
        except ValueError as err:
            raise ValueConversionError(f"legacy {field} must be numeric") from err
    if not isinstance(value, (int, float)):
        raise ValueConversionError(f"legacy {field} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueConversionError(f"legacy {field} must be finite")
    return value


def _validate_new(config: Any, channel: str) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise ValueConversionError(f"value_conversions.{channel} must be a mapping")
    result = deepcopy(dict(config))
    kind = result.get("type")
    if kind == "multiplier":
        factor = _number(result.get("factor"), "factor")
        if factor == 0:
            raise ValueConversionError("multiplier factor must not be zero")
    elif kind == "linear_scale":
        values = [
            _number(result.get(key), key)
            for key in ("plc_min", "plc_max", "ha_min", "ha_max")
        ]
        if values[0] == values[1] or values[2] == values[3]:
            raise ValueConversionError("scale intervals must not be zero")
        if channel == "brightness" and (
            values[2:] != [0, 255] or result.get("clamp") is not True
        ):
            raise ValueConversionError(
                "brightness conversion must use HA 0..255 with clamp"
            )
    elif kind in ("expression", "logo_time_bcd"):
        # Full address/direction-aware validation happens before persistence.
        pass
    else:
        raise ValueConversionError(f"unknown conversion type: {kind}")
    return result


def _equivalent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Compare semantics while ignoring optional serialization defaults."""
    keys = set(left) | set(right)
    for key in keys:
        default = (
            False if key == "clamp" else "half_even" if key == "rounding" else None
        )
        if left.get(key, default) != right.get(key, default):
            return False
    return True


def migrate_legacy_value_conversions(
    entity_type: str, entity: Mapping[str, Any]
) -> tuple[dict[str, Any], MigrationReport]:
    """Return a migrated deep copy of one entity without modifying *entity*."""
    result = deepcopy(dict(entity))
    conversions_raw = result.get("value_conversions")
    if conversions_raw is not None and not isinstance(conversions_raw, Mapping):
        raise ValueConversionError("value_conversions must be a mapping")
    conversions = deepcopy(dict(conversions_raw or {}))
    conflicts: list[str] = []
    multipliers = scales = brightness_scales = 0

    candidates: list[tuple[str, dict[str, Any], tuple[str, ...], str]] = []
    value_fields_present = [key for key in LEGACY_VALUE_FIELDS if key in result]
    scale_present = [key for key in ("scale_raw_min", "scale_raw_max") if key in result]
    if scale_present:
        required = ("scale_raw_min", "scale_raw_max", "min_value", "max_value")
        missing = [
            key for key in required if key not in result or result[key] in (None, "")
        ]
        if missing:
            raise ValueConversionError(
                f"incomplete legacy scale; missing {', '.join(missing)}"
            )
        values = [_number(result[key], key) for key in required]
        if values[0] == values[1] or values[2] == values[3]:
            raise ValueConversionError("legacy scale intervals must not be zero")
        candidates.append(
            (
                "value",
                {
                    "type": "linear_scale",
                    "plc_min": values[0],
                    "plc_max": values[1],
                    "ha_min": values[2],
                    "ha_max": values[3],
                    "clamp": False,
                },
                tuple(value_fields_present),
                "linear_scale",
            )
        )
    elif "value_multiplier" in result:
        factor = _number(result["value_multiplier"], "value_multiplier")
        # Writable numbers historically treated zero as identity.  Migrating it
        # to a multiplier would make division undefined, therefore fail safely.
        if entity_type == "numbers" and factor == 0:
            raise ValueConversionError("legacy writable multiplier must not be zero")
        candidates.append(
            (
                "value",
                {"type": "multiplier", "factor": factor},
                ("value_multiplier",),
                "multiplier",
            )
        )

    if "brightness_scale" in result:
        maximum = _number(result["brightness_scale"], "brightness_scale")
        if maximum < 1:
            # The builder historically canonicalized new input to >= 1; a raw
            # persisted value below it is corrupt and must not be silently fixed.
            raise ValueConversionError("legacy brightness_scale must be at least 1")
        candidates.append(
            (
                "brightness",
                {
                    "type": "linear_scale",
                    "plc_min": 0,
                    "plc_max": maximum,
                    "ha_min": 0,
                    "ha_max": 255,
                    "clamp": True,
                    "rounding": "half_even",
                },
                ("brightness_scale",),
                "brightness_scale",
            )
        )

    for channel, legacy, fields, count_kind in candidates:
        if count_kind == "multiplier":
            multipliers += 1
        elif count_kind == "linear_scale":
            scales += 1
        else:
            brightness_scales += 1
        configured = conversions.get(channel)
        if configured is not None:
            configured = _validate_new(configured, channel)
            if not _equivalent(configured, legacy):
                conflicts.append(channel)
        else:
            conversions[channel] = legacy
        for field in fields:
            result.pop(field, None)

    if conversions:
        result["value_conversions"] = conversions
    else:
        result.pop("value_conversions", None)
    changed = result != dict(entity)
    return result, MigrationReport(
        changed, multipliers, scales, brightness_scales, tuple(conflicts)
    )


# TODO 8.0.0:
# Reject legacy conversion fields in new YAML/import input.
# Keep config-entry migrations for direct upgrades.
def normalize_legacy_conversion_input(entity_type: str, entity: Mapping[str, Any]):
    """Normalize deprecated 7.x YAML/import input before persistence."""
    return migrate_legacy_value_conversions(entity_type, entity)
