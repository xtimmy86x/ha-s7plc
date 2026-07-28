"""Tests for helpers module."""

import pytest
from unittest.mock import MagicMock

from custom_components.s7plc.helpers import (
    build_entity_area_map,
    build_expected_unique_ids,
    ensure_item_uids,
    generate_uid,
    get_coordinator_and_device_info,
    default_entity_name,
    migrate_legacy_brightness_scale,
    migrate_legacy_scale_fields,
    migrate_legacy_uid_device_prefix,
    parse_pulse_duration,
    scale_value,
    inverse_scale_value,
)
from custom_components.s7plc.const import DEFAULT_PULSE_DURATION, DOMAIN


def test_default_entity_name_basic():
    """Test default_entity_name returns humanized uppercase address."""
    assert default_entity_name("DB1,REAL0") == "DB1 REAL0"


def test_default_entity_name_normalization():
    """Test default_entity_name normalizes address: uppercase, multiple spaces, special chars."""
    assert default_entity_name("db1,real0") == "DB1 REAL0"
    assert default_entity_name("DB1,,REAL0") == "DB1 REAL0"
    assert default_entity_name("  DB1,REAL0  ") == "DB1 REAL0"
    assert default_entity_name("DB1,REAL0.5") == "DB1 REAL0.5"


def test_default_entity_name_none_cases():
    """Test default_entity_name returns None when address is missing/empty."""
    assert default_entity_name(None) is None
    assert default_entity_name("") is None


def test_get_coordinator_and_device_info():
    """Test get_coordinator_and_device_info returns correct data."""
    from custom_components.s7plc.helpers import RuntimeEntryData
    
    # Setup mock entry
    entry = MagicMock()
    entry.entry_id = "test-entry"
    
    # Setup mock coordinator
    mock_coordinator = MagicMock()
    
    # Setup runtime data directly on the entry
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Test PLC",
        host="192.168.1.1",
        device_id="test-device-id",
    )
    
    coordinator, device_info, device_id = get_coordinator_and_device_info(entry)
    
    # Verify returned values
    assert coordinator is mock_coordinator
    assert device_id == "test-device-id"
    assert device_info["identifiers"] == {(DOMAIN, "test-device-id")}
    assert device_info["name"] == "Test PLC"
    assert device_info["manufacturer"] == "Siemens"
    assert device_info["model"] == "S7 PLC"


def test_get_coordinator_and_device_info_different_names():
    """Test get_coordinator_and_device_info with different device names."""
    from custom_components.s7plc.helpers import RuntimeEntryData
    
    entry = MagicMock()
    entry.entry_id = "entry-123"
    
    mock_coordinator = MagicMock()
    
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Production Line 1",
        host="192.168.1.10",
        device_id="prod-line-1",
    )
    
    coordinator, device_info, device_id = get_coordinator_and_device_info(entry)
    
    assert device_info["name"] == "Production Line 1"
    assert device_id == "prod-line-1"


# ---------------------------------------------------------------------------
# build_expected_unique_ids / build_entity_area_map
# ---------------------------------------------------------------------------


def test_build_expected_unique_ids_all_entity_types():
    """Every entity type is represented plus the connection sensor.

    unique_id is now derived from each item's permanent "uid" field, not
    from its address — so every fixture item needs one.
    """
    options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "uid-sensor"}],
        "binary_sensors": [{"address": "DB1,X0.0", "uid": "uid-binary"}],
        "switches": [{"state_address": "DB1,X0.1", "uid": "uid-switch"}],
        "covers": [
            {"position_state_address": "DB1,INT0", "uid": "uid-cover-pos"},
            {
                "open_command_address": "DB1,X1.0",
                "close_command_address": "DB1,X1.1",
                "opening_state_address": "DB1,X1.2",
                "uid": "uid-cover-trad",
            },
        ],
        "buttons": [{"address": "DB1,X2.0", "uid": "uid-button"}],
        "lights": [
            {"state_address": "DB1,X2.1", "uid": "uid-light-1"},
            {
                "state_address": "DB1,B10",
                "brightness_scale": 255,
                "uid": "uid-light-2",
            },
        ],
        "numbers": [{"address": "DB1,INT10", "uid": "uid-number"}],
        "texts": [{"address": "DB1,STRING0", "uid": "uid-text"}],
        "climates": [
            {
                "current_temperature_address": "DB1,REAL20",
                "control_mode": "direct",
                "heating_output_address": "DB1,X3.0",
                "uid": "uid-climate-direct",
            },
            {
                "current_temperature_address": "DB1,REAL30",
                "control_mode": "setpoint",
                "target_temperature_address": "DB1,REAL31",
                "uid": "uid-climate-setpoint",
            },
        ],
        "entity_sync": [
            {
                "address": "DB1,REAL100",
                "source_entity": "sensor.test",
                "uid": "uid-entity-sync",
            }
        ],
    }

    ids = build_expected_unique_ids("dev", options)

    assert "uid-sensor" in ids
    assert "uid-binary" in ids
    assert "uid-switch" in ids
    assert "uid-cover-pos" in ids
    assert "uid-cover-trad" in ids
    assert "uid-button" in ids
    assert "uid-light-1" in ids
    assert "uid-light-2" in ids
    assert "uid-number" in ids
    assert "uid-text" in ids
    assert "uid-climate-direct" in ids
    assert "uid-climate-setpoint" in ids
    assert "uid-entity-sync" in ids
    assert "dev:connection" in ids


def test_build_expected_unique_ids_empty_options():
    """Empty options without enable_metrics only include the connection sensor."""
    ids = build_expected_unique_ids("dev", {})
    assert "dev:connection" in ids
    # Only connection, no metrics (enable_metrics defaults to False)
    assert len(ids) == 1


def test_build_expected_unique_ids_empty_options_with_metrics():
    """Empty options with enable_metrics include connection + metrics sensors."""
    from custom_components.s7plc.sensor import METRICS_DEFINITIONS

    ids = build_expected_unique_ids("dev", {}, data={"enable_metrics": True})
    assert "dev:connection" in ids
    for defn in METRICS_DEFINITIONS:
        assert f"dev:metrics:{defn.key}" in ids
    assert len(ids) == 1 + len(METRICS_DEFINITIONS)


def test_build_expected_unique_ids_traditional_cover_variants():
    """Traditional covers (open+close command required) get their uid-based id."""
    # opened_state present
    ids = build_expected_unique_ids("d", {
        "covers": [{
            "opening_state_address": "DB1,X0.2",
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "uid": "uid-opened",
        }],
    })
    assert "uid-opened" in ids

    # closing_state when no opening_state
    ids = build_expected_unique_ids("d", {
        "covers": [{
            "closing_state_address": "DB1,X0.3",
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "uid": "uid-closed",
        }],
    })
    assert "uid-closed" in ids

    # only open/close command, no end-stop sensors
    ids = build_expected_unique_ids("d", {
        "covers": [{
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "uid": "uid-command",
        }],
    })
    assert "uid-command" in ids

    # missing close_command_address: no entity would actually be created
    ids = build_expected_unique_ids("d", {
        "covers": [{"open_command_address": "DB1,X0.0", "uid": "uid-incomplete"}],
    })
    assert "uid-incomplete" not in ids


def test_build_expected_unique_ids_skips_items_without_address():
    """Items missing a key address field are silently skipped."""
    ids = build_expected_unique_ids("d", {
        "sensors": [{"name": "no address"}],
        "switches": [{}],
        "covers": [{}],
    })
    assert "d:connection" in ids
    # Only connection, no entity IDs because addresses are missing
    assert len(ids) == 1


def test_build_entity_area_map():
    """Area map returns correct unique_id → area_id mapping."""
    options = {
        "sensors": [{"address": "DB1,REAL0", "area": "kitchen", "uid": "uid-s"}],
        "binary_sensors": [{"address": "DB1,X0.0", "uid": "uid-bs"}],  # no area
        "lights": [
            {"state_address": "DB1,X1.0", "area": "bedroom", "uid": "uid-l"}
        ],
    }
    area_map = build_entity_area_map("dev", options)

    assert area_map["uid-s"] == "kitchen"
    assert area_map["uid-bs"] is None
    assert area_map["uid-l"] == "bedroom"


# ---------------------------------------------------------------------------
# generate_uid / ensure_item_uids
# ---------------------------------------------------------------------------


def test_generate_uid_format_and_uniqueness():
    """generate_uid returns unique hex strings from a full UUID4."""
    uid1 = generate_uid()
    uid2 = generate_uid()
    assert uid1 != uid2
    assert len(uid1) == 32
    int(uid1, 16)  # must be valid hex


def test_ensure_item_uids_freezes_legacy_id_for_existing_entity():
    """An item with no uid but a legacy address gets that exact id frozen."""
    options = {
        "sensors": [{"address": "DB1,REAL0"}],
    }
    changed = ensure_item_uids("dev", options)
    assert changed is True
    # uid now stores the complete legacy unique_id verbatim, device_id included.
    assert options["sensors"][0]["uid"] == "dev:sensor:DB1,REAL0"


def test_ensure_item_uids_assigns_fresh_uid_when_no_legacy_match():
    """An item that never produced a real entity gets a random uid instead."""
    options = {
        "sensors": [{"name": "no address, never had an entity"}],
    }
    changed = ensure_item_uids("dev", options)
    assert changed is True
    uid = options["sensors"][0]["uid"]
    assert uid
    assert uid != "sensor:"


def test_ensure_item_uids_noop_when_uid_already_present():
    """Items that already have a uid are left untouched."""
    options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "existing-uid"}],
    }
    changed = ensure_item_uids("dev", options)
    assert changed is False
    assert options["sensors"][0]["uid"] == "existing-uid"


def test_ensure_item_uids_idempotent():
    """Calling ensure_item_uids twice doesn't change anything the second time."""
    options = {
        "sensors": [{"address": "DB1,REAL0"}],
        "switches": [{"state_address": "DB1,X0.0"}],
    }
    assert ensure_item_uids("dev", options) is True
    first_uids = {
        key: [dict(i) for i in items] for key, items in options.items()
    }
    assert ensure_item_uids("dev", options) is False
    assert options == first_uids


def test_ensure_item_uids_editing_address_does_not_change_uid():
    """Regression test: editing an item's address must not change its uid."""
    options = {"sensors": [{"address": "DB1,REAL0"}]}
    ensure_item_uids("dev", options)
    uid = options["sensors"][0]["uid"]

    # Simulate the user editing the address via the options flow.
    options["sensors"][0]["address"] = "DB1,REAL99"
    changed = ensure_item_uids("dev", options)

    assert changed is False
    assert options["sensors"][0]["uid"] == uid


# ---------------------------------------------------------------------------
# migrate_legacy_uid_device_prefix
# ---------------------------------------------------------------------------


def test_migrate_legacy_uid_device_prefix_upgrades_short_uid():
    """A uid saved by an earlier build (device-relative suffix only) gets
    the device_id folded in, so the entity keeps its exact existing
    unique_id instead of silently changing and becoming orphaned."""
    options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "sensor:DB1,REAL0"}],
    }
    changed = migrate_legacy_uid_device_prefix("dev", options)
    assert changed is True
    assert options["sensors"][0]["uid"] == "dev:sensor:DB1,REAL0"


def test_migrate_legacy_uid_device_prefix_is_a_noop_for_already_prefixed_uid():
    """A uid that already has the device_id prefix is left untouched."""
    options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "dev:sensor:DB1,REAL0"}],
    }
    changed = migrate_legacy_uid_device_prefix("dev", options)
    assert changed is False
    assert options["sensors"][0]["uid"] == "dev:sensor:DB1,REAL0"


def test_migrate_legacy_uid_device_prefix_skips_items_without_uid():
    """An item with no uid at all yet is left for ensure_item_uids to handle."""
    options = {"sensors": [{"address": "DB1,REAL0"}]}
    changed = migrate_legacy_uid_device_prefix("dev", options)
    assert changed is False
    assert "uid" not in options["sensors"][0]


def test_migrate_legacy_uid_device_prefix_handles_mixed_items():
    """Only items with an un-prefixed uid are touched; others are untouched."""
    options = {
        "sensors": [
            {"address": "DB1,REAL0", "uid": "sensor:DB1,REAL0"},
            {"address": "DB1,REAL4", "uid": "dev:sensor:DB1,REAL4"},
            {"address": "DB1,REAL8"},
        ],
    }
    changed = migrate_legacy_uid_device_prefix("dev", options)
    assert changed is True
    assert options["sensors"][0]["uid"] == "dev:sensor:DB1,REAL0"
    assert options["sensors"][1]["uid"] == "dev:sensor:DB1,REAL4"
    assert "uid" not in options["sensors"][2]


# ---------------------------------------------------------------------------
# migrate_legacy_scale_fields
# ---------------------------------------------------------------------------


def test_migrate_legacy_scale_fields_folds_sensor_scale_into_address():
    options = {
        "sensors": [
            {
                "address": "DB6,B23",
                "scale_raw_min": 0.0,
                "scale_raw_max": 1.0,
                "min_value": 0.0,
                "max_value": 10.0,
            }
        ],
    }
    changed = migrate_legacy_scale_fields(options)
    assert changed is True
    item = options["sensors"][0]
    assert item["address"] == "DB6,B23 Scale(0,1,0,10)"
    assert "scale_raw_min" not in item
    assert "scale_raw_max" not in item
    assert "min_value" not in item
    assert "max_value" not in item


def test_migrate_legacy_scale_fields_folds_number_scale_into_address():
    options = {
        "numbers": [
            {
                "address": "DB1,REAL0",
                "scale_raw_min": -10.5,
                "scale_raw_max": 20.0,
                "min_value": 0.0,
                "max_value": 100.0,
            }
        ],
    }
    changed = migrate_legacy_scale_fields(options)
    assert changed is True
    item = options["numbers"][0]
    assert item["address"] == "DB1,REAL0 Scale(-10.5,20,0,100)"
    assert "scale_raw_min" not in item
    assert "min_value" not in item


def test_migrate_legacy_scale_fields_leaves_plain_number_bounds_untouched():
    """min_value/max_value without raw-scale keys are plain bounds, unrelated
    to scaling, and must not be migrated."""
    options = {
        "numbers": [{"address": "DB1,W0", "min_value": 0.0, "max_value": 100.0}],
    }
    changed = migrate_legacy_scale_fields(options)
    assert changed is False
    item = options["numbers"][0]
    assert item["address"] == "DB1,W0"
    assert item["min_value"] == 0.0
    assert item["max_value"] == 100.0


def test_migrate_legacy_scale_fields_noop_when_nothing_to_migrate():
    options = {"sensors": [{"address": "DB1,REAL0"}], "numbers": []}
    changed = migrate_legacy_scale_fields(options)
    assert changed is False


def test_migrate_legacy_scale_fields_idempotent():
    options = {
        "sensors": [
            {
                "address": "DB6,B23",
                "scale_raw_min": 0.0,
                "scale_raw_max": 1.0,
                "min_value": 0.0,
                "max_value": 10.0,
            }
        ],
    }
    assert migrate_legacy_scale_fields(options) is True
    first = dict(options["sensors"][0])
    assert migrate_legacy_scale_fields(options) is False
    assert options["sensors"][0] == first


# ---------------------------------------------------------------------------
# migrate_legacy_brightness_scale
# ---------------------------------------------------------------------------


def test_migrate_legacy_brightness_scale_folds_into_address():
    options = {
        "lights": [
            {
                "state_address": "DB1,X0.0",
                "brightness_state_address": "DB1,B0",
                "brightness_command_address": "DB1,B1",
                "brightness_scale": 100,
            }
        ],
    }
    changed = migrate_legacy_brightness_scale(options)
    assert changed is True
    item = options["lights"][0]
    assert item["brightness_state_address"] == "DB1,B0 Scale(0,100,0,255)"
    assert item["brightness_command_address"] == "DB1,B1 Scale(0,100,0,255)"
    assert "brightness_scale" not in item


def test_migrate_legacy_brightness_scale_default_255_still_removes_field():
    """Even the default (identity) scale value gets the key retired."""
    options = {
        "lights": [
            {
                "state_address": "DB1,X0.0",
                "brightness_state_address": "DB1,B0",
                "brightness_scale": 255,
            }
        ],
    }
    changed = migrate_legacy_brightness_scale(options)
    assert changed is True
    item = options["lights"][0]
    assert item["brightness_state_address"] == "DB1,B0 Scale(0,255,0,255)"
    assert "brightness_scale" not in item


def test_migrate_legacy_brightness_scale_shared_command_address_not_double_scaled():
    """When command defaults to the same address as state (not separately
    configured), only the state address gets the scale embedded."""
    options = {
        "lights": [
            {
                "state_address": "DB1,X0.0",
                "brightness_state_address": "DB1,B0",
                "brightness_scale": 100,
            }
        ],
    }
    migrate_legacy_brightness_scale(options)
    item = options["lights"][0]
    assert item["brightness_state_address"] == "DB1,B0 Scale(0,100,0,255)"
    assert "brightness_command_address" not in item


def test_migrate_legacy_brightness_scale_noop_when_nothing_to_migrate():
    options = {
        "lights": [{"state_address": "DB1,X0.0", "name": "Plain Light"}],
    }
    assert migrate_legacy_brightness_scale(options) is False


def test_migrate_legacy_brightness_scale_idempotent():
    options = {
        "lights": [
            {
                "state_address": "DB1,X0.0",
                "brightness_state_address": "DB1,B0",
                "brightness_scale": 100,
            }
        ],
    }
    assert migrate_legacy_brightness_scale(options) is True
    first = dict(options["lights"][0])
    assert migrate_legacy_brightness_scale(options) is False
    assert options["lights"][0] == first


# ---------------------------------------------------------------------------
# parse_pulse_duration
# ---------------------------------------------------------------------------


def test_parse_pulse_duration_none_returns_default():
    assert parse_pulse_duration(None) == DEFAULT_PULSE_DURATION


def test_parse_pulse_duration_empty_string_returns_default():
    assert parse_pulse_duration("") == DEFAULT_PULSE_DURATION


def test_parse_pulse_duration_valid_float():
    assert parse_pulse_duration(1.5) == 1.5
    assert parse_pulse_duration("2.3") == 2.3


def test_parse_pulse_duration_rounds_to_one_decimal():
    assert parse_pulse_duration(1.55) == 1.6
    assert parse_pulse_duration("0.123") == 0.1


def test_parse_pulse_duration_below_min_returns_default():
    assert parse_pulse_duration(0.05) == DEFAULT_PULSE_DURATION


def test_parse_pulse_duration_above_max_returns_default():
    assert parse_pulse_duration(61) == DEFAULT_PULSE_DURATION


def test_parse_pulse_duration_boundaries():
    assert parse_pulse_duration(0.1) == 0.1
    assert parse_pulse_duration(60) == 60


def test_parse_pulse_duration_non_numeric_returns_default():
    assert parse_pulse_duration("abc") == DEFAULT_PULSE_DURATION
    assert parse_pulse_duration(object()) == DEFAULT_PULSE_DURATION


# ============================================================================
# scale_value / inverse_scale_value
# ============================================================================


def test_scale_value_midpoint():
    """Middle of raw range maps to middle of scale range."""
    assert scale_value(50, 0, 100, 0, 10) == pytest.approx(5.0)


def test_scale_value_min():
    assert scale_value(0, 0, 100, 0, 10) == pytest.approx(0.0)


def test_scale_value_max():
    assert scale_value(100, 0, 100, 0, 10) == pytest.approx(10.0)


def test_scale_value_offset_range():
    """PLC 4000-20000 mA → 0-100 %."""
    assert scale_value(4000, 4000, 20000, 0, 100) == pytest.approx(0.0)
    assert scale_value(20000, 4000, 20000, 0, 100) == pytest.approx(100.0)
    assert scale_value(12000, 4000, 20000, 0, 100) == pytest.approx(50.0)


def test_scale_value_negative_scale_range():
    """Inverted display range."""
    result = scale_value(0, 0, 100, 100, 0)
    assert result == pytest.approx(100.0)
    result = scale_value(100, 0, 100, 100, 0)
    assert result == pytest.approx(0.0)


def test_scale_value_zero_raw_range_returns_scale_min():
    """Edge case: raw_min == raw_max returns scale_min."""
    assert scale_value(5, 5, 5, 10, 20) == 10


def test_inverse_scale_value_midpoint():
    assert inverse_scale_value(5.0, 0, 100, 0, 10) == pytest.approx(50.0)


def test_inverse_scale_value_min():
    assert inverse_scale_value(0, 0, 100, 0, 10) == pytest.approx(0.0)


def test_inverse_scale_value_max():
    assert inverse_scale_value(10, 0, 100, 0, 10) == pytest.approx(100.0)


def test_inverse_scale_value_roundtrip():
    """scale + inverse_scale should return original value."""
    raw = 7543.0
    scaled = scale_value(raw, 4000, 20000, 0, 100)
    restored = inverse_scale_value(scaled, 4000, 20000, 0, 100)
    assert restored == pytest.approx(raw)


def test_inverse_scale_value_zero_scale_range_returns_raw_min():
    assert inverse_scale_value(50, 0, 100, 5, 5) == 0
