from __future__ import annotations

import asyncio
import pytest

from custom_components.s7plc import entity
from custom_components.s7plc.entity import S7BaseEntity, S7BoolSyncEntity
from homeassistant.core import HomeAssistant


class DummyCoordinator:
    def __init__(self, connected=True):
        self._connected = connected
        self.data = {}
        self.hass = HomeAssistant()
        self.write_calls: list[tuple[str, bool]] = []
        self.refresh_called = False

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def write_bool(self, address: str, value: bool) -> bool:
        self.write_calls.append((address, bool(value)))
        return True

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