"""Tests for cover entities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_NAME

from custom_components.s7plc.cover import S7Cover, async_setup_entry
from custom_components.s7plc.const import (
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_SCAN_INTERVAL,
    CONF_USE_STATE_TOPICS,
    DEFAULT_OPERATE_TIME,
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
    coord.write = MagicMock(return_value=True)
    coord._item_scan_intervals = {}
    coord._default_scan_interval = 10
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
    hass.create_task = MagicMock()
    return hass


@pytest.fixture
def cover_factory(mock_coordinator, device_info, fake_hass):
    """Factory fixture to create S7Cover instances easily."""
    def _create_cover(
        open_command: str = "db1,x0.0",
        close_command: str = "db1,x0.1",
        opened_state: str | None = None,
        closed_state: str | None = None,
        opened_topic: str | None = None,
        closed_topic: str | None = None,
        name: str = "Test Cover",
        unique_id: str = "test_device:cover:db1,x0.0",
        operate_time: float = 15.0,
        use_state_topics: bool = False,
    ):
        cover = S7Cover(
            mock_coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            open_command=open_command,
            close_command=close_command,
            opened_state=opened_state,
            closed_state=closed_state,
            opened_topic=opened_topic,
            closed_topic=closed_topic,
            operate_time=operate_time,
            use_state_topics=use_state_topics,
        )
        cover.hass = fake_hass
        return cover
    return _create_cover


# ============================================================================
# S7Cover Initialization Tests
# ============================================================================


def test_cover_init_basic(cover_factory):
    """Test basic cover initialization."""
    cover = cover_factory()
    
    assert cover._attr_name == "Test Cover"
    assert cover._attr_unique_id == "test_device:cover:db1,x0.0"
    assert cover._open_command_address == "db1,x0.0"
    assert cover._close_command_address == "db1,x0.1"
    assert cover._operate_time == 15.0
    assert cover._use_state_topics is False
    assert cover._is_opening is False
    assert cover._is_closing is False
    assert cover._assumed_closed is False


def test_cover_init_with_state_topics(cover_factory):
    """Test cover initialization with state topics."""
    cover = cover_factory(
        opened_state="db1,x1.0",
        closed_state="db1,x1.1",
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
    )
    
    assert cover._opened_state_address == "db1,x1.0"
    assert cover._closed_state_address == "db1,x1.1"
    assert cover._opened_topic == "cover:opened:db1,x1.0"
    assert cover._closed_topic == "cover:closed:db1,x1.1"
    assert cover._use_state_topics is True


def test_cover_supported_features(cover_factory):
    """Test cover supported features."""
    cover = cover_factory()
    
    expected = (
        CoverEntityFeature.OPEN | 
        CoverEntityFeature.CLOSE | 
        CoverEntityFeature.STOP
    )
    assert cover._attr_supported_features == expected


def test_cover_assumed_state(cover_factory):
    """Test cover assumed_state attribute."""
    cover = cover_factory()
    assert cover._attr_assumed_state is True


# ============================================================================
# State Property Tests
# ============================================================================


def test_is_closed_operate_time_mode_initially(cover_factory):
    """Test is_closed in operate time mode - initial state."""
    cover = cover_factory(use_state_topics=False)
    assert cover.is_closed is False  # Default assumed_closed is False (open)


def test_is_closed_operate_time_mode_opening(cover_factory):
    """Test is_closed when opening."""
    cover = cover_factory(use_state_topics=False)
    cover._is_opening = True
    assert cover.is_closed is False


def test_is_closed_operate_time_mode_closing(cover_factory):
    """Test is_closed when closing."""
    cover = cover_factory(use_state_topics=False)
    cover._is_closing = True
    assert cover.is_closed is False


def test_is_closed_state_topics_closed(cover_factory, mock_coordinator):
    """Test is_closed with state topics - cover is closed."""
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": False,
        "cover:closed:db1,x1.1": True,
    }
    cover = cover_factory(
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
    )
    assert cover.is_closed is True


def test_is_closed_state_topics_opened(cover_factory, mock_coordinator):
    """Test is_closed with state topics - cover is opened."""
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": True,
        "cover:closed:db1,x1.1": False,
    }
    cover = cover_factory(
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
    )
    assert cover.is_closed is False


def test_is_closed_state_topics_unknown(cover_factory, mock_coordinator):
    """Test is_closed with state topics - position unknown."""
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": False,
        "cover:closed:db1,x1.1": False,
    }
    cover = cover_factory(
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
    )
    assert cover.is_closed is None


def test_is_opening(cover_factory):
    """Test is_opening property."""
    cover = cover_factory()
    assert cover.is_opening is False
    cover._is_opening = True
    assert cover.is_opening is True


def test_is_closing(cover_factory):
    """Test is_closing property."""
    cover = cover_factory()
    assert cover.is_closing is False
    cover._is_closing = True
    assert cover.is_closing is True


# ============================================================================
# Open Cover Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_open_cover(cover_factory, mock_coordinator):
    """Test opening cover."""
    cover = cover_factory()
    cover._coord.data = {}  # Make available
    
    await cover.async_open_cover()
    
    mock_coordinator.write.assert_called_with("db1,x0.0", True)
    assert cover._is_opening is True
    assert cover._is_closing is False
    assert cover._assumed_closed is False


@pytest.mark.asyncio
async def test_async_open_cover_write_failure(cover_factory, mock_coordinator):
    """Test opening cover when write fails."""
    mock_coordinator.write.return_value = False
    cover = cover_factory()
    cover._coord.data = {}
    
    with pytest.raises(Exception):  # HomeAssistantError
        await cover.async_open_cover()


# ============================================================================
# Close Cover Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_close_cover(cover_factory, mock_coordinator):
    """Test closing cover."""
    cover = cover_factory()
    cover._coord.data = {}
    
    await cover.async_close_cover()
    
    mock_coordinator.write.assert_called_with("db1,x0.1", True)
    assert cover._is_opening is False
    assert cover._is_closing is True
    assert cover._assumed_closed is True


@pytest.mark.asyncio
async def test_async_close_cover_write_failure(cover_factory, mock_coordinator):
    """Test closing cover when write fails."""
    mock_coordinator.write.return_value = False
    cover = cover_factory()
    cover._coord.data = {}
    
    with pytest.raises(Exception):  # HomeAssistantError
        await cover.async_close_cover()


# ============================================================================
# Stop Cover Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_stop_cover_while_opening(cover_factory, mock_coordinator):
    """Test stopping cover while opening."""
    cover = cover_factory()
    cover._coord.data = {}
    cover._is_opening = True
    
    await cover.async_stop_cover()
    
    mock_coordinator.write.assert_called_with("db1,x0.0", False)
    assert cover._is_opening is False
    assert cover._is_closing is False


@pytest.mark.asyncio
async def test_async_stop_cover_while_closing(cover_factory, mock_coordinator):
    """Test stopping cover while closing."""
    cover = cover_factory()
    cover._coord.data = {}
    cover._is_closing = True
    
    await cover.async_stop_cover()
    
    mock_coordinator.write.assert_called_with("db1,x0.1", False)
    assert cover._is_opening is False
    assert cover._is_closing is False


@pytest.mark.asyncio
async def test_async_stop_cover_idle(cover_factory, mock_coordinator):
    """Test stopping cover when idle."""
    cover = cover_factory()
    cover._coord.data = {}
    
    await cover.async_stop_cover()
    
    # Should not raise error even when not moving
    assert cover._is_opening is False
    assert cover._is_closing is False


# ============================================================================
# Available Tests
# ============================================================================


def test_available_no_state_topics(cover_factory, mock_coordinator):
    """Test available when no state topics configured."""
    mock_coordinator.is_connected.return_value = True
    cover = cover_factory()
    assert cover.available is True


def test_available_disconnected(cover_factory, mock_coordinator):
    """Test available when disconnected."""
    mock_coordinator.is_connected.return_value = False
    cover = cover_factory()
    assert cover.available is False


def test_available_with_state_topics(cover_factory, mock_coordinator):
    """Test available with state topics."""
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": True,
        "cover:closed:db1,x1.1": False,
    }
    cover = cover_factory(
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
    )
    assert cover.available is True


def test_available_missing_state_data(cover_factory, mock_coordinator):
    """Test available when state data missing."""
    mock_coordinator.data = {}
    cover = cover_factory(
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
    )
    assert cover.available is False


# ============================================================================
# Extra Attributes Tests
# ============================================================================


def test_extra_state_attributes_basic(cover_factory):
    """Test extra state attributes without state topics."""
    cover = cover_factory()
    
    attrs = cover.extra_state_attributes
    assert attrs["s7_open_command_address"] == "DB1,X0.0"
    assert attrs["s7_close_command_address"] == "DB1,X0.1"
    assert attrs["state_topics_used"] is False
    assert attrs["operate_time"] == "15.0 s"


def test_extra_state_attributes_with_state_topics(cover_factory):
    """Test extra state attributes with state topics."""
    cover = cover_factory(
        opened_state="db1,x1.0",
        closed_state="db1,x1.1",
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
    )
    
    attrs = cover.extra_state_attributes
    assert attrs["s7_opened_state_address"] == "DB1,X1.0"
    assert attrs["s7_closed_state_address"] == "DB1,X1.1"
    assert attrs["state_topics_used"] is True


# ============================================================================
# async_setup_entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_empty(fake_hass, mock_coordinator, device_info):
    """Test setup with no covers configured."""
    config_entry = MagicMock()
    config_entry.options = {CONF_COVERS: []}
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    async_add_entities.assert_not_called()
    mock_coordinator.async_request_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_covers(fake_hass, mock_coordinator, device_info):
    """Test setup with covers configured."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_NAME: "Cover 1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], S7Cover)
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_skip_missing_addresses(fake_hass, mock_coordinator, device_info):
    """Test setup skips covers with missing command addresses."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0"},  # Missing close
            {CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1"},  # Missing open
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.2",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.3",
            },  # Valid
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_with_state_addresses(fake_hass, mock_coordinator, device_info):
    """Test setup with state addresses."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_OPENING_STATE_ADDRESS: "db1,x1.0",
                CONF_CLOSING_STATE_ADDRESS: "db1,x1.1",
                CONF_NAME: "Cover with States",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    # Should call add_item twice (for opened and closed topics)
    assert mock_coordinator.add_item.call_count == 2
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._opened_state_address == "db1,x1.0"
    assert entities[0]._closed_state_address == "db1,x1.1"


@pytest.mark.asyncio
async def test_async_setup_entry_default_operate_time(fake_hass, mock_coordinator, device_info):
    """Test setup with default operate time."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._operate_time == float(DEFAULT_OPERATE_TIME)


@pytest.mark.asyncio
async def test_async_setup_entry_custom_operate_time(fake_hass, mock_coordinator, device_info):
    """Test setup with custom operate time."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_OPERATE_TIME: 30,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._operate_time == 30.0


@pytest.mark.asyncio
async def test_async_setup_entry_invalid_operate_time(fake_hass, mock_coordinator, device_info):
    """Test setup with invalid operate time falls back to default."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_OPERATE_TIME: "invalid",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._operate_time == float(DEFAULT_OPERATE_TIME)


@pytest.mark.asyncio
async def test_async_setup_entry_negative_operate_time(fake_hass, mock_coordinator, device_info):
    """Test setup with negative operate time falls back to default."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_OPERATE_TIME: -5,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._operate_time == float(DEFAULT_OPERATE_TIME)


@pytest.mark.asyncio
async def test_async_setup_entry_use_state_topics(fake_hass, mock_coordinator, device_info):
    """Test setup with use_state_topics enabled."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_USE_STATE_TOPICS: True,
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._use_state_topics is True
