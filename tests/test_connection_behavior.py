"""Connection ownership contracts and regressions reproduced before the fix.

The controlled client models pyS7 3.1.1 returning immediately from connect
while CONNECTING.
One test also exercises that behavior through the installed real pyS7 client.
Only the dispatch-timing regression wraps a coordinator connection method;
the other cases retain coordinator connection, retry, and lifecycle methods.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.coordinator import S7Coordinator

pytestmark = pytest.mark.asyncio


class ConnectingClient:
    """Expose handshake progress and pyS7's early return to simultaneous callers."""

    def __init__(self):
        self.is_connected = False
        self.connecting = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.connect_calls = 0
        self.handshakes = 0
        self.io_calls = []
        self.error = None
        self.cancelled = False

    async def connect(self):
        self.connect_calls += 1
        if self.is_connected or self.connecting:
            return
        self.connecting = True
        self.handshakes += 1
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            # The real driver also leaves CONNECTING after direct cancellation.
            self.cancelled = True
            raise
        if self.error is not None:
            self.connecting = False
            raise self.error
        self.connecting = False
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.connecting = False

    def check_io(self, operation):
        self.io_calls.append(operation)
        if not self.is_connected:
            raise RuntimeError("I/O started before handshake completed")

    async def read(self, tags, *, optimize=True):
        self.check_io("read")
        return [42] * len(tags)

    async def write(self, tags, values):
        self.check_io("write")

    async def get_cpu_info(self):
        self.check_io("health")
        return {}


class Scenario:
    def __init__(self):
        self.coord = S7Coordinator(
            HomeAssistant(),
            host="plc.local",
            rack=0,
            slot=1,
            op_timeout=0.5,
            max_retries=0,
            enable_write_batching=False,
        )
        self.client = ConnectingClient()
        self.coord._connection.client = self.client
        # The repository's HA stub omits state publication.
        self.coord.async_set_updated_data = MagicMock()
        self.tasks = []

    async def start(self, operation):
        """Wait until the caller enters its operation, without real-time sleeps."""
        entered = asyncio.Event()

        async def run():
            entered.set()
            return await operation()

        task = asyncio.create_task(run())
        self.tasks.append(task)
        await asyncio.wait_for(entered.wait(), timeout=3)
        return task

    async def first_connect(self):
        task = await self.start(self.coord.connect)
        await asyncio.wait_for(self.client.entered.wait(), timeout=3)
        return task


@asynccontextmanager
async def scenario():
    case = Scenario()
    try:
        yield case
    finally:
        # Release before cancelling callers so future shared connection owners
        # can also finish. Shutdown must drain any coordinator-owned work.
        case.client.release.set()
        for task in case.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*case.tasks, return_exceptions=True)
        await asyncio.wait_for(case.coord.async_shutdown(), timeout=3)


async def test_single_handshake_and_established_connection_reuse():
    async with scenario() as case:
        first = await case.first_connect()
        assert not first.done()
        assert not case.coord.is_connected()
        case.client.release.set()
        await asyncio.wait_for(first, timeout=3)
        await asyncio.gather(case.coord.connect(), case.coord.connect())
        assert case.coord.is_connected()
        assert case.client.handshakes == 1
        assert case.client.connect_calls == 1


@pytest.mark.parametrize("operation", ["connect", "poll", "write", "health"])
async def test_concurrent_operation_waits_for_the_same_handshake(operation):
    async with scenario() as case:
        await case.coord.add_item("value", "DB1,W0")
        first = await case.first_connect()
        operations = {
            "connect": case.coord.connect,
            "poll": case.coord._async_update_data,
            "write": lambda: case.coord.write_batched("DB1,W0", 7),
            "health": case.coord.async_health_check,
        }
        second = await case.start(operations[operation])
        assert not second.done(), "Caller completed before the shared handshake"
        assert case.client.io_calls == [], "PLC I/O must wait for connection"
        case.client.release.set()
        first_result, result = await asyncio.wait_for(
            asyncio.gather(first, second), timeout=3
        )
        assert first_result is None
        assert case.coord.is_connected()
        assert case.client.handshakes == 1
        if operation == "poll":
            assert result == {"value": 42}
        elif operation == "health":
            assert result["ok"] is True
        else:
            assert result is None


async def test_failed_handshake_reaches_all_connection_waiters():
    async with scenario() as case:
        case.client.error = OSError("handshake refused")
        first = await case.first_connect()
        second = await case.start(case.coord.connect)
        case.client.release.set()
        results = await asyncio.wait_for(
            asyncio.gather(first, second, return_exceptions=True), timeout=3
        )
        assert all(isinstance(result, RuntimeError) for result in results), results
        assert all("handshake refused" in str(result) for result in results)
        assert not case.coord.is_connected()
        assert case.client.handshakes == 1


async def test_a_later_call_can_recover_after_failed_handshake():
    async with scenario() as case:
        case.client.error = OSError("handshake refused")
        first = await case.first_connect()
        case.client.release.set()
        with pytest.raises(RuntimeError, match="handshake refused"):
            await asyncio.wait_for(first, timeout=3)
        case.client.error = None
        await asyncio.wait_for(case.coord.connect(), timeout=3)
        assert case.coord.is_connected()
        assert case.client.handshakes == 2


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_cancelling_one_waiter_does_not_cancel_the_other(cancel_first):
    async with scenario() as case:
        first = await case.first_connect()
        second = await case.start(case.coord.connect)
        assert not second.done(), "Both callers must await the shared handshake"
        cancelled, survivor = (first, second) if cancel_first else (second, first)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert not survivor.done()
        case.client.release.set()
        await asyncio.wait_for(survivor, timeout=3)
        assert case.coord.is_connected()
        assert case.client.handshakes == 1
        assert not case.client.cancelled


async def test_connection_can_complete_after_its_only_waiter_is_cancelled():
    """Allow either continuing the owned attempt or cleaning up and restarting."""
    async with scenario() as case:
        first = await case.first_connect()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        case.client.release.set()
        await asyncio.wait_for(case.coord.connect(), timeout=3)
        assert case.coord.is_connected(), "A cancelled caller left CONNECTING stuck"


def expire_first_drain(monkeypatch):
    """Exercise lifecycle cancellation without waiting the 0.5 s grace period."""
    real_wait = asyncio.wait
    expired = False

    async def controlled_wait(futures, *, timeout):
        nonlocal expired
        if not expired and timeout == 0.5:
            expired = True
            return set(), set(futures)
        return await real_wait(futures, timeout=timeout)

    monkeypatch.setattr(asyncio, "wait", controlled_wait)


@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
@pytest.mark.parametrize("waiters", [1, 2])
async def test_stop_drains_handshake_and_rejects_every_waiter(
    monkeypatch, stop, waiters
):
    async with scenario() as case:
        expire_first_drain(monkeypatch)
        tasks = [await case.first_connect()]
        if waiters == 2:
            tasks.append(await case.start(case.coord.connect))
        await asyncio.wait_for(getattr(case.coord, stop)(), timeout=3)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(
            isinstance(result, (HomeAssistantError, asyncio.CancelledError))
            for result in results
        ), results
        assert not case.coord.is_connected()
        assert not case.client.connecting
        assert not case.coord._connection.stopping
        assert not case.coord._connection._io_tasks
        assert not case.coord._connection._io_completions
        with pytest.raises(HomeAssistantError):
            await case.coord.connect()


async def test_two_coordinators_connect_independently():
    async with scenario() as left, scenario() as right:
        first = await left.first_connect()
        second = await right.first_connect()
        left.client.release.set()
        await asyncio.wait_for(first, timeout=3)
        assert left.coord.is_connected()
        assert not second.done()
        assert not right.coord.is_connected()
        right.client.release.set()
        await asyncio.wait_for(second, timeout=3)
        assert right.coord.is_connected()
        assert left.client.handshakes == right.client.handshakes == 1


async def test_real_pys7_connect_does_not_report_success_during_tcp_open(monkeypatch):
    """Use installed pyS7, replacing only TCP opening with an event-controlled wait."""
    coord = S7Coordinator(
        HomeAssistant(),
        host="192.0.2.1",
        rack=0,
        slot=1,
        op_timeout=0.5,
    )
    entered = asyncio.Event()
    tcp_calls = []

    async def open_connection(*args, **kwargs):
        tcp_calls.append((args, kwargs))
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    first = asyncio.create_task(coord.connect())
    second = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        second_entered = asyncio.Event()

        async def join():
            second_entered.set()
            await coord.connect()

        second = asyncio.create_task(join())
        await asyncio.wait_for(second_entered.wait(), timeout=3)
        assert not second.done(), "Real pyS7 returned while TCP opening was pending"
        assert not coord.is_connected()
        assert len(tcp_calls) == 1
    finally:
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (first, second) if task is not None),
            return_exceptions=True,
        )
        await asyncio.wait_for(coord.async_shutdown(), timeout=3)


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("writer_first", [False, True])
async def test_cancelled_write_waiter_preserves_another_callers_handshake(
    batch, writer_first
):
    async with scenario() as case:
        operation = (
            (lambda: case.coord.write_multi([("DB1,W0", 7)]))
            if batch
            else (lambda: case.coord.write("DB1,W0", 7))
        )
        if writer_first:
            writer = await case.start(operation)
            await asyncio.wait_for(case.client.entered.wait(), timeout=3)
            connector = await case.start(case.coord.connect)
        else:
            connector = await case.first_connect()
            writer = await case.start(operation)
        assert not writer.done()
        assert not connector.done()
        writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer
        assert case.client.connecting
        assert not case.client.cancelled
        assert not case.coord._connection.stopping
        case.client.release.set()
        await asyncio.wait_for(connector, timeout=3)
        assert case.coord.is_connected()
        assert case.client.handshakes == 1
        assert case.client.io_calls == []


@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
async def test_stop_owns_handshake_after_all_callers_cancel(monkeypatch, stop):
    async with scenario() as case:
        expire_first_drain(monkeypatch)
        caller = await case.first_connect()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert case.client.connecting
        await asyncio.wait_for(getattr(case.coord, stop)(), timeout=3)
        assert case.client.cancelled
        assert not case.client.connecting
        assert not case.coord.is_connected()
        assert case.coord._connection._connect_task is None
        assert not case.coord._connection._io_tasks
        assert not case.coord._connection._io_completions


async def test_failed_owned_handshake_without_waiters_allows_a_later_attempt():
    async with scenario() as case:
        case.client.error = OSError("orphaned handshake refused")
        caller = await case.first_connect()
        attempt = case.coord._connection._connect_task
        finished = asyncio.Event()
        attempt.add_done_callback(lambda _: finished.set())
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        case.client.release.set()
        await asyncio.wait_for(finished.wait(), timeout=3)
        assert case.coord._connection._connect_task is None
        case.client.error = None
        await asyncio.wait_for(case.coord.connect(), timeout=3)
        assert case.coord.is_connected()
        assert case.client.handshakes == 2


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_config_connection_check_always_shuts_down_its_temporary_coordinator(
    monkeypatch, outcome
):
    from custom_components.s7plc import config_flow

    async with scenario() as case:
        expire_first_drain(monkeypatch)
        monkeypatch.setattr(config_flow, "S7Coordinator", lambda *a, **kw: case.coord)
        if outcome == "failure":
            case.client.error = OSError("temporary connection refused")

        async def check():
            await config_flow._test_plc_connection(
                case.coord.hass,
                host="plc.local",
                connection_type="rack_slot",
                rack=0,
                slot=1,
                local_tsap=None,
                remote_tsap=None,
                pys7_connection_type="pg",
                port=102,
                scan_interval=0.5,
                op_timeout=0.5,
                max_retries=0,
                backoff_initial=0.5,
                backoff_max=2,
                optimize_read=True,
                enable_write_batching=False,
                enable_metrics=False,
            )

        task = await case.start(check)
        await asyncio.wait_for(case.client.entered.wait(), timeout=3)
        if outcome == "cancelled":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
        else:
            case.client.release.set()
            if outcome == "failure":
                with pytest.raises(RuntimeError, match="temporary connection refused"):
                    await asyncio.wait_for(task, timeout=3)
            else:
                await asyncio.wait_for(task, timeout=3)
        assert case.coord._connection.shutdown
        assert case.coord._connection._connect_task is None
        assert not case.coord.is_connected()
        assert not case.client.connecting
        assert not case.coord._connection._io_tasks
        assert not case.coord._connection._io_completions


@pytest.mark.parametrize("stop", ["async_shutdown", "async_disable_connection"])
async def test_stop_owns_scheduled_handshake_before_io_registration(monkeypatch, stop):
    """A scheduled connection remains owned before its I/O scope has started."""
    async with scenario() as case:
        expire_first_drain(monkeypatch)
        scheduled = asyncio.Event()
        original_connect = case.coord._connection._connect

        async def delayed_start(generation):
            scheduled.set()
            await asyncio.Event().wait()
            await original_connect(generation)

        # Delay dispatch only: this exercises the interval before _io_operation
        # can register the owned handshake, after its caller has been cancelled.
        monkeypatch.setattr(case.coord._connection, "_connect", delayed_start)
        caller = await case.start(case.coord.connect)
        await asyncio.wait_for(scheduled.wait(), timeout=3)
        attempt = case.coord._connection._connect_task
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert not case.coord._connection._io_tasks
        assert not case.coord._connection._io_completions
        assert not attempt.done()
        await asyncio.wait_for(getattr(case.coord, stop)(), timeout=3)
        assert attempt.done()
        assert case.coord._connection._connect_task is None
        assert case.client.connect_calls == 0
        assert not case.coord._connection.stopping
