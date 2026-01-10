"""Tests for S7Writer entity."""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Callable
from unittest.mock import MagicMock, patch

from homeassistant.core import State

from custom_components.s7plc.sensor import S7Writer
from custom_components.s7plc.address import DataType


class DummyCoordinator:
    """Minimal coordinator mock for writer tests."""

    def __init__(self, connected: bool = True):
        self._connected = connected
        self.data = {}
        self.write_calls: list[tuple[str, str, Any]] = []
        self._write_queue: list[bool] = []
        self._default_write_result = True
        self._item_scan_intervals = {}
        self._default_scan_interval = 10
        self._item_real_precisions = {}

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def write_bool(self, address: str, value: bool) -> bool:
        self.write_calls.append(("write_bool", address, bool(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def write_number(self, address: str, value: float) -> bool:
        self.write_calls.append(("write_number", address, float(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def set_write_queue(self, *results: bool) -> None:
        self._write_queue = list(results)

    def set_default_write_result(self, value: bool) -> None:
        self._default_write_result = value


class _ImmediateAwaitable:
    """Awaitable that immediately returns a value (no event loop needed)."""

    def __init__(self, value: Any = None, exc: Exception | None = None):
        self._value = value
        self._exc = exc

    def __await__(self):
        if self._exc is not None:
            raise self._exc
        if False:
            yield  # pragma: no cover
        return self._value


class FakeHass:
    """Fake hass for writer tests."""

    def __init__(self):
        self.calls = []
        self.data = {}
        self.states = MagicMock()

    def async_add_executor_job(self, func: Callable, *args, **kwargs):
        self.calls.append((func.__name__, args))
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return _ImmediateAwaitable(exc=exc)
            fut = loop.create_future()
            fut.set_exception(exc)
            return fut

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return _ImmediateAwaitable(result)
        fut = loop.create_future()
        fut.set_result(result)
        return fut

    def create_task(self, coro):
        """Mock create_task."""
        # Just execute the coroutine
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            # If no loop, just return a mock
            return MagicMock()


def test_writer_numeric_initialization():
    """Test numeric writer initialization."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )

        assert writer._address == "db1,r0"
        assert writer._source_entity == "sensor.test"
        assert writer._data_type == DataType.REAL
        assert writer._is_binary is False
        assert writer._last_written_value is None
        assert writer._write_count == 0
        assert writer._error_count == 0


def test_writer_binary_initialization():
    """Test binary writer initialization."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )

        assert writer._address == "db1,x0.0"
        assert writer._source_entity == "binary_sensor.test"
        assert writer._data_type == DataType.BIT
        assert writer._is_binary is True


def test_writer_numeric_native_value():
    """Test numeric writer native_value property."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )

        # Initially None
        assert writer.native_value is None

        # Set numeric value
        writer._last_written_value = 42.5
        assert writer.native_value == 42.5


def test_writer_binary_native_value():
    """Test binary writer native_value property displays on/off."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )

        # Initially None
        assert writer.native_value is None

        # Set to True (on)
        writer._last_written_value = 1.0
        assert writer.native_value == "on"

        # Set to False (off)
        writer._last_written_value = 0.0
        assert writer.native_value == "off"


def test_writer_icon_numeric():
    """Test numeric writer uses upload icon."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )

        assert writer.icon == "mdi:upload"


def test_writer_icon_binary():
    """Test binary writer uses toggle icons."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )

        # Initially off icon
        assert writer.icon == "mdi:toggle-switch-off-outline"

        # Set to True (on)
        writer._last_written_value = 1.0
        assert writer.icon == "mdi:toggle-switch"

        # Set to False (off)
        writer._last_written_value = 0.0
        assert writer.icon == "mdi:toggle-switch-off-outline"


def test_writer_extra_attributes():
    """Test writer extra attributes."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()
        
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
        assert attrs["writer_type"] == "numeric"
        assert attrs["source_state"] == "25.5"
        assert attrs["source_last_updated"] == "2026-01-10T10:00:00"


def test_writer_extra_attributes_binary():
    """Test binary writer has correct writer_type."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )
        writer.hass = FakeHass()
        writer.hass.states.get.return_value = None

        attrs = writer.extra_state_attributes
        assert attrs["writer_type"] == "binary"


@pytest.mark.asyncio
async def test_writer_numeric_write():
    """Test numeric writer writes to PLC correctly."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()
        
        # Set name property (from _attr_name)
        writer.name = "Test Writer"

        # Create a mock state
        mock_state = State("sensor.test", "42.5")

        await writer._async_write_to_plc(mock_state)

        # Verify write_number was called
        assert len(coord.write_calls) == 1
        assert coord.write_calls[0] == ("write_number", "db1,r0", 42.5)
        assert writer._last_written_value == 42.5
        assert writer._write_count == 1
        assert writer._error_count == 0


@pytest.mark.asyncio
async def test_writer_binary_write_on():
    """Test binary writer writes boolean 'on' state to PLC."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )
        writer.hass = FakeHass()
        writer.name = "Test Writer"

        # Test "on" state
        mock_state = State("binary_sensor.test", "on")
        await writer._async_write_to_plc(mock_state)

        assert len(coord.write_calls) == 1
        assert coord.write_calls[0] == ("write_bool", "db1,x0.0", True)
        assert writer._last_written_value == 1.0
        assert writer._write_count == 1
        assert writer._error_count == 0


@pytest.mark.asyncio
async def test_writer_binary_write_off():
    """Test binary writer writes boolean 'off' state to PLC."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )
        writer.hass = FakeHass()
        writer.name = "Test Writer"
        writer.name = "Test Writer"

        # Test "off" state
        mock_state = State("binary_sensor.test", "off")
        await writer._async_write_to_plc(mock_state)

        assert len(coord.write_calls) == 1
        assert coord.write_calls[0] == ("write_bool", "db1,x0.0", False)
        assert writer._last_written_value == 0.0
        assert writer._write_count == 1


@pytest.mark.asyncio
async def test_writer_binary_write_true_false():
    """Test binary writer handles true/false strings."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="input_boolean.test",
        )
        writer.name = "Test Writer"
        writer.hass = FakeHass()
        writer.name = "Test Writer"

        # Test "true" state
        mock_state = State("input_boolean.test", "true")
        await writer._async_write_to_plc(mock_state)
        assert coord.write_calls[-1] == ("write_bool", "db1,x0.0", True)

        # Test "false" state
        mock_state = State("input_boolean.test", "false")
        await writer._async_write_to_plc(mock_state)
        assert coord.write_calls[-1] == ("write_bool", "db1,x0.0", False)


@pytest.mark.asyncio
async def test_writer_binary_write_numeric():
    """Test binary writer handles numeric values (0/1)."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()
        writer.name = "Test Writer"

        # Test "1" (true)
        mock_state = State("sensor.test", "1")
        await writer._async_write_to_plc(mock_state)
        assert coord.write_calls[-1] == ("write_bool", "db1,x0.0", True)

        # Test "0" (false)
        mock_state = State("sensor.test", "0")
        await writer._async_write_to_plc(mock_state)
        assert coord.write_calls[-1] == ("write_bool", "db1,x0.0", False)


@pytest.mark.asyncio
async def test_writer_numeric_invalid_state():
    """Test numeric writer handles invalid state."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()

        # Test invalid state
        mock_state = State("sensor.test", "unavailable")
        await writer._async_write_to_plc(mock_state)

        # Should not write
        assert len(coord.write_calls) == 0
        assert writer._error_count == 1
        assert writer._write_count == 0


@pytest.mark.asyncio
async def test_writer_binary_invalid_state():
    """Test binary writer handles invalid state."""
    coord = DummyCoordinator()

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.BIT
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,x0.0",
            source_entity="binary_sensor.test",
        )
        writer.hass = FakeHass()

        # Test invalid state
        mock_state = State("binary_sensor.test", "unknown")
        await writer._async_write_to_plc(mock_state)

        # Should not write
        assert len(coord.write_calls) == 0
        assert writer._error_count == 1
        assert writer._write_count == 0


@pytest.mark.asyncio
async def test_writer_disconnected():
    """Test writer handles disconnected coordinator."""
    coord = DummyCoordinator(connected=False)

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()
        writer.name = "Test Writer"

        # Try to write while disconnected
        mock_state = State("sensor.test", "42.5")
        await writer._async_write_to_plc(mock_state)

        # Should not write
        assert len(coord.write_calls) == 0
        assert writer._error_count == 1
        assert writer._write_count == 0


@pytest.mark.asyncio
async def test_writer_write_failure():
    """Test writer handles write failures."""
    coord = DummyCoordinator()
    coord.set_default_write_result(False)

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )
        writer.hass = FakeHass()
        writer.name = "Test Writer"

        # Try to write
        mock_state = State("sensor.test", "42.5")
        await writer._async_write_to_plc(mock_state)

        # Write was attempted but failed
        assert len(coord.write_calls) == 1
        assert writer._error_count == 1
        assert writer._write_count == 0
        assert writer._last_written_value is None


def test_writer_available():
    """Test writer availability based on coordinator connection."""
    coord = DummyCoordinator(connected=True)

    with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
        mock_tag = MagicMock()
        mock_tag.data_type = DataType.REAL
        mock_parse.return_value = mock_tag

        writer = S7Writer(
            coord,
            name="Test Writer",
            unique_id="uid",
            device_info={"identifiers": {"domain"}},
            address="db1,r0",
            source_entity="sensor.test",
        )

        assert writer.available is True

        coord.set_connected(False)
        assert writer.available is False
