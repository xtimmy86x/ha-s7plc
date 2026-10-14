"""Serialize PLC values for entity-local Home Assistant state restoration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.helpers.restore_state import ExtraStoredData


@dataclass
class S7StoredData(ExtraStoredData):
    """Versioned snapshot; values remain in PLC units, before conversion."""

    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.data


def _is_byte_array(value: Any) -> bool:
    """Bound block snapshots and reject malformed bytes on restore."""
    return (
        isinstance(value, (list, tuple, bytes, bytearray))
        and 0 < len(value) <= 200
        and all(type(byte) is int and 0 <= byte <= 255 for byte in value)
    )


def encode_values(values: dict[str, Any]) -> dict[str, Any]:
    """Keep valid scalar readings, including typed pyS7 TIME values."""
    result = {}
    for topic, value in values.items():
        if topic.startswith("alarm_group:") and _is_byte_array(value):
            result[topic] = {"byte_array": list(value)}
        elif isinstance(value, timedelta):
            result[topic] = {"timedelta_seconds": value.total_seconds()}
        elif (
            isinstance(value, (str, bool, int))
            or isinstance(value, float)
            and math.isfinite(value)
        ):
            result[topic] = value
    return result


def decode_values(values: Any) -> dict[str, Any]:
    """Ignore malformed stored readings rather than inventing a default."""
    if not isinstance(values, dict):
        return {}
    result = {}
    for topic, value in values.items():
        if not isinstance(topic, str):
            continue
        if isinstance(value, dict):
            if topic.startswith("alarm_group:") and _is_byte_array(
                value.get("byte_array")
            ):
                result[topic] = value["byte_array"]
                continue
            seconds = value.get("timedelta_seconds")
            if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
                try:
                    result[topic] = timedelta(seconds=seconds)
                except (OverflowError, ValueError):
                    pass
        elif (
            isinstance(value, (str, bool, int))
            or isinstance(value, float)
            and math.isfinite(value)
        ):
            result[topic] = value
    return result
