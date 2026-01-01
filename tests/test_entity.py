from __future__ import annotations

import asyncio
import pytest
from typing import Any, Callable

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


class DummyCoordinator:
    def __init__(self, connected: bool = True):
        self._connected = connected
        self.data = {}
        self.write_calls: list[tuple[str, object]] = []
        self.refresh_called = False
        self._write_queue: list[bool] = []
        self._default_write_result = True
        self._item_scan_intervals = {}
        self._default_scan_interval = 10
        self._item_real_precisions = {}

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def add_item(self, *args, **kwargs):
        return None

    def write_bool(self, address: str, value: bool) -> bool:
        self.write_calls.append((address, bool(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def write_number(self, address: str, value: float) -> bool:
        self.write_calls.append((address, float(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def set_write_queue(self, *results: bool) -> None:
        self._write_queue = list(results)

    def set_default_write_result(self, value: bool) -> None:
        self._default_write_result = value

    async def async_request_refresh(self):
        self.refresh_called = True


class _ImmediateAwaitable:
    """Awaitable that immediately returns a value (no event loop needed)."""
    def __init__(self, value: Any = None, exc: Exception | None = None):
        self._value = value
        self._exc = exc

    def __await__(self):
        if self._exc is not None:
            raise self._exc
        if False:
            yield  # pragma: no cover (keeps this a generator)
        return self._value


class FakeHass:
    """Fake hass compatible with both async and sync tests on modern asyncio."""

    def __init__(self):
        self.calls = []
        self.data = {}

    def async_add_executor_job(self, func: Callable, *args, **kwargs):
        self.calls.append((func.__name__, args))
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            # If we're in an async test (running loop), return a Future with exception.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return _ImmediateAwaitable(exc=exc)
            fut = loop.create_future()
            fut.set_exception(exc)
            return fut

        # Success path: return Future if loop is running, else immediate awaitable.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return _ImmediateAwaitable(result)
        fut = loop.create_future()
        fut.set_result(result)
        return fut


class DummyEntry:
    def __init__(self, options):
        self.options = options
        self.data = {}
        self.entry_id = "test_entry"


def test_default_entity_name_humanizes_address():
    assert default_entity_name("PLC", "db1,w0") == "PLC DB1 W0"
    assert default_entity_name("PLC", "db1,x0.0") == "PLC DB1 X0.0"
    assert default_entity_name("PLC", "db1, x0.0") == "PLC DB1 X0.0"
    assert default_entity_name(None, "db1,w0") == "db1 w0"
    assert default_entity_name("PLC", None) == "PLC"
    assert default_entity_name(None, None) is None


def test_base_entity_availability_and_attrs():
    coord = DummyCoordinator(connected=False)
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

    assert base.extra_state_attributes == {"s7_address": "DB1,X0.0", "scan_interval": 10}


@pytest.mark.asyncio
async def test_bool_entity_commands_and_refresh():
    coord = DummyCoordinator()
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
    ent.hass = FakeHass()

    await ent.async_turn_on()
    assert ent._pending_command is True
    assert coord.write_calls[-1] == ("db1,x0.1", True)
    assert coord.refresh_called

    coord.refresh_called = False
    await ent.async_turn_off()
    assert ent._pending_command is False
    assert coord.write_calls[-1] == ("db1,x0.1", False)
    assert coord.refresh_called


@pytest.mark.asyncio
async def test_bool_entity_write_failure():
    coord = DummyCoordinator()
    coord.data = {"topic": False}
    coord.set_default_write_result(False)

    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1,x0.0",
        command_address="db1,x0.1",
        sync_state=True,
    )
    ent.hass = FakeHass()

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()

    assert coord.write_calls[-1] == ("db1,x0.1", True)
    assert ent._pending_command is None
    assert not coord.refresh_called


@pytest.mark.asyncio
async def test_bool_entity_ensure_connected():
    coord = DummyCoordinator(connected=False)
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
    ent.hass = FakeHass()

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


def test_bool_entity_state_synchronization_fire_and_forget():
    coord = DummyCoordinator()
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
    ent.hass = FakeHass()

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

    assert ent.hass.calls == [("write_bool", ("db1,x0.1", True))]
    assert coord.write_calls == [("db1,x0.1", True)]
    assert ent._last_state is True
    assert ent._ha_state_calls == 3


@pytest.mark.asyncio
async def test_button_press_write_failures(monkeypatch):
    coord = DummyCoordinator()
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
    button.hass = FakeHass()

    coord.set_default_write_result(False)
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    assert coord.write_calls == [("db1,x0.0", True)]

    coord.write_calls.clear()
    coord.set_default_write_result(True)
    coord.set_write_queue(True, False)

    with pytest.raises(HomeAssistantError):
        await button.async_press()

    assert coord.write_calls == [
        ("db1,x0.0", True),
        ("db1,x0.0", False),
    ]


def test_number_clamps_configured_limits():
    coord = DummyCoordinator()

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
async def test_number_async_set_native_value_success():
    coord = DummyCoordinator()
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
    ent.hass = FakeHass()

    await ent.async_set_native_value(42)
    assert coord.write_calls[-1] == ("db1,w0", 42.0)
    assert coord.refresh_called


@pytest.mark.asyncio
async def test_number_async_set_native_value_failure():
    coord = DummyCoordinator()
    coord.data = {"number:db1,w0": 10}
    coord.set_default_write_result(False)

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
    ent.hass = FakeHass()

    with pytest.raises(HomeAssistantError):
        await ent.async_set_native_value(42)

    assert coord.write_calls[-1] == ("db1,w0", 42.0)
    assert not coord.refresh_called


@pytest.mark.asyncio
async def test_number_setup_entry_generates_name_from_address(monkeypatch):
    hass = FakeHass()
    coord = DummyCoordinator()

    def fake_get_coordinator_and_device_info(hass_in, entry_in):
        return coord, {"name": "PLC"}, "deviceid"

    monkeypatch.setattr(
        "custom_components.s7plc.number.get_coordinator_and_device_info",
        fake_get_coordinator_and_device_info,
    )

    entry = DummyEntry(
        options={
            CONF_NUMBERS: [
                {CONF_ADDRESS: "db1,w0"}  # no name -> default_entity_name()
            ]
        }
    )

    added = []

    def fake_async_add_entities(entities, *args, **kwargs):
        added.extend(entities)

    await number_setup_entry(hass, entry, fake_async_add_entities)

    assert len(added) == 1
    assert getattr(added[0], "_attr_name", None) == "PLC DB1 W0"


@pytest.mark.asyncio
async def test_button_setup_entry_pulse_parsing(monkeypatch):
    hass = FakeHass()
    coord = DummyCoordinator()

    def fake_get_coordinator_and_device_info(hass_in, entry_in):
        return coord, {"name": "PLC"}, "deviceid"

    monkeypatch.setattr(
        "custom_components.s7plc.button.get_coordinator_and_device_info",
        fake_get_coordinator_and_device_info,
    )

    entry = DummyEntry(
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

    await button_setup_entry(hass, entry, fake_async_add_entities)

    assert len(added) == 4
    pulses = [e._button_pulse for e in added]
    assert pulses[0] == 2
    assert pulses[1] == DEFAULT_BUTTON_PULSE
    assert pulses[2] == DEFAULT_BUTTON_PULSE
    assert pulses[3] == DEFAULT_BUTTON_PULSE
