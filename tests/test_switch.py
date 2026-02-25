"""Tests for switch entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_NAME

from custom_components.s7plc.switch import S7Switch, async_setup_entry
from custom_components.s7plc.const import (
    CONF_COMMAND_ADDRESS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
)

# Test constants
TEST_STATE_ADDRESS = "db1,x0.0"
TEST_COMMAND_ADDRESS = "db1,x0.1"
TEST_TOPIC = "switch:db1,x0.0"


# ============================================================================
# Fixtures
# ============================================================================
# Note: mock_coordinator fixture is now imported from conftest.py (DummyCoordinator)


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
def switch_factory(mock_coordinator, device_info):
    """Factory fixture to create S7Switch instances easily."""
    def _create_switch(
        state_address: str = "db1,x0.0",
        command_address: str | None = None,
        name: str = "Test Switch",
        topic: str = "switch:db1,x0.0",
        unique_id: str = "test_device:switch:db1,x0.0",
        sync_state: bool = False,
        pulse_command: bool = False,
        pulse_duration: float = 0.5,
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
            pulse_command=pulse_command,
            pulse_duration=pulse_duration,
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
    switch = switch_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    
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
@pytest.mark.parametrize("action,initial_state,expected_value", [
    ("turn_on", False, True),
    ("turn_off", True, False),
])
async def test_switch_actions(switch_factory, mock_coordinator, fake_hass, action, initial_state, expected_value):
    """Test switch turn on/off actions."""
    mock_coordinator.data = {TEST_TOPIC: initial_state}
    switch = switch_factory()
    switch.hass = fake_hass
    
    if action == "turn_on":
        await switch.async_turn_on()
    else:
        await switch.async_turn_off()
    
    assert ("write_batched", TEST_STATE_ADDRESS, expected_value) in mock_coordinator.write_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("action,initial_state,expected_value", [
    ("turn_on", False, True),
    ("turn_off", True, False),
])
async def test_switch_actions_different_command_address(switch_factory, mock_coordinator, fake_hass, action, initial_state, expected_value):
    """Test switch turn on/off with different command address."""
    mock_coordinator.data = {TEST_TOPIC: initial_state}
    switch = switch_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS
    )
    switch.hass = fake_hass
    
    if action == "turn_on":
        await switch.async_turn_on()
    else:
        await switch.async_turn_off()
    
    assert ("write_batched", TEST_COMMAND_ADDRESS, expected_value) in mock_coordinator.write_calls


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
    # Verify refresh was not called
    assert not mock_coordinator.refresh_called


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
    assert len(mock_coordinator.add_item_calls) == 2
    
    # Verify refresh was called
    assert mock_coordinator.refresh_count == 1


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
    assert len(mock_coordinator.add_item_calls) == 1


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
            
            mock_default_name.assert_called_once_with("db1,x0.0")


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
    assert len(mock_coordinator.add_item_calls) == 1
    args, kwargs = mock_coordinator.add_item_calls[0]
    assert args == ("switch:db1,x0.0", "db1,x0.0", 5)


@pytest.mark.asyncio
async def test_async_setup_entry_with_sync_state(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state enabled."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
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


# ============================================================================
# Pulse command tests
# ============================================================================


@pytest.mark.asyncio
async def test_switch_pulse_turn_on(switch_factory, mock_coordinator, fake_hass):
    """Pulse turn_on: entity is off → pulse fires (True, sleep, False)."""
    mock_coordinator.data = {TEST_TOPIC: False}
    switch = switch_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    switch.hass = fake_hass

    await switch.async_turn_on()

    # Pulse writes True then False to the command address
    assert ("write_batched", TEST_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    assert ("write_batched", TEST_COMMAND_ADDRESS, False) in mock_coordinator.write_calls
    # True must come before False
    idx_true = mock_coordinator.write_calls.index(("write_batched", TEST_COMMAND_ADDRESS, True))
    idx_false = mock_coordinator.write_calls.index(("write_batched", TEST_COMMAND_ADDRESS, False))
    assert idx_true < idx_false


@pytest.mark.asyncio
async def test_switch_pulse_turn_off(switch_factory, mock_coordinator, fake_hass):
    """Pulse turn_off: entity is on → pulse fires (True, sleep, False)."""
    mock_coordinator.data = {TEST_TOPIC: True}
    switch = switch_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    switch.hass = fake_hass

    await switch.async_turn_off()

    assert ("write_batched", TEST_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    assert ("write_batched", TEST_COMMAND_ADDRESS, False) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_switch_pulse_turn_on_already_on_noop(switch_factory, mock_coordinator, fake_hass):
    """Pulse turn_on when already on → no pulse sent."""
    mock_coordinator.data = {TEST_TOPIC: True}
    switch = switch_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    switch.hass = fake_hass

    await switch.async_turn_on()

    assert len(mock_coordinator.write_calls) == 0


@pytest.mark.asyncio
async def test_switch_pulse_turn_off_already_off_noop(switch_factory, mock_coordinator, fake_hass):
    """Pulse turn_off when already off → no pulse sent."""
    mock_coordinator.data = {TEST_TOPIC: False}
    switch = switch_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    switch.hass = fake_hass

    await switch.async_turn_off()

    assert len(mock_coordinator.write_calls) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_with_pulse(fake_hass, mock_coordinator, device_info):
    """Test setup entry passes pulse_command and pulse_duration to entity."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_SWITCHES: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
                CONF_NAME: "Pulse Switch",
                CONF_PULSE_COMMAND: True,
                CONF_PULSE_DURATION: 1.5,
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.switch.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    switch = entities[0]

    assert switch._pulse_command is True
    assert switch._pulse_duration == 1.5
