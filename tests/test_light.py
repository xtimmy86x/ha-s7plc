"""Tests for light entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from homeassistant.components.light import ColorMode
from homeassistant.const import CONF_NAME

from custom_components.s7plc.light import S7Light, S7DimmerLight, async_setup_entry
from custom_components.s7plc.const import (
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_SCALE,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_LIGHTS,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_STATE_ADDRESS,
    CONF_SYNC_STATE,
)

# Test constants
TEST_STATE_ADDRESS = "db1,x0.0"
TEST_COMMAND_ADDRESS = "db1,x0.1"
TEST_TOPIC = "light:db1,x0.0"


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
def light_factory(mock_coordinator, device_info):
    """Factory fixture to create S7Light instances easily."""
    def _create_light(
        state_address: str = "db1,x0.0",
        command_address: str | None = None,
        name: str = "Test Light",
        topic: str = "light:db1,x0.0",
        unique_id: str = "test_device:light:db1,x0.0",
        sync_state: bool = False,
        pulse_command: bool = False,
        pulse_duration: float = 0.5,
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
            pulse_command=pulse_command,
            pulse_duration=pulse_duration,
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
    light = light_factory(
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    
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
@pytest.mark.parametrize("action,initial_state,expected_value", [
    ("turn_on", False, True),
    ("turn_off", True, False),
])
async def test_light_actions(light_factory, mock_coordinator, fake_hass, action, initial_state, expected_value):
    """Test light turn on/off actions."""
    mock_coordinator.data = {TEST_TOPIC: initial_state}
    light = light_factory()
    light.hass = fake_hass
    
    if action == "turn_on":
        await light.async_turn_on()
    else:
        await light.async_turn_off()
    
    assert ("write_batched", TEST_STATE_ADDRESS, expected_value) in mock_coordinator.write_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("action,initial_state,expected_value", [
    ("turn_on", False, True),
    ("turn_off", True, False),
])
async def test_light_actions_different_command_address(light_factory, mock_coordinator, fake_hass, action, initial_state, expected_value):
    """Test light turn on/off with different command address."""
    mock_coordinator.data = {TEST_TOPIC: initial_state}
    light = light_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS
    )
    light.hass = fake_hass
    
    if action == "turn_on":
        await light.async_turn_on()
    else:
        await light.async_turn_off()
    
    assert ("write_batched", TEST_COMMAND_ADDRESS, expected_value) in mock_coordinator.write_calls


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
    # Verify refresh was not called
    assert not mock_coordinator.refresh_called


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
    assert len(mock_coordinator.add_item_calls) == 2
    
    # Verify refresh was called
    assert mock_coordinator.refresh_count == 1


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
    assert len(mock_coordinator.add_item_calls) == 1


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
            
            mock_default_name.assert_called_once_with("db1,x0.0")


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
    assert len(mock_coordinator.add_item_calls) == 1
    args, kwargs = mock_coordinator.add_item_calls[0]
    assert args == ("light:db1,x0.0", "db1,x0.0", 5)


@pytest.mark.asyncio
async def test_async_setup_entry_with_sync_state(fake_hass, mock_coordinator, device_info):
    """Test setup with sync_state enabled."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
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


# ============================================================================
# S7DimmerLight Tests
# ============================================================================


TEST_DIMMER_STATE_ADDRESS = "db1,x0.0"
TEST_DIMMER_COMMAND_ADDRESS = "db1,x0.1"
TEST_DIMMER_BRIGHTNESS_STATE_ADDRESS = "db1,b0"
TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS = "db1,b1"
TEST_DIMMER_TOPIC = "light:db1,x0.0"


@pytest.fixture
def dimmer_factory(mock_coordinator, device_info):
    """Factory fixture to create S7DimmerLight instances easily."""
    def _create(
        state_address: str = TEST_DIMMER_STATE_ADDRESS,
        command_address: str = TEST_DIMMER_COMMAND_ADDRESS,
        brightness_state_address: str = TEST_DIMMER_BRIGHTNESS_STATE_ADDRESS,
        brightness_command_address: str = TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS,
        brightness_scale: int = 255,
        name: str = "Test Dimmer",
        topic: str = TEST_DIMMER_TOPIC,
        unique_id: str = f"test_device:{TEST_DIMMER_TOPIC}",
    ):
        return S7DimmerLight(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            state_address=state_address,
            command_address=command_address,
            brightness_scale=brightness_scale,
            brightness_state_address=brightness_state_address,
            brightness_command_address=brightness_command_address,
        )
    return _create


def test_dimmer_light_init(dimmer_factory):
    """Test dimmer light initialization."""
    dimmer = dimmer_factory()

    assert dimmer._attr_name == "Test Dimmer"
    assert dimmer._attr_unique_id == f"test_device:{TEST_DIMMER_TOPIC}"
    assert dimmer._topic == TEST_DIMMER_TOPIC
    assert dimmer._address == TEST_DIMMER_STATE_ADDRESS
    assert dimmer._command_address == TEST_DIMMER_COMMAND_ADDRESS
    assert dimmer._brightness_state_address == TEST_DIMMER_BRIGHTNESS_STATE_ADDRESS
    assert dimmer._brightness_command_address == TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS
    assert dimmer._brightness_scale == 255


def test_dimmer_light_color_mode(dimmer_factory):
    """Test dimmer light has BRIGHTNESS color mode."""
    dimmer = dimmer_factory()

    assert dimmer.color_mode == ColorMode.BRIGHTNESS
    assert dimmer._attr_color_mode == ColorMode.BRIGHTNESS
    assert dimmer._attr_supported_color_modes == {ColorMode.BRIGHTNESS}


def test_dimmer_light_brightness(dimmer_factory, mock_coordinator):
    """Test brightness property returns HA 0-255 value."""
    mock_coordinator.data = {f"{TEST_DIMMER_TOPIC}:brightness": 128}
    dimmer = dimmer_factory()

    assert dimmer.brightness == 128


def test_dimmer_light_brightness_zero(dimmer_factory, mock_coordinator):
    """Test brightness returns 0 when PLC value is 0."""
    mock_coordinator.data = {f"{TEST_DIMMER_TOPIC}:brightness": 0}
    dimmer = dimmer_factory()

    assert dimmer.brightness == 0


def test_dimmer_light_brightness_none(dimmer_factory, mock_coordinator):
    """Test brightness returns None when data not available."""
    mock_coordinator.data = {}
    dimmer = dimmer_factory()

    assert dimmer.brightness is None


def test_dimmer_light_is_on_true(dimmer_factory, mock_coordinator):
    """Test is_on returns True when boolean state is True."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: True,
        f"{TEST_DIMMER_TOPIC}:brightness": 100,
    }
    dimmer = dimmer_factory()

    assert dimmer.is_on is True


def test_dimmer_light_is_on_false(dimmer_factory, mock_coordinator):
    """Test is_on returns False when boolean state is False."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: False,
        f"{TEST_DIMMER_TOPIC}:brightness": 0,
    }
    dimmer = dimmer_factory()

    assert dimmer.is_on is False


def test_dimmer_light_is_on_none(dimmer_factory, mock_coordinator):
    """Test is_on returns None when boolean data not available."""
    mock_coordinator.data = {}
    dimmer = dimmer_factory()

    assert dimmer.is_on is None


def test_dimmer_light_available_with_data(dimmer_factory, mock_coordinator):
    """Test dimmer is available when both boolean and brightness data exist."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: True,
        f"{TEST_DIMMER_TOPIC}:brightness": 128,
    }
    mock_coordinator._connected = True
    dimmer = dimmer_factory()

    assert dimmer.available is True


def test_dimmer_light_unavailable_no_data(dimmer_factory, mock_coordinator):
    """Test dimmer is unavailable when brightness key is missing."""
    mock_coordinator.data = {TEST_DIMMER_TOPIC: True}
    mock_coordinator._connected = True
    dimmer = dimmer_factory()

    assert dimmer.available is False


def test_dimmer_light_unavailable_no_boolean(dimmer_factory, mock_coordinator):
    """Test dimmer is unavailable when boolean topic is missing."""
    mock_coordinator.data = {f"{TEST_DIMMER_TOPIC}:brightness": 128}
    mock_coordinator._connected = True
    dimmer = dimmer_factory()

    assert dimmer.available is False


def test_dimmer_light_unavailable_disconnected(dimmer_factory, mock_coordinator):
    """Test dimmer is unavailable when PLC is disconnected."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: True,
        f"{TEST_DIMMER_TOPIC}:brightness": 128,
    }
    mock_coordinator._connected = False
    dimmer = dimmer_factory()

    assert dimmer.available is False


def test_dimmer_light_brightness_scale_100(dimmer_factory, mock_coordinator):
    """Test brightness scaling from 0-100 PLC range to 0-255 HA range."""
    mock_coordinator.data = {f"{TEST_DIMMER_TOPIC}:brightness": 50}
    dimmer = dimmer_factory(brightness_scale=100)

    # 50 * 255 / 100 = 127.5 → 128 (rounded)
    assert dimmer.brightness == 128


def test_dimmer_light_brightness_scale_100_full(dimmer_factory, mock_coordinator):
    """Test full brightness with scale 100."""
    mock_coordinator.data = {f"{TEST_DIMMER_TOPIC}:brightness": 100}
    dimmer = dimmer_factory(brightness_scale=100)

    assert dimmer.brightness == 255


def test_dimmer_light_ha_to_plc_brightness(dimmer_factory):
    """Test HA brightness to PLC brightness conversion."""
    dimmer = dimmer_factory(brightness_scale=100)

    # 255 * 100 / 255 = 100
    assert dimmer._ha_to_plc_brightness(255) == 100
    # 128 * 100 / 255 = 50.2 → 50
    assert dimmer._ha_to_plc_brightness(128) == 50
    # 0 stays 0
    assert dimmer._ha_to_plc_brightness(0) == 0


def test_dimmer_light_ha_to_plc_brightness_255_scale(dimmer_factory):
    """Test HA brightness to PLC brightness with default 255 scale."""
    dimmer = dimmer_factory(brightness_scale=255)

    assert dimmer._ha_to_plc_brightness(255) == 255
    assert dimmer._ha_to_plc_brightness(128) == 128
    assert dimmer._ha_to_plc_brightness(0) == 0


def test_dimmer_light_brightness_scale_min_is_1(dimmer_factory):
    """Test brightness scale cannot be less than 1."""
    dimmer = dimmer_factory(brightness_scale=0)
    assert dimmer._brightness_scale == 1


@pytest.mark.asyncio
async def test_dimmer_light_turn_on(dimmer_factory, mock_coordinator, fake_hass):
    """Test turn on writes True to boolean command address."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: False,
        f"{TEST_DIMMER_TOPIC}:brightness": 0,
    }
    dimmer = dimmer_factory()
    dimmer.hass = fake_hass

    await dimmer.async_turn_on()

    assert ("write_batched", TEST_DIMMER_COMMAND_ADDRESS, True) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_dimmer_light_turn_on_with_brightness(dimmer_factory, mock_coordinator, fake_hass):
    """Test turn on with brightness writes True + brightness value."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: False,
        f"{TEST_DIMMER_TOPIC}:brightness": 0,
    }
    dimmer = dimmer_factory()
    dimmer.hass = fake_hass

    await dimmer.async_turn_on(brightness=128)

    assert ("write_batched", TEST_DIMMER_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    assert ("write_batched", TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS, 128) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_dimmer_light_turn_off(dimmer_factory, mock_coordinator, fake_hass):
    """Test turn off writes False to boolean command address."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: True,
        f"{TEST_DIMMER_TOPIC}:brightness": 128,
    }
    dimmer = dimmer_factory()
    dimmer.hass = fake_hass

    await dimmer.async_turn_off()

    assert ("write_batched", TEST_DIMMER_COMMAND_ADDRESS, False) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_dimmer_light_turn_on_with_scale(dimmer_factory, mock_coordinator, fake_hass):
    """Test turn on with brightness scaling."""
    mock_coordinator.data = {
        TEST_DIMMER_TOPIC: False,
        f"{TEST_DIMMER_TOPIC}:brightness": 0,
    }
    dimmer = dimmer_factory(brightness_scale=100)
    dimmer.hass = fake_hass

    await dimmer.async_turn_on(brightness=128)

    # Boolean on
    assert ("write_batched", TEST_DIMMER_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    # 128 * 100 / 255 = 50.2 → 50
    assert ("write_batched", TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS, 50) in mock_coordinator.write_calls


def test_dimmer_light_extra_state_attributes(dimmer_factory, mock_coordinator):
    """Test extra state attributes include relevant info."""
    dimmer = dimmer_factory()

    attrs = dimmer.extra_state_attributes
    assert attrs["s7_state_address"] == TEST_DIMMER_STATE_ADDRESS.upper()
    assert attrs["s7_command_address"] == TEST_DIMMER_COMMAND_ADDRESS.upper()
    assert attrs["s7_brightness_state_address"] == TEST_DIMMER_BRIGHTNESS_STATE_ADDRESS.upper()
    assert attrs["s7_brightness_command_address"] == TEST_DIMMER_BRIGHTNESS_COMMAND_ADDRESS.upper()
    assert attrs["brightness_scale"] == 255


def test_dimmer_light_extra_state_attributes_same_brightness_addr(dimmer_factory, mock_coordinator):
    """Test extra state attributes when brightness command defaults to state."""
    dimmer = dimmer_factory(
        brightness_state_address="db1,b5",
        brightness_command_address="db1,b5",
    )

    attrs = dimmer.extra_state_attributes
    assert attrs["s7_brightness_state_address"] == "DB1,B5"
    assert attrs["s7_brightness_command_address"] == "DB1,B5"
    assert attrs["brightness_scale"] == 255


# ============================================================================
# async_setup_entry Tests for Dimmer Lights
# ============================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_dimmer_lights(fake_hass, mock_coordinator, device_info):
    """Test setup with dimmer lights configured."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
                CONF_NAME: "Dimmer 1",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b0",
                CONF_BRIGHTNESS_COMMAND_ADDRESS: "db1,b1",
                CONF_BRIGHTNESS_SCALE: 255,
            },
            {
                CONF_STATE_ADDRESS: "db1,x0.2",
                CONF_COMMAND_ADDRESS: "db1,x0.3",
                CONF_NAME: "Dimmer 2",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b2",
                CONF_BRIGHTNESS_COMMAND_ADDRESS: "db1,b3",
                CONF_BRIGHTNESS_SCALE: 100,
            },
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], S7DimmerLight)
    assert isinstance(entities[1], S7DimmerLight)

    # Check second dimmer has scale
    assert entities[1]._brightness_scale == 100
    assert entities[1]._brightness_state_address == "db1,b2"
    assert entities[1]._brightness_command_address == "db1,b3"

    # Verify coordinator.add_item was called for each (boolean + brightness = 4)
    assert len(mock_coordinator.add_item_calls) == 4

    # Verify refresh was called
    assert mock_coordinator.refresh_count == 1


@pytest.mark.asyncio
async def test_async_setup_entry_dimmer_skip_missing_state_address(
    fake_hass, mock_coordinator, device_info
):
    """Test setup skips dimmer lights without state_address."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_NAME: "No Address Dimmer",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b0",
                CONF_BRIGHTNESS_SCALE: 255,
            },
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
                CONF_NAME: "Valid Dimmer",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b0",
                CONF_BRIGHTNESS_COMMAND_ADDRESS: "db1,b1",
                CONF_BRIGHTNESS_SCALE: 255,
            },
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7DimmerLight)


@pytest.mark.asyncio
async def test_async_setup_entry_mixed_lights_and_dimmers(
    fake_hass, mock_coordinator, device_info
):
    """Test setup with both regular lights and dimmer lights."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Regular Light",
            },
            {
                CONF_STATE_ADDRESS: "db1,x0.2",
                CONF_COMMAND_ADDRESS: "db1,x0.3",
                CONF_NAME: "Dimmer Light",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b0",
                CONF_BRIGHTNESS_COMMAND_ADDRESS: "db1,b1",
                CONF_BRIGHTNESS_SCALE: 255,
            },
        ],
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], S7Light)
    assert isinstance(entities[1], S7DimmerLight)


@pytest.mark.asyncio
async def test_async_setup_entry_dimmer_default_command_address(
    fake_hass, mock_coordinator, device_info
):
    """Test dimmer defaults command_address to state_address."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_NAME: "Dimmer",
                CONF_BRIGHTNESS_STATE_ADDRESS: "db1,b0",
                CONF_BRIGHTNESS_SCALE: 255,
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    dimmer = entities[0]
    # Command address should default to state address
    assert dimmer._command_address == "db1,x0.0"
    # Brightness command should default to brightness state
    assert dimmer._brightness_command_address == "db1,b0"


# ============================================================================
# Pulse command tests
# ============================================================================


@pytest.mark.asyncio
async def test_light_pulse_turn_on(light_factory, mock_coordinator, fake_hass):
    """Pulse turn_on: light is off → pulse fires (True, sleep, False)."""
    mock_coordinator.data = {TEST_TOPIC: False}
    light = light_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    light.hass = fake_hass

    await light.async_turn_on()

    assert ("write_batched", TEST_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    assert ("write_batched", TEST_COMMAND_ADDRESS, False) in mock_coordinator.write_calls
    idx_true = mock_coordinator.write_calls.index(("write_batched", TEST_COMMAND_ADDRESS, True))
    idx_false = mock_coordinator.write_calls.index(("write_batched", TEST_COMMAND_ADDRESS, False))
    assert idx_true < idx_false


@pytest.mark.asyncio
async def test_light_pulse_turn_off(light_factory, mock_coordinator, fake_hass):
    """Pulse turn_off: light is on → pulse fires (True, sleep, False)."""
    mock_coordinator.data = {TEST_TOPIC: True}
    light = light_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    light.hass = fake_hass

    await light.async_turn_off()

    assert ("write_batched", TEST_COMMAND_ADDRESS, True) in mock_coordinator.write_calls
    assert ("write_batched", TEST_COMMAND_ADDRESS, False) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_light_pulse_turn_on_already_on_noop(light_factory, mock_coordinator, fake_hass):
    """Pulse turn_on when already on → no pulse sent."""
    mock_coordinator.data = {TEST_TOPIC: True}
    light = light_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    light.hass = fake_hass

    await light.async_turn_on()

    assert len(mock_coordinator.write_calls) == 0


@pytest.mark.asyncio
async def test_light_pulse_turn_off_already_off_noop(light_factory, mock_coordinator, fake_hass):
    """Pulse turn_off when already off → no pulse sent."""
    mock_coordinator.data = {TEST_TOPIC: False}
    light = light_factory(
        state_address=TEST_STATE_ADDRESS,
        command_address=TEST_COMMAND_ADDRESS,
        pulse_command=True,
        pulse_duration=0.3,
    )
    light.hass = fake_hass

    await light.async_turn_off()

    assert len(mock_coordinator.write_calls) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_with_pulse(fake_hass, mock_coordinator, device_info):
    """Test setup entry passes pulse_command and pulse_duration to light entity."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_LIGHTS: [
            {
                CONF_STATE_ADDRESS: "db1,x0.0",
                CONF_COMMAND_ADDRESS: "db1,x0.1",
                CONF_NAME: "Pulse Light",
                CONF_PULSE_COMMAND: True,
                CONF_PULSE_DURATION: 1.5,
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.light.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    light = entities[0]

    assert light._pulse_command is True
    assert light._pulse_duration == 1.5