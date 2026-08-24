"""Tests for cover entities."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_NAME

from custom_components.s7plc.cover import S7Cover, async_setup_entry
from custom_components.s7plc.const import (
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_UID,
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
    coord.write_batched = AsyncMock(return_value=None)
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
        feedback_mode: str | None = None,
        cover_opening_address: str | None = None,
        cover_closing_address: str | None = None,
        cover_stopped_address: str | None = None,
        cover_opening_topic: str | None = None,
        cover_closing_topic: str | None = None,
        cover_stopped_topic: str | None = None,
        cover_status_topic: str | None = None,
        cover_status_address: str | None = None,
        cover_status_open_values: str = "",
        cover_status_closed_values: str = "",
        cover_status_opening_values: str = "",
        cover_status_closing_values: str = "",
        cover_status_stopped_values: str = "",
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
            feedback_mode=feedback_mode,
            cover_opening_address=cover_opening_address,
            cover_closing_address=cover_closing_address,
            cover_stopped_address=cover_stopped_address,
            cover_opening_topic=cover_opening_topic,
            cover_closing_topic=cover_closing_topic,
            cover_stopped_topic=cover_stopped_topic,
            cover_status_topic=cover_status_topic,
            cover_status_address=cover_status_address,
            cover_status_open_values=cover_status_open_values,
            cover_status_closed_values=cover_status_closed_values,
            cover_status_opening_values=cover_status_opening_values,
            cover_status_closing_values=cover_status_closing_values,
            cover_status_stopped_values=cover_status_stopped_values,
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
    cover.coordinator.data = {}  # Make available
    
    await cover.async_open_cover()
    
    mock_coordinator.write_batched.assert_called_with("db1,x0.0", True)
    assert cover._is_opening is True
    assert cover._is_closing is False
    assert cover._assumed_closed is False


@pytest.mark.asyncio
async def test_async_open_cover_write_failure(cover_factory, mock_coordinator):
    """Test opening cover when write fails - batched writes don't raise exceptions."""
    mock_coordinator.write_batched.return_value = None  # Batched writes are fire-and-forget
    cover = cover_factory()
    cover.coordinator.data = {}
    
    # Batched writes don't raise exceptions, they just log errors
    await cover.async_open_cover()
    
    # Verify the write was attempted
    mock_coordinator.write_batched.assert_called()


# ============================================================================
# Close Cover Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_close_cover(cover_factory, mock_coordinator):
    """Test closing cover."""
    cover = cover_factory()
    cover.coordinator.data = {}
    
    await cover.async_close_cover()
    
    mock_coordinator.write_batched.assert_called_with("db1,x0.1", True)
    assert cover._is_opening is False
    assert cover._is_closing is True
    assert cover._assumed_closed is True


@pytest.mark.asyncio
async def test_async_close_cover_write_failure(cover_factory, mock_coordinator):
    """Test closing cover when write fails - batched writes don't raise exceptions."""
    mock_coordinator.write_batched.return_value = None
    cover = cover_factory()
    cover.coordinator.data = {}
    
    # Batched writes don't raise exceptions
    await cover.async_close_cover()
    
    # Verify the write was attempted
    mock_coordinator.write_batched.assert_called()


# ============================================================================
# Stop Cover Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_stop_cover_while_opening(cover_factory, mock_coordinator):
    """Test stopping cover while opening."""
    cover = cover_factory()
    cover.coordinator.data = {}
    cover._is_opening = True
    
    await cover.async_stop_cover()
    
    assert mock_coordinator.write_batched.await_args_list == [
        call("db1,x0.0", False),
        call("db1,x0.1", False),
    ]
    assert cover._is_opening is False
    assert cover._is_closing is False


@pytest.mark.asyncio
async def test_async_stop_cover_while_closing(cover_factory, mock_coordinator):
    """Test stopping cover while closing."""
    cover = cover_factory()
    cover.coordinator.data = {}
    cover._is_closing = True
    
    await cover.async_stop_cover()
    
    assert mock_coordinator.write_batched.await_args_list == [
        call("db1,x0.0", False),
        call("db1,x0.1", False),
    ]
    assert cover._is_opening is False
    assert cover._is_closing is False


@pytest.mark.asyncio
async def test_async_stop_cover_idle(cover_factory, mock_coordinator):
    """Test stopping cover when idle."""
    cover = cover_factory()
    cover.coordinator.data = {}
    
    await cover.async_stop_cover()
    
    assert mock_coordinator.write_batched.await_args_list == [
        call("db1,x0.0", False),
        call("db1,x0.1", False),
    ]
    assert cover._is_opening is False
    assert cover._is_closing is False


@pytest.mark.asyncio
async def test_async_stop_cover_with_plc_opening_feedback(
    cover_factory, mock_coordinator
):
    """Stop both commands when PLC feedback reports external movement."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
    )
    mock_coordinator.data = {"cover:opening:db1,b10": True}
    cover._is_opening = False
    cover._is_closing = False

    await cover.async_stop_cover()

    assert cover.is_opening is True
    assert mock_coordinator.write_batched.await_args_list == [
        call("db1,x0.0", False),
        call("db1,x0.1", False),
    ]


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
        feedback_mode="both",
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
    assert attrs["cover_type"] == "open/close"


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
    assert attrs["cover_type"] == "open/close"


# ============================================================================
# Real movement status (cover_opening_address / cover_closing_address /
# cover_stopped_address) Tests
# ============================================================================


def test_movement_contract_a_status_opening_overrides_false_opening_bit(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": False,
        "cover:status:db1,b10": 1,
    }

    assert cover.is_opening is True


def test_movement_contract_b_unknown_status_does_not_fall_back_to_opening_bit(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,
        "cover:status:db1,b10": 99,
    }

    assert cover.is_opening is False


def test_movement_contract_c_status_closing_overrides_true_opening_bit(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_closing_values="2",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,
        "cover:status:db1,b10": 2,
    }

    assert cover.is_opening is False
    assert cover.is_closing is True


def test_movement_contract_d_stopped_bit_overrides_true_opening_bit(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_stopped_address="db1,b2",
        cover_stopped_topic="cover:stopped:db1,b2",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,
        "cover:stopped:db1,b2": True,
    }

    assert cover.is_opening is False


def test_movement_contract_contradictory_direction_bits_are_unknown(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_closing_address="db1,b2",
        cover_closing_topic="cover:closing:db1,b2",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,
        "cover:closing:db1,b2": True,
    }

    assert cover._get_feedback_movement() is None
    assert cover.is_opening is False
    assert cover.is_closing is False


@pytest.mark.asyncio
async def test_movement_contract_e_ha_open_command_without_plc_feedback(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
    )
    mock_coordinator.data = {}

    await cover.async_open_cover()

    assert cover.is_opening is True


def test_movement_contract_f_restart_uses_true_opening_feedback(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
    )
    cover._is_opening = False
    cover._is_closing = False
    mock_coordinator.data = {"cover:opening:db1,b1": True}

    assert cover.is_opening is True


@pytest.mark.asyncio
async def test_movement_contract_g_stop_writes_both_outputs_false_after_restart(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
    )
    cover._is_opening = False
    cover._is_closing = False
    mock_coordinator.data = {"cover:opening:db1,b1": True}

    await cover.async_stop_cover()

    assert mock_coordinator.write_batched.await_args_list == [
        call("db1,x0.0", False),
        call("db1,x0.1", False),
    ]


@pytest.mark.asyncio
async def test_external_movement_stopping_does_not_write_outputs(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
    )
    mock_coordinator.data = {"cover:opening:db1,b1": True}
    cover._handle_coordinator_update()
    mock_coordinator.data = {"cover:opening:db1,b1": False}

    cover._handle_coordinator_update()
    await asyncio.sleep(0)

    mock_coordinator.write_batched.assert_not_awaited()


@pytest.mark.asyncio
async def test_ha_movement_stopping_completes_command(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
    )
    await cover.async_open_cover()
    assert "open" in cover._reset_handles
    mock_coordinator.write_batched.reset_mock()
    mock_coordinator.data = {"cover:opening:db1,b1": True}
    cover._handle_coordinator_update()
    mock_coordinator.data = {"cover:opening:db1,b1": False}

    cover._handle_coordinator_update()
    await asyncio.sleep(0)

    mock_coordinator.write_batched.assert_awaited_once_with("db1,x0.0", False)
    assert "open" not in cover._reset_handles


def test_cover_status_unconfigured_uses_timer_flags(cover_factory):
    """Without the movement-status addresses, is_opening/is_closing are
    unaffected (already covered by test_is_opening/test_is_closing, asserted
    again here for clarity alongside the configured-case tests below)."""
    cover = cover_factory()
    cover._is_opening = True
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_cover_status_opening_address_drives_is_opening(cover_factory, mock_coordinator):
    """A True cover_opening_address reading makes is_opening True even if
    the internal timer flag disagrees."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
    )
    cover._is_opening = False
    mock_coordinator.data = {"cover:opening:db1,b10": True}
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_cover_status_closing_address_drives_is_closing(cover_factory, mock_coordinator):
    """A True cover_closing_address reading makes is_closing True."""
    cover = cover_factory(
        cover_closing_address="db1,b11",
        cover_closing_topic="cover:closing:db1,b11",
    )
    mock_coordinator.data = {"cover:closing:db1,b11": True}
    assert cover.is_closing is True
    assert cover.is_opening is False


def test_cover_stopped_address_overrides_opening_and_closing(
    cover_factory, mock_coordinator
):
    """A True cover_stopped_address reading forces both is_opening and
    is_closing False, even when cover_opening_address/cover_closing_address
    still report a stale in-motion reading - otherwise a dedicated stopped
    signal would have no effect on the entity's state."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
        cover_closing_address="db1,b11",
        cover_closing_topic="cover:closing:db1,b11",
        cover_stopped_address="db1,b12",
        cover_stopped_topic="cover:stopped:db1,b12",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b10": True,
        "cover:closing:db1,b11": True,
        "cover:stopped:db1,b12": True,
    }
    assert cover.is_opening is False
    assert cover.is_closing is False


def test_cover_stopped_address_false_defers_to_opening_and_closing(
    cover_factory, mock_coordinator
):
    """A False (or unset) cover_stopped_address reading doesn't interfere -
    cover_opening_address/cover_closing_address still drive movement."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
        cover_stopped_address="db1,b12",
        cover_stopped_topic="cover:stopped:db1,b12",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b10": True,
        "cover:stopped:db1,b12": False,
    }
    assert cover.is_opening is True


def test_cover_status_opening_address_false_overrides_stale_timer_flag(
    cover_factory, mock_coordinator
):
    """Real PLC feedback is authoritative: a False reading forces
    is_opening False even if the internal timer flag still thinks it's
    moving."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
    )
    cover._is_opening = True  # stale/simulated flag
    mock_coordinator.data = {"cover:opening:db1,b10": False}
    assert cover.is_opening is False


def test_cover_status_no_data_yet_uses_timer_flag(cover_factory, mock_coordinator):
    """Before the first coordinator poll, fall back to the HA command flag."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_opening_topic="cover:opening:db1,b10",
    )
    cover._is_opening = True
    mock_coordinator.data = {}
    assert cover.is_opening is True


def test_cover_status_does_not_affect_is_closed(cover_factory, mock_coordinator):
    """The movement-status addresses are explicitly out of scope for
    is_closed: it stays driven by opened_state/closed_state / the timer
    fallback."""
    cover = cover_factory(
        opened_state="db1,x1.0",
        closed_state="db1,x1.1",
        opened_topic="cover:opened:db1,x1.0",
        closed_topic="cover:closed:db1,x1.1",
        use_state_topics=True,
        cover_closing_address="db1,b10",
        cover_closing_topic="cover:closing:db1,b10",
    )
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": False,
        "cover:closed:db1,x1.1": True,
        "cover:closing:db1,b10": True,  # unrelated to is_closed
    }
    assert cover.is_closed is True  # driven by closed_state, not status
    assert cover.is_closing is True  # driven by status, independent of is_closed


def test_cover_status_extra_state_attributes(cover_factory):
    """Attributes expose each configured movement-status address."""
    cover = cover_factory(
        cover_opening_address="db1,b10",
        cover_closing_address="db1,b11",
        cover_stopped_address="db1,b12",
    )
    attrs = cover.extra_state_attributes
    assert attrs["s7_cover_opening_address"] == "DB1,B10"
    assert attrs["s7_cover_closing_address"] == "DB1,B11"
    assert attrs["s7_cover_stopped_address"] == "DB1,B12"


def test_cover_status_absent_from_attrs_when_unconfigured(cover_factory):
    """No movement-status attributes appear when the addresses aren't set."""
    cover = cover_factory()
    attrs = cover.extra_state_attributes
    assert "s7_cover_opening_address" not in attrs
    assert "s7_cover_closing_address" not in attrs
    assert "s7_cover_stopped_address" not in attrs


# ============================================================================
# Real movement status (cover_status_address) Tests — S7Cover
#
# cover_status_address is an alternative to the 3 boolean addresses above,
# for PLCs that expose movement as a single status word instead of separate
# bits. Takes priority over the booleans when configured.
# ============================================================================


def test_cover_status_address_unmatched_falls_back_to_booleans(
    cover_factory, mock_coordinator
):
    """An unmatched status word does not fall back to incompatible bits."""
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,  # boolean says opening
        "cover:status:db1,b10": 99,  # status word is not mapped
    }
    assert cover.is_opening is False


def test_cover_status_address_unmatched_falls_back_to_stopped(
    cover_factory, mock_coordinator
):
    """An unmatched status word still honors a dedicated stopped bit."""
    cover = cover_factory(
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_stopped_address="db1,b2",
        cover_stopped_topic="cover:stopped:db1,b2",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": True,
        "cover:stopped:db1,b2": True,
        "cover:status:db1,b10": 99,
    }
    assert cover.is_opening is False
    assert cover.is_closing is False


def test_cover_status_address_opening_value_drives_is_opening(
    cover_factory, mock_coordinator
):
    """A matching 'opening' status value makes is_opening True."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 1}
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_cover_status_address_closing_value_drives_is_closing(
    cover_factory, mock_coordinator
):
    """A matching 'closing' status value makes is_closing True."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closing_values="2",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 2}
    assert cover.is_closing is True
    assert cover.is_opening is False


def test_cover_status_address_closed_value_overrides_is_closed(
    cover_factory, mock_coordinator
):
    """A matching 'closed' status value makes is_closed True, even without
    opened_state/closed_state configured."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closed_values="3",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 3}
    assert cover.is_closed is True


def test_cover_status_address_open_value_overrides_is_closed(
    cover_factory, mock_coordinator
):
    """A matching 'open' status value makes is_closed False, even if the
    internal timer/assumed state would say otherwise."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_open_values="4",
    )
    cover._assumed_closed = True  # would otherwise report closed
    mock_coordinator.data = {"cover:status:db1,b10": 4}
    assert cover.is_closed is False


def test_cover_status_address_unmatched_falls_back_to_existing_logic(
    cover_factory, mock_coordinator
):
    """An opening status has no hidden timer-position fallback."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    cover._assumed_closed = True
    mock_coordinator.data = {"cover:status:db1,b10": 1}  # "opening", not open/closed
    assert cover.is_closed is None


def test_cover_status_address_extra_state_attributes(cover_factory):
    """Attributes expose the status address and configured value mapping
    when configured, alongside/instead of the boolean address attrs."""
    cover = cover_factory(
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
        cover_status_closing_values="2",
    )
    attrs = cover.extra_state_attributes
    assert attrs["s7_cover_status_address"] == "DB1,B10"
    assert attrs["s7_cover_status_values"]["opening"] == [1]
    assert attrs["s7_cover_status_values"]["closing"] == [2]


def test_cover_status_address_absent_from_attrs_when_unconfigured(cover_factory):
    """No cover_status_* attributes appear when the address isn't set."""
    cover = cover_factory()
    attrs = cover.extra_state_attributes
    assert "s7_cover_status_address" not in attrs
    assert "s7_cover_status_values" not in attrs


@pytest.mark.asyncio
async def test_async_setup_entry_traditional_with_status_address(
    fake_hass, mock_coordinator, device_info
):
    """Setup registers cover_status_address as its own coordinator topic for
    a traditional cover, alongside open/close commands."""
    from custom_components.s7plc.const import (
        CONF_OPEN_COMMAND_ADDRESS,
        CONF_CLOSE_COMMAND_ADDRESS,
        CONF_COVER_STATUS_ADDRESS,
        CONF_COVER_STATUS_OPENING_VALUES,
        CONF_COVER_STATUS_CLOSING_VALUES,
    )

    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_COVER_STATUS_ADDRESS: "db1,b10",
                CONF_COVER_STATUS_OPENING_VALUES: "1",
                CONF_COVER_STATUS_CLOSING_VALUES: "2",
                CONF_NAME: "Test Traditional Cover",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    assert mock_coordinator.add_item.call_count == 1
    entities = async_add_entities.call_args[0][0]
    cover = entities[0]
    assert cover._cover_status_address == "db1,b10"
    assert cover._cover_status_values["opening"] == [1]
    assert cover._cover_status_values["closing"] == [2]


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
                CONF_UID: "uid-1",
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
async def test_async_setup_entry_skip_missing_command_addresses(
    fake_hass, mock_coordinator, device_info
):
    """Test setup skips traditional covers missing open or close command addresses."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_UID: "uid-missing-open",
            },  # Missing open
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.2",
                CONF_UID: "uid-missing-close",
            },  # Missing close
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.3",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.4",
                CONF_UID: "uid-valid",
            },  # Valid
        ]
    }

    async_add_entities = MagicMock()

    with patch(
        "custom_components.s7plc.cover.get_coordinator_and_device_info"
    ) as mock_get:
        mock_get.return_value = (
            mock_coordinator,
            device_info,
            "test_device",
        )

        await async_setup_entry(
            fake_hass,
            config_entry,
            async_add_entities,
        )

    entities = async_add_entities.call_args[0][0]

    assert len(entities) == 1
    assert isinstance(entities[0], S7Cover)
    assert entities[0]._open_command_address == "db1,x0.3"
    assert entities[0]._close_command_address == "db1,x0.4"


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
                CONF_UID: "uid-1",
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
async def test_async_setup_entry_with_movement_status_addresses(
    fake_hass, mock_coordinator, device_info
):
    """Setup registers each configured movement-status address as its own
    coordinator topic, alongside the opened/closed end-stop topics."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_COVER_OPENING_ADDRESS: "db1,b10",
                CONF_COVER_CLOSING_ADDRESS: "db1,b11",
                CONF_COVER_STOPPED_ADDRESS: "db1,b12",
                CONF_NAME: "Cover with Status",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    # One add_item call per movement-status address (no opened/closed topics
    # configured here).
    assert mock_coordinator.add_item.call_count == 3
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._cover_opening_address == "db1,b10"
    assert entities[0]._cover_closing_address == "db1,b11"
    assert entities[0]._cover_stopped_address == "db1,b12"


@pytest.mark.asyncio
async def test_async_setup_entry_default_operate_time(fake_hass, mock_coordinator, device_info):
    """Test setup with default operate time."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                CONF_UID: "uid-1",
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
                CONF_UID: "uid-1",
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
                CONF_UID: "uid-1",
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
                CONF_UID: "uid-1",
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
                CONF_UID: "uid-1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    entities = async_add_entities.call_args[0][0]
    assert entities[0]._use_state_topics is False


# ============================================================================
# Tests for S7PositionCover
# ============================================================================


@pytest.mark.asyncio
async def test_position_cover_setup(fake_hass, mock_coordinator, device_info):
    """Test position-based cover setup."""
    from custom_components.s7plc.const import (
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
    )
    
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_POSITION_STATE_ADDRESS: "db1,b0",
                CONF_POSITION_COMMAND_ADDRESS: "db1,b1",
                CONF_NAME: "Test Position Cover",
                CONF_UID: "uid-1",
            }
        ]
    }
    
    async_add_entities = MagicMock()
    
    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        
        await async_setup_entry(fake_hass, config_entry, async_add_entities)
    
    mock_coordinator.add_item.assert_called_once()
    mock_coordinator.async_request_refresh.assert_called_once()
    
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    
    cover = entities[0]
    assert cover._attr_name == "Test Position Cover"
    assert cover._position_state_address == "db1,b0"
    assert cover._position_command_address == "db1,b1"


@pytest.mark.asyncio
async def test_position_cover_current_position(fake_hass, mock_coordinator, device_info):
    """Test position cover current_cover_position property."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    
    # Test with no data
    assert cover.current_cover_position is None
    
    # Test with position data
    mock_coordinator.data = {"cover:position:db1,b0": 50}
    assert cover.current_cover_position == 50
    
    # Test clamping to 0-100
    mock_coordinator.data = {"cover:position:db1,b0": 150}
    assert cover.current_cover_position == 100
    
    mock_coordinator.data = {"cover:position:db1,b0": -10}
    assert cover.current_cover_position == 0


@pytest.mark.asyncio
async def test_position_cover_is_closed(fake_hass, mock_coordinator, device_info):
    """Test position cover is_closed property."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        None,
    )
    
    # Closed when position is 0
    mock_coordinator.data = {"cover:position:db1,b0": 0}
    assert cover.is_closed is True
    
    # Open when position >= 1
    mock_coordinator.data = {"cover:position:db1,b0": 1}
    assert cover.is_closed is False
    
    mock_coordinator.data = {"cover:position:db1,b0": 50}
    assert cover.is_closed is False
    
    mock_coordinator.data = {"cover:position:db1,b0": 100}
    assert cover.is_closed is False
    
    # None when no data
    mock_coordinator.data = {}
    assert cover.is_closed is None


@pytest.mark.asyncio
async def test_position_cover_open(fake_hass, mock_coordinator, device_info):
    """Test opening position cover (sets position to 100)."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}
    
    await cover.async_open_cover()
    
    # Should write 100 to command address
    mock_coordinator.write_batched.assert_called_with("db1,b1", 100)


@pytest.mark.asyncio
async def test_position_cover_close(fake_hass, mock_coordinator, device_info):
    """Test closing position cover (sets position to 0)."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}
    
    await cover.async_close_cover()
    
    # Should write 0 to command address
    mock_coordinator.write_batched.assert_called_with("db1,b1", 0)


@pytest.mark.asyncio
async def test_position_cover_set_position(fake_hass, mock_coordinator, device_info):
    """Test setting cover position."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}
    
    await cover.async_set_cover_position(position=75)
    
    # Should write 75 to command address
    mock_coordinator.write_batched.assert_called_with("db1,b1", 75)


@pytest.mark.asyncio
async def test_position_cover_features(fake_hass, mock_coordinator, device_info):
    """Test position cover supported features."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        None,
    )
    
    features = cover._attr_supported_features
    assert features & CoverEntityFeature.OPEN
    assert features & CoverEntityFeature.CLOSE
    assert features & CoverEntityFeature.SET_POSITION
    assert features & CoverEntityFeature.STOP


@pytest.mark.asyncio
async def test_position_cover_extra_state_attributes(fake_hass, mock_coordinator, device_info):
    """Test position cover extra state attributes."""
    from custom_components.s7plc.cover import S7PositionCover
    
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    
    attrs = cover.extra_state_attributes
    assert "s7_position_state_address" in attrs
    assert "s7_position_command_address" in attrs
    assert attrs["cover_type"] == "position"
    assert attrs["s7_position_state_address"] == "DB1,B0"
    assert attrs["s7_position_command_address"] == "DB1,B1"


@pytest.mark.asyncio
async def test_position_cover_inverted_current_position(fake_hass, mock_coordinator, device_info):
    """Test position cover with inverted logic - current position."""
    from custom_components.s7plc.cover import S7PositionCover
    
    # Create inverted position cover
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Inverted",
        "test_id_inv",
        device_info,
        "db1,b0",
        "db1,b1",
        invert_position=True,
    )
    
    # Set up mock data: PLC reports 0, should appear as 100 (fully open)
    mock_coordinator.data = {"cover:position:db1,b0": 0}
    assert cover.current_cover_position == 100
    
    # PLC reports 100, should appear as 0 (fully closed)
    mock_coordinator.data = {"cover:position:db1,b0": 100}
    assert cover.current_cover_position == 0
    
    # PLC reports 50, should appear as 50 (middle position)
    mock_coordinator.data = {"cover:position:db1,b0": 50}
    assert cover.current_cover_position == 50
    
    # PLC reports 25, should appear as 75
    mock_coordinator.data = {"cover:position:db1,b0": 25}
    assert cover.current_cover_position == 75


@pytest.mark.asyncio
async def test_position_cover_inverted_is_closed(fake_hass, mock_coordinator, device_info):
    """Test position cover with inverted logic - is_closed property."""
    from custom_components.s7plc.cover import S7PositionCover
    
    # Create inverted position cover
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Inverted",
        "test_id_inv",
        device_info,
        "db1,b0",
        "db1,b1",
        invert_position=True,
    )
    
    # PLC reports 100 -> appears as 0 -> closed
    mock_coordinator.data = {"cover:position:db1,b0": 100}
    assert cover.is_closed is True
    
    # PLC reports 0 -> appears as 100 -> open
    mock_coordinator.data = {"cover:position:db1,b0": 0}
    assert cover.is_closed is False
    
    # PLC reports 50 -> appears as 50 -> open
    mock_coordinator.data = {"cover:position:db1,b0": 50}
    assert cover.is_closed is False


@pytest.mark.asyncio
async def test_position_cover_inverted_set_position(fake_hass, mock_coordinator, device_info):
    """Test position cover with inverted logic - set position command."""
    from custom_components.s7plc.cover import S7PositionCover
    
    # Create inverted position cover
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Inverted",
        "test_id_inv",
        device_info,
        "db1,b0",
        "db1,b1",
        invert_position=True,
    )
    cover.hass = fake_hass
    
    # User wants position 100 (fully open) -> PLC should receive 0
    await cover.async_set_cover_position(position=100)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 0)
    
    # User wants position 0 (fully closed) -> PLC should receive 100
    await cover.async_set_cover_position(position=0)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 100)
    
    # User wants position 50 (middle) -> PLC should receive 50
    await cover.async_set_cover_position(position=50)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 50)
    
    # User wants position 75 -> PLC should receive 25
    await cover.async_set_cover_position(position=75)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 25)


@pytest.mark.asyncio
async def test_position_cover_inverted_open_close(fake_hass, mock_coordinator, device_info):
    """Test position cover with inverted logic - open and close commands."""
    from custom_components.s7plc.cover import S7PositionCover
    
    # Create inverted position cover
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Inverted",
        "test_id_inv",
        device_info,
        "db1,b0",
        "db1,b1",
        invert_position=True,
    )
    cover.hass = fake_hass
    
    # Open command should write 0 to PLC (inverted: 100 becomes 0)
    await cover.async_open_cover()
    mock_coordinator.write_batched.assert_called_with("db1,b1", 0)
    
    # Close command should write 100 to PLC (inverted: 0 becomes 100)
    await cover.async_close_cover()
    mock_coordinator.write_batched.assert_called_with("db1,b1", 100)


@pytest.mark.asyncio
async def test_position_cover_normal_mode_backward_compatibility(fake_hass, mock_coordinator, device_info):
    """Test position cover without invert flag maintains normal behavior."""
    from custom_components.s7plc.cover import S7PositionCover
    
    # Create normal position cover (no invert_position parameter)
    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Normal",
        "test_id_normal",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass
    
    # PLC reports 0 -> appears as 0 -> closed
    mock_coordinator.data = {"cover:position:db1,b0": 0}
    assert cover.current_cover_position == 0
    assert cover.is_closed is True
    
    # PLC reports 100 -> appears as 100 -> open
    mock_coordinator.data = {"cover:position:db1,b0": 100}
    assert cover.current_cover_position == 100
    assert cover.is_closed is False
    
    # User wants position 100 (fully open) -> PLC should receive 100
    await cover.async_set_cover_position(position=100)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 100)
    
    # User wants position 0 (fully closed) -> PLC should receive 0
    await cover.async_set_cover_position(position=0)
    mock_coordinator.write_batched.assert_called_with("db1,b1", 0)


@pytest.mark.asyncio
async def test_position_cover_stop_writes_current_position(fake_hass, mock_coordinator, device_info):
    """Test that stopping a position cover writes the current position back to PLC."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass

    # Simulate cover at position 42
    mock_coordinator.data = {"cover:position:db1,b0": 42}

    await cover.async_stop_cover()

    # Should write current position (42) to command address
    mock_coordinator.write_batched.assert_called_with("db1,b1", 42)


@pytest.mark.asyncio
async def test_position_cover_stop_inverted(fake_hass, mock_coordinator, device_info):
    """Test stopping an inverted position cover writes the inverted position."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover Inverted",
        "test_id_inv",
        device_info,
        "db1,b0",
        "db1,b1",
        invert_position=True,
    )
    cover.hass = fake_hass

    # PLC reports 30, which is displayed as 70 (inverted)
    mock_coordinator.data = {"cover:position:db1,b0": 30}

    await cover.async_stop_cover()

    # _get_position_value returns inverted value (70), so 70 is written
    mock_coordinator.write_batched.assert_called_with("db1,b1", 70)


@pytest.mark.asyncio
async def test_position_cover_stop_unknown_position(fake_hass, mock_coordinator, device_info):
    """Test stopping a position cover when position is unknown does not write."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass

    # No position data available
    mock_coordinator.data = {}

    await cover.async_stop_cover()

    # Should NOT write anything since position is unknown
    mock_coordinator.write_batched.assert_not_called()


@pytest.mark.asyncio
async def test_position_cover_stop_with_stop_address(fake_hass, mock_coordinator, device_info):
    """Test that stop with a stop_command_address pulses the stop address."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        stop_command="db1,x1.0",
        stop_pulse_duration=0.1,
    )
    cover.hass = fake_hass
    mock_coordinator.data = {"cover:position:db1,b0": 42}

    await cover.async_stop_cover()

    # Should pulse stop address: True then False
    calls = mock_coordinator.write_batched.call_args_list
    assert len(calls) == 2
    assert calls[0].args == ("db1,x1.0", True)
    assert calls[1].args == ("db1,x1.0", False)


@pytest.mark.asyncio
async def test_position_cover_stop_with_stop_address_does_not_write_position(
    fake_hass, mock_coordinator, device_info
):
    """Test that stop with stop_command_address does NOT write position back."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        stop_command="db1,x1.0",
        stop_pulse_duration=0.1,
    )
    cover.hass = fake_hass
    mock_coordinator.data = {"cover:position:db1,b0": 42}

    await cover.async_stop_cover()

    # Should NOT have written position (42) to command address
    for call in mock_coordinator.write_batched.call_args_list:
        assert call.args[0] != "db1,b1", "Should not write to position command address"


@pytest.mark.asyncio
async def test_position_cover_stop_without_stop_address_fallback(
    fake_hass, mock_coordinator, device_info
):
    """Test that stop without stop_command_address falls back to writing current position."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {"cover:position:db1,b0": 55}

    await cover.async_stop_cover()

    # Should write current position (55) to command address
    mock_coordinator.write_batched.assert_called_with("db1,b1", 55)


@pytest.mark.asyncio
async def test_position_cover_extra_state_attributes_with_stop(
    fake_hass, mock_coordinator, device_info
):
    """Test extra state attributes include stop address info when configured."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        stop_command="db1,x1.0",
        stop_pulse_duration=1.5,
    )

    attrs = cover.extra_state_attributes
    assert attrs["s7_stop_command_address"] == "DB1,X1.0"
    assert attrs["stop_pulse_duration"] == "1.5 s"
    assert attrs["cover_type"] == "position"


@pytest.mark.asyncio
async def test_position_cover_extra_state_attributes_without_stop(
    fake_hass, mock_coordinator, device_info
):
    """Test extra state attributes do not include stop info when not configured."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
    )

    attrs = cover.extra_state_attributes
    assert "s7_stop_command_address" not in attrs
    assert "stop_pulse_duration" not in attrs


@pytest.mark.asyncio
async def test_position_cover_setup_with_stop_address(fake_hass, mock_coordinator, device_info):
    """Test position-based cover setup with stop command address."""
    from custom_components.s7plc.const import (
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_STOP_COMMAND_ADDRESS,
        CONF_STOP_PULSE_DURATION,
    )

    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_POSITION_STATE_ADDRESS: "db1,b0",
                CONF_POSITION_COMMAND_ADDRESS: "db1,b1",
                CONF_STOP_COMMAND_ADDRESS: "db1,x1.0",
                CONF_STOP_PULSE_DURATION: 2.0,
                CONF_NAME: "Test Position Cover",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1

    cover = entities[0]
    assert cover._stop_command_address == "db1,x1.0"
    assert cover._stop_pulse_duration == 2.0


# ============================================================================
# Real movement status (cover_status_address) Tests — S7PositionCover
# ============================================================================


def test_position_cover_status_unconfigured_is_never_opening_or_closing(
    fake_hass, mock_coordinator, device_info
):
    """Without cover_status_address, is_opening/is_closing stay False: a raw
    position alone can't tell HA whether the cover is actively moving."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator, "Test Cover", "test_id", device_info, "db1,b0", "db1,b1"
    )
    assert cover.is_opening is False
    assert cover.is_closing is False


def test_position_cover_status_opening_value_drives_is_opening(
    fake_hass, mock_coordinator, device_info
):
    """A matching 'opening' status value makes is_opening True."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 1}
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_position_cover_status_closing_value_drives_is_closing(
    fake_hass, mock_coordinator, device_info
):
    """A matching 'closing' status value makes is_closing True."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closing_values="2",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 2}
    assert cover.is_closing is True
    assert cover.is_opening is False


def test_position_cover_status_unmatched_value_forces_false(
    fake_hass, mock_coordinator, device_info
):
    """An unrecognized status value means neither opening nor closing."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_opening_values="1",
    )
    mock_coordinator.data = {"cover:status:db1,b10": 99}
    assert cover.is_opening is False
    assert cover.is_closing is False


def test_position_cover_status_does_not_affect_is_closed_when_unconfigured(
    fake_hass, mock_coordinator, device_info
):
    """Without cover_status_open_values/cover_status_closed_values
    configured, a status match of "opening"/"closing"/"stopped" leaves
    is_closed driven by the position value (position == 0), same as
    before this override existed."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closing_values="2",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 50,
        "cover:status:db1,b10": 2,  # "closing" per status
    }
    assert cover.is_closed is False  # driven by position, not status
    assert cover.is_closing is True  # driven by status, independent of position


def test_position_cover_status_closed_value_overrides_is_closed(
    fake_hass, mock_coordinator, device_info
):
    """A matching 'closed' status value makes is_closed True, even if the
    raw position value would say otherwise (e.g. a stale/unscaled reading)."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closed_values="1",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 50,  # would say "not closed" on its own
        "cover:status:db1,b10": 1,  # "closed" per status
    }
    assert cover.is_closed is True


def test_position_cover_status_open_value_overrides_is_closed(
    fake_hass, mock_coordinator, device_info
):
    """A matching 'open' status value makes is_closed False, even if the
    raw position value is 0."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_open_values="1",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 0,  # would say "closed" on its own
        "cover:status:db1,b10": 1,  # "open" per status
    }
    assert cover.is_closed is False


def test_position_cover_status_extra_state_attributes(
    fake_hass, mock_coordinator, device_info
):
    """Attributes expose the status address and configured value mapping
    when configured, matching climate's hvac_status attribute pattern."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_open_values="0",
        cover_status_closed_values="3",
        cover_status_opening_values="1",
        cover_status_closing_values="2",
    )
    attrs = cover.extra_state_attributes
    assert attrs["s7_cover_status_address"] == "DB1,B10"
    assert attrs["s7_cover_status_values"]["open"] == [0]
    assert attrs["s7_cover_status_values"]["closed"] == [3]
    assert attrs["s7_cover_status_values"]["opening"] == [1]
    assert attrs["s7_cover_status_values"]["closing"] == [2]


def test_position_cover_status_absent_from_attrs_when_unconfigured(
    fake_hass, mock_coordinator, device_info
):
    """No cover_status_* attributes appear when the address isn't set."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator, "Test Cover", "test_id", device_info, "db1,b0", "db1,b1"
    )
    attrs = cover.extra_state_attributes
    assert "s7_cover_status_address" not in attrs
    assert "s7_cover_status_values" not in attrs


@pytest.mark.asyncio
async def test_position_cover_setup_with_status_address(
    fake_hass, mock_coordinator, device_info
):
    """Setup registers cover_status_address as its own coordinator topic,
    alongside the position topic."""
    from custom_components.s7plc.const import (
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_COVER_STATUS_ADDRESS,
        CONF_COVER_STATUS_OPEN_VALUES,
        CONF_COVER_STATUS_CLOSED_VALUES,
        CONF_COVER_STATUS_OPENING_VALUES,
        CONF_COVER_STATUS_CLOSING_VALUES,
    )

    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_POSITION_STATE_ADDRESS: "db1,b0",
                CONF_POSITION_COMMAND_ADDRESS: "db1,b1",
                CONF_COVER_STATUS_ADDRESS: "db1,b10",
                CONF_COVER_STATUS_OPEN_VALUES: "0",
                CONF_COVER_STATUS_CLOSED_VALUES: "3",
                CONF_COVER_STATUS_OPENING_VALUES: "1",
                CONF_COVER_STATUS_CLOSING_VALUES: "2",
                CONF_NAME: "Test Position Cover",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    # Two add_item calls: one for the position topic, one for the status topic.
    assert mock_coordinator.add_item.call_count == 2
    entities = async_add_entities.call_args[0][0]
    cover = entities[0]
    assert cover._cover_status_address == "db1,b10"
    assert cover._cover_status_values["open"] == [0]
    assert cover._cover_status_values["closed"] == [3]
    assert cover._cover_status_values["opening"] == [1]
    assert cover._cover_status_values["closing"] == [2]


# ============================================================================
# Tilt support (S7PositionCover) Tests
# ============================================================================


def test_position_cover_tilt_unconfigured_no_features(fake_hass, mock_coordinator, device_info):
    """Without tilt_state_address, no tilt feature flags are advertised and
    current_cover_tilt_position is always None."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator, "Test Cover", "test_id", device_info, "db1,b0", "db1,b1"
    )

    assert not (cover._attr_supported_features & CoverEntityFeature.OPEN_TILT)
    assert not (cover._attr_supported_features & CoverEntityFeature.CLOSE_TILT)
    assert not (cover._attr_supported_features & CoverEntityFeature.SET_TILT_POSITION)
    assert not (cover._attr_supported_features & CoverEntityFeature.STOP_TILT)
    assert cover.current_cover_tilt_position is None


def test_position_cover_tilt_configured_features(fake_hass, mock_coordinator, device_info):
    """With tilt_state_address configured, tilt feature flags are added on
    top of the base position/stop features (which stay present)."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
    )

    features = cover._attr_supported_features
    for flag in (
        CoverEntityFeature.OPEN,
        CoverEntityFeature.CLOSE,
        CoverEntityFeature.SET_POSITION,
        CoverEntityFeature.STOP,
        CoverEntityFeature.OPEN_TILT,
        CoverEntityFeature.CLOSE_TILT,
        CoverEntityFeature.SET_TILT_POSITION,
        CoverEntityFeature.STOP_TILT,
    ):
        assert features & flag, f"{flag} missing"


def test_position_cover_current_tilt_position(fake_hass, mock_coordinator, device_info):
    """current_cover_tilt_position clamps to 0-100, mirroring position."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
    )

    mock_coordinator.data = {"cover:tilt:db1,b2": 50}
    assert cover.current_cover_tilt_position == 50

    mock_coordinator.data = {"cover:tilt:db1,b2": 150}
    assert cover.current_cover_tilt_position == 100

    mock_coordinator.data = {"cover:tilt:db1,b2": -10}
    assert cover.current_cover_tilt_position == 0

    mock_coordinator.data = {}
    assert cover.current_cover_tilt_position is None


def test_position_cover_tilt_invert(fake_hass, mock_coordinator, device_info):
    """invert_tilt flips the reported/written tilt value, mirroring
    invert_position."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
        invert_tilt=True,
    )
    cover.hass = fake_hass

    mock_coordinator.data = {"cover:tilt:db1,b2": 30}
    assert cover.current_cover_tilt_position == 70


@pytest.mark.asyncio
async def test_position_cover_open_close_tilt(fake_hass, mock_coordinator, device_info):
    """open/close_cover_tilt set tilt to 100/0."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}

    await cover.async_open_cover_tilt()
    mock_coordinator.write_batched.assert_called_with("db1,b3", 100)

    await cover.async_close_cover_tilt()
    mock_coordinator.write_batched.assert_called_with("db1,b3", 0)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_position_cover_tilt_command_falls_back_to_state_address(
    fake_hass, mock_coordinator, device_info
):
    """Without a separate tilt_command_address, writes go to
    tilt_state_address, mirroring position_command_address's fallback."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}

    await cover.async_set_cover_tilt_position(tilt_position=50)
    mock_coordinator.write_batched.assert_called_with("db1,b2", 50)


@pytest.mark.asyncio
async def test_position_cover_set_tilt_position_not_configured(
    fake_hass, mock_coordinator, device_info
):
    """Calling set_cover_tilt_position when tilt isn't configured logs an
    error and does not write anything (defensive guard)."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator, "Test Cover", "test_id", device_info, "db1,b0", "db1,b1"
    )
    cover.hass = fake_hass

    await cover.async_set_cover_tilt_position(tilt_position=50)
    mock_coordinator.write_batched.assert_not_called()


@pytest.mark.asyncio
async def test_position_cover_stop_tilt_with_stop_address(
    fake_hass, mock_coordinator, device_info
):
    """stop_cover_tilt pulses stop_command_address, the same physical stop
    line used for position stop."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        stop_command="db1,x1.0",
        stop_pulse_duration=0.01,
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {}

    await cover.async_stop_cover_tilt()

    calls = mock_coordinator.write_batched.call_args_list
    assert calls[0].args == ("db1,x1.0", True)
    assert calls[1].args == ("db1,x1.0", False)


@pytest.mark.asyncio
async def test_position_cover_stop_tilt_without_stop_address(
    fake_hass, mock_coordinator, device_info
):
    """Without a stop address, stop_cover_tilt falls back to writing the
    current tilt position back, same trick async_stop_cover uses."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
    )
    cover.hass = fake_hass
    mock_coordinator.data = {"cover:tilt:db1,b2": 42}

    await cover.async_stop_cover_tilt()
    mock_coordinator.write_batched.assert_called_with("db1,b3", 42)


def test_position_cover_tilt_extra_state_attributes(fake_hass, mock_coordinator, device_info):
    """Tilt addresses appear in extra_state_attributes when configured."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        tilt_state_address="db1,b2",
        tilt_command_address="db1,b3",
    )

    attrs = cover.extra_state_attributes
    assert attrs["s7_tilt_state_address"] == "DB1,B2"
    assert attrs["s7_tilt_command_address"] == "DB1,B3"


def test_position_cover_tilt_absent_from_attrs_when_unconfigured(
    fake_hass, mock_coordinator, device_info
):
    """No tilt attributes appear when tilt isn't configured."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator, "Test Cover", "test_id", device_info, "db1,b0", "db1,b1"
    )

    attrs = cover.extra_state_attributes
    assert "s7_tilt_state_address" not in attrs
    assert "s7_tilt_command_address" not in attrs


@pytest.mark.asyncio
async def test_position_cover_setup_with_tilt(fake_hass, mock_coordinator, device_info):
    """async_setup_entry wires tilt_state_address/tilt_command_address and
    invert_tilt through to the entity."""
    from custom_components.s7plc.const import (
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_TILT_STATE_ADDRESS,
        CONF_TILT_COMMAND_ADDRESS,
        CONF_INVERT_TILT,
    )

    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_POSITION_STATE_ADDRESS: "db1,b0",
                CONF_POSITION_COMMAND_ADDRESS: "db1,b1",
                CONF_TILT_STATE_ADDRESS: "db1,b2",
                CONF_TILT_COMMAND_ADDRESS: "db1,b3",
                CONF_INVERT_TILT: True,
                CONF_NAME: "Test Position Cover",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1

    cover = entities[0]
    assert cover._tilt_state_address == "db1,b2"
    assert cover._tilt_command_address == "db1,b3"
    assert cover._invert_tilt is True
    assert cover._attr_supported_features & CoverEntityFeature.SET_TILT_POSITION
