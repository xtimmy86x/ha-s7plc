"""Cancellation must not leave a PLC reply available to the next operation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyS7 import AsyncS7Client
from pyS7.constants import ConnectionState

from custom_components.s7plc.coordinator import S7Coordinator

pytestmark = pytest.mark.asyncio


class PacketClient:
    """Model a pending reply and pyS7's packet lock; expose exact event ordering."""

    def __init__(self):
        self.is_connected = True
        self.lock = asyncio.Lock()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_release.set()
        self.block = True
        self.pending_reply = False
        self.calls = []
        self.closes = 0
        self.connects = 0
        self.contaminated = 0

    async def execute(self, kind):
        async with self.lock:
            assert self.is_connected
            self.calls.append(kind)
            if self.pending_reply:
                self.contaminated += 1
            if self.block:
                self.block = False
                self.pending_reply = True
                self.entered.set()
                await self.release.wait()
                self.pending_reply = False
            return 42

    async def read(self, tags, *, optimize=True):
        value = await self.execute("read")
        return [
            "fresh" if tag.data_type.name in {"STRING", "WSTRING"} else value
            for tag in tags
        ]

    async def write(self, tags, values):
        await self.execute("write")

    async def get_cpu_info(self):
        await self.execute("health")
        return {}

    async def disconnect(self):
        async with self.lock:
            self.closes += 1
            self.close_entered.set()
            await self.close_release.wait()
            self.pending_reply = False
            self.is_connected = False

    async def connect(self):
        async with self.lock:
            self.connects += 1
            self.is_connected = True


@asynccontextmanager
async def scenario(address="DB1,W0"):
    coord = S7Coordinator(
        HomeAssistant(), host="plc.local", op_timeout=0.5, max_retries=0
    )
    coord.async_set_updated_data = MagicMock()
    client = PacketClient()
    coord._connection.client = client
    await coord.add_item("value", address)
    coord._data_cache = {"value": "previous"}
    tasks = []

    async def start(operation):
        entered = asyncio.Event()

        async def run():
            entered.set()
            return await operation()

        task = asyncio.create_task(run())
        tasks.append(task)
        await asyncio.wait_for(entered.wait(), timeout=3)
        return task

    try:
        yield coord, client, start
    finally:
        client.release.set()
        client.close_release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.wait_for(coord.async_shutdown(), timeout=3)


@pytest.mark.parametrize(
    "kind,address",
    [
        ("poll", "DB1,W0"),
        ("poll", "DB1,S0.12"),
        ("poll", "DB1,WS0.12"),
        ("single", "DB1,W0"),
        ("health", "DB1,W0"),
    ],
)
async def test_cancelled_dispatched_read_closes_transport_without_publishing(
    kind, address
):
    async with scenario(address) as (coord, client, start):
        operation = {
            "poll": coord._async_update_data,
            "single": lambda: coord._read_one(address),
            "health": coord.async_health_check,
        }[kind]
        task = await start(operation)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)
        assert client.closes == 1
        assert not client.pending_reply
        assert not coord.is_connected()
        assert coord._data_cache == {"value": "previous"}
        assert coord.get_topic_read_revision("value") == 0
        assert coord.last_health_ok is not True
        result = await coord._async_update_data()
        assert result == {
            "value": "fresh" if ",S" in address or ",WS" in address else 42
        }
        assert client.connects == 1
        assert client.contaminated == 0


@pytest.mark.parametrize("next_kind", ["read", "write", "health"])
async def test_already_waiting_operation_cannot_consume_cancelled_reads_reply(
    next_kind,
):
    async with scenario() as (coord, client, start):
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        operation = {
            "read": lambda: coord._read_one("DB1,W2"),
            "write": lambda: coord.write("DB1,W2", 7),
            "health": coord.async_health_check,
        }[next_kind]
        second = await start(operation)
        assert not second.done()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, timeout=3)
        result = await asyncio.wait_for(second, timeout=3)
        assert client.contaminated == 0
        assert client.closes == 1
        assert client.connects == 1
        assert (
            result == 42
            if next_kind == "read"
            else result is True
            if next_kind == "write"
            else result["ok"]
        )


async def test_real_pys7_cancelled_read_closes_the_used_stream():
    class Reader:
        def __init__(self):
            self.entered = asyncio.Event()

        async def readexactly(self, length):
            self.entered.set()
            await asyncio.Event().wait()

    class Writer:
        closed = False

        def write(self, data):
            pass

        async def drain(self):
            pass

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    coord = S7Coordinator(HomeAssistant(), host="192.0.2.1", rack=0, slot=1)
    client = AsyncS7Client("192.0.2.1", 0, 1)
    reader, writer = Reader(), Writer()
    client._reader, client._writer = reader, writer
    client._set_connection_state(ConnectionState.CONNECTED)
    coord._connection.client = client
    task = asyncio.create_task(coord._read_one("DB1,W0"))
    try:
        await asyncio.wait_for(reader.entered.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)
        assert writer.closed
        assert not client.is_connected
        assert client._reader is None
        assert client._writer is None
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await coord.async_shutdown()


async def test_cancelling_a_queued_read_does_not_close_active_requests_stream():
    async with scenario() as (coord, client, start):
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        queued = await start(lambda: coord._read_one("DB1,W2"))
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert client.closes == 0
        assert not first.done()
        client.release.set()
        assert await asyncio.wait_for(first, timeout=3) == {"value": 42}
        assert client.closes == 0


@pytest.mark.parametrize("action", ["connect", "read", "write", "health"])
async def test_second_cancellation_keeps_cleanup_owned_and_new_io_waiting(action):
    async with scenario() as (coord, client, start):
        client.close_release.clear()
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        first.cancel()
        await asyncio.wait_for(client.close_entered.wait(), timeout=3)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        operation = {
            "connect": coord.connect,
            "read": lambda: coord._read_one("DB1,W2"),
            "write": lambda: coord.write("DB1,W2", 7),
            "health": coord.async_health_check,
        }[action]
        waiting = await start(operation)
        assert not waiting.done()
        assert client.calls == ["read"]
        assert client.connects == 0
        client.close_release.set()
        result = await asyncio.wait_for(waiting, timeout=3)
        assert client.contaminated == 0
        assert client.closes == 1
        assert client.connects == 1
        if action == "connect":
            assert result is None
        elif action == "read":
            assert result == 42
        elif action == "write":
            assert result is True
        else:
            assert result["ok"] is True


@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
async def test_stop_during_owned_cleanup_rejects_waiters_and_finishes(stop):
    async with scenario() as (coord, client, start):
        client.close_release.clear()
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        first.cancel()
        await asyncio.wait_for(client.close_entered.wait(), timeout=3)
        queued = await start(lambda: coord._read_one("DB1,W2"))
        stopping = await start(getattr(coord, stop))
        client.close_release.set()
        await asyncio.wait_for(stopping, timeout=3)
        results = await asyncio.gather(first, queued, return_exceptions=True)
        assert all(
            isinstance(result, (asyncio.CancelledError, HomeAssistantError))
            for result in results
        )
        assert not coord.is_connected()
        assert not coord._connection.stopping
        assert not coord._connection._io_tasks
        assert not coord._connection._io_completions
        assert coord._connection._transport_reset_task is None
        assert client.calls == ["read"]
        assert client.connects == 0


async def test_failed_cleanup_keeps_admission_closed_until_explicit_stop_recovers():
    async with scenario() as (coord, client, start):
        client.close_release.clear()
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        first.cancel()
        # The real 0.5 s timeout is exercised; 3 s is only a deadlock watchdog.
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, timeout=3)
        assert coord._connection.stopping
        for operation in (
            coord.connect,
            lambda: coord._read_one("DB1,W2"),
            lambda: coord.write("DB1,W2", 7),
        ):
            with pytest.raises(HomeAssistantError):
                await operation()
        assert client.calls == ["read"]
        client.close_release.set()
        await asyncio.wait_for(coord.disconnect(), timeout=3)
        assert not coord._connection.stopping
        assert await coord._read_one("DB1,W2") == 42
        assert client.contaminated == 0


async def test_another_plc_keeps_reading_while_cancelled_stream_is_closed():
    async with (
        scenario() as (left, left_client, start_left),
        scenario() as (right, right_client, _),
    ):
        left_client.close_release.clear()
        first = await start_left(left._async_update_data)
        await asyncio.wait_for(left_client.entered.wait(), timeout=3)
        first.cancel()
        await asyncio.wait_for(left_client.close_entered.wait(), timeout=3)
        right_client.release.set()
        assert await asyncio.wait_for(right._async_update_data(), timeout=3) == {
            "value": 42
        }
        assert right_client.closes == 0
        assert right_client.connects == 0
        assert not first.done()
        left_client.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await first


@pytest.mark.parametrize(
    "failure",
    [
        OSError("close failed"),
        RuntimeError("close failed"),
        AttributeError("close failed"),
        None,
    ],
)
async def test_cleanup_errors_cannot_be_swallowed_and_reopen_an_uncertain_stream(
    failure,
):
    async with scenario() as (coord, client, start):
        disconnect = client.disconnect

        async def failed_disconnect():
            if failure is not None:
                raise failure
            # A driver returning normally while still connected is unsafe too.

        client.disconnect = failed_disconnect
        first = await start(coord._async_update_data)
        await asyncio.wait_for(client.entered.wait(), timeout=3)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert coord._connection.stopping
        with pytest.raises((OSError, RuntimeError, AttributeError)):
            await coord.disconnect()
        assert coord._connection.stopping
        with pytest.raises(HomeAssistantError):
            await coord._read_one("DB1,W2")
        client.disconnect = disconnect
        await coord.disconnect()
        assert not coord._connection.stopping
        assert await coord._read_one("DB1,W2") == 42
        assert client.contaminated == 0
