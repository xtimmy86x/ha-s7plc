"""Tests for sensor.py module."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)

from custom_components.s7plc.sensor import (
    S7Sensor,
    async_setup_entry,
    DEVICE_CLASS_UNITS,
    TOTAL_INCREASING_CLASSES,
    NO_MEASUREMENT_CLASSES,
)
from custom_components.s7plc.address import DataType


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coord = MagicMock()
    coord.data = {}
    coord._plans_str = {}
    coord._plans_batch = {}
    coord.add_item = MagicMock()
    coord.async_request_refresh = MagicMock(return_value=None)
    return coord


@pytest.fixture
def device_info():
    """Create device info."""
    return {
        "identifiers": {("s7plc", "test-device")},
        "name": "Test Device",
        "manufacturer": "Siemens",
    }


@pytest.fixture
def sensor_factory(mock_coordinator, device_info):
    """Factory to create S7Sensor instances."""
    def _create_sensor(
        name="Test Sensor",
        unique_id="test-sensor",
        topic="sensor:DB1,REAL0",
        address="DB1,REAL0",
        device_class=None,
        value_multiplier=None,
    ):
        return S7Sensor(
            mock_coordinator,
            name,
            unique_id,
            device_info,
            topic,
            address,
            device_class,
            value_multiplier,
        )
    return _create_sensor


# ============================================================================
# S7Sensor Tests
# ============================================================================

def test_sensor_basic_initialization(sensor_factory):
    """Test basic sensor initialization."""
    sensor = sensor_factory()
    # Name is stored internally but exposed via property
    assert sensor._attr_unique_id == "test-sensor"
    assert sensor._topic == "sensor:DB1,REAL0"
    assert sensor._address == "DB1,REAL0"
    assert sensor._value_multiplier is None


def test_sensor_with_value_multiplier(sensor_factory):
    """Test sensor with value multiplier."""
    sensor = sensor_factory(value_multiplier=10.5)
    assert sensor._value_multiplier == 10.5


def test_sensor_with_empty_string_multiplier(sensor_factory):
    """Test sensor with empty string multiplier."""
    sensor = sensor_factory(value_multiplier="")
    assert sensor._value_multiplier is None


def test_sensor_with_device_class_temperature(sensor_factory):
    """Test sensor with temperature device class."""
    sensor = sensor_factory(device_class="temperature")
    assert sensor._attr_device_class == SensorDeviceClass.TEMPERATURE
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    # Check that unit is set from DEVICE_CLASS_UNITS
    assert sensor._attr_native_unit_of_measurement is not None


def test_sensor_with_device_class_energy(sensor_factory):
    """Test sensor with energy device class (TOTAL_INCREASING)."""
    sensor = sensor_factory(device_class="energy")
    assert sensor._attr_device_class == SensorDeviceClass.ENERGY
    assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING


def test_sensor_with_device_class_gas(sensor_factory):
    """Test sensor with gas device class (NO_MEASUREMENT)."""
    sensor = sensor_factory(device_class="gas")
    assert sensor._attr_device_class == SensorDeviceClass.GAS
    # Gas should have no state_class
    assert sensor._attr_state_class is None


def test_sensor_with_device_class_water(sensor_factory):
    """Test sensor with water device class (NO_MEASUREMENT)."""
    sensor = sensor_factory(device_class="water")
    assert sensor._attr_device_class == SensorDeviceClass.WATER
    assert sensor._attr_state_class is None


def test_sensor_with_invalid_device_class(sensor_factory):
    """Test sensor with invalid device class."""
    sensor = sensor_factory(device_class="invalid_class")
    # Should not set device_class
    assert not hasattr(sensor, "_attr_device_class")
    assert not hasattr(sensor, "_attr_native_unit_of_measurement")


def test_sensor_string_type_no_device_class(sensor_factory, mock_coordinator):
    """Test that string sensors don't get device_class or state_class."""
    # Make this sensor a string type
    mock_coordinator._plans_str = {"sensor:DB1,REAL0": MagicMock()}
    
    sensor = sensor_factory(device_class="temperature")
    # String sensors should not have device_class even if specified
    assert not hasattr(sensor, "_attr_device_class")
    assert not hasattr(sensor, "_attr_state_class")


def test_sensor_char_type_no_device_class(sensor_factory, mock_coordinator):
    """Test that char sensors don't get device_class or state_class."""
    # Make this sensor a char type
    mock_plan = MagicMock()
    mock_plan.tag.data_type = DataType.CHAR
    mock_coordinator._plans_batch = {"sensor:DB1,REAL0": mock_plan}
    
    sensor = sensor_factory(device_class="temperature")
    # Char sensors should not have device_class even if specified
    assert not hasattr(sensor, "_attr_device_class")
    assert not hasattr(sensor, "_attr_state_class")


def test_sensor_native_value_no_data(sensor_factory, mock_coordinator):
    """Test native_value when no data available."""
    mock_coordinator.data = {}
    sensor = sensor_factory()
    assert sensor.native_value is None


def test_sensor_native_value_simple(sensor_factory, mock_coordinator):
    """Test native_value without multiplier."""
    mock_coordinator.data = {"sensor:DB1,REAL0": 25.5}
    sensor = sensor_factory()
    assert sensor.native_value == 25.5


def test_sensor_native_value_with_multiplier(sensor_factory, mock_coordinator):
    """Test native_value with multiplier."""
    mock_coordinator.data = {"sensor:DB1,REAL0": 10.0}
    sensor = sensor_factory(value_multiplier=2.5)
    assert sensor.native_value == 25.0


def test_sensor_native_value_boolean_unchanged(sensor_factory, mock_coordinator):
    """Test native_value with boolean (should not apply multiplier)."""
    mock_coordinator.data = {"sensor:DB1,REAL0": True}
    sensor = sensor_factory(value_multiplier=2.5)
    assert sensor.native_value is True


def test_sensor_native_value_string_with_multiplier(sensor_factory, mock_coordinator):
    """Test native_value with string that can be converted to float."""
    mock_coordinator.data = {"sensor:DB1,REAL0": "15.5"}
    sensor = sensor_factory(value_multiplier=2.0)
    assert sensor.native_value == 31.0


def test_sensor_native_value_invalid_string_with_multiplier(
    sensor_factory, mock_coordinator
):
    """Test native_value with string that cannot be converted."""
    mock_coordinator.data = {"sensor:DB1,REAL0": "not_a_number"}
    sensor = sensor_factory(value_multiplier=2.0)
    # Should return original value without multiplying
    assert sensor.native_value == "not_a_number"


def test_sensor_extra_attributes_no_multiplier(sensor_factory):
    """Test extra_state_attributes without multiplier."""
    sensor = sensor_factory()
    attrs = sensor.extra_state_attributes
    assert "s7_address" in attrs
    assert attrs["s7_address"] == "DB1,REAL0"
    assert "value_multiplier" not in attrs


def test_sensor_extra_attributes_with_multiplier(sensor_factory):
    """Test extra_state_attributes with multiplier."""
    sensor = sensor_factory(value_multiplier=3.5)
    attrs = sensor.extra_state_attributes
    assert "value_multiplier" in attrs
    assert attrs["value_multiplier"] == 3.5


def test_sensor_device_class_units_mapping():
    """Test that DEVICE_CLASS_UNITS contains expected mappings."""
    # Test some known device classes
    assert SensorDeviceClass.TEMPERATURE in DEVICE_CLASS_UNITS
    assert SensorDeviceClass.ENERGY in DEVICE_CLASS_UNITS
    # Test that the mapping is a dict
    assert isinstance(DEVICE_CLASS_UNITS, dict)


def test_sensor_total_increasing_classes():
    """Test TOTAL_INCREASING_CLASSES set."""
    assert SensorDeviceClass.ENERGY in TOTAL_INCREASING_CLASSES
    assert SensorDeviceClass.ENERGY_STORAGE in TOTAL_INCREASING_CLASSES


def test_sensor_no_measurement_classes():
    """Test NO_MEASUREMENT_CLASSES set."""
    assert SensorDeviceClass.GAS in NO_MEASUREMENT_CLASSES
    assert SensorDeviceClass.WATER in NO_MEASUREMENT_CLASSES
    assert SensorDeviceClass.VOLUME in NO_MEASUREMENT_CLASSES


# ============================================================================
# async_setup_entry Tests
# ============================================================================

@pytest.mark.asyncio
async def test_async_setup_entry_no_sensors():
    """Test setup with no sensors configured."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {}
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.async_request_refresh = MagicMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should not add any entities
        async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_sensors():
    """Test setup with sensors configured."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=None)
    entry = MagicMock()
    entry.options = {
        "sensors": [
            {
                "address": "DB1,REAL0",
                "name": "Temperature",
                "device_class": "temperature",
                "value_multiplier": None,
                "real_precision": None,
                "scan_interval": None,
            }
        ]
    }
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.add_item = MagicMock()
        mock_coord.async_request_refresh = AsyncMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should add entities
        assert async_add_entities.called
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], S7Sensor)
        
        # Should request refresh
        mock_coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_skip_empty_address():
    """Test setup skips sensors without address."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        "sensors": [
            {
                "address": "",  # Empty address
                "name": "Invalid",
            }
        ]
    }
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.async_request_refresh = MagicMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should not add any entities
        async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_entity_syncs():
    """Test setup with entity syncs (writers) configured."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        "sensors": [],
        "writers": [
            {
                "address": "DB1,REAL0",
                "source_entity": "sensor.test",
                "name": "Test Sync",
            }
        ]
    }
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.async_request_refresh = MagicMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should add entity sync
        assert async_add_entities.called
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_skip_invalid_entity_syncs():
    """Test setup skips entity syncs with missing data."""
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {
        "sensors": [],
        "writers": [
            {
                "address": "",  # Missing address
                "source_entity": "sensor.test",
            },
            {
                "address": "DB1,REAL0",
                "source_entity": "",  # Missing source
            }
        ]
    }
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.async_request_refresh = MagicMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should not add any entities
        async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_default_names():
    """Test setup generates default names when not provided."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=None)
    entry = MagicMock()
    entry.options = {
        "sensors": [
            {
                "address": "DB1,REAL0",
                # No name provided
            }
        ]
    }
    async_add_entities = MagicMock()
    
    with patch(
        "custom_components.s7plc.sensor.get_coordinator_and_device_info"
    ) as mock_get_coord:
        mock_coord = MagicMock()
        mock_coord.add_item = MagicMock()
        mock_coord.async_request_refresh = AsyncMock(return_value=None)
        mock_get_coord.return_value = (
            mock_coord,
            {"name": "Test Device"},
            "test-device",
        )
        
        await async_setup_entry(hass, entry, async_add_entities)
        
        # Should create sensor with default name
        assert async_add_entities.called
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1
        # Name should be generated - just check unique_id exists
        assert entities[0]._attr_unique_id is not None


# ============================================================================
# S7EntitySync Tests (previously in test_writer.py)
# ============================================================================


@pytest.fixture
def entity_sync_factory(fake_hass):
    """Factory fixture to create S7EntitySync instances easily."""
    from custom_components.s7plc.sensor import S7EntitySync
    from conftest import DummyCoordinator
    
    def _create_entity_sync(
        address: str,
        data_type,
        source_entity: str = "sensor.test",
        name: str = "Test Entity Sync",
        coordinator = None,
    ):
        coord = coordinator if coordinator is not None else DummyCoordinator()
        
        with patch("custom_components.s7plc.sensor.parse_tag") as mock_parse:
            mock_tag = MagicMock()
            mock_tag.data_type = data_type
            mock_parse.return_value = mock_tag

            entity_sync = S7EntitySync(
                coord,
                name=name,
                unique_id="uid",
                device_info={"identifiers": {"domain"}},
                address=address,
                source_entity=source_entity,
            )
            entity_sync.hass = fake_hass
            entity_sync.name = name
            return entity_sync
    
    return _create_entity_sync


def test_entity_sync_numeric_initialization(entity_sync_factory):
    """Test numeric entity sync initialization."""
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL)

    assert entity_sync._address == "db1,r0"
    assert entity_sync._source_entity == "sensor.test"
    assert entity_sync._data_type == DataType.REAL
    assert entity_sync._is_binary is False
    assert entity_sync._last_written_value is None
    assert entity_sync._write_count == 0
    assert entity_sync._error_count == 0


def test_entity_sync_binary_initialization(entity_sync_factory):
    """Test binary entity sync initialization."""
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    assert entity_sync._address == "db1,x0.0"
    assert entity_sync._source_entity == "binary_sensor.test"
    assert entity_sync._data_type == DataType.BIT
    assert entity_sync._is_binary is True


def test_entity_sync_numeric_native_value(entity_sync_factory):
    """Test numeric entity sync native_value property."""
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL)

    # Initially None
    assert entity_sync.native_value is None

    # Set numeric value
    entity_sync._last_written_value = 42.5
    assert entity_sync.native_value == 42.5


def test_entity_sync_binary_native_value(entity_sync_factory):
    """Test binary entity sync native_value property displays on/off."""
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    # Initially None
    assert entity_sync.native_value is None

    # Set to True (on)
    entity_sync._last_written_value = 1.0
    assert entity_sync.native_value == "on"

    # Set to False (off)
    entity_sync._last_written_value = 0.0
    assert entity_sync.native_value == "off"


def test_entity_sync_icon_numeric(entity_sync_factory):
    """Test numeric entity sync uses upload icon."""
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL)
    assert entity_sync.icon == "mdi:upload"


def test_entity_sync_icon_binary(entity_sync_factory):
    """Test binary entity sync uses toggle icons."""
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")

    # Initially off icon
    assert entity_sync.icon == "mdi:toggle-switch-off-outline"

    # Set to True (on)
    entity_sync._last_written_value = 1.0
    assert entity_sync.icon == "mdi:toggle-switch"

    # Set to False (off)
    entity_sync._last_written_value = 0.0
    assert entity_sync.icon == "mdi:toggle-switch-off-outline"


def test_entity_sync_extra_attributes(entity_sync_factory):
    """Test entity sync extra attributes."""
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL)
    
    # Mock source entity state
    mock_state = MagicMock()
    mock_state.state = "25.5"
    mock_state.last_updated.isoformat.return_value = "2026-01-10T10:00:00"
    entity_sync.hass.states.get.return_value = mock_state

    entity_sync._write_count = 5
    entity_sync._error_count = 2

    attrs = entity_sync.extra_state_attributes

    assert attrs["s7_address"] == "DB1,R0"
    assert attrs["source_entity"] == "sensor.test"
    assert attrs["write_count"] == 5
    assert attrs["error_count"] == 2
    assert attrs["entity_sync_type"] == "numeric"
    assert attrs["source_state"] == "25.5"
    assert attrs["source_last_updated"] == "2026-01-10T10:00:00"


def test_entity_sync_extra_attributes_binary(entity_sync_factory):
    """Test binary entity sync has correct entity_sync_type."""
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test")
    entity_sync.hass.states.get.return_value = None

    attrs = entity_sync.extra_state_attributes
    assert attrs["entity_sync_type"] == "binary"


@pytest.mark.asyncio
async def test_entity_sync_numeric_write(entity_sync_factory):
    """Test numeric entity sync writes to PLC correctly."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL, coordinator=coord)

    # Create a mock state
    from homeassistant.core import State
    mock_state = State("sensor.test", "42.5")
    await entity_sync._async_write_to_plc(mock_state)

    # Verify write_number was called
    assert len(coord.write_calls) == 1
    assert coord.write_calls[0] == ("write_number", "db1,r0", 42.5)
    assert entity_sync._last_written_value == 42.5
    assert entity_sync._write_count == 1
    assert entity_sync._error_count == 0


@pytest.mark.asyncio
async def test_entity_sync_numeric_invalid_state(entity_sync_factory):
    """Test numeric entity sync handles invalid state."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL, coordinator=coord)

    # Test invalid state
    from homeassistant.core import State
    mock_state = State("sensor.test", "unavailable")
    await entity_sync._async_write_to_plc(mock_state)

    # Should not write
    assert len(coord.write_calls) == 0
    assert entity_sync._error_count == 1
    assert entity_sync._write_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("state_str,expected_bool,expected_value", [
    ("on", True, 1.0),
    ("off", False, 0.0),
    ("true", True, 1.0),
    ("false", False, 0.0),
    ("1", True, 1.0),
    ("0", False, 0.0),
])
async def test_entity_sync_binary_write_states(
    entity_sync_factory, state_str, expected_bool, expected_value
):
    """Test binary entity sync handles various boolean state formats."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test", coordinator=coord)

    from homeassistant.core import State
    mock_state = State("binary_sensor.test", state_str)
    await entity_sync._async_write_to_plc(mock_state)

    assert len(coord.write_calls) == 1
    assert coord.write_calls[0] == ("write_bool", "db1,x0.0", expected_bool)
    assert entity_sync._last_written_value == expected_value
    assert entity_sync._write_count == 1
    assert entity_sync._error_count == 0


@pytest.mark.asyncio
async def test_entity_sync_binary_invalid_state(entity_sync_factory):
    """Test binary entity sync handles invalid state."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    entity_sync = entity_sync_factory("db1,x0.0", DataType.BIT, "binary_sensor.test", coordinator=coord)

    # Test invalid state
    from homeassistant.core import State
    mock_state = State("binary_sensor.test", "unknown")
    await entity_sync._async_write_to_plc(mock_state)

    # Should not write
    assert len(coord.write_calls) == 0
    assert entity_sync._error_count == 1
    assert entity_sync._write_count == 0


@pytest.mark.asyncio
async def test_entity_sync_disconnected(entity_sync_factory):
    """Test entity sync handles disconnected coordinator."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator(connected=False)
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL, coordinator=coord)

    # Try to write while disconnected
    from homeassistant.core import State
    mock_state = State("sensor.test", "42.5")
    await entity_sync._async_write_to_plc(mock_state)

    # Should not write
    assert len(coord.write_calls) == 0
    assert entity_sync._error_count == 1
    assert entity_sync._write_count == 0


@pytest.mark.asyncio
async def test_entity_sync_write_failure(entity_sync_factory):
    """Test entity sync handles write failures."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    coord.set_default_write_result(False)
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL, coordinator=coord)

    # Try to write
    from homeassistant.core import State
    mock_state = State("sensor.test", "42.5")
    await entity_sync._async_write_to_plc(mock_state)

    # Write was attempted but failed
    assert len(coord.write_calls) == 1
    assert entity_sync._error_count == 1
    assert entity_sync._write_count == 0
    assert entity_sync._last_written_value is None


def test_entity_sync_available(entity_sync_factory):
    """Test entity sync availability based on coordinator connection."""
    from conftest import DummyCoordinator
    
    coord = DummyCoordinator()
    entity_sync = entity_sync_factory("db1,r0", DataType.REAL, coordinator=coord)

    assert entity_sync.available is True

    coord.set_connected(False)
    assert entity_sync.available is False
