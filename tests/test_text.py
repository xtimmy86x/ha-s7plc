"""Tests for the S7 PLC text entity."""

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_MAX_LENGTH,
    CONF_MIN_LENGTH,
    CONF_PATTERN,
    CONF_TEXTS,
)
from custom_components.s7plc.text import S7Text


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def text_config():
    """Return text entity configuration."""
    return {
        CONF_TEXTS: [
            {
                CONF_NAME: "Test String",
                CONF_ADDRESS: "DB1,S0.50",
                CONF_COMMAND_ADDRESS: "DB1,S100.50",
                CONF_MIN_LENGTH: 5,
                CONF_MAX_LENGTH: 50,
            },
            {
                CONF_NAME: "Test WString",
                CONF_ADDRESS: "DB2,W0.100",
                CONF_MIN_LENGTH: 0,
                CONF_MAX_LENGTH: 100,
                CONF_PATTERN: r"^[A-Z0-9]+$",
            },
            {
                CONF_NAME: "String No Command",
                CONF_ADDRESS: "DB3,S200.30",
            },
        ]
    }


@pytest.fixture
def device_info():
    """Device info dict."""
    return {
        "identifiers": {("s7plc", "test_device")},
        "name": "Test PLC",
        "manufacturer": "Siemens",
        "model": "S7-1200",
    }


# ============================================================================
# Tests
# ============================================================================


def test_text_entity_initialization(mock_coordinator, device_info):
    """Test text entity initialization."""
    text = S7Text(
        coordinator=mock_coordinator,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=5,
        max_length=50,
        pattern=None,
    )

    assert text._attr_unique_id == "test_string"
    assert text._address == "DB1,S0.50"
    assert text._command_address == "DB1,S100.50"
    assert text._attr_native_min == 5
    assert text._attr_native_max == 50


def test_text_entity_with_pattern(mock_coordinator, device_info):
    """Test text entity with pattern."""
    text = S7Text(
        coordinator=mock_coordinator,
        name="Test Pattern",
        unique_id="test_pattern",
        device_info=device_info,
        topic="DB2,W0.100",
        address="DB2,W0.100",
        command_address=None,
        min_length=0,
        max_length=100,
        pattern=r"^[A-Z0-9]+$",
    )

    assert text._attr_pattern == r"^[A-Z0-9]+$"


def test_text_entity_native_value(mock_coordinator, device_info):
    """Test text entity reads value correctly."""
    mock_coordinator.data = {"DB1,S0.50": "Hello World"}

    text = S7Text(
        coordinator=mock_coordinator,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=0,
        max_length=50,
        pattern=None,
    )

    assert text.native_value == "Hello World"


def test_text_entity_native_value_none(mock_coordinator, device_info):
    """Test text entity handles None value."""
    mock_coordinator.data = {"DB1,S0.50": None}

    text = S7Text(
        coordinator=mock_coordinator,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=0,
        max_length=50,
        pattern=None,
    )

    assert text.native_value is None


def test_text_entity_native_value_conversion(mock_coordinator, device_info):
    """Test text entity converts non-string values to string."""
    mock_coordinator.data = {"DB1,S0.50": 12345}

    text = S7Text(
        coordinator=mock_coordinator,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=0,
        max_length=50,
        pattern=None,
    )

    assert text.native_value == "12345"


@pytest.mark.asyncio
async def test_text_entity_set_value(mock_coordinator, device_info, fake_hass):
    """Test writing text value to PLC."""
    mock_coordinator.data = {"DB1,S0.50": "Old Text"}

    text = S7Text(
        coordinator=mock_coordinator,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=0,
        max_length=50,
        pattern=None,
    )
    text.hass = fake_hass

    await text.async_set_value("New Text")

    # Check that write was called with the command address
    assert len(mock_coordinator.write_calls) == 1
    assert mock_coordinator.write_calls[0] == ("write_batched", "DB1,S100.50", "New Text")
    assert mock_coordinator.refresh_called


@pytest.mark.asyncio
async def test_text_entity_set_value_no_command_address(
    mock_coordinator, device_info, fake_hass
):
    """Test that writing without command_address uses address as fallback."""
    mock_coordinator.data = {"text:DB3,S200.30": "Test"}

    text = S7Text(
        coordinator=mock_coordinator,
        name="String No Command",
        unique_id="string_no_command",
        device_info=device_info,
        topic="text:DB3,S200.30",
        address="DB3,S200.30",
        command_address="DB3,S200.30",  # In setup, this is set to address if None
        min_length=0,
        max_length=30,
        pattern=None,
    )
    text.hass = fake_hass

    # Should write to the address (used as fallback for command_address)
    await text.async_set_value("Test Value")
    
    assert len(mock_coordinator.write_calls) == 1
    assert mock_coordinator.write_calls[0] == ("write_batched", "DB3,S200.30", "Test Value")
    assert mock_coordinator.refresh_called


@pytest.mark.asyncio
async def test_text_entity_set_value_disconnected(
    mock_coordinator_disconnected, device_info, fake_hass
):
    """Test that writing when disconnected raises error."""
    text = S7Text(
        coordinator=mock_coordinator_disconnected,
        name="Test String",
        unique_id="test_string",
        device_info=device_info,
        topic="DB1,S0.50",
        address="DB1,S0.50",
        command_address="DB1,S100.50",
        min_length=0,
        max_length=50,
        pattern=None,
    )
    text.hass = fake_hass

    with pytest.raises(HomeAssistantError, match="not connected"):
        await text.async_set_value("Test")

