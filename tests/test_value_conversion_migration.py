"""Tests for persistent legacy conversion migration."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

import pytest

from custom_components.s7plc.value_conversion import ValueConversionError
from custom_components.s7plc.value_conversion_migration import (
    migrate_legacy_value_conversions,
    normalize_legacy_conversion_input,
)
from custom_components.s7plc import async_migrate_entry


@pytest.mark.parametrize(
    ("entity_type", "legacy", "channel", "expected"),
    [
        (
            "sensors",
            {"value_multiplier": 2.5},
            "value",
            {"type": "multiplier", "factor": 2.5},
        ),
        (
            "numbers",
            {"value_multiplier": -2},
            "value",
            {"type": "multiplier", "factor": -2},
        ),
        (
            "sensors",
            {
                "scale_raw_min": 0,
                "scale_raw_max": 27648,
                "min_value": 0,
                "max_value": 100,
            },
            "value",
            {
                "type": "linear_scale",
                "plc_min": 0,
                "plc_max": 27648,
                "ha_min": 0,
                "ha_max": 100,
                "clamp": False,
            },
        ),
        (
            "lights",
            {"brightness_scale": 1000},
            "brightness",
            {
                "type": "linear_scale",
                "plc_min": 0,
                "plc_max": 1000,
                "ha_min": 0,
                "ha_max": 255,
                "clamp": True,
                "rounding": "half_even",
            },
        ),
    ],
)
def test_migration_is_pure_and_idempotent(entity_type, legacy, channel, expected):
    entity = {"uid": "unchanged", "unknown": {"nested": True}, **legacy}
    original = deepcopy(entity)
    migrated, report = migrate_legacy_value_conversions(entity_type, entity)

    assert entity == original
    assert migrated["uid"] == "unchanged"
    assert migrated["unknown"] == {"nested": True}
    assert migrated["value_conversions"][channel] == expected
    assert not {
        "value_multiplier",
        "scale_raw_min",
        "scale_raw_max",
        "brightness_scale",
    } & set(migrated)
    assert report.changed
    assert migrate_legacy_value_conversions(entity_type, migrated)[0] == migrated


@pytest.mark.parametrize("legacy_maximum", [0, -1, "invalid", 65536])
def test_input_normalization_defaults_invalid_legacy_brightness_scale(
    legacy_maximum,
):
    """Invalid 7.x brightness maxima retain the old builder's safe default."""
    normalized, report = normalize_legacy_conversion_input(
        "lights", {"brightness_scale": legacy_maximum}
    )

    assert report.changed
    assert "brightness_scale" not in normalized
    assert normalized["value_conversions"]["brightness"]["plc_max"] == 255


def test_input_normalization_converts_legacy_value_multiplier() -> None:
    """The 7.x sensor multiplier is canonicalized at the input boundary."""
    normalized, report = normalize_legacy_conversion_input(
        "sensors", {"address": "DB1,REAL0", "value_multiplier": 2.5}
    )

    assert report.changed
    assert "value_multiplier" not in normalized
    assert normalized["value_conversions"]["value"] == {
        "type": "multiplier",
        "factor": 2.5,
    }


@pytest.mark.parametrize(
    "operation", [migrate_legacy_value_conversions, normalize_legacy_conversion_input]
)
def test_sensor_scale_consumes_limits_but_number_scale_preserves_them(operation):
    legacy = {
        "scale_raw_min": 0,
        "scale_raw_max": 27648,
        "min_value": -20,
        "max_value": 80,
    }
    sensor, sensor_report = operation("sensors", legacy)
    number, number_report = operation("numbers", legacy)
    assert sensor["value_conversions"]["value"] == number["value_conversions"]["value"]
    assert (
        not {"scale_raw_min", "scale_raw_max", "min_value", "max_value"} & sensor.keys()
    )
    assert not {"scale_raw_min", "scale_raw_max"} & number.keys()
    assert number["min_value"] == -20
    assert number["max_value"] == 80
    assert sensor_report.discarded_sensor_limits == 2
    assert number_report.discarded_sensor_limits == 0


def test_isolated_sensor_limits_are_discarded_without_conversion():
    migrated, report = migrate_legacy_value_conversions(
        "sensors", {"address": "DB1,REAL0", "min_value": -10, "max_value": 10}
    )
    assert migrated == {"address": "DB1,REAL0"}
    assert "value_conversions" not in migrated
    assert report.discarded_sensor_limits == 2
    number, number_report = migrate_legacy_value_conversions(
        "numbers", {"address": "DB1,REAL0", "min_value": -10, "max_value": 10}
    )
    assert number["min_value"] == -10 and number["max_value"] == 10
    assert not number_report.changed
    assert number_report.discarded_sensor_limits == 0


def test_single_isolated_sensor_limit_is_counted_once():
    migrated, report = migrate_legacy_value_conversions(
        "sensors", {"address": "DB1,REAL0", "min_value": -10}
    )
    assert migrated == {"address": "DB1,REAL0"}
    assert report.discarded_sensor_limits == 1


def test_sensor_without_limits_reports_no_discarded_limits():
    migrated, report = migrate_legacy_value_conversions(
        "sensors", {"address": "DB1,REAL0", "value_multiplier": 2}
    )
    assert migrated["value_conversions"]["value"]["factor"] == 2
    assert report.discarded_sensor_limits == 0


@pytest.mark.parametrize(
    "legacy",
    [
        {"scale_raw_min": 0},
        {"scale_raw_max": 10},
        {"scale_raw_min": 1, "scale_raw_max": 1, "min_value": 0, "max_value": 10},
        {"value_multiplier": "bad"},
    ],
)
def test_corrupt_legacy_configuration_fails_without_mutation(legacy):
    original = deepcopy(legacy)
    with pytest.raises(ValueConversionError):
        migrate_legacy_value_conversions("sensors", legacy)
    assert legacy == original


def test_valid_new_conversion_is_authoritative_in_conflict():
    entity = {
        "value_multiplier": 10,
        "value_conversions": {"value": {"type": "multiplier", "factor": 3}},
    }
    migrated, report = migrate_legacy_value_conversions("numbers", entity)
    assert migrated["value_conversions"]["value"]["factor"] == 3
    assert "value_multiplier" not in migrated
    assert report.conflicts == ("value",)


def test_invalid_new_conversion_does_not_delete_legacy():
    entity = {
        "value_multiplier": 10,
        "value_conversions": {"value": {"type": "multiplier", "factor": "bad"}},
    }
    with pytest.raises(ValueConversionError):
        migrate_legacy_value_conversions("numbers", entity)
    assert entity["value_multiplier"] == 10


@pytest.mark.asyncio
async def test_config_entry_migration_is_atomic_and_idempotent():
    entry = SimpleNamespace(
        version=1,
        entry_id="plc-one",
        options={
            "sensors": [
                {"uid": "one", "address": "DB1,REAL0", "value_multiplier": 10},
                {"uid": "two", "address": "DB1,REAL4"},
            ]
        },
    )
    calls = []

    def update(target, **changes):
        calls.append(changes)
        target.options = changes["options"]
        target.version = changes["version"]

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1
    assert entry.version == 3
    assert [item["uid"] for item in entry.options["sensors"]] == ["one", "two"]
    assert entry.options["sensors"][0]["value_conversions"]["value"]["factor"] == 10
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_previous_version_is_cleaned_for_sensors_without_changing_numbers():
    entry = SimpleNamespace(
        version=2,
        entry_id="branch-upgrade",
        options={
            "sensors": [
                {
                    "address": "DB1,REAL0",
                    "min_value": 0,
                    "max_value": 100,
                    "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
                }
            ],
            "numbers": [{"address": "DB1,INT4", "min_value": -10, "max_value": 10}],
        },
    )
    calls = []

    def update(target, **changes):
        calls.append(deepcopy(changes))
        target.options = changes["options"]
        target.version = changes["version"]

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 3
    assert "min_value" not in entry.options["sensors"][0]
    assert "max_value" not in entry.options["sensors"][0]
    assert entry.options["numbers"][0]["min_value"] == -10
    assert entry.options["numbers"][0]["max_value"] == 10
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_maximum", [0, -1, "invalid", 65536])
async def test_versioned_migration_defaults_invalid_legacy_brightness_scale(
    legacy_maximum,
):
    """Direct upgrades preserve the former light-builder normalization."""
    entry = SimpleNamespace(
        version=1,
        entry_id="legacy-light",
        options={
            "lights": [
                {
                    "uid": "light-one",
                    "state_address": "DB1,X0.0",
                    "brightness_state_address": "DB1,W2",
                    "brightness_scale": legacy_maximum,
                }
            ]
        },
    )

    def update(target, **changes):
        target.options = changes["options"]
        target.version = changes["version"]

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))

    assert await async_migrate_entry(hass, entry)
    light = entry.options["lights"][0]
    assert "brightness_scale" not in light
    assert light["value_conversions"]["brightness"]["plc_max"] == 255


@pytest.mark.asyncio
async def test_config_entry_migrates_redundant_switch_and_light_sync_atomically():
    entry = SimpleNamespace(
        version=1,
        entry_id="legacy-sync",
        options={
            "switches": [
                {
                    "uid": "switch-one",
                    "state_address": "DB1,X0.0",
                    "command_address": "db1,x0.0",
                    "sync_state": True,
                },
                {
                    "uid": "switch-two",
                    "state_address": "DB1,X0.1",
                    "command_address": "DB1,X0.2",
                    "sync_state": False,
                },
            ],
            "lights": [
                {
                    "uid": "light-one",
                    "state_address": "DB1,X1.0",
                    "sync_state": True,
                    "brightness_state_address": "DB1,W2",
                    "brightness_command_address": "DB1,W4",
                    "brightness_scale": 1000,
                }
            ],
        },
    )
    calls = []

    def update(target, **changes):
        calls.append(deepcopy(changes))
        target.options = changes["options"]
        target.version = changes["version"]

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))

    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1
    assert entry.version == 3
    assert [item["uid"] for item in entry.options["switches"]] == [
        "switch-one",
        "switch-two",
    ]
    switch = entry.options["switches"][0]
    assert switch["sync_state"] is False
    assert "command_address" not in switch
    light = entry.options["lights"][0]
    assert light["sync_state"] is False
    assert "command_address" not in light
    assert light["brightness_state_address"] == "DB1,W2"
    assert light["brightness_command_address"] == "DB1,W4"
    assert light["value_conversions"]["brightness"]["plc_max"] == 1000
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_sync_canonicalization_is_not_persisted_if_later_entity_fails():
    options = {
        "switches": [
            {
                "uid": "would-change",
                "state_address": "DB1,X0.0",
                "command_address": "DB1,X0.0",
                "sync_state": True,
            }
        ],
        "sensors": [
            {"uid": "broken-later", "address": "DB1,REAL4", "scale_raw_min": 0}
        ],
    }
    entry = SimpleNamespace(
        version=1, entry_id="atomic-sync", options=deepcopy(options)
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=lambda *_args, **_kwargs: pytest.fail(
                "partial update attempted"
            )
        )
    )

    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 1
    assert entry.options == options


@pytest.mark.asyncio
async def test_config_entry_failure_does_not_update_any_data():
    options = {
        "sensors": [
            {"uid": "one", "address": "DB1,REAL0", "value_multiplier": 2},
            {"uid": "broken", "address": "DB1,REAL4", "scale_raw_min": 0},
        ]
    }
    entry = SimpleNamespace(version=1, entry_id="plc-broken", options=deepcopy(options))
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=lambda *_args, **_kwargs: pytest.fail(
                "partial update attempted"
            )
        )
    )
    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 1
    assert entry.options == options


def test_platforms_do_not_read_legacy_conversion_fields():
    """Prevent accidental restoration of setup-time legacy fallbacks."""
    for platform in ("sensor.py", "number.py", "light.py"):
        source = (Path("custom_components/s7plc") / platform).read_text()
        assert "value_multiplier" not in source
        assert "scale_raw_min" not in source
        assert "scale_raw_max" not in source
        assert "brightness_scale" not in source


@pytest.mark.asyncio
async def test_migration_does_not_revalidate_unrelated_legacy_rules():
    """A tolerated historical sibling rule must not block conversion migration."""
    entry = SimpleNamespace(
        version=1,
        entry_id="legacy-panel-rule",
        options={
            "switches": [
                {
                    "uid": "preserved",
                    "state_address": "DB1,X0.0",
                    "command_address": "DB1,X0.1",
                    "sync_state": False,
                    "sync_same_address": True,
                    "future_compatible_field": {"keep": True},
                }
            ],
            "sensors": [
                {
                    "uid": "converted",
                    "address": "DB1,REAL0",
                    "value_multiplier": 2,
                }
            ],
        },
    )

    def update(target, **changes):
        target.options = changes["options"]
        target.version = changes["version"]

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    assert await async_migrate_entry(hass, entry)
    assert entry.options["switches"][0]["sync_same_address"] is True
    assert entry.options["switches"][0]["future_compatible_field"] == {"keep": True}
    assert entry.options["sensors"][0]["value_conversions"]["value"]["factor"] == 2
