"""Diagnostics support for the S7 PLC integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BINARY_SENSORS,
    CONF_BUTTONS,
    CONF_CLIMATES,
    CONF_COVERS,
    CONF_ENTITY_SYNC,
    CONF_LIGHTS,
    CONF_LOCAL_TSAP,
    CONF_NUMBERS,
    CONF_RACK,
    CONF_REMOTE_TSAP,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_SWITCHES,
    CONF_TEXTS,
)

TO_REDACT: frozenset[str] = frozenset(
    {
        CONF_HOST,
        CONF_PORT,
        CONF_LOCAL_TSAP,
        CONF_REMOTE_TSAP,
    }
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
        "data": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
    }

    diagnostics: dict[str, Any] = {
        "config_entry": entry_data,
    }

    # Access runtime data directly from the config entry
    if not hasattr(entry, "runtime_data"):
        return diagnostics

    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator

    runtime_info: dict[str, Any] = {
        "device": async_redact_data(
            {
                "name": runtime_data.name,
                "device_id": runtime_data.device_id,
                CONF_HOST: runtime_data.host,
            },
            TO_REDACT,
        ),
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
                CONF_COVERS: len(entry.options.get(CONF_COVERS, [])),
                CONF_LIGHTS: len(entry.options.get(CONF_LIGHTS, [])),
                CONF_NUMBERS: len(entry.options.get(CONF_NUMBERS, [])),
                CONF_BUTTONS: len(entry.options.get(CONF_BUTTONS, [])),
                CONF_TEXTS: len(entry.options.get(CONF_TEXTS, [])),
                CONF_CLIMATES: len(entry.options.get(CONF_CLIMATES, [])),
                CONF_ENTITY_SYNC: len(entry.options.get(CONF_ENTITY_SYNC, [])),
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

        # Health probe info
        coordinator_info["health"] = {
            "ok": coordinator.last_health_ok,
            "latency_seconds": coordinator.last_health_latency,
        }

        # Error diagnostics
        error_info: dict[str, Any] = {
            "last_error_category": coordinator.last_error_category,
            "last_error_message": coordinator.last_error_message,
            "error_counts_by_category": coordinator.error_count_by_category,
        }
        if coordinator.error_count_by_category:
            error_info["total_errors"] = sum(
                coordinator.error_count_by_category.values()
            )
        coordinator_info["errors"] = error_info

        runtime_info["coordinator"] = coordinator_info

    diagnostics["runtime"] = runtime_info

    return diagnostics
