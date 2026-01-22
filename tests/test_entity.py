"""Tests for S7 entity classes - Refactored with fixtures."""

from __future__ import annotations

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
    DEFAULT_BUTTON_PULSE,
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
    assert default_entity_name("PLC", "db1,w0") == "PLC DB1 W0"
    assert default_entity_name("PLC", "db1,x0.0") == "PLC DB1 X0.0"
    assert default_entity_name("PLC", "db1, x0.0") == "PLC DB1 X0.0"
    assert default_entity_name(None, "db1,w0") == "db1 w0"
    assert default_entity_name("PLC", None) == "PLC"
    assert default_entity_name(None, None) is None


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
    assert coord.write_calls[-1] == ("write", "db1,x0.1", True)
    assert coord.refresh_called

    coord.refresh_called = False
    await ent.async_turn_off()
    assert ent._pending_command is False
    assert coord.write_calls[-1] == ("write", "db1,x0.1", False)
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

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()

    assert coord.write_calls[-1] == ("write", "db1,x0.1", True)
    assert ent._pending_command is None
    assert not coord.refresh_called


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


def test_bool_entity_state_synchronization_fire_and_forget(mock_coordinator, fake_hass):
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
    ent.async_write_ha_state()

    assert ent.hass.calls == [("write", ("db1,x0.1", True))]
    assert coord.write_calls == [("write", "db1,x0.1", True)]
    assert ent._last_state is True
    assert ent._ha_state_calls == 3


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
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    assert coord.write_calls == [("write", "db1,x0.0", True)]

    coord.write_calls.clear()
    coord.set_default_write_result(True)
    coord.set_write_queue(True, False)

    with pytest.raises(HomeAssistantError):
        await button.async_press()

    assert coord.write_calls == [
        ("write", "db1,x0.0", True),
        ("write", "db1,x0.0", False),
    ]


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
    assert coord.write_calls[-1] == ("write", "db1,w0", 42.0)
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

    with pytest.raises(HomeAssistantError):
        await ent.async_set_native_value(42)

    assert coord.write_calls[-1] == ("write", "db1,w0", 42.0)
    assert not coord.refresh_called


# ============================================================================
# Setup Entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_number_setup_entry_generates_name_from_address(mock_coordinator, fake_hass, dummy_entry, monkeypatch):
    """Test number setup entry generates default names."""
    coord = mock_coordinator

    def fake_get_coordinator_and_device_info(hass_in, entry_in):
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
    assert getattr(added[0], "_attr_name", None) == "PLC DB1 W0"


@pytest.mark.asyncio
async def test_button_setup_entry_pulse_parsing(mock_coordinator, fake_hass, dummy_entry, monkeypatch):
    """Test button setup entry parses pulse configuration."""
    coord = mock_coordinator

    def fake_get_coordinator_and_device_info(hass_in, entry_in):
        return coord, {"name": "PLC"}, "deviceid"

    monkeypatch.setattr(
        "custom_components.s7plc.button.get_coordinator_and_device_info",
        fake_get_coordinator_and_device_info,
    )

    entry = dummy_entry(
        options={
            CONF_BUTTONS: [
                {CONF_ADDRESS: "db1,x0.0", CONF_BUTTON_PULSE: "2"},
                {CONF_ADDRESS: "db1,x0.1", CONF_BUTTON_PULSE: -1},     # invalid -> default
                {CONF_ADDRESS: "db1,x0.2", CONF_BUTTON_PULSE: "bad"},  # invalid -> default
                {CONF_ADDRESS: "db1,x0.3"},                             # missing -> default
            ]
        }
    )

    added = []

    def fake_async_add_entities(entities, *args, **kwargs):
        added.extend(entities)

    await button_setup_entry(fake_hass, entry, fake_async_add_entities)

    assert len(added) == 4
    pulses = [e._button_pulse for e in added]
    assert pulses[0] == 2
    assert pulses[1] == DEFAULT_BUTTON_PULSE
    assert pulses[2] == DEFAULT_BUTTON_PULSE
    assert pulses[3] == DEFAULT_BUTTON_PULSE
