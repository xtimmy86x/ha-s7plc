"""Tests for binary sensor entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import EntityCategory

from custom_components.s7plc.binary_sensor import (
    S7BinarySensor,
    PlcConnectionBinarySensor,
    async_setup_entry,
)
from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_BINARY_SENSORS,
    CONF_DEVICE_CLASS,
    CONF_SCAN_INTERVAL,
)
from conftest import DummyCoordinator


# ============================================================================
# Fixtures
# ============================================================================
# Note: mock_coordinator fixture is now imported from conftest.py (DummyCoordinator)
#       with all necessary attributes (host, rack, slot, connection_type, etc.)


@pytest.fixture
def device_info():
    """Device info dict."""
    return {
        "identifiers": {("s7plc", "test_device")},
        "name": "Test PLC",
        "manufacturer": "Siemens",
        "model": "S7-1200",
    }


@pytest.fixture
def binary_sensor_factory(mock_coordinator, device_info):
    """Factory fixture to create S7BinarySensor instances easily."""
    def _create_sensor(
        address: str = "db1,x0.0",
        name: str = "Test Binary Sensor",
        topic: str = "binary_sensor:db1,x0.0",
        unique_id: str = "test_device:binary_sensor:db1,x0.0",
        device_class: str | None = None,
        invert_state: bool = False,
    ):
        return S7BinarySensor(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
            device_class=device_class,
            invert_state=invert_state,
        )
    return _create_sensor


# ============================================================================
# S7BinarySensor Tests
# ============================================================================


def test_binary_sensor_init(binary_sensor_factory):
    """Test binary sensor initialization."""
    sensor = binary_sensor_factory()
    
    assert sensor._attr_name == "Test Binary Sensor"
    assert sensor._attr_unique_id == "test_device:binary_sensor:db1,x0.0"
    assert sensor._topic == "binary_sensor:db1,x0.0"
    assert sensor._address == "db1,x0.0"


def test_binary_sensor_with_device_class(binary_sensor_factory):
    """Test binary sensor with valid device class."""
    sensor = binary_sensor_factory(device_class="door")
    
    assert sensor._attr_device_class == BinarySensorDeviceClass.DOOR


def test_binary_sensor_with_invalid_device_class(binary_sensor_factory, caplog):
    """Test binary sensor with invalid device class."""
    sensor = binary_sensor_factory(device_class="invalid_class")
    
    assert not hasattr(sensor, "_attr_device_class")
    assert "Invalid device class invalid_class" in caplog.text


@pytest.mark.parametrize("data_value,expected", [
    (True, True),
    (False, False),
    (None, None),
    (1, True),   # Truthy value
    (0, False),  # Falsy value
])
def test_binary_sensor_is_on_values(binary_sensor_factory, mock_coordinator, data_value, expected):
    """Test binary sensor is_on with various data values."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": data_value}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is expected


def test_binary_sensor_is_on_missing_data(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on returns None when topic not in data."""
    mock_coordinator.data = {}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is None


@pytest.mark.parametrize("invert,data_value,expected", [
    (True, True, False),
    (True, False, True),
    (True, None, None),
    (False, True, True),
])
def test_binary_sensor_invert_state(binary_sensor_factory, mock_coordinator, invert, data_value, expected):
    """Test binary sensor with invert_state option."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": data_value}
    sensor = binary_sensor_factory(invert_state=invert)
    
    assert sensor.is_on is expected


# ============================================================================
# PlcConnectionBinarySensor Tests
# ============================================================================


def test_plc_connection_sensor_init(mock_coordinator, device_info):
    """Test PlcConnectionBinarySensor initialization."""
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    assert sensor._attr_unique_id == "test_device:connection"
    assert sensor._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert sensor._attr_translation_key == "plc_connection"


def test_plc_connection_sensor_is_on_connected(mock_coordinator, device_info):
    """Test connection sensor is_on when PLC is connected."""
    mock_coordinator.set_connected(True)
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    assert sensor.is_on is True


def test_plc_connection_sensor_is_on_disconnected(mock_coordinator, device_info):
    """Test connection sensor is_on when PLC is disconnected."""
    mock_coordinator.set_connected(False)
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    assert sensor.is_on is False


def test_plc_connection_sensor_extra_attributes(mock_coordinator, device_info):
    """Test connection sensor extra state attributes."""
    mock_coordinator.last_health_ok = True
    mock_coordinator.last_health_latency = 0.123
    mock_coordinator.last_error_category = None
    mock_coordinator.last_error_message = None
    mock_coordinator.error_count_by_category = {}
    
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    attrs = sensor.extra_state_attributes
    assert attrs["s7_ip"] == "192.168.1.100"
    assert attrs["connection_type"] == "Rack/Slot"
    assert attrs["rack"] == 0
    assert attrs["slot"] == 1
    assert attrs["last_health_ok"] is True
    assert attrs["last_health_latency_s"] == 0.123
    assert "last_error_category" not in attrs
    assert "error_counts" not in attrs


def test_plc_connection_sensor_extra_attributes_tsap(device_info):
    """Test connection sensor extra state attributes with TSAP connection."""
    coord = MagicMock(spec=DummyCoordinator)
    coord.host = "192.168.1.100"
    coord.connection_type = "tsap"
    coord.local_tsap = "01.00"
    coord.remote_tsap = "01.01"
    coord.rack = None
    coord.slot = None
    coord._pys7_connection_type_str = "pg"
    coord.last_health_ok = False
    coord.last_health_latency = 1.5
    coord.last_error_category = None
    coord.last_error_message = None
    coord.error_count_by_category = {}
    
    sensor = PlcConnectionBinarySensor(
        coord,
        device_info,
        "test_device:connection"
    )
    
    attrs = sensor.extra_state_attributes
    assert attrs["s7_ip"] == "192.168.1.100"
    assert attrs["connection_type"] == "TSAP"
    assert attrs["local_tsap"] == "01.00"
    assert attrs["remote_tsap"] == "01.01"
    assert attrs["last_health_ok"] is False
    assert attrs["last_health_latency_s"] == 1.5


def test_plc_connection_sensor_error_attributes(device_info):
    """Test connection sensor exposes error diagnostics in attributes."""
    coord = MagicMock(spec=DummyCoordinator)
    coord.host = "192.168.1.100"
    coord.connection_type = "rack_slot"
    coord.rack = 0
    coord.slot = 1
    coord._pys7_connection_type_str = "pg"
    coord.last_health_ok = False
    coord.last_health_latency = 2.5
    coord.last_error_category = "s7_communication"
    coord.last_error_message = "Connection timeout"
    coord.error_count_by_category = {
        "s7_communication": 5,
        "network": 2,
    }
    
    sensor = PlcConnectionBinarySensor(
        coord,
        device_info,
        "test_device:connection"
    )
    
    attrs = sensor.extra_state_attributes
    assert attrs["last_error_category"] == "s7_communication"
    assert attrs["last_error_message"] == "Connection timeout"
    assert attrs["error_counts"] == {"s7_communication": 5, "network": 2}
    assert attrs["total_errors"] == 7


def test_plc_connection_sensor_available(mock_coordinator, device_info):
    """Test connection sensor is always available."""
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    # Should be available even if coordinator is not connected
    mock_coordinator.set_connected(False)
    assert sensor.available is True


def test_plc_connection_sensor_translation_placeholders(mock_coordinator, device_info):
    """Test connection sensor translation placeholders."""
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    placeholders = sensor.translation_placeholders
    assert placeholders["plc_name"] == "Test PLC"


# ============================================================================
# async_setup_entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_empty(fake_hass, mock_coordinator, device_info):
    """Test setup with no binary sensors configured."""
    config_entry = MagicMock()
    config_entry.options = {CONF_BINARY_SENSORS: []}
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add connection sensor
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], PlcConnectionBinarySensor)
    
    # Verify refresh was called
    assert mock_coordinator.refresh_count == 1


@pytest.mark.asyncio
async def test_async_setup_entry_with_sensors(fake_hass, mock_coordinator, device_info):
    """Test setup with binary sensors configured."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_BINARY_SENSORS: [
            {
                CONF_ADDRESS: "db1,x0.0",
                CONF_NAME: "Sensor 1",
                CONF_DEVICE_CLASS: "door",
            },
            {
                CONF_ADDRESS: "db1,x0.1",
                CONF_NAME: "Sensor 2",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add connection sensor + 2 binary sensors
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 3
    assert isinstance(entities[0], PlcConnectionBinarySensor)
    assert isinstance(entities[1], S7BinarySensor)
    assert isinstance(entities[2], S7BinarySensor)
    
    # Verify coordinator.add_item was called for each sensor
    assert len(mock_coordinator.add_item_calls) == 2
    
    # Verify refresh was called
    assert mock_coordinator.refresh_count == 1


@pytest.mark.asyncio
async def test_async_setup_entry_skip_missing_address(fake_hass, mock_coordinator, device_info):
    """Test setup skips sensors without address."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_BINARY_SENSORS: [
            {CONF_NAME: "No Address Sensor"},
            {CONF_ADDRESS: "db1,x0.0", CONF_NAME: "Valid Sensor"},
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add connection sensor + 1 valid sensor (skip the one without address)
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], PlcConnectionBinarySensor)
    assert isinstance(entities[1], S7BinarySensor)
    
    # Only one sensor added to coordinator
    assert len(mock_coordinator.add_item_calls) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_default_name(fake_hass, mock_coordinator, device_info):
    """Test setup uses default name when not provided."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_BINARY_SENSORS: [
            {CONF_ADDRESS: "db1,x0.0"}  # No name
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        with patch("custom_components.s7plc.binary_sensor.default_entity_name") as mock_default_name:
            mock_default_name.return_value = "Test PLC db1,x0.0"
            
            await async_setup_entry(fake_hass, config_entry, async_add_entities)
            
            mock_default_name.assert_called_once_with("db1,x0.0")


@pytest.mark.asyncio
async def test_async_setup_entry_with_scan_interval(fake_hass, mock_coordinator, device_info):
    """Test setup passes scan_interval to coordinator."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_BINARY_SENSORS: [
            {
                CONF_ADDRESS: "db1,x0.0",
                CONF_NAME: "Sensor 1",
                CONF_SCAN_INTERVAL: 5,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Verify scan_interval was passed to add_item
    assert len(mock_coordinator.add_item_calls) == 1
    args, kwargs = mock_coordinator.add_item_calls[0]
    assert args == ("binary_sensor:db1,x0.0", "db1,x0.0", 5)


@pytest.mark.asyncio
async def test_async_setup_entry_with_invert_state(fake_hass, mock_coordinator, device_info):
    """Test setup with invert_state option."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_BINARY_SENSORS: [
            {
                CONF_ADDRESS: "db1,x0.0",
                CONF_NAME: "Inverted Sensor",
                "invert_state": True,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.binary_sensor.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add connection sensor + 1 binary sensor
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    
    # Check that the binary sensor has invert_state enabled
    binary_sensor = entities[1]
    assert isinstance(binary_sensor, S7BinarySensor)
    assert binary_sensor._invert_state is True
