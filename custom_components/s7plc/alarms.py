"""Validated, inclusive DB bit ranges and shared byte-block alarm decoding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .plc.address import DataType, MemoryArea, S7Tag, parse_tag

MAX_ALARM_BITS = 8192
# Fits the smallest supported S7 PDU (240 bytes), including protocol overhead.
ALARM_BLOCK_BYTES = 200


@dataclass(frozen=True)
class AlarmRange:
    db: int
    first: int
    last: int

    @classmethod
    def parse(cls, start: str, end: str) -> AlarmRange:
        def bit_tag(address: str):
            address = address.strip().upper()
            address = re.sub(r"^(DB\d+,)(?=\d+\.[0-7]$)", r"\1X", address)
            return parse_tag(address)

        a, b = bit_tag(start), bit_tag(end)
        if (
            a.data_type != DataType.BIT
            or b.data_type != DataType.BIT
            or a.memory_area != MemoryArea.DB
            or b.memory_area != MemoryArea.DB
            or a.db_number != b.db_number
        ):
            raise ValueError("alarm_range_invalid")
        first, last = a.start * 8 + a.bit_offset, b.start * 8 + b.bit_offset
        if not 0 <= first <= last or last - first + 1 > MAX_ALARM_BITS:
            raise ValueError("alarm_range_invalid")
        return cls(a.db_number, first, last)

    def address(self, bit: int) -> str:
        return f"DB{self.db},X{bit // 8}.{bit % 8}"

    def blocks(self, uid: str) -> list[tuple[str, S7Tag]]:
        end = self.last // 8 + 1
        return [
            (
                f"alarm_group:{uid}:{start}",
                S7Tag(
                    memory_area=MemoryArea.DB,
                    db_number=self.db,
                    data_type=DataType.BYTE,
                    start=start,
                    bit_offset=0,
                    length=min(ALARM_BLOCK_BYTES, end - start),
                ),
            )
            for start in range(self.first // 8, end, ALARM_BLOCK_BYTES)
        ]


def normalize_alarm_group(entity: dict[str, Any]) -> dict[str, Any]:
    """Validate overrides; unspecified bits are included with their address label."""
    try:
        region = AlarmRange.parse(
            entity.get("start_address", ""), entity.get("end_address", "")
        )
    except (ValueError, TypeError, AttributeError) as err:
        raise ValueError("alarm_range_invalid") from err
    active = entity.get("active_value", 1)
    if isinstance(active, bool) or active not in (0, 1, "0", "1"):
        raise ValueError("alarm_active_value_invalid")
    rows = entity.get("alarms", [])
    if not isinstance(rows, list) or len(rows) > MAX_ALARM_BITS:
        raise ValueError("alarm_mapping_invalid")
    alarms, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {
            "address",
            "description",
            "enabled",
        }:
            raise ValueError("alarm_mapping_invalid")
        try:
            bit = AlarmRange.parse(row.get("address", ""), row.get("address", ""))
        except (ValueError, TypeError, AttributeError) as err:
            raise ValueError("alarm_mapping_invalid") from err
        description, enabled = row.get("description", ""), row.get("enabled", True)
        if (
            bit.db != region.db
            or not region.first <= bit.first <= region.last
            or bit.first in seen
            or not isinstance(description, str)
            or len(description) > 255
            or not isinstance(enabled, bool)
        ):
            raise ValueError("alarm_mapping_invalid")
        seen.add(bit.first)
        alarms.append(
            {
                "address": region.address(bit.first),
                "description": description.strip(),
                "enabled": enabled,
            }
        )
    return {
        **entity,
        "start_address": region.address(region.first),
        "end_address": region.address(region.last),
        "active_value": int(active),
        "alarms": alarms,
    }


def active_alarms(item: dict, data: dict) -> list[dict[str, str]] | None:
    """Decode a complete sample. Missing/invalid bytes never mean no alarms."""
    region = AlarmRange.parse(item["start_address"], item["end_address"])
    raw = []
    for topic, tag in region.blocks(item["uid"]):
        value = data.get(topic)
        values = [value] if isinstance(value, int) else value
        if (
            not isinstance(values, (list, tuple, bytes, bytearray))
            or len(values) != tag.length
            or any(type(v) is not int or not 0 <= v <= 255 for v in values)
        ):
            return None
        raw.extend(values)
    overrides = {row["address"]: row for row in item.get("alarms", [])}
    active = item.get("active_value", 1)
    result = []
    for bit in range(region.first, region.last + 1):
        address = region.address(bit)
        row = overrides.get(address, {})
        if (
            row.get("enabled", True)
            and ((raw[bit // 8 - region.first // 8] >> (bit % 8)) & 1) == active
        ):
            result.append(
                {"address": address, "description": row.get("description") or address}
            )
    return result
