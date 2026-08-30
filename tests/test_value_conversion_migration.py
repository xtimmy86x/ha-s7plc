"""Tests for persistent legacy conversion migration."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

import pytest

from custom_components.s7plc.value_conversion import ValueConversionError
from custom_components.s7plc.value_conversion_migration import (
    migrate_legacy_value_conversions,
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
    assert entry.version == 2
    assert [item["uid"] for item in entry.options["sensors"]] == ["one", "two"]
    assert entry.options["sensors"][0]["value_conversions"]["value"]["factor"] == 10
    assert await async_migrate_entry(hass, entry)
    assert len(calls) == 1


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
