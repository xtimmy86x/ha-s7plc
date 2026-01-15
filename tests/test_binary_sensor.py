"""Tests for binary sensor entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import CONF_NAME

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


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coord = MagicMock(spec=DummyCoordinator)
    coord.data = {}
    coord.host = "192.168.1.100"
    coord.is_connected.return_value = True
    coord.add_item = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.connection_type = "rack_slot"
    coord.rack = 0
    coord.slot = 1
    coord.local_tsap = None
    coord.remote_tsap = None
    coord._pys7_connection_type_str = "pg"
    return coord


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
def fake_hass():
    """Create a fake hass object."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    return hass


@pytest.fixture
def binary_sensor_factory(mock_coordinator, device_info):
    """Factory fixture to create S7BinarySensor instances easily."""
    def _create_sensor(
        address: str = "db1,x0.0",
        name: str = "Test Binary Sensor",
        topic: str = "binary_sensor:db1,x0.0",
        unique_id: str = "test_device:binary_sensor:db1,x0.0",
        device_class: str | None = None,
    ):
        return S7BinarySensor(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
            device_class=device_class,
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


def test_binary_sensor_is_on_true(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on returns True."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": True}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is True


def test_binary_sensor_is_on_false(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on returns False."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": False}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is False


def test_binary_sensor_is_on_none(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on returns None when data is None."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": None}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is None


def test_binary_sensor_is_on_missing_data(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on returns None when topic not in data."""
    mock_coordinator.data = {}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is None


def test_binary_sensor_is_on_truthy_value(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on converts truthy values to bool."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": 1}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is True


def test_binary_sensor_is_on_falsy_value(binary_sensor_factory, mock_coordinator):
    """Test binary sensor is_on converts falsy values to bool."""
    mock_coordinator.data = {"binary_sensor:db1,x0.0": 0}
    sensor = binary_sensor_factory()
    
    assert sensor.is_on is False


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
    assert sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert sensor.entity_category == "diagnostic"
    assert sensor._attr_translation_key == "plc_connection"


def test_plc_connection_sensor_is_on_connected(mock_coordinator, device_info):
    """Test connection sensor is_on when PLC is connected."""
    mock_coordinator.is_connected.return_value = True
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    assert sensor.is_on is True


def test_plc_connection_sensor_is_on_disconnected(mock_coordinator, device_info):
    """Test connection sensor is_on when PLC is disconnected."""
    mock_coordinator.is_connected.return_value = False
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    assert sensor.is_on is False


def test_plc_connection_sensor_extra_attributes(mock_coordinator, device_info):
    """Test connection sensor extra state attributes."""
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


def test_plc_connection_sensor_available(mock_coordinator, device_info):
    """Test connection sensor is always available."""
    sensor = PlcConnectionBinarySensor(
        mock_coordinator,
        device_info,
        "test_device:connection"
    )
    
    # Should be available even if coordinator is not connected
    mock_coordinator.is_connected.return_value = False
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
    
    mock_coordinator.async_request_refresh.assert_called_once()


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
    assert mock_coordinator.add_item.call_count == 2
    
    mock_coordinator.async_request_refresh.assert_called_once()


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
    assert mock_coordinator.add_item.call_count == 1


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
            
            mock_default_name.assert_called_once_with("Test PLC", "db1,x0.0")


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
    mock_coordinator.add_item.assert_called_once_with(
        "binary_sensor:db1,x0.0", "db1,x0.0", 5
    )
