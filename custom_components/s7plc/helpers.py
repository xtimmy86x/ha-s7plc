"""Helper utilities shared by the S7 PLC platforms."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:  # pragma: no cover - used for type checking only
    from .coordinator import S7Coordinator


@dataclass
class RuntimeEntryData:
    """Runtime data stored for each config entry."""

    coordinator: "S7Coordinator"
    name: str
    host: str
    device_id: str


def get_coordinator_and_device_info(
    entry: ConfigEntry,
) -> tuple["S7Coordinator", DeviceInfo, str]:
    """Return the coordinator, device info and identifier for a config entry."""

    data: RuntimeEntryData = entry.runtime_data
    coordinator = data.coordinator
    device_id = data.device_id
    device_name = data.name

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
    )

    return coordinator, device_info, device_id


def default_entity_name(plc_name: str | None, address: str | None) -> str | None:
    """Return a default entity name using the PLC name and a humanized address."""

    if address:
        humanized = re.sub(r"[^0-9A-Za-z\.]+", " ", address)
        humanized = re.sub(r"\s+", " ", humanized).strip()
    else:
        humanized = None

    if plc_name and humanized:
        return f"{plc_name} {humanized.upper()}"

    return plc_name or humanized
