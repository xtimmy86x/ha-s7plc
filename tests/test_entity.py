"""Tests for S7 entity classes - Refactored with fixtures."""

from __future__ import annotations

import asyncio
import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.button import S7Button, async_setup_entry as button_setup_entry
from custom_components.s7plc.entity import S7BaseEntity, S7BoolSyncEntity
from custom_components.s7plc.helpers import default_entity_name
from custom_components.s7plc.number import S7Number, async_setup_entry as number_setup_entry
from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_BUTTONS,
    CONF_BUTTON_PULSE,
    CONF_NUMBERS,
    DEFAULT_PULSE_DURATION,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def dummy_entry():
    """Provide a dummy entry factory (already in conftest)."""
    def _create_entry(options):
        from conftest import DummyEntry
        return DummyEntry(options)
    return _create_entry


# ============================================================================
# Helper Name Tests
# ============================================================================


# ============================================================================
# Helper Name Tests
# ============================================================================


def test_default_entity_name_humanizes_address():
    assert default_entity_name("db1,w0") == "DB1 W0"
    assert default_entity_name("db1,x0.0") == "DB1 X0.0"
    assert default_entity_name("db1, x0.0") == "DB1 X0.0"

    # Without address, returns None
    assert default_entity_name(None) is None


# ============================================================================
# S7BaseEntity Tests
# ============================================================================


def test_base_entity_availability_and_attrs(mock_coordinator_disconnected):
    """Test base entity availability based on connection and data."""
    coord = mock_coordinator_disconnected
    base = S7BaseEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic1",
        address="db1,x0.0",
    )

    assert not base.available

    coord.set_connected(True)
    coord.data = {}
    assert not base.available

    coord.data = {"topic1": None}
    assert not base.available

    coord.data = {"topic1": 1}
    assert base.available

    assert base.extra_state_attributes == {"s7_address": "DB1,X0.0", "scan_interval": "10 s"}


# ============================================================================
# S7BoolSyncEntity Tests
# ============================================================================


@pytest.mark.asyncio
async def test_bool_entity_commands_and_refresh(mock_coordinator, fake_hass):
    """Test boolean entity turn on/off commands."""
    coord = mock_coordinator
    coord.data = {"topic": False}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    ent.hass = fake_hass

    await ent.async_turn_on()
    assert ent._pending_command is True
    assert coord.write_calls[-1] == ("write_batched", "db1,x0.1", True)
    assert coord.refresh_called

    coord.refresh_called = False
    await ent.async_turn_off()
    assert ent._pending_command is False
    assert coord.write_calls[-1] == ("write_batched", "db1,x0.1", False)
    assert coord.refresh_called


@pytest.mark.asyncio
async def test_bool_entity_write_failure(mock_coordinator_failing, fake_hass):
    """Test boolean entity handles write failure."""
    coord = mock_coordinator_failing
    coord.data = {"topic": False}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    ent.hass = fake_hass

    # Batched writes are fire-and-forget, so they don't raise exceptions
    await ent.async_turn_on()

    assert coord.write_calls[-1] == ("write_batched", "db1,x0.1", True)
    assert ent._pending_command is True  # Still set even if write fails
    assert coord.refresh_called  # Refresh is still called


@pytest.mark.asyncio
async def test_bool_entity_ensure_connected(mock_coordinator_disconnected, fake_hass):
    """Test boolean entity requires connection."""
    coord = mock_coordinator_disconnected
    coord.data = {"topic": False}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    ent.hass = fake_hass

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


@pytest.mark.asyncio
async def test_bool_entity_state_synchronization_fire_and_forget(mock_coordinator, fake_hass):
    """Test state synchronization with fire-and-forget writes."""
    coord = mock_coordinator
    coord.data = {"topic": True}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    ent.hass = fake_hass

    ent.async_write_ha_state()
    assert ent._last_state is True
    assert ent.hass.calls == []
    assert coord.write_calls == []
    assert ent._ha_state_calls == 1

    coord.data["topic"] = False
    ent._pending_command = False
    ent.async_write_ha_state()
    assert ent._pending_command is None
    assert ent._last_state is False
    assert ent.hass.calls == []
    assert ent._ha_state_calls == 2

    coord.data["topic"] = True
    ent._pending_command = None
    
    # Trigger state update - need to give asyncio.create_task time to execute
    ent.async_write_ha_state()
    await asyncio.sleep(0.01)  # Give task time to execute

    assert coord.write_calls == [("write_batched", "db1,x0.1", True)]
    assert ent._last_state is True
    assert ent._ha_state_calls == 3


def test_bool_entity_pulse_disables_sync(mock_coordinator):
    """When both pulse_command and sync_state are True, sync is disabled."""
    coord = mock_coordinator
    coord.data = {"topic": False}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
        pulse_command=True,
        pulse_duration=0.5,
    )

    assert ent._pulse_command is True
    assert ent._sync_state is False  # pulse takes priority


def test_bool_entity_same_address_disables_sync(mock_coordinator):
    """When state and command addresses are the same, sync is disabled."""
    coord = mock_coordinator
    coord.data = {"topic": False}

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.0",
        sync_state=True,
    )

    assert ent._sync_state is False  # same address, sync disabled


# ============================================================================
# S7Button Tests
# ============================================================================


@pytest.mark.asyncio
async def test_button_press_write_failures(mock_coordinator, fake_hass, monkeypatch):
    """Test button press handles write failures."""
    coord = mock_coordinator
    coord.data = {"button:db1,x0.0": True}

    # patch sleep to avoid waiting
    async def fake_sleep(_):
        return None

    monkeypatch.setattr("custom_components.s7plc.button.asyncio.sleep", fake_sleep)

    button = S7Button(
        coord,
        name="Test Button",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        address="db1,x0.0",
        button_pulse=0,
    )
    button.hass = fake_hass

    coord.set_default_write_result(False)
    
    # Batched writes don't raise exceptions
    # Button always writes True then False (pulse behavior)
    await button.async_press()
    
    assert len(coord.write_calls) == 2
    assert coord.write_calls[0] == ("write_batched", "db1,x0.0", True)
    assert coord.write_calls[1] == ("write_batched", "db1,x0.0", False)


# ============================================================================
# S7Number Tests
# ============================================================================


def test_number_clamps_configured_limits(mock_coordinator):
    """Test number entity clamps limits to data type bounds."""
    coord = mock_coordinator

    number_entity = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=-99999,
        max_value=99999,
        step=None,
    )

    assert number_entity.native_min_value == 0.0  # WORD lower bound
    assert number_entity.native_max_value == 65535.0  # WORD upper bound


@pytest.mark.asyncio
async def test_number_async_set_native_value_success(mock_coordinator, fake_hass):
    """Test number entity set value successfully."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 10}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=None,
        max_value=None,
        step=None,
    )
    ent.hass = fake_hass

    await ent.async_set_native_value(42)
    assert coord.write_calls[-1] == ("write_batched", "db1,w0", 42.0)
    assert coord.refresh_called


@pytest.mark.asyncio
async def test_number_async_set_native_value_failure(mock_coordinator_failing, fake_hass):
    """Test number entity handles write failure."""
    coord = mock_coordinator_failing
    coord.data = {"number:db1,w0": 10}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=None,
        max_value=None,
        step=None,
    )
    ent.hass = fake_hass

    # Batched writes don't raise exceptions
    await ent.async_set_native_value(42)

    assert coord.write_calls[-1] == ("write_batched", "db1,w0", 42.0)
    assert coord.refresh_called  # Refresh is still called


def test_number_value_multiplier_scales_native_value(mock_coordinator):
    """native_value is PLC value * multiplier."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 100}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0,
        max_value=1000,
        step=1,
        value_multiplier=0.1,
    )

    assert ent.native_value == pytest.approx(10.0)  # 100 * 0.1
    assert ent.native_min_value == pytest.approx(0.0)   # 0 * 0.1
    assert ent.native_max_value == pytest.approx(100.0)  # 1000 * 0.1
    assert ent._attr_native_step == pytest.approx(0.1)  # 1 * 0.1


@pytest.mark.asyncio
async def test_number_value_multiplier_divides_on_write(mock_coordinator, fake_hass):
    """async_set_native_value writes display value / multiplier to PLC."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 500}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0,
        max_value=1000,
        step=1,
        value_multiplier=0.1,
    )
    ent.hass = fake_hass

    # User sets 25.0 (display units) → PLC should receive 250.0
    await ent.async_set_native_value(25.0)
    assert coord.write_calls[-1] == ("write_batched", "db1,w0", pytest.approx(250.0))


def test_number_value_multiplier_in_attributes(mock_coordinator):
    """value_multiplier appears in extra_state_attributes."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 0}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=None,
        max_value=None,
        step=None,
        value_multiplier=2.0,
    )

    attrs = ent.extra_state_attributes
    assert attrs.get("value_multiplier") == pytest.approx(2.0)


def test_number_no_multiplier_unchanged(mock_coordinator):
    """Without multiplier, native_value is the raw PLC value."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 42}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=None,
        max_value=None,
        step=None,
    )

    assert ent.native_value == 42
    assert "value_multiplier" not in ent.extra_state_attributes


# ============================================================================
# S7Number linear-scale tests
# ============================================================================


def test_number_scale_params_stored(mock_coordinator):
    """Scale parameters are parsed and stored when all four are provided."""
    coord = mock_coordinator
    coord.data = {}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
    )

    assert ent._scale_params == (0.0, 1000.0, 0.0, 100.0)


def test_number_scale_partial_params_ignored(mock_coordinator):
    """Only raw range set, no display range → _scale_params stays None."""
    coord = mock_coordinator
    coord.data = {}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=None,
        max_value=None,
        step=None,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
        # min_value and max_value missing → scale does not activate
    )

    assert ent._scale_params is None


def test_number_native_value_with_scale(mock_coordinator):
    """native_value applies linear scaling: raw 500 in [0,1000] → 50 in [0,100]."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 500.0}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
    )

    assert ent.native_value == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_number_scale_inverse_on_write(mock_coordinator, fake_hass):
    """async_set_native_value applies inverse scaling before writing to PLC."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 500.0}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
    )
    ent.hass = fake_hass

    # User writes 75 % → PLC should receive 750
    await ent.async_set_native_value(75.0)
    assert coord.write_calls[-1] == ("write_batched", "db1,w0", pytest.approx(750.0))


def test_number_scale_takes_precedence_over_multiplier(mock_coordinator):
    """When both scale and multiplier are set, scale wins."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 500.0}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        value_multiplier=10.0,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
    )

    # scale: 500/1000*100 = 50, NOT 500*10 = 5000
    assert ent.native_value == pytest.approx(50.0)


def test_number_scale_attributes_exposed(mock_coordinator):
    """Scale parameters appear in extra_state_attributes."""
    coord = mock_coordinator
    coord.data = {}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        scale_raw_min=4000.0,
        scale_raw_max=20000.0,
    )

    attrs = ent.extra_state_attributes
    assert attrs["scale_raw_min"] == 4000.0
    assert attrs["scale_raw_max"] == 20000.0
    assert "value_multiplier" not in attrs


def test_number_scale_ui_min_max_mapped(mock_coordinator):
    """When scale is active, native_min/max_value equal min_value/max_value (the display range)."""
    coord = mock_coordinator
    coord.data = {}

    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=0.0,
        max_value=100.0,
        step=None,
        scale_raw_min=0.0,
        scale_raw_max=1000.0,
    )

    assert ent.native_min_value == pytest.approx(0.0)
    assert ent.native_max_value == pytest.approx(100.0)





@pytest.mark.asyncio
async def test_number_setup_entry_generates_name_from_address(mock_coordinator, fake_hass, dummy_entry, monkeypatch):
    """Test number setup entry generates default names."""
    coord = mock_coordinator

    def fake_get_coordinator_and_device_info(entry_in):
        return coord, {"name": "PLC"}, "deviceid"

    monkeypatch.setattr(
        "custom_components.s7plc.number.get_coordinator_and_device_info",
        fake_get_coordinator_and_device_info,
    )

    entry = dummy_entry(
        options={
            CONF_NUMBERS: [
                {CONF_ADDRESS: "db1,w0"}  # no name -> default_entity_name()
            ]
        }
    )

    added = []

    def fake_async_add_entities(entities, *args, **kwargs):
        added.extend(entities)

    await number_setup_entry(fake_hass, entry, fake_async_add_entities)

    assert len(added) == 1
    assert getattr(added[0], "_attr_name", None) == "DB1 W0"


@pytest.mark.asyncio
async def test_button_setup_entry_pulse_parsing(mock_coordinator, fake_hass, dummy_entry, monkeypatch):
    """Test button setup entry uses pulse configuration from config flow."""
    coord = mock_coordinator

    def fake_get_coordinator_and_device_info(entry_in):
        return coord, {"name": "PLC"}, "deviceid"

    monkeypatch.setattr(
        "custom_components.s7plc.button.get_coordinator_and_device_info",
        fake_get_coordinator_and_device_info,
    )

    # Config flow already validates values; entities receive clean data
    entry = dummy_entry(
        options={
            CONF_BUTTONS: [
                {CONF_ADDRESS: "db1,x0.0", CONF_BUTTON_PULSE: 2.0},
                {CONF_ADDRESS: "db1,x0.1", CONF_BUTTON_PULSE: 0.3},
                {CONF_ADDRESS: "db1,x0.2"},  # missing -> default
            ]
        }
    )

    added = []

    def fake_async_add_entities(entities, *args, **kwargs):
        added.extend(entities)

    await button_setup_entry(fake_hass, entry, fake_async_add_entities)

    assert len(added) == 3
    pulses = [e._button_pulse for e in added]
    assert pulses[0] == 2.0
    assert pulses[1] == 0.3
    assert pulses[2] == DEFAULT_PULSE_DURATION
