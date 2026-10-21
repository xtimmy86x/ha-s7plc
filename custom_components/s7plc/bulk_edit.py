"""Prepare an atomic entity patch and bind its preview to the configuration."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .config_validation import EntityConfigBuilder
from .const import CONF_UID, DEFAULT_SCAN_INTERVAL, OPTION_KEYS
from .entity_metadata import (
    METADATA_FIELDS,
    metadata_error,
    number_metadata,
    sensor_metadata,
)
from .helpers import STATE_CLASS_VALUES, device_class_values
from .plc.address import DataType, is_time_data_type, parse_tag
from .plc.plans import DEFAULT_REAL_PRECISION
from .value_conversion import (
    conversion_contexts,
    normalize_value_conversion,
    supports_value_conversion,
    validate_value_conversion,
)
from .value_conversion_migration import (
    LEGACY_VALUE_FIELDS,
    normalize_legacy_conversion_input,
)

BULK_EDIT_FIELDS = frozenset(
    {"area", "scan_interval", "value_multiplier", "real_precision"} | METADATA_FIELDS
)
# Match the panel: these platforms are driven by commands or HA events.
SCAN_ENTITY_TYPES = frozenset(OPTION_KEYS) - {"buttons", "entity_sync"}
DEVICE_CLASS_TYPES = frozenset({"sensors", "numbers", "binary_sensors", "covers"})


def _validate_changes(changes: dict) -> dict:
    """Reject malformed values even when every selected entity is unsupported."""
    if not changes or not changes.keys() <= BULK_EDIT_FIELDS:
        raise ValueError("invalid_bulk_changes")
    changes = dict(changes)
    for field in ("area", *METADATA_FIELDS):
        value = changes.get(field)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    "invalid_bulk_area" if field == "area" else f"invalid_{field}"
                )
            changes[field] = value.strip()
    for field in ("scan_interval", "value_multiplier"):
        value = changes.get(field)
        if value is not None:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"invalid_bulk_{field}")
            changes[field] = float(value)
    interval = changes.get("scan_interval")
    if (
        interval is not None
        and not EntityConfigBuilder._MIN_ITEM_SCAN_INTERVAL
        <= interval
        <= EntityConfigBuilder._MAX_ITEM_SCAN_INTERVAL
    ):
        raise ValueError("invalid_bulk_scan_interval")
    precision = changes.get("real_precision")
    if precision is not None and (
        type(precision) is not int or not 0 <= precision <= 6
    ):
        raise ValueError("invalid_bulk_real_precision")
    if changes.get("device_class") and changes["device_class"] not in {
        value for kind in DEVICE_CLASS_TYPES for value in device_class_values(kind)
    }:
        raise ValueError("invalid_device_class")
    if changes.get("state_class") and changes["state_class"] not in (
        *STATE_CLASS_VALUES,
        "none",
    ):
        raise ValueError("invalid_state_class")
    return changes


def bulk_edit_fields(entity_type: str, item: dict) -> set[str]:
    """List supported fields; semantic conflicts are reported separately."""
    fields = {"area"}
    if entity_type in SCAN_ENTITY_TYPES:
        fields.add("scan_interval")
    if entity_type in {"binary_sensors", "covers"}:
        fields.add("device_class")
    if entity_type not in {"sensors", "numbers"}:
        return fields
    try:
        data_type = parse_tag(item["address"]).data_type
        conversion = normalize_value_conversion(item, "value")
        if not supports_value_conversion(data_type) or (
            conversion and conversion.get("type") == "enum_map"
        ):
            return fields
        fields.update({"device_class", "unit_of_measurement"})
        if entity_type == "sensors":
            fields.add("state_class")
        if data_type in {DataType.REAL, DataType.LREAL}:
            fields.add("real_precision")
        # Clock/enum conversions have a different meaning; retain them in bulk.
        if not conversion or conversion.get("type") != "logo_time_bcd":
            if all(
                supports_value_conversion(context.data_type)
                for context in conversion_contexts(entity_type, item, "value")
            ):
                fields.add("value_multiplier")
    except (KeyError, RuntimeError, ValueError):
        pass
    return fields


def _conversion(entity_type: str, item: dict) -> dict | None:
    """Show canonical and legacy conversions without normalizing other fields."""
    normalized, _ = normalize_legacy_conversion_input(entity_type, item)
    return normalize_value_conversion(normalized, "value")


def _set_multiplier(item: dict, value: float | None) -> None:
    conversions = dict(item.get("value_conversions") or {})
    if value is None:
        conversions.pop("value", None)
    else:
        conversions["value"] = {"type": "multiplier", "factor": value}
    if conversions:
        item["value_conversions"] = conversions
    else:
        item.pop("value_conversions", None)
    for field in LEGACY_VALUE_FIELDS:
        item.pop(field, None)


def _effective_metadata(entity_type: str, item: dict) -> dict:
    if entity_type not in {"sensors", "numbers"}:
        return {"device_class": item.get("device_class")}
    is_time = is_time_data_type(parse_tag(item["address"]).data_type)
    args = (item.get("device_class"), item.get("unit_of_measurement"))
    attributes = (
        sensor_metadata(*args, item.get("state_class"), is_time=is_time)
        if entity_type == "sensors"
        else number_metadata(*args, is_time=is_time)
    )
    return {
        "device_class": attributes["_attr_device_class"],
        "unit_of_measurement": attributes["_attr_native_unit_of_measurement"],
        "state_class": attributes.get("_attr_state_class"),
    }


def prepare_bulk_edit(entry, targets: list[dict], changes: dict) -> tuple[dict, dict]:
    """Return a new options mapping and preview without touching the entry.

    Patch only the requested fields. Rebuilding an entire item would normalize
    unrelated legacy settings and could introduce changes absent from the preview.
    """
    changes = _validate_changes(changes)
    if not targets:
        raise ValueError("invalid_selection")

    options = dict(entry.options)
    selected = set()
    lookups = {}
    rows: list[dict[str, Any]] = []
    for target in targets:
        entity_type, uid = target["entity_type"], target["uid"]
        identity = (entity_type, uid)
        if entity_type not in OPTION_KEYS or not uid or identity in selected:
            raise ValueError("invalid_selection")
        selected.add(identity)
        if entity_type not in lookups:
            options[entity_type] = list(options.get(entity_type, []))
            lookup = lookups[entity_type] = {}
            for index, item in enumerate(options[entity_type]):
                key = item.get(CONF_UID)
                lookup[key] = None if key in lookup else index
        items = options[entity_type]
        index = lookups[entity_type].get(uid)
        if index is None:
            raise ValueError("invalid_selection")
        old = items[index]
        new = dict(old)
        supported = bulk_edit_fields(entity_type, old)
        for field, value in changes.items():
            if field not in supported:
                continue
            if field == "value_multiplier":
                _set_multiplier(new, value)
            elif value is None:
                new.pop(field, None)
            else:
                new[field] = value
        errors = []
        active_fields = changes.keys() & supported
        if active_fields & METADATA_FIELDS:
            if error := metadata_error(entity_type, new):
                errors.append(error)
        if "value_multiplier" in active_fields:
            conversion = normalize_value_conversion(new, "value")
            try:
                for context in conversion_contexts(entity_type, new, "value"):
                    validate_value_conversion(conversion, context)
            except ValueError:
                errors.append("invalid_bulk_write_multiplier")
        before = {field: old.get(field) for field in changes}
        after = {field: new.get(field) for field in changes}
        replacement = False
        if "value_multiplier" in active_fields:
            before["value_multiplier"] = _conversion(entity_type, old)
            after["value_multiplier"] = _conversion(entity_type, new)
            replacement = bool(
                before["value_multiplier"]
                and before["value_multiplier"].get("type") != "multiplier"
                and before["value_multiplier"] != after["value_multiplier"]
            )
        rows.append(
            {
                **target,
                "name": old.get("name"),
                "address": next(
                    (
                        old[key]
                        for key in (
                            "address",
                            "state_address",
                            "position_state_address",
                            "open_command_address",
                            "current_temperature_address",
                            "start_address",
                        )
                        if old.get(key)
                    ),
                    None,
                ),
                "before": before,
                "after": after,
                "effective_before": (
                    _effective_metadata(entity_type, old)
                    if active_fields & METADATA_FIELDS
                    else {}
                ),
                "effective_after": (
                    _effective_metadata(entity_type, new)
                    if active_fields & METADATA_FIELDS
                    else {}
                ),
                "supported_fields": sorted(supported),
                "scan_supported": "scan_interval" in supported,
                "conversion_replaced": replacement,
                "errors": errors,
                "changed": old != new,
            }
        )
        items[index] = new

    # Bind the token to this entry, the complete config and the exact operation.
    # Any concurrent edit requires a fresh preview; no server token store needed.
    snapshot = {
        "entry_id": entry.entry_id,
        "data": dict(entry.data),
        "options": dict(entry.options),
        "targets": targets,
        "changes": changes,
    }
    token = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return options, {
        "preview_token": token,
        "rows": rows,
        "changed_count": sum(row["changed"] for row in rows),
        "error_count": sum(bool(row["errors"]) for row in rows),
        "default_scan_interval": entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
        "default_real_precision": DEFAULT_REAL_PRECISION,
    }
