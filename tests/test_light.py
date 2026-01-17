"""Tests for light entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.components.light import ColorMode
from homeassistant.const import CONF_NAME

from custom_components.s7plc.light import S7Light, async_setup_entry
from custom_components.s7plc.const import (
    CONF_COMMAND_ADDRESS,
    CONF_LIGHTS,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SYNC_STATE,
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
    coord.is_connected.return_value = True
    coord.add_item = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    coord.write_bool = MagicMock(return_value=True)
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
def light_factory(mock_coordinator, device_info):
    """Factory fixture to create S7Light instances easily."""
    def _create_light(
        state_address: str = "db1,x0.0",
        command_address: str | None = None,
        name: str = "Test Light",
        topic: str = "light:db1,x0.0",
        unique_id: str = "test_device:light:db1,x0.0",
        sync_state: bool = False,
    ):
        if command_address is None:
            command_address = state_address
        
        return S7Light(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            state_address=state_address,
            command_address=command_address,
            sync_state=sync_state,
        )
    return _create_light


# ============================================================================
# S7Light Tests
# ============================================================================


def test_light_init(light_factory):
    """Test light initialization."""
    light = light_factory()
    
    assert light._attr_name == "Test Light"
    assert light._attr_unique_id == "test_device:light:db1,x0.0"
    assert light._topic == "light:db1,x0.0"
    assert light._address == "db1,x0.0"
    assert light._command_address == "db1,x0.0"
    assert light._sync_state is False


def test_light_init_different_addresses(light_factory):
    """Test light with different state and command addresses."""
    light = light_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    
    assert light._address == "db1,x0.0"
    assert light._command_address == "db1,x0.1"


def test_light_init_with_sync_state(light_factory):
    """Test light with sync_state enabled."""
    light = light_factory(sync_state=True)
    
    assert light._sync_state is True


def test_light_color_mode(light_factory):
    """Test light has ONOFF color mode."""
    light = light_factory()
    
    assert light.color_mode == ColorMode.ONOFF
    assert light._attr_color_mode == ColorMode.ONOFF
    assert light._attr_supported_color_modes == {ColorMode.ONOFF}


def test_light_is_on_true(light_factory, mock_coordinator):
    """Test light is_on returns True."""
    mock_coordinator.data = {"light:db1,x0.0": True}
    light = light_factory()
    
    assert light.is_on is True


def test_light_is_on_false(light_factory, mock_coordinator):
    """Test light is_on returns False."""
    mock_coordinator.data = {"light:db1,x0.0": False}
    light = light_factory()
    
    assert light.is_on is False


def test_light_is_on_none(light_factory, mock_coordinator):
    """Test light is_on returns None when data is None."""
    mock_coordinator.data = {"light:db1,x0.0": None}
    light = light_factory()
    
    assert light.is_on is None


def test_light_is_on_missing_data(light_factory, mock_coordinator):
    """Test light is_on returns None when topic not in data."""
    mock_coordinator.data = {}
    light = light_factory()
    
    assert light.is_on is None


@pytest.mark.asyncio
async def test_light_turn_on(light_factory, mock_coordinator, fake_hass):
    """Test turning light on."""
    mock_coordinator.data = {"light:db1,x0.0": False}  # Make entity available
    light = light_factory()
    light.hass = fake_hass
    
    await light.async_turn_on()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.0", True)


@pytest.mark.asyncio
async def test_light_turn_off(light_factory, mock_coordinator, fake_hass):
    """Test turning light off."""
    mock_coordinator.data = {"light:db1,x0.0": True}  # Make entity available
    light = light_factory()
    light.hass = fake_hass
    
    await light.async_turn_off()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.0", False)


@pytest.mark.asyncio
async def test_light_turn_on_different_command_address(light_factory, mock_coordinator, fake_hass):
    """Test turning light on with different command address."""
    mock_coordinator.data = {"light:db1,x0.0": False}  # Make entity available
    light = light_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    light.hass = fake_hass
    
    await light.async_turn_on()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.1", True)


@pytest.mark.asyncio
async def test_light_turn_off_different_command_address(light_factory, mock_coordinator, fake_hass):
    """Test turning light off with different command address."""
    mock_coordinator.data = {"light:db1,x0.0": True}  # Make entity available
    light = light_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    light.hass = fake_hass
    
    await light.async_turn_off()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.1", False)


# ============================================================================
# async_setup_entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_empty(fake_hass, mock_coordinator, device_info):
    """Test setup with no lights configured."""
    config_entry = MagicMock()
    config_entry.options = {CONF_LIGHTS: []}
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should not add any entities
    async_add_entities.assert_not_called()
    mock_coordinator.async_request_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_lights(fake_hass, mock_coordinator, device_info):
    """Test setup with lights configured."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Light 1",
            },
            {
                CONF_STATE_ADDRESS: "db1,x0.1",
                CONF_NAME: "Light 2",
                CONF_COMMAND_ADDRESS: "db1,x0.2",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add 2 lights
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], S7Light)
    assert isinstance(entities[1], S7Light)
    
    # Verify coordinator.add_item was called for each light
    assert mock_coordinator.add_item.call_count == 2
    
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_skip_missing_state_address(fake_hass, mock_coordinator, device_info):
    """Test setup skips lights without state_address."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {CONF_NAME: "No Address Light"},
            {CONF_STATE_ADDRESS: "db1,x0.0", CONF_NAME: "Valid Light"},
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add only 1 valid light
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7Light)
    
    # Only one light added to coordinator
    assert mock_coordinator.add_item.call_count == 1


@pytest.mark.asyncio
async def test_async_setup_entry_default_name(fake_hass, mock_coordinator, device_info):
    """Test setup uses default name when not provided."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {CONF_STATE_ADDRESS: "db1,x0.0"}  # No name
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        with patch("custom_components.s7plc.light.default_entity_name") as mock_default_name:
            mock_default_name.return_value = "Test PLC db1,x0.0"
            
            await async_setup_entry(fake_hass, config_entry, async_add_entities)
            
            mock_default_name.assert_called_once_with("Test PLC", "db1,x0.0")


@pytest.mark.asyncio
async def test_async_setup_entry_default_command_address(fake_hass, mock_coordinator, device_info):
    """Test setup uses state_address as command_address when not provided."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Light 1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    light = entities[0]
    
    # Command address should default to state address
    assert light._command_address == "db1,x0.0"


@pytest.mark.asyncio
async def test_async_setup_entry_with_scan_interval(fake_hass, mock_coordinator, device_info):
    """Test setup passes scan_interval to coordinator."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Light 1",
                CONF_SCAN_INTERVAL: 5,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Verify scan_interval was passed to add_item
    mock_coordinator.add_item.assert_called_once_with(
        "light:db1,x0.0", "db1,x0.0", 5
    )


@pytest.mark.asyncio
async def test_async_setup_entry_with_sync_state(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state enabled."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Light 1",
                CONF_SYNC_STATE: True,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    light = entities[0]
    
    assert light._sync_state is True


@pytest.mark.asyncio
async def test_async_setup_entry_sync_state_default_false(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state defaults to False."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Light 1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    light = entities[0]
    
    assert light._sync_state is False
