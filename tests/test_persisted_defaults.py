"""Defaults are applied at runtime instead of being persisted by the builders."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.s7plc import async_migrate_entry
from custom_components.s7plc.climate import async_setup_entry as climate_setup_entry
from custom_components.s7plc.config_entry_migration import strip_persisted_defaults
from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import (
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_PULSE_DURATION,
    DEFAULT_TEMP_STEP,
)
from custom_components.s7plc.cover import async_setup_entry as cover_setup_entry
from custom_components.s7plc.switch import async_setup_entry as switch_setup_entry

DEVICE_INFO = {"name": "Test PLC"}
TRADITIONAL_COVER = {
    "open_command_address": "DB1,X0.0",
    "close_command_address": "DB1,X0.1",
}
POSITION_COVER = {
    "position_state_address": "DB1,B2",
    "position_command_address": "DB1,B3",
    "stop_command_address": "DB1,X4.0",
}
TOGGLE_COVER = {
    "open_command_address": "DB1,X0.0",
    "toggle_mode": True,
    "cover_status_address": "DB1,B10",
    "cover_status_open_values": "0",
    "cover_status_closed_values": "1",
    "cover_status_opening_values": "2",
    "cover_status_closing_values": "3",
    "cover_status_stopped_values": "4",
}
SETPOINT_CLIMATE = {
    "control_mode": "setpoint",
    "current_temperature_address": "DB1,REAL0",
    "target_temperature_address": "DB1,REAL4",
}
DIRECT_CLIMATE = {
    "control_mode": "direct",
    "current_temperature_address": "DB1,REAL0",
    "heating_output_address": "DB1,X8.0",
}
DEFAULT_KEYS = (
    "pulse_duration",
    "button_pulse",
    "operate_time",
    "stop_pulse_duration",
    "toggle_pulse_duration",
    "min_temp",
    "max_temp",
    "temp_step",
)


@pytest.mark.parametrize(
    ("entity_type", "entity", "keys"),
    [
        (
            "switches",
            {"state_address": "DB1,X0.0", "pulse_command": True},
            ("pulse_duration",),
        ),
        (
            "lights",
            {"state_address": "DB1,X0.0", "pulse_command": True},
            ("pulse_duration",),
        ),
        ("buttons", {"address": "DB1,X0.0"}, ("button_pulse",)),
        ("covers", TRADITIONAL_COVER, ("operate_time",)),
        ("covers", POSITION_COVER, ("stop_pulse_duration",)),
        ("covers", TOGGLE_COVER, ("operate_time", "toggle_pulse_duration")),
        ("climates", SETPOINT_CLIMATE, ("min_temp", "max_temp", "temp_step")),
        ("climates", DIRECT_CLIMATE, ("min_temp", "max_temp", "temp_step")),
    ],
)
@pytest.mark.parametrize("empty", [None, ""])
def test_empty_fields_are_not_persisted(
    entity_type: str, entity: dict[str, Any], keys: tuple[str, ...], empty: Any
) -> None:
    item, errors = build_entity_item(
        entity_type, {**entity, **dict.fromkeys(keys, empty)}, options={}
    )
    assert errors == {}
    assert not set(DEFAULT_KEYS) & item.keys()


@pytest.mark.parametrize(
    ("entity_type", "entity", "values"),
    [
        ("buttons", {"address": "DB1,X0.0"}, {"button_pulse": 2}),
        ("covers", TRADITIONAL_COVER, {"operate_time": 0}),
        ("covers", TRADITIONAL_COVER, {"operate_time": "60"}),
        ("covers", POSITION_COVER, {"stop_pulse_duration": 0.5}),
        ("covers", TOGGLE_COVER, {"toggle_pulse_duration": "1,5"}),
        (
            "climates",
            SETPOINT_CLIMATE,
            {"min_temp": "5", "max_temp": 28, "temp_step": 0.1},
        ),
        ("climates", DIRECT_CLIMATE, {"min_temp": 7, "max_temp": 35}),
    ],
)
def test_explicit_values_are_persisted_even_when_equal_to_default(
    entity_type: str, entity: dict[str, Any], values: dict[str, Any]
) -> None:
    item, errors = build_entity_item(entity_type, {**entity, **values}, options={})
    assert errors == {}
    for key, value in values.items():
        assert item[key] == float(str(value).replace(",", "."))


@pytest.mark.parametrize(
    ("entity_type", "entity", "values", "error"),
    [
        ("buttons", {"address": "DB1,X0.0"}, {"button_pulse": 0}, "pulse"),
        ("buttons", {"address": "DB1,X0.0"}, {"button_pulse": "abc"}, "pulse"),
        ("covers", POSITION_COVER, {"stop_pulse_duration": 61}, "pulse"),
        ("covers", POSITION_COVER, {"stop_pulse_duration": "x"}, "pulse"),
        ("covers", TRADITIONAL_COVER, {"operate_time": -1}, "operate"),
        ("covers", TRADITIONAL_COVER, {"operate_time": "abc"}, "operate"),
        ("covers", TRADITIONAL_COVER, {"operate_time": True}, "operate"),
        ("climates", SETPOINT_CLIMATE, {"min_temp": 30, "max_temp": 20}, "temp"),
        ("climates", SETPOINT_CLIMATE, {"min_temp": 40}, "temp"),
        ("climates", DIRECT_CLIMATE, {"max_temp": 5}, "temp"),
        ("climates", DIRECT_CLIMATE, {"temp_step": 0}, "temp"),
        ("climates", DIRECT_CLIMATE, {"temp_step": "abc"}, "temp"),
    ],
)
def test_invalid_values_are_reported_instead_of_replaced(
    entity_type: str, entity: dict[str, Any], values: dict[str, Any], error: str
) -> None:
    expected = {
        "pulse": "invalid_pulse_duration",
        "operate": "invalid_operate_time",
        "temp": "invalid_temperature_limits",
    }[error]
    assert build_entity_item(entity_type, {**entity, **values}, options={}) == (
        None,
        {"base": expected},
    )


@pytest.mark.asyncio
async def test_switch_without_pulse_duration_uses_default(fake_hass, mock_coordinator):
    entry = MagicMock()
    entry.options = {
        "switches": [
            {
                "state_address": "db1,x0.0",
                "command_address": "db1,x0.1",
                "pulse_command": True,
                "uid": "uid-1",
            }
        ]
    }
    add_entities = MagicMock()
    with patch(
        "custom_components.s7plc.switch.get_coordinator_and_device_info",
        return_value=(mock_coordinator, DEVICE_INFO, "test_device"),
    ):
        await switch_setup_entry(fake_hass, entry, add_entities)
    assert add_entities.call_args[0][0][0]._pulse_duration == DEFAULT_PULSE_DURATION


@pytest.mark.asyncio
async def test_cover_without_pulse_fields_uses_defaults(fake_hass, mock_coordinator):
    entry = MagicMock()
    entry.options = {
        "covers": [
            {**POSITION_COVER, "uid": "position"},
            {**TOGGLE_COVER, "uid": "toggle"},
        ]
    }
    add_entities = MagicMock()
    with patch(
        "custom_components.s7plc.cover.get_coordinator_and_device_info",
        return_value=(mock_coordinator, DEVICE_INFO, "test_device"),
    ):
        await cover_setup_entry(fake_hass, entry, add_entities)
    entities = [call.args[0] for call in add_entities.call_args_list]
    covers = [cover for group in entities for cover in group]
    position = next(c for c in covers if hasattr(c, "_stop_pulse_duration"))
    toggle = next(c for c in covers if hasattr(c, "_toggle_pulse_duration"))
    assert position._stop_pulse_duration == DEFAULT_PULSE_DURATION
    assert toggle._toggle_pulse_duration == DEFAULT_PULSE_DURATION


@pytest.mark.asyncio
async def test_climate_without_limits_uses_defaults(fake_hass, mock_coordinator):
    entry = MagicMock()
    entry.options = {"climates": [{**SETPOINT_CLIMATE, "uid": "uid-1"}]}
    add_entities = MagicMock()
    with patch(
        "custom_components.s7plc.climate.get_coordinator_and_device_info",
        return_value=(mock_coordinator, DEVICE_INFO, "test_device"),
    ):
        await climate_setup_entry(fake_hass, entry, add_entities)
    climate = add_entities.call_args[0][0][0]
    assert climate._attr_min_temp == DEFAULT_MIN_TEMP
    assert climate._attr_max_temp == DEFAULT_MAX_TEMP
    assert climate._attr_target_temperature_step == DEFAULT_TEMP_STEP


def test_strip_persisted_defaults_only_removes_matching_values() -> None:
    entity = {
        "operate_time": 60,
        "stop_pulse_duration": "0.5",
        "toggle_pulse_duration": 1.5,
        "open_command_address": "DB1,X0.0",
    }
    stripped, removed = strip_persisted_defaults("covers", entity)
    assert removed == 2
    assert stripped == {"toggle_pulse_duration": 1.5, "open_command_address": "DB1,X0.0"}
    assert entity["operate_time"] == 60  # the input is never mutated

    climate = {"min_temp": 7.0, "max_temp": 30, "temp_step": True}
    assert strip_persisted_defaults("climates", climate) == (
        {"max_temp": 30, "temp_step": True},
        1,
    )
    assert strip_persisted_defaults("covers", "broken") == ("broken", 0)
    # Keys are only stripped for the entity type that defaulted them.
    assert strip_persisted_defaults("sensors", {"operate_time": 60}) == (
        {"operate_time": 60},
        0,
    )


def _migration_hass(calls: list[dict[str, Any]]) -> SimpleNamespace:
    def update(target, **changes):
        calls.append(changes)
        for key, value in changes.items():
            setattr(target, key, value)

    return SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))


@pytest.mark.asyncio
async def test_current_entries_drop_stored_defaults_once() -> None:
    entry = SimpleNamespace(
        version=3,
        minor_version=1,
        entry_id="plc",
        options={
            "buttons": [{"uid": "b", "address": "DB1,X0.0", "button_pulse": 0.5}],
            "switches": [{"uid": "s", "state_address": "DB1,X0.1", "pulse_duration": 2}],
            "climates": [
                {"uid": "c", **SETPOINT_CLIMATE, "min_temp": 7, "max_temp": 35.0}
            ],
            "lights": None,
            "scan_interval": 1,
        },
    )
    calls: list[dict[str, Any]] = []
    hass = _migration_hass(calls)

    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1
    assert entry.version == 3
    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    assert entry.options["buttons"] == [{"uid": "b", "address": "DB1,X0.0"}]
    assert entry.options["switches"][0]["pulse_duration"] == 2
    assert "min_temp" not in entry.options["climates"][0]
    assert "max_temp" not in entry.options["climates"][0]
    assert entry.options["scan_interval"] == 1
    assert entry.options["lights"] is None

    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_legacy_entries_drop_stored_defaults_in_the_same_update() -> None:
    entry = SimpleNamespace(
        version=1,
        minor_version=1,
        entry_id="legacy",
        options={"covers": [{**TRADITIONAL_COVER, "uid": "c", "operate_time": 60.0}]},
    )
    calls: list[dict[str, Any]] = []
    hass = _migration_hass(calls)

    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1
    assert calls[0]["version"] == 3
    assert calls[0]["minor_version"] == CONFIG_ENTRY_MINOR_VERSION
    assert "operate_time" not in entry.options["covers"][0]
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1
