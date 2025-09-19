"""Diagnostics support for the S7 PLC integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BINARY_SENSORS,
    CONF_BUTTONS,
    CONF_LIGHTS,
    CONF_RACK,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_SWITCHES,
    DOMAIN,
)


def _iso_or_none(value: Any) -> str | None:
    """Return an ISO formatted string for datetime like values."""

    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    return str(value)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    entry_data = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": dict(entry.data),
        "options": dict(entry.options),
    }

    diagnostics: dict[str, Any] = {
        "config_entry": entry_data,
    }

    domain_data = hass.data.get(DOMAIN, {})
    runtime = domain_data.get(entry.entry_id)
    if not runtime:
        return diagnostics

    coordinator = runtime.get("coordinator")

    runtime_info: dict[str, Any] = {
        "device": {
            "name": runtime.get("name"),
            "device_id": runtime.get("device_id"),
            "host": runtime.get("host"),
        },
    }

    if coordinator is not None:
        update_interval = getattr(coordinator, "update_interval", None)
        if update_interval is not None:
            update_interval = getattr(update_interval, "total_seconds", None)
            if callable(update_interval):
                try:
                    update_interval = update_interval()
                except TypeError:
                    update_interval = None

        plans_batch = getattr(coordinator, "_plans_batch", [])
        plans_str = getattr(coordinator, "_plans_str", [])
        items = dict(getattr(coordinator, "_items", {}))

        coordinator_info: dict[str, Any] = {
            "connected": coordinator.is_connected(),
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": update_interval,
            "registered_topics": sorted(items.keys()),
            "configured_items": [
                {"topic": topic, "address": address}
                for topic, address in sorted(items.items())
            ],
            "planned_batches": len(plans_batch),
            "planned_strings": len(plans_str),
            "stored_values": coordinator.data,
            "option_counts": {
                CONF_SENSORS: len(entry.options.get(CONF_SENSORS, [])),
                CONF_BINARY_SENSORS: len(entry.options.get(CONF_BINARY_SENSORS, [])),
                CONF_SWITCHES: len(entry.options.get(CONF_SWITCHES, [])),
                CONF_LIGHTS: len(entry.options.get(CONF_LIGHTS, [])),
                CONF_BUTTONS: len(entry.options.get(CONF_BUTTONS, [])),
            },
            "rack": entry.data.get(CONF_RACK),
            "slot": entry.data.get(CONF_SLOT),
        }

        last_success_time = _iso_or_none(
            getattr(coordinator, "last_update_success_time", None)
        )
        if last_success_time is not None:
            coordinator_info["last_update_success_time"] = last_success_time

        last_failure_time = _iso_or_none(
            getattr(coordinator, "last_update_failure_time", None)
        )
        if last_failure_time is not None:
            coordinator_info["last_update_failure_time"] = last_failure_time

        last_exception = getattr(coordinator, "last_exception", None)
        if last_exception is not None:
            coordinator_info["last_exception"] = repr(last_exception)

        runtime_info["coordinator"] = coordinator_info

    diagnostics["runtime"] = runtime_info

    return diagnostics