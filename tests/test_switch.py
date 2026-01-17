"""Tests for switch entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.const import CONF_NAME

from custom_components.s7plc.switch import S7Switch, async_setup_entry
from custom_components.s7plc.const import (
    CONF_COMMAND_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
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
def switch_factory(mock_coordinator, device_info):
    """Factory fixture to create S7Switch instances easily."""
    def _create_switch(
        state_address: str = "db1,x0.0",
        command_address: str | None = None,
        name: str = "Test Switch",
        topic: str = "switch:db1,x0.0",
        unique_id: str = "test_device:switch:db1,x0.0",
        sync_state: bool = False,
    ):
        if command_address is None:
            command_address = state_address
        
        return S7Switch(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            state_address=state_address,
            command_address=command_address,
            sync_state=sync_state,
        )
    return _create_switch


# ============================================================================
# S7Switch Tests
# ============================================================================


def test_switch_init(switch_factory):
    """Test switch initialization."""
    switch = switch_factory()
    
    assert switch._attr_name == "Test Switch"
    assert switch._attr_unique_id == "test_device:switch:db1,x0.0"
    assert switch._topic == "switch:db1,x0.0"
    assert switch._address == "db1,x0.0"
    assert switch._command_address == "db1,x0.0"
    assert switch._sync_state is False


def test_switch_init_different_addresses(switch_factory):
    """Test switch with different state and command addresses."""
    switch = switch_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    
    assert switch._address == "db1,x0.0"
    assert switch._command_address == "db1,x0.1"


def test_switch_init_with_sync_state(switch_factory):
    """Test switch with sync_state enabled."""
    switch = switch_factory(sync_state=True)
    
    assert switch._sync_state is True


def test_switch_is_on_true(switch_factory, mock_coordinator):
    """Test switch is_on returns True."""
    mock_coordinator.data = {"switch:db1,x0.0": True}
    switch = switch_factory()
    
    assert switch.is_on is True


def test_switch_is_on_false(switch_factory, mock_coordinator):
    """Test switch is_on returns False."""
    mock_coordinator.data = {"switch:db1,x0.0": False}
    switch = switch_factory()
    
    assert switch.is_on is False


def test_switch_is_on_none(switch_factory, mock_coordinator):
    """Test switch is_on returns None when data is None."""
    mock_coordinator.data = {"switch:db1,x0.0": None}
    switch = switch_factory()
    
    assert switch.is_on is None


def test_switch_is_on_missing_data(switch_factory, mock_coordinator):
    """Test switch is_on returns None when topic not in data."""
    mock_coordinator.data = {}
    switch = switch_factory()
    
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_switch_turn_on(switch_factory, mock_coordinator, fake_hass):
    """Test turning switch on."""
    mock_coordinator.data = {"switch:db1,x0.0": False}  # Make entity available
    switch = switch_factory()
    switch.hass = fake_hass
    
    await switch.async_turn_on()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.0", True)


@pytest.mark.asyncio
async def test_switch_turn_off(switch_factory, mock_coordinator, fake_hass):
    """Test turning switch off."""
    mock_coordinator.data = {"switch:db1,x0.0": True}  # Make entity available
    switch = switch_factory()
    switch.hass = fake_hass
    
    await switch.async_turn_off()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.0", False)


@pytest.mark.asyncio
async def test_switch_turn_on_different_command_address(switch_factory, mock_coordinator, fake_hass):
    """Test turning switch on with different command address."""
    mock_coordinator.data = {"switch:db1,x0.0": False}  # Make entity available
    switch = switch_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    switch.hass = fake_hass
    
    await switch.async_turn_on()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.1", True)


@pytest.mark.asyncio
async def test_switch_turn_off_different_command_address(switch_factory, mock_coordinator, fake_hass):
    """Test turning switch off with different command address."""
    mock_coordinator.data = {"switch:db1,x0.0": True}  # Make entity available
    switch = switch_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1"
    )
    switch.hass = fake_hass
    
    await switch.async_turn_off()
    
    mock_coordinator.write_bool.assert_called_once_with("db1,x0.1", False)


# ============================================================================
# async_setup_entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_empty(fake_hass, mock_coordinator, device_info):
    """Test setup with no switches configured."""
    config_entry = MagicMock()
    config_entry.options = {CONF_SWITCHES: []}
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should not add any entities
    async_add_entities.assert_not_called()
    mock_coordinator.async_request_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_switches(fake_hass, mock_coordinator, device_info):
    """Test setup with switches configured."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Switch 1",
            },
            {
                CONF_STATE_ADDRESS: "db1,x0.1",
                CONF_NAME: "Switch 2",
                CONF_COMMAND_ADDRESS: "db1,x0.2",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add 2 switches
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], S7Switch)
    assert isinstance(entities[1], S7Switch)
    
    # Verify coordinator.add_item was called for each switch
    assert mock_coordinator.add_item.call_count == 2
    
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_skip_missing_state_address(fake_hass, mock_coordinator, device_info):
    """Test setup skips switches without state_address."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {CONF_NAME: "No Address Switch"},
            {CONF_STATE_ADDRESS: "db1,x0.0", CONF_NAME: "Valid Switch"},
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should add only 1 valid switch
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7Switch)
    
    # Only one switch added to coordinator
    assert mock_coordinator.add_item.call_count == 1


@pytest.mark.asyncio
async def test_async_setup_entry_default_name(fake_hass, mock_coordinator, device_info):
    """Test setup uses default name when not provided."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {CONF_STATE_ADDRESS: "db1,x0.0"}  # No name
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        with patch("custom_components.s7plc.switch.default_entity_name") as mock_default_name:
            mock_default_name.return_value = "Test PLC db1,x0.0"
            
            await async_setup_entry(fake_hass, config_entry, async_add_entities)
            
            mock_default_name.assert_called_once_with("Test PLC", "db1,x0.0")


@pytest.mark.asyncio
async def test_async_setup_entry_default_command_address(fake_hass, mock_coordinator, device_info):
    """Test setup uses state_address as command_address when not provided."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Switch 1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    switch = entities[0]
    
    # Command address should default to state address
    assert switch._command_address == "db1,x0.0"


@pytest.mark.asyncio
async def test_async_setup_entry_with_scan_interval(fake_hass, mock_coordinator, device_info):
    """Test setup passes scan_interval to coordinator."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Switch 1",
                CONF_SCAN_INTERVAL: 5,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Verify scan_interval was passed to add_item
    mock_coordinator.add_item.assert_called_once_with(
        "switch:db1,x0.0", "db1,x0.0", 5
    )


@pytest.mark.asyncio
async def test_async_setup_entry_with_sync_state(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state enabled."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Switch 1",
                CONF_SYNC_STATE: True,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    switch = entities[0]
    
    assert switch._sync_state is True


@pytest.mark.asyncio
async def test_async_setup_entry_sync_state_default_false(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state defaults to False."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Switch 1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    switch = entities[0]
    
    assert switch._sync_state is False
