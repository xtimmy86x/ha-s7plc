"""Tests for helpers module."""

from unittest.mock import MagicMock
import pytest

from custom_components.s7plc.helpers import (
    get_coordinator_and_device_info,
    default_entity_name,
)
from custom_components.s7plc.const import DOMAIN


def test_default_entity_name_with_both():
    """Test default_entity_name returns only address (plc_name ignored with has_entity_name=True)."""
    result = default_entity_name("MyPLC", "DB1,REAL0")
    assert result == "DB1 REAL0"


def test_default_entity_name_with_special_chars():
    """Test default_entity_name normalizes special characters."""
    result = default_entity_name("MyPLC", "DB1,REAL0.5")
    assert result == "DB1 REAL0.5"


def test_default_entity_name_multiple_spaces():
    """Test default_entity_name normalizes multiple spaces."""
    result = default_entity_name("MyPLC", "DB1,,REAL0")
    assert result == "DB1 REAL0"


def test_default_entity_name_only_plc_name():
    """Test default_entity_name with only PLC name returns None (address required)."""
    result = default_entity_name("MyPLC", None)
    assert result is None


def test_default_entity_name_only_address():
    """Test default_entity_name with only address."""
    result = default_entity_name(None, "DB1,REAL0")
    assert result == "DB1 REAL0"


def test_default_entity_name_both_none():
    """Test default_entity_name with both None."""
    result = default_entity_name(None, None)
    assert result is None


def test_default_entity_name_empty_strings():
    """Test default_entity_name with empty strings."""
    result = default_entity_name("", "")
    # Empty strings are falsy, so function returns None
    assert result is None


def test_default_entity_name_uppercase_conversion():
    """Test default_entity_name converts address to uppercase."""
    result = default_entity_name("MyPLC", "db1,real0")
    assert result == "DB1 REAL0"


def test_default_entity_name_strips_whitespace():
    """Test default_entity_name strips leading/trailing whitespace."""
    result = default_entity_name("MyPLC", "  DB1,REAL0  ")
    assert "DB1 REAL0" in result


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
