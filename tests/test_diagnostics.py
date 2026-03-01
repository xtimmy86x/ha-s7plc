"""Tests for diagnostics module."""

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock
import pytest

from custom_components.s7plc.diagnostics import (
    async_get_config_entry_diagnostics,
    _iso_or_none,
)


@dataclass
class RuntimeEntryData:
    """Mock runtime data."""
    coordinator: object
    name: str
    host: str
    device_id: str


def test_iso_or_none_with_none():
    """Test _iso_or_none with None value."""
    assert _iso_or_none(None) is None


def test_iso_or_none_with_datetime():
    """Test _iso_or_none with datetime object."""
    dt = datetime(2026, 1, 10, 12, 30, 45)
    result = _iso_or_none(dt)
    assert result == "2026-01-10T12:30:45"


def test_iso_or_none_with_string():
    """Test _iso_or_none with string value."""
    assert _iso_or_none("test") == "test"


def test_iso_or_none_with_number():
    """Test _iso_or_none with numeric value."""
    assert _iso_or_none(42) == "42"


def test_iso_or_none_with_object_no_isoformat():
    """Test _iso_or_none with object without isoformat."""
    obj = MagicMock()
    del obj.isoformat
    result = _iso_or_none(obj)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_diagnostics_no_runtime_data():
    """Test diagnostics when runtime data is not available."""
    hass = MagicMock()
    hass.data = {}
    
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = "Test PLC"
    entry.data = {"host": "192.168.1.1"}
    entry.options = {"sensors": []}
    # Simulate entry without runtime_data
    del entry.runtime_data
    
    result = await async_get_config_entry_diagnostics(hass, entry)
    
    assert "config_entry" in result
    assert result["config_entry"]["entry_id"] == "test-entry"
    assert result["config_entry"]["title"] == "Test PLC"
    assert "runtime" not in result


@pytest.mark.asyncio
async def test_diagnostics_with_coordinator():
    """Test diagnostics with full coordinator data."""
    
    # Setup mock hass
    hass = MagicMock()
    
    # Setup mock coordinator
    mock_coordinator = MagicMock()
    mock_coordinator.is_connected.return_value = True
    mock_coordinator.last_update_success = True
    mock_coordinator.update_interval = MagicMock()
    mock_coordinator.update_interval.total_seconds = lambda: 1.0
    mock_coordinator._plans_batch = [MagicMock(), MagicMock()]
    mock_coordinator._plans_str = [MagicMock()]
    mock_coordinator._items = {
        "sensor:DB1,REAL0": "DB1,REAL0",
        "sensor:DB1,REAL4": "DB1,REAL4",
    }
    mock_coordinator.data = {
        "sensor:DB1,REAL0": 25.5,
        "sensor:DB1,REAL4": 30.0,
    }
    mock_coordinator.last_update_success_time = datetime(2026, 1, 10, 12, 0, 0)
    mock_coordinator.last_update_failure_time = None
    mock_coordinator.last_exception = None
    
    # Setup config entry
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = "Test PLC"
    entry.data = {"host": "192.168.1.1", "rack": 0, "slot": 1}
    entry.options = {
        "sensors": [{"address": "DB1,REAL0"}],
        "binary_sensors": [],
        "switches": [{"address": "DB1,X0.0"}],
        "lights": [],
        "buttons": [],
    }
    # Use runtime_data with dataclass
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Test PLC",
        host="192.168.1.1",
        device_id="test-device",
    )
    
    result = await async_get_config_entry_diagnostics(hass, entry)
    
    # Verify config entry data
    assert result["config_entry"]["entry_id"] == "test-entry"
    assert result["config_entry"]["title"] == "Test PLC"
    assert result["config_entry"]["data"]["host"] == "**REDACTED**"
    assert result["config_entry"]["data"]["rack"] == 0
    
    # Verify runtime data
    assert "runtime" in result
    assert result["runtime"]["device"]["name"] == "Test PLC"
    assert result["runtime"]["device"]["device_id"] == "test-device"
    assert result["runtime"]["device"]["host"] == "**REDACTED**"
    
    # Verify coordinator data
    coordinator_info = result["runtime"]["coordinator"]
    assert coordinator_info["connected"] is True
    assert coordinator_info["last_update_success"] is True
    assert coordinator_info["update_interval_seconds"] == 1.0
    assert len(coordinator_info["registered_topics"]) == 2
    assert len(coordinator_info["configured_items"]) == 2
    assert coordinator_info["planned_batches"] == 2
    assert coordinator_info["planned_strings"] == 1
    assert coordinator_info["option_counts"]["sensors"] == 1
    assert coordinator_info["option_counts"]["switches"] == 1
    assert coordinator_info["rack"] == 0
    assert coordinator_info["slot"] == 1
    assert "last_update_success_time" in coordinator_info


@pytest.mark.asyncio
async def test_diagnostics_with_failure_time():
    """Test diagnostics includes failure time when present."""
    
    hass = MagicMock()
    
    mock_coordinator = MagicMock()
    mock_coordinator.is_connected.return_value = False
    mock_coordinator.last_update_success = False
    mock_coordinator.update_interval = None
    mock_coordinator._plans_batch = []
    mock_coordinator._plans_str = []
    mock_coordinator._items = {}
    mock_coordinator.data = {}
    mock_coordinator.last_update_success_time = None
    mock_coordinator.last_update_failure_time = datetime(2026, 1, 10, 12, 30, 0)
    mock_coordinator.last_exception = RuntimeError("Connection failed")
    
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = "Test PLC"
    entry.data = {}
    entry.options = {}
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Test PLC",
        device_id="test-device",
        host="192.168.1.1",
    )
    
    result = await async_get_config_entry_diagnostics(hass, entry)
    
    coordinator_info = result["runtime"]["coordinator"]
    assert coordinator_info["connected"] is False
    assert "last_update_failure_time" in coordinator_info
    assert "last_exception" in coordinator_info
    assert "RuntimeError" in coordinator_info["last_exception"]


@pytest.mark.asyncio
async def test_diagnostics_with_no_update_interval():
    """Test diagnostics when update_interval is not set."""
    
    hass = MagicMock()
    
    mock_coordinator = MagicMock()
    mock_coordinator.is_connected.return_value = True
    mock_coordinator.last_update_success = True
    # No update_interval attribute
    del mock_coordinator.update_interval
    mock_coordinator._plans_batch = []
    mock_coordinator._plans_str = []
    mock_coordinator._items = {}
    mock_coordinator.data = {}
    
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = "Test PLC"
    entry.data = {}
    entry.options = {}
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Test PLC",
        host="192.168.1.1",
        device_id="test-device",
    )
    
    result = await async_get_config_entry_diagnostics(hass, entry)
    
    coordinator_info = result["runtime"]["coordinator"]
    assert coordinator_info["update_interval_seconds"] is None


@pytest.mark.asyncio
async def test_diagnostics_configured_items_sorted():
    """Test that configured items are sorted in diagnostics."""
    
    hass = MagicMock()
    
    mock_coordinator = MagicMock()
    mock_coordinator.is_connected.return_value = True
    mock_coordinator.last_update_success = True
    mock_coordinator.update_interval = None
    mock_coordinator._plans_batch = []
    mock_coordinator._plans_str = []
    mock_coordinator._items = {
        "sensor:DB1,REAL8": "DB1,REAL8",
        "sensor:DB1,REAL0": "DB1,REAL0",
        "sensor:DB1,REAL4": "DB1,REAL4",
    }
    mock_coordinator.data = {}
    
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.title = "Test PLC"
    entry.data = {}
    entry.options = {}
    entry.runtime_data = RuntimeEntryData(
        coordinator=mock_coordinator,
        name="Test PLC",
        host="192.168.1.1",
        device_id="test-device",
    )
    
    result = await async_get_config_entry_diagnostics(hass, entry)
    
    coordinator_info = result["runtime"]["coordinator"]
    topics = coordinator_info["registered_topics"]
    
    # Verify topics are sorted
    assert topics == sorted(topics)
    assert topics[0] == "sensor:DB1,REAL0"
    assert topics[1] == "sensor:DB1,REAL4"
    assert topics[2] == "sensor:DB1,REAL8"
