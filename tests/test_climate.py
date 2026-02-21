"""Tests for climate entities."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_NAME

from custom_components.s7plc.climate import (
    S7ClimateDirectControl,
    S7ClimateSetpointControl,
    async_setup_entry,
)
from custom_components.s7plc.const import (
    CONF_CLIMATES,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_HVAC_STATUS_ADDRESS,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
)

# Test constants
TEST_CURRENT_TEMP_ADDRESS = "db1,real0"
TEST_HEATING_OUTPUT = "q0.0"
TEST_COOLING_OUTPUT = "q0.1"
TEST_TARGET_TEMP_ADDRESS = "db1,real4"
TEST_HVAC_STATUS_ADDRESS = "db1,int8"


# ============================================================================
# Fixtures
# ============================================================================


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
def climate_direct_factory(mock_coordinator, device_info):
    """Factory fixture to create S7ClimateDirectControl instances easily."""
    def _create_climate(
        current_temp_address: str = TEST_CURRENT_TEMP_ADDRESS,
        heating_output_address: str | None = TEST_HEATING_OUTPUT,
        cooling_output_address: str | None = TEST_COOLING_OUTPUT,
        name: str = "Test Climate",
        topic: str = f"climate_direct:{TEST_CURRENT_TEMP_ADDRESS}",
        unique_id: str = f"test_device:climate_direct:{TEST_CURRENT_TEMP_ADDRESS}",
    ):
        return S7ClimateDirectControl(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            current_temp_address=current_temp_address,
            heating_output_address=heating_output_address,
            cooling_output_address=cooling_output_address,
            heating_action_address=None,
            cooling_action_address=None,
            min_temp=7.0,
            max_temp=35.0,
            temp_step=0.5,
        )

    return _create_climate


@pytest.fixture
def climate_setpoint_factory(mock_coordinator, device_info):
    """Factory fixture to create S7ClimateSetpointControl instances easily."""
    def _create_climate(
        current_temp_address: str = TEST_CURRENT_TEMP_ADDRESS,
        target_temp_address: str = TEST_TARGET_TEMP_ADDRESS,
        hvac_status_address: str | None = None,
        name: str = "Test Climate",
        topic: str = f"climate_setpoint:{TEST_CURRENT_TEMP_ADDRESS}",
        unique_id: str = f"test_device:climate_setpoint:{TEST_CURRENT_TEMP_ADDRESS}",
    ):
        return S7ClimateSetpointControl(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            current_temp_address=current_temp_address,
            target_temp_address=target_temp_address,
            preset_mode_address=None,
            hvac_status_address=hvac_status_address,
            min_temp=7.0,
            max_temp=35.0,
            temp_step=0.5,
        )

    return _create_climate


# ============================================================================
# Tests for Direct Control Climate
# ============================================================================


@pytest.mark.asyncio
async def test_climate_direct_creation(climate_direct_factory):
    """Test creating a direct control climate entity."""
    climate = climate_direct_factory()
    
    assert climate._attr_name == "Test Climate"
    assert climate._current_temp_address == TEST_CURRENT_TEMP_ADDRESS
    assert climate._heating_output_address == TEST_HEATING_OUTPUT
    assert climate._cooling_output_address == TEST_COOLING_OUTPUT
    assert climate._attr_min_temp == 7.0
    assert climate._attr_max_temp == 35.0
    assert climate._attr_target_temperature_step == 0.5
    
    # Verify target temperature is initialized to midpoint
    expected_default = (7.0 + 35.0) / 2
    assert climate.target_temperature == expected_default


@pytest.mark.asyncio
async def test_climate_direct_current_temperature(climate_direct_factory, mock_coordinator):
    """Test reading current temperature."""
    climate = climate_direct_factory()
    topic = f"{climate._topic}:current_temp"
    
    # Simulate temperature reading from PLC
    mock_coordinator.data = {topic: 22.5}
    
    assert climate.current_temperature == 22.5


@pytest.mark.asyncio
async def test_climate_direct_set_temperature(climate_direct_factory, mock_coordinator):
    """Test setting target temperature."""
    climate = climate_direct_factory()
    
    # Set target temperature
    await climate.async_set_temperature(temperature=21.0)
    
    assert climate.target_temperature == 21.0


@pytest.mark.asyncio
async def test_climate_direct_set_hvac_mode(climate_direct_factory, mock_coordinator):
    """Test setting HVAC mode."""
    climate = climate_direct_factory()
    mock_coordinator.write_batched = AsyncMock()
    
    # Set to heating mode
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    
    assert climate.hvac_mode == HVACMode.HEAT


@pytest.mark.asyncio
async def test_climate_direct_hvac_modes(climate_direct_factory):
    """Test available HVAC modes."""
    # Climate with both heating and cooling
    climate = climate_direct_factory()
    assert HVACMode.OFF in climate._attr_hvac_modes
    assert HVACMode.HEAT in climate._attr_hvac_modes
    assert HVACMode.COOL in climate._attr_hvac_modes
    assert HVACMode.HEAT_COOL in climate._attr_hvac_modes
    
    # Climate with only heating
    climate_heat_only = climate_direct_factory(cooling_output_address=None)
    assert HVACMode.OFF in climate_heat_only._attr_hvac_modes
    assert HVACMode.HEAT in climate_heat_only._attr_hvac_modes
    assert HVACMode.COOL not in climate_heat_only._attr_hvac_modes
    assert HVACMode.HEAT_COOL not in climate_heat_only._attr_hvac_modes


# ============================================================================
# Tests for Setpoint Control Climate
# ============================================================================


@pytest.mark.asyncio
async def test_climate_setpoint_creation(climate_setpoint_factory):
    """Test creating a setpoint control climate entity."""
    climate = climate_setpoint_factory()
    
    assert climate._attr_name == "Test Climate"
    assert climate._current_temp_address == TEST_CURRENT_TEMP_ADDRESS
    assert climate._target_temp_address == TEST_TARGET_TEMP_ADDRESS
    assert climate._attr_min_temp == 7.0
    assert climate._attr_max_temp == 35.0
    assert climate._attr_target_temperature_step == 0.5


@pytest.mark.asyncio
async def test_climate_setpoint_current_temperature(climate_setpoint_factory, mock_coordinator):
    """Test reading current temperature."""
    climate = climate_setpoint_factory()
    topic_current = f"{climate._topic}:current_temp"
    
    # Simulate temperature reading from PLC
    mock_coordinator.data = {topic_current: 23.0}
    
    assert climate.current_temperature == 23.0


@pytest.mark.asyncio
async def test_climate_setpoint_target_temperature(climate_setpoint_factory, mock_coordinator):
    """Test reading target temperature from PLC."""
    climate = climate_setpoint_factory()
    topic_target = f"{climate._topic}:target_temp"
    
    # Simulate target temperature reading from PLC
    mock_coordinator.data = {topic_target: 21.0}
    
    assert climate.target_temperature == 21.0


@pytest.mark.asyncio
async def test_climate_setpoint_set_temperature(climate_setpoint_factory, mock_coordinator):
    """Test setting target temperature on PLC."""
    climate = climate_setpoint_factory()
    mock_coordinator.write_batched = AsyncMock()
    
    # Set target temperature
    await climate.async_set_temperature(temperature=20.0)
    
    # Verify write was called
    mock_coordinator.write_batched.assert_called_once_with(TEST_TARGET_TEMP_ADDRESS, 20.0)


@pytest.mark.asyncio
async def test_climate_setpoint_hvac_action_from_status_address(
    climate_setpoint_factory, mock_coordinator
):
    """Test hvac_action reads from PLC status address when configured."""
    from homeassistant.components.climate import HVACAction

    climate = climate_setpoint_factory(hvac_status_address=TEST_HVAC_STATUS_ADDRESS)

    # Status = 0 → OFF
    mock_coordinator.data = {
        f"{climate._topic}:hvac_status": 0,
        f"{climate._topic}:current_temp": 20.0,
        f"{climate._topic}:target_temp": 22.0,
    }
    assert climate.hvac_action == HVACAction.OFF

    # Status = 1 → HEATING
    mock_coordinator.data[f"{climate._topic}:hvac_status"] = 1
    assert climate.hvac_action == HVACAction.HEATING

    # Status = 2 → COOLING
    mock_coordinator.data[f"{climate._topic}:hvac_status"] = 2
    assert climate.hvac_action == HVACAction.COOLING


@pytest.mark.asyncio
async def test_climate_setpoint_hvac_action_fallback_without_status_address(
    climate_setpoint_factory, mock_coordinator
):
    """Test hvac_action infers from temperature when no status address configured."""
    from homeassistant.components.climate import HVACAction

    climate = climate_setpoint_factory()  # No hvac_status_address

    # Target > current → HEATING
    mock_coordinator.data = {
        f"{climate._topic}:current_temp": 18.0,
        f"{climate._topic}:target_temp": 22.0,
    }
    assert climate.hvac_action == HVACAction.HEATING

    # Target < current → COOLING
    mock_coordinator.data[f"{climate._topic}:target_temp"] = 16.0
    assert climate.hvac_action == HVACAction.COOLING

    # Target == current → IDLE
    mock_coordinator.data[f"{climate._topic}:target_temp"] = 18.0
    assert climate.hvac_action == HVACAction.IDLE


@pytest.mark.asyncio
async def test_climate_setpoint_hvac_action_off_mode(
    climate_setpoint_factory, mock_coordinator
):
    """Test hvac_action returns OFF when mode is OFF, even with status address."""
    from homeassistant.components.climate import HVACAction

    climate = climate_setpoint_factory(hvac_status_address=TEST_HVAC_STATUS_ADDRESS)
    climate._hvac_mode = HVACMode.OFF

    mock_coordinator.data = {
        f"{climate._topic}:hvac_status": 1,
        f"{climate._topic}:current_temp": 20.0,
    }
    assert climate.hvac_action == HVACAction.OFF


# ============================================================================
# Tests for async_setup_entry
# ============================================================================


@pytest.mark.asyncio
async def test_setup_entry_direct_control(fake_hass, mock_coordinator):
    """Test setting up direct control climate entities from config entry."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_CLIMATES: [
            {
                CONF_CLIMATE_CONTROL_MODE: CONTROL_MODE_DIRECT,
                CONF_CURRENT_TEMPERATURE_ADDRESS: TEST_CURRENT_TEMP_ADDRESS,
                CONF_HEATING_OUTPUT_ADDRESS: TEST_HEATING_OUTPUT,
                CONF_COOLING_OUTPUT_ADDRESS: TEST_COOLING_OUTPUT,
                CONF_NAME: "Living Room",
                CONF_MIN_TEMP: 10.0,
                CONF_MAX_TEMP: 30.0,
                CONF_TEMP_STEP: 0.5,
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch(
        "custom_components.s7plc.climate.get_coordinator_and_device_info",
        return_value=(
            mock_coordinator,
            {"name": "Test PLC"},
            "test_device",
        ),
    ):
        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7ClimateDirectControl)


@pytest.mark.asyncio
async def test_setup_entry_setpoint_control(fake_hass, mock_coordinator):
    """Test setting up setpoint control climate entities from config entry."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_CLIMATES: [
            {
                CONF_CLIMATE_CONTROL_MODE: CONTROL_MODE_SETPOINT,
                CONF_CURRENT_TEMPERATURE_ADDRESS: TEST_CURRENT_TEMP_ADDRESS,
                CONF_TARGET_TEMPERATURE_ADDRESS: TEST_TARGET_TEMP_ADDRESS,
                CONF_NAME: "Bedroom",
                CONF_MIN_TEMP: 15.0,
                CONF_MAX_TEMP: 28.0,
                CONF_TEMP_STEP: 0.5,
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch(
        "custom_components.s7plc.climate.get_coordinator_and_device_info",
        return_value=(
            mock_coordinator,
            {"name": "Test PLC"},
            "test_device",
        ),
    ):
        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7ClimateSetpointControl)


@pytest.mark.asyncio
async def test_setup_entry_no_climates(fake_hass, mock_coordinator):
    """Test setup with no climate entities configured."""
    config_entry = MagicMock()
    config_entry.options = {CONF_CLIMATES: []}

    async_add_entities = MagicMock()

    with patch(
        "custom_components.s7plc.climate.get_coordinator_and_device_info",
        return_value=(
            mock_coordinator,
            {"name": "Test PLC"},
            "test_device",
        ),
    ):
        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    assert not async_add_entities.called

# ============================================================================
# Tests for State Restoration
# ============================================================================


@pytest.mark.asyncio
async def test_climate_direct_restore_state(climate_direct_factory, fake_hass):
    """Test that direct control climate restores target temperature and HVAC mode."""
    climate = climate_direct_factory()
    
    # Mock last state with saved temperature and mode
    class MockState:
        state = "heat"
        attributes = {"temperature": 23.5}
    
    # Replace async_get_last_state to return our mock
    async def mock_get_last_state():
        return MockState()
    
    climate.async_get_last_state = mock_get_last_state
    climate.hass = fake_hass
    
    # Call async_added_to_hass which should restore the state
    await climate.async_added_to_hass()
    
    # Verify state was restored
    assert climate.target_temperature == 23.5
    assert climate.hvac_mode == HVACMode.HEAT


@pytest.mark.asyncio
async def test_climate_setpoint_restore_state(climate_setpoint_factory, fake_hass):
    """Test that setpoint control climate restores HVAC mode."""
    climate = climate_setpoint_factory()
    
    # Mock last state with saved mode
    class MockState:
        state = "off"
        attributes = {}
    
    # Replace async_get_last_state to return our mock
    async def mock_get_last_state():
        return MockState()
    
    climate.async_get_last_state = mock_get_last_state
    climate.hass = fake_hass
    
    # Call async_added_to_hass which should restore the state
    await climate.async_added_to_hass()
    
    # Verify mode was restored
    assert climate.hvac_mode == HVACMode.OFF


@pytest.mark.asyncio
async def test_climate_direct_no_restore_invalid_mode(climate_direct_factory, fake_hass):
    """Test that invalid HVAC mode is not restored."""
    climate = climate_direct_factory()
    
    # Mock last state with invalid mode
    class MockState:
        state = "invalid_mode"
        attributes = {"temperature": 20.0}
    
    async def mock_get_last_state():
        return MockState()
    
    climate.async_get_last_state = mock_get_last_state
    climate.hass = fake_hass
    
    # Store initial mode
    initial_mode = climate.hvac_mode
    
    await climate.async_added_to_hass()
    
    # Mode should not change, but temperature should be restored
    assert climate.hvac_mode == initial_mode
    assert climate.target_temperature == 20.0