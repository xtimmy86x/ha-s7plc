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
    CONF_UID,
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

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()

    assert coord.write_calls[-1] == ("write_batched", "db1,x0.1", True)
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

    with pytest.raises(HomeAssistantError):
        await button.async_press()

    # First write fails and raises, so pulse-off write is not executed.
    assert len(coord.write_calls) == 1
    assert coord.write_calls[0] == ("write_batched", "db1,x0.0", True)


# ============================================================================
# S7Number Tests
# ============================================================================


def test_number_preserves_configured_ha_limits(mock_coordinator):
    """Test number entity preserves explicit Home Assistant limits."""
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

    assert number_entity.native_min_value == -99999.0
    assert number_entity.native_max_value == 99999.0


@pytest.mark.parametrize(
    ("address", "datatype_min", "datatype_max"),
    [
        ("db1,byte0", 0.0, 255.0),
        ("db1,word0", 0.0, 65535.0),
        ("db1,int0", -32768.0, 32767.0),
        ("db1,dint0", -2147483648.0, 2147483647.0),
        ("db1,sint0", -128.0, 127.0),
        ("db1,usint0", 0.0, 255.0),
        ("db1,dword0", 0.0, 4294967295.0),
        ("db1,time0", -2147483.648, 2147483.647),
    ],
)
@pytest.mark.parametrize(
    ("explicit_min", "explicit_max"),
    [
        (None, None),
        (-9999999999.0, 9999999999.0),
        (-9999999999.0, None),
        (None, 9999999999.0),
    ],
)
def test_number_runtime_combines_explicit_and_datatype_limits(
    mock_coordinator,
    address,
    datatype_min,
    datatype_max,
    explicit_min,
    explicit_max,
):
    """Integer and TIME limits fall back independently without clamping."""
    number_entity = S7Number(
        mock_coordinator,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic=f"number:{address}",
        address=address,
        command_address=address,
        min_value=explicit_min,
        max_value=explicit_max,
        step=None,
    )

    assert number_entity.native_min_value == (
        explicit_min if explicit_min is not None else datatype_min
    )
    assert number_entity.native_max_value == (
        explicit_max if explicit_max is not None else datatype_max
    )


def test_number_limit_fallback_uses_state_address_datatype(mock_coordinator):
    """Runtime defaults come from the state address, not the command address."""
    number_entity = S7Number(
        mock_coordinator,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,real4",
        min_value=None,
        max_value=None,
        step=None,
    )

    assert number_entity.native_min_value == 0.0
    assert number_entity.native_max_value == 65535.0


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

    with pytest.raises(HomeAssistantError):
        await ent.async_set_native_value(42)

    assert coord.write_calls[-1] == ("write_batched", "db1,w0", 42.0)
    assert not coord.refresh_called


def test_number_limits_are_independent_of_linear_conversion(mock_coordinator):
    """HA limits do not supply or alter conversion endpoints."""
    coord = mock_coordinator
    coord.data = {"number:db1,w0": 500.0}
    conversion = {
        "type": "linear_scale",
        "plc_min": 0,
        "plc_max": 1000,
        "ha_min": -50,
        "ha_max": 50,
    }
    ent = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=-100,
        max_value=100000,
        step=1,
        value_conversion=conversion,
    )
    assert ent.native_value == pytest.approx(0.0)
    assert ent.native_min_value == -100
    assert ent.native_max_value == 100000


@pytest.mark.asyncio
async def test_number_linear_scale_writes_using_conversion_endpoints(
    mock_coordinator, fake_hass
):
    """Writes use plc/HA conversion endpoints rather than entity limits."""
    ent = S7Number(
        mock_coordinator,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1,w0",
        address="db1,w0",
        command_address="db1,w0",
        min_value=-200,
        max_value=200,
        step=1,
        value_conversion={
            "type": "linear_scale",
            "plc_min": 0,
            "plc_max": 1000,
            "ha_min": -50,
            "ha_max": 50,
        },
    )
    ent.hass = fake_hass
    await ent.async_set_native_value(25)
    assert mock_coordinator.write_calls[-1] == (
        "write_batched",
        "db1,w0",
        pytest.approx(750),
    )


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
                {CONF_ADDRESS: "db1,w0", CONF_UID: "uid-1"}  # no name -> default_entity_name()
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
                {CONF_ADDRESS: "db1,x0.0", CONF_BUTTON_PULSE: 2.0, CONF_UID: "uid-1"},
                {CONF_ADDRESS: "db1,x0.1", CONF_BUTTON_PULSE: 0.3, CONF_UID: "uid-2"},
                {CONF_ADDRESS: "db1,x0.2", CONF_UID: "uid-3"},  # missing -> default
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
@pytest.mark.asyncio
async def test_central_availability_policies(mock_coordinator) -> None:
    """Always and BIT policies are applied without bypassing PLC state checks."""
    entity = S7BaseEntity(
        mock_coordinator,
        name="Policy",
        unique_id="policy-uid",
        device_info={},
        topic="sensor:state",
    )
    mock_coordinator.data = {}
    mock_coordinator.set_connected(False)
    await entity.async_configure_availability(
        {"uid": entity._attr_unique_id, "availability_mode": "always"}
    )
    assert entity.available

    await entity.async_configure_availability(
        {
            "uid": entity._attr_unique_id,
            "availability_mode": "bit",
            "availability_address": "DB1,X10.0",
        }
    )
    mock_coordinator.data[entity._availability_topic] = True
    assert not entity.available
    mock_coordinator.set_connected(True)
    mock_coordinator.data[entity._topic] = True
    assert entity.available
    mock_coordinator.data[entity._availability_topic] = False
    assert not entity.available
