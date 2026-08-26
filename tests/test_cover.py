"""Tests for cover entities."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_NAME
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.cover import (S7Cover, _traditional_feedback_mode, async_setup_entry)
from custom_components.s7plc.const import (
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVER_POSITION_FEEDBACK,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_UID,
    CONF_USE_STATE_TOPICS,
    DEFAULT_OPERATE_TIME,
)
from conftest import DummyCoordinator


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({CONF_COVER_POSITION_FEEDBACK: mode}, mode)
        for mode in ("timed", "opening", "closing", "both", "status")
    ]
    + [
        ({CONF_USE_STATE_TOPICS: False, CONF_OPENING_STATE_ADDRESS: "open"}, "timed"),
        ({CONF_USE_STATE_TOPICS: True, CONF_OPENING_STATE_ADDRESS: "open"}, "opening"),
        ({CONF_USE_STATE_TOPICS: True, CONF_CLOSING_STATE_ADDRESS: "closed"}, "closing"),
        ({CONF_USE_STATE_TOPICS: True, CONF_OPENING_STATE_ADDRESS: "open", CONF_CLOSING_STATE_ADDRESS: "closed"}, "both"),
        ({CONF_USE_STATE_TOPICS: True}, "timed"),
        ({CONF_OPENING_STATE_ADDRESS: "open", CONF_COVER_STATUS_ADDRESS: "word"}, "opening"),
        ({CONF_COVER_STATUS_ADDRESS: "word"}, "timed"),
    ],
)
def test_traditional_feedback_mode_legacy_and_explicit_precedence(item, expected):
    assert _traditional_feedback_mode(item) == expected


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
        toggle_mode: bool = False,
        toggle_pulse_duration: float = 0.5,
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
            toggle_mode=toggle_mode,
            toggle_pulse_duration=toggle_pulse_duration,
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


def test_extra_state_attributes_omits_toggle_mode_when_not_toggle(cover_factory):
    """PR #117 review round 7, point 8: a plain traditional cover's state
    attributes shouldn't gain a new toggle_mode:false attribute just
    because the feature exists - only expose it when actually enabled."""
    cover = cover_factory()

    attrs = cover.extra_state_attributes
    assert "toggle_mode" not in attrs
    assert "s7_toggle_last_direction" not in attrs


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


def test_explicit_endstop_position_and_status_word_movement(
    cover_factory, mock_coordinator
):
    """The end-stop remains positional while the word reports movement."""
    cover = cover_factory(
        opened_state="db1,x1.0",
        opened_topic="cover:opened:db1,x1.0",
        use_state_topics=True,
        feedback_mode="opening",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_open_values="1",
        cover_status_opening_values="2",
    )
    mock_coordinator.data = {
        "cover:opened:db1,x1.0": False,
        "cover:status:db1,b10": 1,
    }
    assert cover.is_closed is None
    assert cover.is_opening is False

    mock_coordinator.data["cover:status:db1,b10"] = 2
    assert cover.is_closed is None
    assert cover.is_opening is True

    mock_coordinator.data["cover:opened:db1,x1.0"] = True
    assert cover.is_closed is False


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


@pytest.mark.asyncio
async def test_async_setup_entry_explicit_endstop_keeps_status_movement(
    fake_hass, mock_coordinator, device_info
):
    """An explicit end-stop mode still wires the movement status word."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                "cover_position_feedback": "opening",
                "opening_state_address": "db1,x1.0",
                "cover_status_address": "db1,b10",
                "cover_status_opening_values": "2",
                CONF_NAME: "Hybrid Cover",
                CONF_UID: "uid-hybrid",
            }
        ]
    }
    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    cover = async_add_entities.call_args[0][0][0]
    assert cover._feedback_mode == "opening"
    assert cover._cover_status_address == "db1,b10"
    assert cover._cover_status_values["opening"] == [2]
    assert mock_coordinator.add_item.call_count == 2


@pytest.mark.asyncio
async def test_async_setup_entry_position_status_with_movement_bits(
    fake_hass, mock_coordinator, device_info
):
    """Integration-level regression for PR #117 review round 3, point 1:
    position feedback = status word (open/closed only) and movement
    feedback = boolean bits must both survive the real async_setup_entry()
    path, not just direct S7Cover construction - the movement-bit addresses
    used to be silently discarded there whenever feedback_mode=="status"."""
    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_OPEN_COMMAND_ADDRESS: "db1,x0.0",
                CONF_CLOSE_COMMAND_ADDRESS: "db1,x0.1",
                "toggle_mode": True,
                "cover_position_feedback": "status",
                CONF_COVER_STATUS_ADDRESS: "db1,b10",
                "cover_status_open_values": "0",
                "cover_status_closed_values": "1",
                CONF_COVER_OPENING_ADDRESS: "db1,x2.0",
                CONF_COVER_CLOSING_ADDRESS: "db1,x2.1",
                CONF_NAME: "Mixed Feedback Cover",
                CONF_UID: "uid-mixed",
            }
        ]
    }
    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")
        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    cover = async_add_entities.call_args[0][0][0]
    assert cover._feedback_mode == "status"
    assert cover._cover_status_address == "db1,b10"
    assert cover._cover_opening_address == "db1,x2.0"
    assert cover._cover_closing_address == "db1,x2.1"
    add_item_topics = {c.args[0] for c in mock_coordinator.add_item.call_args_list}
    assert "cover:status:db1,b10" in add_item_topics
    assert "cover:opening:db1,x2.0" in add_item_topics
    assert "cover:closing:db1,x2.1" in add_item_topics


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
        position_feedback="status",
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
        position_feedback="status",
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
# End-stop/movement feedback parity (S7PositionCover) Tests
# ============================================================================


def test_position_cover_is_closed_uses_end_stop_bits_opening_mode(
    fake_hass, mock_coordinator, device_info
):
    """position_feedback="opening": the opened end-stop bit is authoritative
    for is_closed, even when the raw position disagrees."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        position_feedback="opening",
        opening_state_address="db1,x1.0",
        opening_topic="cover:opened:db1,x1.0",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 0,  # would say "closed" on its own
        "cover:opened:db1,x1.0": True,
    }
    assert cover.is_closed is False


def test_position_cover_is_closed_uses_end_stop_bits_both_mode(
    fake_hass, mock_coordinator, device_info
):
    """position_feedback="both": the closed end-stop bit makes is_closed
    True, independent of the raw position value."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        position_feedback="both",
        opening_state_address="db1,x1.0",
        opening_topic="cover:opened:db1,x1.0",
        closing_state_address="db1,x1.1",
        closing_topic="cover:closed:db1,x1.1",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 50,  # would say "not closed" on its own
        "cover:opened:db1,x1.0": False,
        "cover:closed:db1,x1.1": True,
    }
    assert cover.is_closed is True


def test_position_cover_is_closed_ignores_status_when_feedback_timed(
    fake_hass, mock_coordinator, device_info
):
    """A configured cover_status_address is not consulted for is_closed
    unless position_feedback selects it - "timed" always falls back to the
    raw position value."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        position_feedback="timed",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closed_values="1",
    )
    mock_coordinator.data = {
        "cover:position:db1,b0": 50,  # not closed per raw position
        "cover:status:db1,b10": 1,  # would say "closed" per status
    }
    assert cover.is_closed is False


def test_position_cover_movement_bits_drive_is_opening_is_closing(
    fake_hass, mock_coordinator, device_info
):
    """cover_opening_address/cover_closing_address drive is_opening/
    is_closing independently of position_feedback, same as S7Cover."""
    from custom_components.s7plc.cover import S7PositionCover

    cover = S7PositionCover(
        mock_coordinator,
        "Test Cover",
        "test_id",
        device_info,
        "db1,b0",
        "db1,b1",
        position_feedback="status",
        cover_status_topic="cover:status:db1,b10",
        cover_status_address="db1,b10",
        cover_status_closed_values="1",
        cover_opening_address="db1,x2.0",
        cover_opening_topic="cover:opening:db1,x2.0",
        cover_closing_address="db1,x2.1",
        cover_closing_topic="cover:closing:db1,x2.1",
    )
    mock_coordinator.data = {
        "cover:status:db1,b10": 0,  # unmatched - not "closed"
        "cover:opening:db1,x2.0": True,
        "cover:closing:db1,x2.1": False,
    }
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_position_cover_movement_status_wins_over_bits(
    fake_hass, mock_coordinator, device_info
):
    """When cover_status_address resolves the movement, it takes priority
    over the boolean bits - same precedence as S7Cover."""
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
        cover_opening_address="db1,x2.0",
        cover_opening_topic="cover:opening:db1,x2.0",
    )
    mock_coordinator.data = {
        "cover:status:db1,b10": 2,  # "closing" per status
        "cover:opening:db1,x2.0": True,  # bits disagree
    }
    assert cover.is_closing is True
    assert cover.is_opening is False


@pytest.mark.asyncio
async def test_position_cover_setup_with_end_stop_and_movement_feedback(
    fake_hass, mock_coordinator, device_info
):
    """Setup wires opening/closing_state_address and the movement bits as
    their own coordinator topics, alongside the position topic, and passes
    position_feedback through to the entity."""
    from custom_components.s7plc.const import (
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_OPENING_STATE_ADDRESS,
        CONF_CLOSING_STATE_ADDRESS,
        CONF_COVER_OPENING_ADDRESS,
        CONF_COVER_CLOSING_ADDRESS,
        CONF_COVER_STOPPED_ADDRESS,
        CONF_COVER_POSITION_FEEDBACK,
    )

    config_entry = MagicMock()
    config_entry.options = {
        CONF_COVERS: [
            {
                CONF_POSITION_STATE_ADDRESS: "db1,b0",
                CONF_POSITION_COMMAND_ADDRESS: "db1,b1",
                CONF_COVER_POSITION_FEEDBACK: "both",
                CONF_OPENING_STATE_ADDRESS: "db1,x1.0",
                CONF_CLOSING_STATE_ADDRESS: "db1,x1.1",
                CONF_COVER_OPENING_ADDRESS: "db1,x2.0",
                CONF_COVER_CLOSING_ADDRESS: "db1,x2.1",
                CONF_COVER_STOPPED_ADDRESS: "db1,x2.2",
                CONF_NAME: "Test Position Cover",
                CONF_UID: "uid-1",
            }
        ]
    }

    async_add_entities = MagicMock()

    with patch("custom_components.s7plc.cover.get_coordinator_and_device_info") as mock_get:
        mock_get.return_value = (mock_coordinator, device_info, "test_device")

        await async_setup_entry(fake_hass, config_entry, async_add_entities)

    # position + opening + closing + 3 movement bits = 6 topics.
    assert mock_coordinator.add_item.call_count == 6
    entities = async_add_entities.call_args[0][0]
    cover = entities[0]
    assert cover._position_feedback == "both"
    assert cover._opening_state_address == "db1,x1.0"
    assert cover._closing_state_address == "db1,x1.1"
    assert cover._cover_opening_address == "db1,x2.0"
    assert cover._cover_closing_address == "db1,x2.1"
    assert cover._cover_stopped_address == "db1,x2.2"


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


def test_legacy_hybrid_uses_endstop_position_and_status_word_movement(
    cover_factory, mock_coordinator
):
    """The legacy status word complements rather than replaces an end-stop."""
    cover = cover_factory(
        opened_state="DB1,X1.0",
        opened_topic="cover:opened:DB1,X1.0",
        use_state_topics=True,
        feedback_mode="opening",
        cover_status_address="DB1,B10",
        cover_status_topic="cover:status:DB1,B10",
        cover_status_opening_values="2",
    )
    mock_coordinator.data = {
        "cover:opened:DB1,X1.0": True,
        "cover:status:DB1,B10": 2,
    }
    assert cover.is_closed is False
    assert cover.is_opening is True

    mock_coordinator.data["cover:opened:DB1,X1.0"] = False
    assert cover.is_closed is None


def test_explicit_status_is_authoritative_without_endstop_fallback(
    cover_factory, mock_coordinator
):
    cover = cover_factory(
        opened_state="DB1,X1.0",
        opened_topic="cover:opened:DB1,X1.0",
        use_state_topics=False,
        feedback_mode="status",
        cover_status_address="DB1,B10",
        cover_status_topic="cover:status:DB1,B10",
        cover_status_open_values="1",
    )
    mock_coordinator.data = {
        "cover:opened:DB1,X1.0": True,
        "cover:status:DB1,B10": 99,
    }
    assert cover.is_closed is None
    assert cover.is_opening is False


# ============================================================================
# toggle_mode Tests
# ============================================================================


def _status_cover(cover_factory, **extra):
    return cover_factory(
        toggle_mode=True,
        close_command=None,
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_open_values="0",
        cover_status_closed_values="1",
        cover_status_opening_values="2",
        cover_status_closing_values="3",
        cover_status_stopped_values="4",
        **extra,
    )


def test_toggle_state_reads_every_value_from_cover_status_address(
    cover_factory, mock_coordinator
):
    cover = _status_cover(cover_factory)
    for raw, expected in (
        (0, "open"),
        (1, "closed"),
        (2, "opening"),
        (3, "closing"),
        (4, "stopped"),
    ):
        mock_coordinator.data = {"cover:status:db1,b10": raw}
        assert cover._toggle_state() == expected


def test_toggle_state_infers_stopped_without_a_dedicated_signal(
    cover_factory, mock_coordinator
):
    """Boolean feedback (no cover_status_address): if a gate reports
    neither opening, closing, nor a conclusive open/closed position, it
    must be stopped mid-travel - inferred, not read directly."""
    cover = cover_factory(
        toggle_mode=True,
        close_command=None,
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_closing_address="db1,b2",
        cover_closing_topic="cover:closing:db1,b2",
        opened_state="db1,b3",
        closed_state="db1,b4",
        opened_topic="cover:opened:db1,b3",
        closed_topic="cover:closed:db1,b4",
        use_state_topics=True,
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": False,
        "cover:closing:db1,b2": False,
        "cover:opened:db1,b3": False,
        "cover:closed:db1,b4": False,
    }
    assert cover._toggle_state() == "stopped"


def test_toggle_mode_supported_features_is_full(cover_factory):
    """Toggle mode advertises the full OPEN|CLOSE|STOP set, same as a
    normal cover - HA's service layer checks supported_features before
    ever calling our entity methods, so anything less would make it
    silently reject close_cover/stop_cover/toggle calls."""
    cover = _status_cover(cover_factory)
    assert cover._attr_supported_features == (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )


def test_toggle_mode_extra_state_attributes_exposes_toggle_mode(
    cover_factory, mock_coordinator
):
    """Mirror of test_extra_state_attributes_omits_toggle_mode_when_not_toggle:
    a real toggle_mode cover does get the attribute, and its value."""
    cover = _status_cover(cover_factory)
    attrs = cover.extra_state_attributes
    assert attrs["toggle_mode"] is True
    assert attrs["s7_toggle_last_direction"] == "unknown"


@pytest.mark.asyncio
async def test_toggle_open_noop_when_already_open(cover_factory, mock_coordinator, monkeypatch):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 0}  # open

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_open_noop_when_already_opening(cover_factory, mock_coordinator, monkeypatch):
    """The exact case the maintainer flagged: calling open_cover again on
    an already-opening cover must never stop it just because the physical
    relay uses the same input."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction == "opening"


@pytest.mark.asyncio
async def test_toggle_open_from_closed_presses_and_sets_opening(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 1}  # closed

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    mock_coordinator.write_batched.assert_any_call("db1,x0.0", False)
    assert cover._last_toggle_direction == "opening"


@pytest.mark.asyncio
async def test_toggle_open_while_closing_halts_without_claiming_direction(
    cover_factory, mock_coordinator, monkeypatch
):
    """A single press from "closing" only reaches "stopped", not "opening"
    - halt the wrong-direction move but don't claim a direction we haven't
    actually reached; real feedback sets it next."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    assert cover._last_toggle_direction == "closing"


@pytest.mark.asyncio
async def test_toggle_open_from_stopped_after_closing_reverses_to_opening(
    cover_factory, mock_coordinator, monkeypatch
):
    """Stopped mid-close: the next press reverses to opening, exactly like
    the physical step-by-step relay - and that's the goal, so press."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    assert cover._last_toggle_direction == "opening"


@pytest.mark.asyncio
async def test_toggle_open_from_stopped_after_opening_refuses(
    cover_factory, mock_coordinator, monkeypatch
):
    """Stopped mid-open: the next press would reverse to closing - the
    wrong way. Refuse rather than move the cover further shut to (much
    later) reach open."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction == "opening"


@pytest.mark.asyncio
async def test_toggle_open_from_stopped_unknown_direction_refuses(
    cover_factory, mock_coordinator, monkeypatch
):
    """Fresh Home Assistant restart, cover already stopped mid-travel:
    direction has never been observed this session, so which way a press
    goes is unknown. Unlike a single undifferentiated press-anything
    handler, open_cover has a specific goal now - pressing blindly could
    visibly move the cover the wrong way first, so refuse and wait for
    feedback instead."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    assert cover._last_toggle_direction is None
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction is None


@pytest.mark.asyncio
async def test_toggle_close_noop_when_already_closed(cover_factory, mock_coordinator, monkeypatch):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 1}  # closed

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_close_noop_when_already_closing(cover_factory, mock_coordinator, monkeypatch):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction == "closing"


@pytest.mark.asyncio
async def test_toggle_close_from_open_presses_and_sets_closing(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 0}  # open

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    assert cover._last_toggle_direction == "closing"


@pytest.mark.asyncio
async def test_toggle_close_while_opening_halts_without_claiming_direction(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    assert cover._last_toggle_direction == "opening"


@pytest.mark.asyncio
async def test_toggle_close_from_stopped_after_opening_reverses_to_closing(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)
    assert cover._last_toggle_direction == "closing"


@pytest.mark.asyncio
async def test_toggle_close_from_stopped_after_closing_refuses(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    await cover.async_close_cover()

    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction == "closing"


@pytest.mark.asyncio
async def test_toggle_stop_presses_while_moving(cover_factory, mock_coordinator, monkeypatch):
    """Each case starts from a fresh cover: once a stop press has been
    issued, self._toggle_awaiting_halt_confirmation stays set until real
    "stopped" feedback confirms it (see
    test_toggle_stop_ignores_stale_pre_halt_feedback), so reusing the same
    instance across both directions without a real confirmation in
    between would incorrectly suppress the second press."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())

    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening
    await cover.async_stop_cover()
    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)

    cover = _status_cover(cover_factory)
    mock_coordinator.write_batched.reset_mock()
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing
    await cover.async_stop_cover()
    mock_coordinator.write_batched.assert_any_call("db1,x0.0", True)


@pytest.mark.asyncio
async def test_toggle_stop_noop_when_not_moving(cover_factory, mock_coordinator, monkeypatch):
    """Stopping is always safe/idempotent, but there's nothing to press
    when the cover isn't moving - open/closed/stopped are all no-ops."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)

    for raw in (0, 1, 4):  # open, closed, stopped
        mock_coordinator.data = {"cover:status:db1,b10": raw}
        await cover.async_stop_cover()
        mock_coordinator.write_batched.assert_not_called()


def test_toggle_direction_memory_persists_through_a_stop(cover_factory, mock_coordinator):
    """The last real direction of travel must survive the transition to
    "stopped" - it's the only way to know which way the next press goes."""
    cover = _status_cover(cover_factory)

    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening
    cover._handle_coordinator_update()
    assert cover._last_toggle_direction == "opening"

    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped
    cover._handle_coordinator_update()
    assert cover._last_toggle_direction == "opening"  # unchanged, not cleared


@pytest.mark.asyncio
async def test_pulse_toggle_writes_true_then_false_and_refreshes(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)

    await cover._pulse_toggle()

    calls = [c.args for c in mock_coordinator.write_batched.call_args_list]
    assert ("db1,x0.0", True) in calls
    assert ("db1,x0.0", False) in calls
    assert calls.index(("db1,x0.0", True)) < calls.index(("db1,x0.0", False))
    mock_coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_pulse_toggle_uses_configured_duration(
    cover_factory, mock_coordinator, monkeypatch
):
    """_pulse_toggle sleeps for the entity's own toggle_pulse_duration, not
    the shared DEFAULT_PULSE_DURATION constant."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", sleep_mock)
    cover = _status_cover(cover_factory, toggle_pulse_duration=1.5)

    await cover._pulse_toggle()

    sleep_mock.assert_awaited_once_with(1.5)


# ---------------------------------------------------------------------------
# "unknown" vs "stopped" (maintainer review point 2)
# ---------------------------------------------------------------------------


def test_toggle_state_is_unknown_for_unmatched_status_value(
    cover_factory, mock_coordinator
):
    """An unmapped/unmatched status value must not be silently treated as
    a genuine "stopped" reading - toggle_mode's command decisions depend
    entirely on knowing the real state."""
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 99}  # not in any mapping

    assert cover._toggle_state() == "unknown"


def test_toggle_state_is_unknown_before_first_feedback(cover_factory, mock_coordinator):
    """Boolean feedback with no data at all yet (e.g. right after a Home
    Assistant restart, before the coordinator's first refresh) must be
    "unknown", not "stopped"."""
    cover = cover_factory(
        toggle_mode=True,
        close_command=None,
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_closing_address="db1,b2",
        cover_closing_topic="cover:closing:db1,b2",
        opened_state="db1,b3",
        closed_state="db1,b4",
        opened_topic="cover:opened:db1,b3",
        closed_topic="cover:closed:db1,b4",
        use_state_topics=True,
    )
    mock_coordinator.data = {}

    assert cover._toggle_state() == "unknown"


def test_toggle_state_still_infers_stopped_with_real_boolean_feedback(
    cover_factory, mock_coordinator
):
    """Unchanged from before: real data (all gates reporting False, not
    unset) still means a genuine mid-travel stop."""
    cover = cover_factory(
        toggle_mode=True,
        close_command=None,
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_closing_address="db1,b2",
        cover_closing_topic="cover:closing:db1,b2",
        opened_state="db1,b3",
        closed_state="db1,b4",
        opened_topic="cover:opened:db1,b3",
        closed_topic="cover:closed:db1,b4",
        use_state_topics=True,
    )
    mock_coordinator.data = {
        "cover:opening:db1,b1": False,
        "cover:closing:db1,b2": False,
        "cover:opened:db1,b3": False,
        "cover:closed:db1,b4": False,
    }

    assert cover._toggle_state() == "stopped"


@pytest.mark.asyncio
async def test_toggle_open_refuses_when_state_is_unknown(
    cover_factory, mock_coordinator, monkeypatch
):
    """Unlike a stopped-but-direction-ambiguous refusal, this is "no real
    feedback at all yet" - must still refuse rather than press blindly."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    mock_coordinator.data = {"cover:status:db1,b10": 99}  # unmatched

    await cover.async_open_cover()

    mock_coordinator.write_batched.assert_not_called()


# ---------------------------------------------------------------------------
# open/close reach the requested target automatically (maintainer review
# point 1): halting a wrong-direction move now continues toward the goal
# once real "stopped" feedback confirms the halt succeeded, instead of
# requiring the caller to issue a second service call.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_open_while_closing_defers_continuation_until_real_stop(
    cover_factory, mock_coordinator, monkeypatch
):
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()

    # Only the halt pulse fired - real feedback hasn't confirmed the stop
    # yet (the mock data is unchanged), so the continuation is deferred.
    calls = [c.args for c in mock_coordinator.write_batched.call_args_list]
    assert calls.count(("db1,x0.0", True)) == 1
    assert cover._toggle_pending_goal == "open"
    assert cover._last_toggle_direction == "closing"  # not yet reversed


@pytest.mark.asyncio
async def test_toggle_open_while_closing_completes_immediately_when_feedback_is_instant(
    cover_factory, mock_coordinator, monkeypatch
):
    """If real "stopped" feedback is already visible right after the halt
    pulse completes, the second pulse toward the goal fires within the
    same service call - no need to wait for another coordinator update."""

    async def instant_feedback(_duration):
        mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped

    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", instant_feedback)
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()

    calls = [c.args for c in mock_coordinator.write_batched.call_args_list]
    assert calls.count(("db1,x0.0", True)) == 2  # halt pulse + continuation pulse
    assert cover._last_toggle_direction == "opening"
    assert cover._toggle_pending_goal is None


@pytest.mark.asyncio
async def test_toggle_open_while_closing_completes_via_coordinator_update(
    cover_factory, mock_coordinator, monkeypatch
):
    """The deferred case: a later, independent coordinator update that
    finally reports real "stopped" feedback triggers the continuation
    pulse automatically, without a second explicit service call."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()
    assert cover._toggle_pending_goal == "open"

    tasks: list = []
    monkeypatch.setattr(cover.hass, "async_create_task", tasks.append)
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # now genuinely stopped
    cover._handle_coordinator_update()

    assert len(tasks) == 1
    await tasks[0]

    calls = [c.args for c in mock_coordinator.write_batched.call_args_list]
    assert calls.count(("db1,x0.0", True)) == 2
    assert cover._last_toggle_direction == "opening"
    assert cover._toggle_pending_goal is None


@pytest.mark.asyncio
async def test_toggle_stop_cancels_pending_continuation(
    cover_factory, mock_coordinator, monkeypatch
):
    """An explicit stop_cover call cancels any automatic continuation -
    the user asking to stop means the cover shouldn't keep moving toward
    a previously requested target."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()
    assert cover._toggle_pending_goal == "open"

    mock_coordinator.write_batched.reset_mock()
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # already stopped
    await cover.async_stop_cover()

    assert cover._toggle_pending_goal is None
    mock_coordinator.write_batched.assert_not_called()  # nothing moving - no-op


# ---------------------------------------------------------------------------
# PR #117 review round 2: a pending continuation must always represent the
# latest requested target, stop_cover must never act on stale pre-halt
# feedback, and _toggle_state() must compose independently selected
# position/movement feedback sources.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_new_explicit_command_cancels_stale_pending_goal(
    cover_factory, mock_coordinator, monkeypatch
):
    """opening -> close_cover (halts, queues a pending "close" continuation
    that *would* succeed on confirmation - reversing from an opening-halt
    correctly reaches "closing" - and starts awaiting real halt
    confirmation) -> open_cover, before fresh "stopped" feedback arrives.
    Movement feedback can't be trusted yet (still stale pre-halt data), so
    open_cover must not make a physical decision from it - it just
    registers itself as the new latest desired target, superseding
    "close". Once real "stopped" feedback finally arrives, the
    continuation must evaluate against "open" (the caller's latest
    request) - which reversing from an opening-halt can *not* reach, so it
    correctly refuses rather than pressing. If the stale "close" goal had
    survived instead, this same confirmation would have pressed - the
    absence of a press is exactly what proves the supersession worked."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening

    await cover.async_close_cover()
    assert cover._toggle_pending_goal == "close"
    assert cover._toggle_awaiting_halt_confirmation is True

    mock_coordinator.write_batched.reset_mock()
    await cover.async_open_cover()  # still stale "opening" data

    assert cover._toggle_pending_goal == "open"  # latest request wins
    mock_coordinator.write_batched.assert_not_called()  # no decision on stale data

    # Real "stopped" feedback now arrives - must evaluate against "open",
    # the latest request, not the superseded (and now reachable) "close".
    tasks: list = []
    monkeypatch.setattr(cover.hass, "async_create_task", tasks.append)
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped
    cover._handle_coordinator_update()

    assert len(tasks) == 1
    await tasks[0]
    mock_coordinator.write_batched.assert_not_called()  # "open" unreachable - refuses
    assert cover._toggle_pending_goal is None
    assert cover._last_toggle_direction == "opening"  # unchanged


@pytest.mark.asyncio
async def test_toggle_stop_ignores_stale_pre_halt_feedback(
    cover_factory, mock_coordinator, monkeypatch
):
    """closing -> open_cover halts (queues a pending continuation) ->
    stop_cover, before fresh feedback confirms the halt. The coordinator
    still reports the stale pre-halt "closing" value, but a pulse was
    already sent - pressing again on top of stale data could resume the
    movement the halt just stopped, so stop_cover must not press."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()
    assert cover._toggle_pending_goal == "open"

    mock_coordinator.write_batched.reset_mock()
    await cover.async_stop_cover()  # data still stale "closing"

    assert cover._toggle_pending_goal is None
    mock_coordinator.write_batched.assert_not_called()


def test_toggle_state_composes_status_movement_with_endstop_position(
    cover_factory, mock_coordinator
):
    """Position feedback = end-stops, movement feedback = status word
    (mapped only for opening/closing/stopped, not open/closed) - the two
    are independently selectable, so the status word's motion reading
    must be honored even though it isn't the position source."""
    cover = cover_factory(
        toggle_mode=True,
        close_command=None,
        feedback_mode="both",
        use_state_topics=True,
        opened_state="db1,b3",
        closed_state="db1,b4",
        opened_topic="cover:opened:db1,b3",
        closed_topic="cover:closed:db1,b4",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_opening_values="2",
        cover_status_closing_values="3",
        cover_status_stopped_values="4",
    )
    # Moving (per status word); end-stops both false (in transit).
    mock_coordinator.data = {
        "cover:status:db1,b10": 2,
        "cover:opened:db1,b3": False,
        "cover:closed:db1,b4": False,
    }
    assert cover._toggle_state() == "opening"

    # Settled open (per end-stop); status word is unmapped/idle at rest.
    mock_coordinator.data = {
        "cover:status:db1,b10": 0,  # not in any configured mapping
        "cover:opened:db1,b3": True,
        "cover:closed:db1,b4": False,
    }
    assert cover._toggle_state() == "open"


def test_toggle_state_composes_status_position_with_bits_movement(
    cover_factory, mock_coordinator
):
    """The inverse combination: position feedback = status word (mapped
    only for open/closed), movement feedback = boolean bits. The bits'
    motion reading must be honored even though the status word is the
    position source, not the movement source."""
    cover = cover_factory(
        toggle_mode=True,
        close_command=None,
        feedback_mode="status",
        cover_status_address="db1,b10",
        cover_status_topic="cover:status:db1,b10",
        cover_status_open_values="0",
        cover_status_closed_values="1",
        cover_opening_address="db1,b1",
        cover_opening_topic="cover:opening:db1,b1",
        cover_closing_address="db1,b2",
        cover_closing_topic="cover:closing:db1,b2",
    )
    # Moving (per bits); status word idle/unmapped mid-travel.
    mock_coordinator.data = {
        "cover:status:db1,b10": 99,
        "cover:opening:db1,b1": True,
        "cover:closing:db1,b2": False,
    }
    assert cover._toggle_state() == "opening"

    # Settled closed (per status word); bits both false (not moving).
    mock_coordinator.data = {
        "cover:status:db1,b10": 1,
        "cover:opening:db1,b1": False,
        "cover:closing:db1,b2": False,
    }
    assert cover._toggle_state() == "closed"


@pytest.mark.asyncio
async def test_toggle_scheduled_continuation_aborts_if_superseded_before_it_runs(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 3, point 4: closes the race window between
    _toggle_pending_goal being cleared (to schedule the continuation task)
    and that task actually acquiring the lock and pressing. If a newer
    explicit command (here stop_cover) runs to completion in that window -
    finding no pending goal to cancel, since it was already consumed - the
    stale scheduled continuation must still notice it has been superseded
    once it finally runs, and must not press."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    await cover.async_open_cover()  # halts, queues pending continuation "open"
    assert cover._toggle_pending_goal == "open"

    # Real "stopped" feedback arrives - _handle_coordinator_update clears
    # the pending goal and schedules the continuation, but capture the
    # scheduled coroutine instead of letting it run yet (simulating the
    # race: the task exists but hasn't acquired the lock).
    tasks: list = []
    monkeypatch.setattr(cover.hass, "async_create_task", tasks.append)
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # now genuinely stopped
    cover._handle_coordinator_update()
    assert len(tasks) == 1
    assert cover._toggle_pending_goal is None  # already consumed

    # Before the scheduled continuation runs, a newer explicit command
    # arrives and completes - it can't see the (already-cleared) pending
    # goal, but it does bump the generation counter.
    mock_coordinator.write_batched.reset_mock()
    await cover.async_stop_cover()
    mock_coordinator.write_batched.assert_not_called()  # already stopped

    # Now let the stale scheduled continuation actually run - it must
    # detect it was superseded and press nothing.
    await tasks[0]
    mock_coordinator.write_batched.assert_not_called()
    assert cover._last_toggle_direction == "closing"  # unchanged, not "opening"


@pytest.mark.asyncio
async def test_toggle_immediate_continuation_aborts_if_superseded_during_pulse(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 4, point 2: a newer explicit command can arrive
    (and start waiting on self._toggle_lock, having already bumped the
    generation counter) while an earlier command's own halt pulse is still
    in flight - awaiting asyncio.sleep inside _pulse_toggle. Once that
    pulse completes and real feedback shows "stopped", the earlier
    command's *immediate* recursive continuation (inside _toggle_step,
    not the deferred task from _handle_coordinator_update) must notice the
    generation changed and must not press toward its own now-stale goal,
    even though it never released self._toggle_lock in between."""
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    async def fake_sleep(_duration):
        # While this pulse is "in flight", real feedback confirms the halt
        # succeeded, and a newer explicit command bumps the generation
        # counter - exactly what the real async_stop_cover does as its
        # first action, before it even tries to acquire the lock that
        # open_cover currently holds.
        mock_coordinator.data = {"cover:status:db1,b10": 4}  # now stopped
        cover._toggle_command_generation += 1

    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", fake_sleep)

    await cover.async_open_cover()

    calls = [c.args for c in mock_coordinator.write_batched.call_args_list]
    assert calls.count(("db1,x0.0", True)) == 1  # only the halt pulse
    assert cover._last_toggle_direction == "closing"  # unchanged, not "opening"
    assert cover._toggle_pending_goal is None  # no stale deferred goal either


@pytest.mark.asyncio
async def test_toggle_stop_after_halt_confirmation_still_pending_sends_no_second_pulse(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 5 - the exact sequence from review:

    closing -> open_cover starts a halt pulse -> stop_cover arrives
    (bumping the generation counter) while that pulse is still in flight
    -> the halt pulse completes but the coordinator still reports the
    stale pre-halt "closing" value (real confirmation hasn't arrived yet).

    open_cover's own generation check aborts it (already covered by
    test_toggle_immediate_continuation_aborts_if_superseded_during_pulse
    above). The new case here: stop_cover must not trust that still-stale
    "closing" reading either - self._toggle_awaiting_halt_confirmation,
    not just the generation counter, is what tells it a halt was already
    sent and real feedback is still pending. Only one physical pulse
    should occur in the whole sequence, and the cover simply remains
    stopped once real confirmation finally arrives."""
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing

    async def fake_sleep(_duration):
        # A newer explicit command bumps the generation counter while
        # this pulse is in flight - exactly what stop_cover does as its
        # first action, before it even tries to acquire the lock
        # open_cover currently holds. Feedback is deliberately left
        # stale here - real confirmation has not arrived yet.
        cover._toggle_command_generation += 1

    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", fake_sleep)

    await cover.async_open_cover()  # halts, then aborts (superseded)
    assert cover._toggle_awaiting_halt_confirmation is True

    mock_coordinator.write_batched.reset_mock()
    await cover.async_stop_cover()  # data still stale "closing"

    mock_coordinator.write_batched.assert_not_called()  # no second pulse
    assert cover._toggle_pending_goal is None

    # Later, real "stopped" feedback finally arrives - nothing further
    # happens, the cover simply remains stopped.
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped
    cover._handle_coordinator_update()
    mock_coordinator.write_batched.assert_not_called()
    assert cover._toggle_awaiting_halt_confirmation is False


@pytest.mark.asyncio
async def test_toggle_new_target_after_halt_confirmation_pending_waits_for_fresh_feedback(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 5, the open/close equivalent of the stop_cover
    case above: a newer explicit open_cover/close_cover call arrives while
    an earlier command's own halt pulse is still in flight. It must
    become the latest desired target without making any physical decision
    on the still-stale feedback, and once real "stopped" feedback finally
    arrives, that latest target - not the original, now-superseded one -
    is what actually gets evaluated."""
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "opening"
    mock_coordinator.data = {"cover:status:db1,b10": 2}  # opening

    async def fake_sleep(_duration):
        cover._toggle_command_generation += 1  # newer command "arrives"

    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", fake_sleep)

    await cover.async_close_cover()  # halts (opening != close's goal), then aborts
    assert cover._toggle_awaiting_halt_confirmation is True

    mock_coordinator.write_batched.reset_mock()
    await cover.async_open_cover()  # data still stale "opening"

    assert cover._toggle_pending_goal == "open"  # latest request retained
    mock_coordinator.write_batched.assert_not_called()

    tasks: list = []
    monkeypatch.setattr(cover.hass, "async_create_task", tasks.append)
    mock_coordinator.data = {"cover:status:db1,b10": 4}  # stopped
    cover._handle_coordinator_update()
    assert len(tasks) == 1
    await tasks[0]

    # target="open" from stopped-after-opening is direction-ambiguous
    # (reversing only ever reaches "closing") - refuses, no press. That
    # absence of a press proves the *latest* target ("open") was what got
    # evaluated: the superseded "close" goal was still reachable from an
    # opening-halt and would have pressed instead.
    mock_coordinator.write_batched.assert_not_called()
    assert cover._toggle_pending_goal is None


@pytest.mark.asyncio
async def test_toggle_halt_confirmation_not_set_when_rising_edge_write_fails(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 6: self._toggle_awaiting_halt_confirmation must
    only be set once the rising edge has actually reached the PLC. If
    write_batched(open_command_address, True) itself fails - connection
    down, PLC unreachable, etc. - the physical relay almost certainly
    never received the pulse, so the flag must stay False. Otherwise the
    entity would believe a halt was sent when it wasn't, and could get
    stuck forever waiting for a "stopped" confirmation that will never
    arrive."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing
    mock_coordinator.write_batched.side_effect = HomeAssistantError("write failed")

    with pytest.raises(HomeAssistantError):
        await cover.async_stop_cover()

    assert cover._toggle_awaiting_halt_confirmation is False


@pytest.mark.asyncio
async def test_toggle_halt_confirmation_stays_set_when_later_pulse_step_fails(
    cover_factory, mock_coordinator, monkeypatch
):
    """PR #117 review round 6, the mirror case: once the rising edge write
    succeeds, the relay may already have physically reacted, so
    self._toggle_awaiting_halt_confirmation must stay True even if a later
    step of the same pulse (the falling edge write, here) then fails -
    real "stopped" feedback is still required before movement state can
    be trusted again."""
    monkeypatch.setattr("custom_components.s7plc.cover.asyncio.sleep", AsyncMock())
    cover = _status_cover(cover_factory)
    cover._last_toggle_direction = "closing"
    mock_coordinator.data = {"cover:status:db1,b10": 3}  # closing
    mock_coordinator.write_batched.side_effect = [
        None,  # rising edge (True) succeeds
        HomeAssistantError("write failed"),  # falling edge (False) fails
    ]

    with pytest.raises(HomeAssistantError):
        await cover.async_stop_cover()

    assert cover._toggle_awaiting_halt_confirmation is True
