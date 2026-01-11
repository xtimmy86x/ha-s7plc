"""Tests for S7EntitySync entity - Refactored with fixtures and parametrization."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.core import State

from custom_components.s7plc.sensor import S7EntitySync
from custom_components.s7plc.address import DataType
from conftest import DummyCoordinator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def writer_factory(mock_coordinator, fake_hass):
    """Factory fixture to create S7EntitySync instances easily."""
    def _create_writer(
        address: str,
        data_type,
        source_entity: str = "sensor.test",
        name: str = "Test Entity Sync",
        coordinator = None,
    ):
        coord = coordinator if coordinator is not None else mock_coordinator
        
        with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
            mock_tag = MagicMock()
            mock_tag.data_type = data_type
            mock_parse.return_value = mock_tag

            writer = S7EntitySync(
                coord,
                name=name,
                unique_id="uid",
                device_info={"identifiers": {"domain"}},
                address=address,
                source_entity=source_entity,
            )
            writer.hass = fake_hass
            writer.name = name
            return writer
    
    return _create_writer


# ============================================================================
# Initialization Tests
# ============================================================================


def test_writer_numeric_initialization(writer_factory):
    """Test numeric writer initialization."""
    writer = writer_factory("db1,r0", DataType.REAL)

    assert writer._address == "db1,r0"
    assert writer._source_entity == "sensor.test"
    assert writer._data_type == DataType.REAL
    assert writer._is_binary is False
    assert writer._last_written_value is None
    assert writer._write_count == 0
    assert writer._error_count == 0


def test_writer_binary_initialization(writer_factory):
    """Test binary writer initialization."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    assert writer._address == "db1,x0.0"
    assert writer._source_entity == "binary_sensor.test"
    assert writer._data_type == DataType.BIT
    assert writer._is_binary is True


# ============================================================================
# Representation Tests
# ============================================================================


def test_writer_numeric_native_value(writer_factory):
    """Test numeric writer native_value property."""
    writer = writer_factory("db1,r0", DataType.REAL)

    # Initially None
    assert writer.native_value is None

    # Set numeric value
    writer._last_written_value = 42.5
    assert writer.native_value == 42.5


def test_writer_binary_native_value(writer_factory):
    """Test binary writer native_value property displays on/off."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    # Initially None
    assert writer.native_value is None

    # Set to True (on)
    writer._last_written_value = 1.0
    assert writer.native_value == "on"

    # Set to False (off)
    writer._last_written_value = 0.0
    assert writer.native_value == "off"


# ============================================================================
# Icon Tests
# ============================================================================


def test_writer_icon_numeric(writer_factory):
    """Test numeric writer uses upload icon."""
    writer = writer_factory("db1,r0", DataType.REAL)
    assert writer.icon == "mdi:upload"


def test_writer_icon_binary(writer_factory):
    """Test binary writer uses toggle icons."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    # Initially off icon
    assert writer.icon == "mdi:toggle-switch-off-outline"

    # Set to True (on)
    writer._last_written_value = 1.0
    assert writer.icon == "mdi:toggle-switch"

    # Set to False (off)
    writer._last_written_value = 0.0
    assert writer.icon == "mdi:toggle-switch-off-outline"


# ============================================================================
# Attributes Tests
# ============================================================================


def test_writer_extra_attributes(writer_factory):
    """Test writer extra attributes."""
    writer = writer_factory("db1,r0", DataType.REAL)
    
    # Mock source entity state
    mock_state = MagicMock()
    mock_state.state = "25.5"
    mock_state.last_updated.isoformat.return_value = "2026-01-10T10:00:00"
    writer.hass.states.get.return_value = mock_state

    writer._write_count = 5
    writer._error_count = 2

    attrs = writer.extra_state_attributes

    assert attrs["s7_address"] == "DB1,R0"
    assert attrs["source_entity"] == "sensor.test"
    assert attrs["write_count"] == 5
    assert attrs["error_count"] == 2
    assert attrs["entity_sync_type"] == "numeric"
    assert attrs["source_state"] == "25.5"
    assert attrs["source_last_updated"] == "2026-01-10T10:00:00"


def test_writer_extra_attributes_binary(writer_factory):
    """Test binary entity sync has correct entity_sync_type."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")
    writer.hass.states.get.return_value = None

    attrs = writer.extra_state_attributes
    assert attrs["entity_sync_type"] == "binary"


# ============================================================================
# Write Tests - Numeric
# ============================================================================


@pytest.mark.asyncio
async def test_writer_numeric_write(writer_factory, mock_coordinator):
    """Test numeric writer writes to PLC correctly."""
    writer = writer_factory("db1,r0", DataType.REAL, coordinator=mock_coordinator)

    # Create a mock state
    mock_state = State("sensor.test", "42.5")
    await writer._async_write_to_plc(mock_state)

    # Verify write_number was called
    assert len(mock_coordinator.write_calls) == 1
    assert mock_coordinator.write_calls[0] == ("write_number", "db1,r0", 42.5)
    assert writer._last_written_value == 42.5
    assert writer._write_count == 1
    assert writer._error_count == 0


@pytest.mark.asyncio
async def test_writer_numeric_invalid_state(writer_factory, mock_coordinator):
    """Test numeric writer handles invalid state."""
    writer = writer_factory("db1,r0", DataType.REAL, coordinator=mock_coordinator)

    # Test invalid state
    mock_state = State("sensor.test", "unavailable")
    await writer._async_write_to_plc(mock_state)

    # Should not write
    assert len(mock_coordinator.write_calls) == 0
    assert writer._error_count == 1
    assert writer._write_count == 0


# ============================================================================
# Write Tests - Binary (Parametrized)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("state_str,expected_bool,expected_value", [
    ("on", True, 1.0),
    ("off", False, 0.0),
    ("true", True, 1.0),
    ("false", False, 0.0),
    ("1", True, 1.0),
    ("0", False, 0.0),
])
async def test_writer_binary_write_states(
    writer_factory, mock_coordinator, state_str, expected_bool, expected_value
):
    """Test binary writer handles various boolean state formats."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test", coordinator=mock_coordinator)

    mock_state = State("binary_sensor.test", state_str)
    await writer._async_write_to_plc(mock_state)

    assert len(mock_coordinator.write_calls) == 1
    assert mock_coordinator.write_calls[0] == ("write_bool", "db1,x0.0", expected_bool)
    assert writer._last_written_value == expected_value
    assert writer._write_count == 1
    assert writer._error_count == 0


@pytest.mark.asyncio
async def test_writer_binary_invalid_state(writer_factory, mock_coordinator):
    """Test binary writer handles invalid state."""
    writer = writer_factory("db1,x0.0", DataType.BIT, "binary_sensor.test", coordinator=mock_coordinator)

    # Test invalid state
    mock_state = State("binary_sensor.test", "unknown")
    await writer._async_write_to_plc(mock_state)

    # Should not write
    assert len(mock_coordinator.write_calls) == 0
    assert writer._error_count == 1
    assert writer._write_count == 0


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_writer_disconnected(writer_factory, mock_coordinator_disconnected):
    """Test writer handles disconnected coordinator."""
    writer = writer_factory("db1,r0", DataType.REAL, coordinator=mock_coordinator_disconnected)

    # Try to write while disconnected
    mock_state = State("sensor.test", "42.5")
    await writer._async_write_to_plc(mock_state)

    # Should not write
    assert len(mock_coordinator_disconnected.write_calls) == 0
    assert writer._error_count == 1
    assert writer._write_count == 0


@pytest.mark.asyncio
async def test_writer_write_failure(writer_factory, mock_coordinator_failing):
    """Test writer handles write failures."""
    writer = writer_factory("db1,r0", DataType.REAL, coordinator=mock_coordinator_failing)

    # Try to write
    mock_state = State("sensor.test", "42.5")
    await writer._async_write_to_plc(mock_state)

    # Write was attempted but failed
    assert len(mock_coordinator_failing.write_calls) == 1
    assert writer._error_count == 1
    assert writer._write_count == 0
    assert writer._last_written_value is None


# ============================================================================
# Availability Tests
# ============================================================================


def test_writer_available(writer_factory, mock_coordinator):
    """Test writer availability based on coordinator connection."""
    writer = writer_factory("db1,r0", DataType.REAL, coordinator=mock_coordinator)

    assert writer.available is True

    mock_coordinator.set_connected(False)
    assert writer.available is False
