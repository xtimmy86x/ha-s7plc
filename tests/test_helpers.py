"""Tests for helpers module."""

from unittest.mock import MagicMock
import pytest

from custom_components.s7plc.helpers import (
    get_coordinator_and_device_info,
    default_entity_name,
)
from custom_components.s7plc.const import DOMAIN


def test_default_entity_name_basic():
    """Test default_entity_name returns humanized uppercase address (plc_name is ignored)."""
    # First parameter is ignored (kept for backward compatibility)
    assert default_entity_name("MyPLC", "DB1,REAL0") == "DB1 REAL0"
    assert default_entity_name(None, "DB1,REAL0") == "DB1 REAL0"
    assert default_entity_name("Different", "DB1,REAL0") == "DB1 REAL0"


def test_default_entity_name_normalization():
    """Test default_entity_name normalizes address: uppercase, multiple spaces, special chars."""
    assert default_entity_name("PLC", "db1,real0") == "DB1 REAL0"
    assert default_entity_name("PLC", "DB1,,REAL0") == "DB1 REAL0"
    assert default_entity_name("PLC", "  DB1,REAL0  ") == "DB1 REAL0"
    assert default_entity_name("PLC", "DB1,REAL0.5") == "DB1 REAL0.5"


def test_default_entity_name_none_cases():
    """Test default_entity_name returns None when address is missing/empty."""
    assert default_entity_name("MyPLC", None) is None
    assert default_entity_name(None, None) is None
    assert default_entity_name("", "") is None


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
