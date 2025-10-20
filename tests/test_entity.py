from __future__ import annotations

import asyncio

import pytest
from types import SimpleNamespace

from custom_components.s7plc import entity
from custom_components.s7plc.button import S7Button
from custom_components.s7plc.entity import S7BaseEntity, S7BoolSyncEntity
from custom_components.s7plc import number as number_comp
from custom_components.s7plc.number import S7Number
from homeassistant.core import HomeAssistant


class DummyCoordinator:
    def __init__(self, connected: bool = True):
        self._connected = connected
        self.data = {}
        self.hass = HomeAssistant()
        self.write_calls: list[tuple[str, bool]] = []
        self.refresh_called = False
        self._write_queue: list[bool] = []
        self._default_write_result = True

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def write_bool(self, address: str, value: bool) -> bool:
        self.write_calls.append((address, bool(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def set_write_queue(self, *results: bool) -> None:
        self._write_queue = list(results)

    def set_default_write_result(self, value: bool) -> None:
        self._default_write_result = value

    async def async_request_refresh(self):
        self.refresh_called = True


def test_base_entity_availability_and_attrs():
    coord = DummyCoordinator(connected=False)
    base = S7BaseEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic1",
        address="db1.dbx0.0",
    )

    assert not base.available

    coord.set_connected(True)
    coord.data = {}
    assert not base.available

    coord.data = {"topic1": None}
    assert not base.available

    coord.data = {"topic1": 1}
    assert base.available

    assert base.extra_state_attributes == {"s7_address": "DB1.DBX0.0"}


def test_bool_entity_commands_and_refresh():
    coord = DummyCoordinator()
    coord.data = {"topic": False}
    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1.dbx0.0",
        command_address="db1.dbx0.1",
        sync_state=True,
    )

    calls: list[tuple[str, tuple]] = []

    async def fake_executor(func, *args):
        calls.append((func.__name__, args))
        return func(*args)

    ent.hass.async_add_executor_job = fake_executor  # type: ignore[assignment]

    asyncio.run(ent.async_turn_on())

    assert ent._pending_command is True
    assert coord.write_calls[-1] == ("db1.dbx0.1", True)
    assert coord.refresh_called

    coord.refresh_called = False
    asyncio.run(ent.async_turn_off())
    assert ent._pending_command is False
    assert coord.write_calls[-1] == ("db1.dbx0.1", False)
    assert coord.refresh_called


def test_bool_entity_write_failure():
    coord = DummyCoordinator()
    coord.data = {"topic": False}
    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1.dbx0.0",
        command_address="db1.dbx0.1",
        sync_state=True,
    )

    async def fake_executor(func, *args):
        return func(*args)

    ent.hass.async_add_executor_job = fake_executor  # type: ignore[assignment]

    coord.set_default_write_result(False)

    with pytest.raises(entity.HomeAssistantError):
        asyncio.run(ent.async_turn_on())

    assert coord.write_calls[-1] == ("db1.dbx0.1", True)
    assert ent._pending_command is None
    assert not coord.refresh_called


def test_bool_entity_ensure_connected():
    coord = DummyCoordinator(connected=False)
    coord.data = {}
    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1.dbx0.0",
        command_address="db1.dbx0.1",
        sync_state=True,
    )

    with pytest.raises(entity.HomeAssistantError):
        asyncio.run(ent.async_turn_on())


def test_bool_entity_state_synchronization():
    coord = DummyCoordinator()
    coord.data = {"topic": True}
    ent = S7BoolSyncEntity(
        coord,
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="topic",
        state_address="db1.dbx0.0",
        command_address="db1.dbx0.1",
        sync_state=True,
    )

    calls: list[tuple[str, tuple]] = []

    def fake_executor(func, *args):
        calls.append((func.__name__, args))
        return func(*args)

    ent.hass.async_add_executor_job = fake_executor  # type: ignore[assignment]

    # First update caches the initial state without issuing commands
    ent.async_write_ha_state()
    assert ent._last_state is True
    assert calls == []
    assert ent.coordinator.write_calls == []
    assert ent._ha_state_calls == 1

    # Matching pending command clears it without new write
    coord.data["topic"] = False
    ent._pending_command = False
    ent.async_write_ha_state()
    assert ent._pending_command is None
    assert ent._last_state is False
    assert calls == []
    assert ent._ha_state_calls == 2

    # External change triggers a write to keep PLC in sync
    coord.data["topic"] = True
    ent._pending_command = None
    ent.async_write_ha_state()
    assert calls == [("write_bool", ("db1.dbx0.1", True))]
    assert ent._last_state is True
    assert ent._ha_state_calls == 3


def test_button_press_write_failures():
    coord = DummyCoordinator()
    coord.data = {"button:db1.dbx0.0": True}
    button = S7Button(
        coord,
        name="Test Button",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        address="db1.dbx0.0",
        button_pulse=0,
    )

    async def fake_executor(func, *args):
        return func(*args)

    button.hass.async_add_executor_job = fake_executor  # type: ignore[assignment]

    coord.set_default_write_result(False)
    with pytest.raises(entity.HomeAssistantError):
        asyncio.run(button.async_press())
    assert coord.write_calls == [("db1.dbx0.0", True)]

    coord.write_calls.clear()
    coord.set_default_write_result(True)
    coord.set_write_queue(True, False)

    with pytest.raises(entity.HomeAssistantError):
        asyncio.run(button.async_press())

    assert coord.write_calls == [
        ("db1.dbx0.0", True),
        ("db1.dbx0.0", False),
    ]

def test_number_clamps_configured_limits(monkeypatch):
    coord = DummyCoordinator()
    monkeypatch.setattr(
        number_comp, "parse_tag", lambda addr: SimpleNamespace(data_type="INT")
    )
    monkeypatch.setattr(
        number_comp,
        "get_numeric_limits",
        lambda data_type: (-32768.0, 32767.0),
    )

    number_entity = S7Number(
        coord,
        name="Number",
        unique_id="uid",
        device_info={"identifiers": {"domain"}},
        topic="number:db1.dbw0",
        address="db1.dbw0",
        command_address="db1.dbw0",
        min_value=-99999,
        max_value=99999,
        step=None,
    )

    assert number_entity.native_min_value == -32768.0
    assert number_entity.native_max_value == 32767.0