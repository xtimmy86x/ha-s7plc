"""Helper utilities shared by the S7 PLC platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:  # pragma: no cover - used for type checking only
    from .coordinator import S7Coordinator


class RuntimeEntryData(TypedDict):
    """Runtime data stored for each config entry."""

    coordinator: "S7Coordinator"
    name: str
    device_id: str


def get_coordinator_and_device_info(
    hass: HomeAssistant, entry: ConfigEntry
) -> tuple["S7Coordinator", DeviceInfo, str]:
    """Return the coordinator, device info and identifier for a config entry."""

    data: RuntimeEntryData = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device_id = data["device_id"]
    device_name = data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
    )

    return coordinator, device_info, device_id