"""Tests for helpers module."""

from unittest.mock import MagicMock

from custom_components.s7plc.helpers import (
    build_entity_area_map,
    build_expected_unique_ids,
    get_coordinator_and_device_info,
    default_entity_name,
    parse_pulse_duration,
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
    """Every entity type is represented plus the connection sensor."""
    options = {
        "sensors": [{"address": "DB1,REAL0"}],
        "binary_sensors": [{"address": "DB1,X0.0"}],
        "switches": [{"state_address": "DB1,X0.1"}],
        "covers": [
            {"position_state_address": "DB1,INT0"},
            {
                "open_command_address": "DB1,X1.0",
                "close_command_address": "DB1,X1.1",
                "opening_state_address": "DB1,X1.2",
            },
        ],
        "buttons": [{"address": "DB1,X2.0"}],
        "lights": [
            {"state_address": "DB1,X2.1"},
            {"state_address": "DB1,B10", "brightness_scale": 255},
        ],
        "numbers": [{"address": "DB1,INT10"}],
        "texts": [{"address": "DB1,STRING0"}],
        "climates": [
            {
                "current_temperature_address": "DB1,REAL20",
                "control_mode": "direct",
            },
            {
                "current_temperature_address": "DB1,REAL30",
                "control_mode": "setpoint",
            },
        ],
        "entity_sync": [{"address": "DB1,REAL100", "source_entity": "sensor.test"}],
    }

    ids = build_expected_unique_ids("dev", options)

    assert "dev:sensor:DB1,REAL0" in ids
    assert "dev:binary_sensor:DB1,X0.0" in ids
    assert "dev:switch:DB1,X0.1" in ids
    assert "dev:cover:position:DB1,INT0" in ids
    assert "dev:cover:opened:DB1,X1.2" in ids
    assert "dev:button:DB1,X2.0" in ids
    assert "dev:light:DB1,X2.1" in ids
    assert "dev:light:DB1,B10" in ids
    assert "dev:number:DB1,INT10" in ids
    assert "dev:text:DB1,STRING0" in ids
    assert "dev:climate_direct:DB1,REAL20" in ids
    assert "dev:climate_setpoint:DB1,REAL30" in ids
    assert "dev:entity_sync:DB1,REAL100" in ids
    assert "dev:connection" in ids


def test_build_expected_unique_ids_empty_options():
    """Empty options still include the connection sensor."""
    ids = build_expected_unique_ids("dev", {})
    assert ids == {"dev:connection"}


def test_build_expected_unique_ids_traditional_cover_variants():
    """Traditional covers pick the right unique id based on available addresses."""
    # opened_state takes priority
    ids = build_expected_unique_ids("d", {
        "covers": [{"opening_state_address": "DB1,X0.2", "open_command_address": "DB1,X0.0"}],
    })
    assert "d:cover:opened:DB1,X0.2" in ids

    # closing_state when no opening_state
    ids = build_expected_unique_ids("d", {
        "covers": [{"closing_state_address": "DB1,X0.3", "open_command_address": "DB1,X0.0"}],
    })
    assert "d:cover:closed:DB1,X0.3" in ids

    # open_command as fallback
    ids = build_expected_unique_ids("d", {
        "covers": [{"open_command_address": "DB1,X0.0"}],
    })
    assert "d:cover:command:DB1,X0.0" in ids


def test_build_expected_unique_ids_skips_items_without_address():
    """Items missing a key address field are silently skipped."""
    ids = build_expected_unique_ids("d", {
        "sensors": [{"name": "no address"}],
        "switches": [{}],
        "covers": [{}],
    })
    assert ids == {"d:connection"}


def test_build_entity_area_map():
    """Area map returns correct unique_id → area_id mapping."""
    options = {
        "sensors": [{"address": "DB1,REAL0", "area": "kitchen"}],
        "binary_sensors": [{"address": "DB1,X0.0"}],  # no area
        "lights": [{"state_address": "DB1,X1.0", "area": "bedroom"}],
    }
    area_map = build_entity_area_map("dev", options)

    assert area_map["dev:sensor:DB1,REAL0"] == "kitchen"
    assert area_map["dev:binary_sensor:DB1,X0.0"] is None
    assert area_map["dev:light:DB1,X1.0"] == "bedroom"


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
