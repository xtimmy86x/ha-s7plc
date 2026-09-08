"""Concurrency and race-condition tests for S7Coordinator."""

from __future__ import annotations

import asyncio

import pytest
from conftest import DummyTag

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import TagPlan

# ============================================================================
# Helpers
# ============================================================================


def _make_coordinator(**kwargs) -> S7Coordinator:
    """Create a coordinator with real (un-stubbed) connection methods."""
    hass = coordinator.HomeAssistant()
    return S7Coordinator(hass, host="plc.local", **kwargs)


# ============================================================================
# Test 1 – Reconnect before reading and reuse of the established connection
# ============================================================================


@pytest.mark.asyncio
async def test_poll_waits_for_connection_and_reuses_connected_client():
    """Polling waits for the handshake; later callers reuse the connection.

    No test-side coordinator lock is added. This does not claim that the
    coordinator serializes simultaneous handshakes on an unconnected client.
    """
    coord = _make_coordinator(max_retries=0)
    entered, release = asyncio.Event(), asyncio.Event()
    operations = []

    class FakeClient:
        is_connected = False

        async def connect(self):
            operations.append("connect-start")
            entered.set()
            await release.wait()
            self.is_connected = True
            operations.append("connect-end")

        async def read(self, tags, optimize=True):
            assert self.is_connected
            operations.append("read")
            return [42]

        async def disconnect(self):
            self.is_connected = False

    coord._client = FakeClient()
    await coord.add_item("value", "DB1,W0")
    polling = asyncio.create_task(coord._async_update_data())
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        assert not polling.done()
        assert operations == ["connect-start"]
        release.set()
        assert await asyncio.wait_for(polling, timeout=3) == {"value": 42}
        await asyncio.gather(coord.connect(), coord.connect())
        assert operations == ["connect-start", "connect-end", "read"]
    finally:
        release.set()
        if not polling.done():
            polling.cancel()
        await asyncio.gather(polling, return_exceptions=True)
        await coord.async_shutdown()


# ============================================================================
# Test 2 – Disconnect during read
#
# A read is in progress; disconnect() is called mid-flight.
# The read must raise (UpdateFailed), and no zombie task must remain.
# ============================================================================


@pytest.mark.asyncio
async def test_disconnect_during_read():
    """Disconnect while a read is in progress must not leave zombie tasks."""
    coord = _make_coordinator()
    coord._max_retries = 0  # no retries – fail immediately

    read_started = asyncio.Event()

    class FakeClient:
        is_connected = True

        async def disconnect(self):
            FakeClient.is_connected = False

        def read(self, tags, optimize=True):
            read_started.set()
            # Simulate the socket being torn down mid-read
            raise OSError("Connection reset by peer")

    coord._client = FakeClient()

    tag = DummyTag(data_type=coordinator.DataType.WORD, start=0)
    plans = [TagPlan("topic/a", tag)]

    # Patch _build_tag_cache so _async_update_data has something to read
    coord._plans_batch = {"topic/a": plans[0]}
    coord._plans_str = {}
    coord._items["topic/a"] = "DB1.DBW0"
    coord._item_scan_intervals["topic/a"] = 0.5
    coord._item_next_read["topic/a"] = 0.0

    async def disconnect_after_read_starts():
        await read_started.wait()
        await coord.disconnect()

    # Run read + disconnect concurrently
    read_task = asyncio.create_task(coord._async_update_data())
    disconnect_task = asyncio.create_task(disconnect_after_read_starts())

    with pytest.raises(coordinator.UpdateFailed):
        await read_task

    await disconnect_task

    # No lingering tasks – sanity: both completed without cancellation leak
    assert read_task.done()
    assert disconnect_task.done()


# ============================================================================
# Test 3 – Unload during retry sleep
#
# The retry loop is sleeping between attempts; unload cancels the task.
# The sleep must be interrupted, and no further retry attempt must occur.
# ============================================================================


@pytest.mark.asyncio
async def test_unload_cancels_retry_sleep():
    """Cancelling during retry back-off must stop immediately."""
    coord = _make_coordinator(max_retries=5, backoff_initial=10.0)

    attempt_count = 0

    # Use the REAL _sleep (asyncio.sleep) so cancellation propagates.
    async def real_sleep(seconds):
        await asyncio.sleep(seconds)

    coord._sleep = real_sleep

    async def fake_ensure():
        pass

    async def fake_drop():
        pass

    coord._ensure_connected = fake_ensure
    coord._drop_connection = fake_drop

    def always_fail():
        nonlocal attempt_count
        attempt_count += 1
        raise RuntimeError("PLC offline")

    task = asyncio.create_task(coord._retry(always_fail))

    # Let the first attempt fail and the sleep begin
    await asyncio.sleep(0.05)
    assert attempt_count >= 1, "At least one attempt should have been made"

    # Simulate unload → cancel the running task
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    saved_count = attempt_count
    # Give the loop a full turn to prove no more attempts sneak through
    await asyncio.sleep(0.05)
    assert attempt_count == saved_count, (
        "No further retry attempts should occur after cancellation"
    )


# ============================================================================
# Test 4 – Overlapping poll and write through the driver's shared I/O lock
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("first_kind", ["read", "write"])
async def test_write_and_poll_overlap_without_corrupting_results(first_kind):
    """Keep both operations in flight using events and the modeled driver lock."""
    coord = _make_coordinator(enable_write_batching=False, max_retries=0)
    first_entered = asyncio.Event()
    second_requested = asyncio.Event()
    release = asyncio.Event()
    operation_log = []

    class FakeClient:
        is_connected = True

        def __init__(self):
            self.lock = asyncio.Lock()
            self.value = 42
            self.read_calls = []
            self.write_calls = []

        async def execute(self, kind):
            # Model pyS7's packet lock. The coordinator now gates dispatch too,
            # so a cancelled packet can be cleaned up before the next request.
            async with self.lock:
                operation_log.append((kind, "start"))
                if kind == first_kind:
                    first_entered.set()
                    await release.wait()
                if kind == "write":
                    self.value = 99
                operation_log.append((kind, "end"))
                return self.value

        async def read(self, tags, optimize=True):
            self.read_calls.append((tags, optimize))
            return [await self.execute("read")]

        async def write(self, tags, payloads):
            self.write_calls.append((tags, payloads))
            await self.execute("write")

        async def disconnect(self):
            self.is_connected = False

    client = FakeClient()
    coord._client = client
    await coord.add_item("value", "DB1,W0")

    def start(kind):
        async def operation():
            if kind != first_kind:
                second_requested.set()
            if kind == "read":
                return await coord._async_update_data()
            return await coord.write("DB1,W0", 99)

        return asyncio.create_task(operation())

    first = start(first_kind)
    second = None
    try:
        await asyncio.wait_for(first_entered.wait(), timeout=3)
        second_kind = "write" if first_kind == "read" else "read"
        second = start(second_kind)
        await asyncio.wait_for(second_requested.wait(), timeout=3)
        assert not first.done()
        assert not second.done()
        assert operation_log == [(first_kind, "start")]
        assert len(client.read_calls) + len(client.write_calls) == 1
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=3)
        poll_result, write_result = results if first_kind == "read" else results[::-1]
        assert poll_result == {"value": 42 if first_kind == "read" else 99}
        assert write_result is True
        assert coord.get_topic_read_revision("value") == 1
        assert operation_log == [
            (first_kind, "start"), (first_kind, "end"),
            (second_kind, "start"), (second_kind, "end"),
        ]
        assert len(client.read_calls) == len(client.write_calls) == 1
        assert client.read_calls[0][1] is True
        assert client.read_calls[0][0] == client.write_calls[0][0]
        assert client.write_calls[0][1] == [99]
    finally:
        release.set()
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await coord.async_shutdown()


# ============================================================================
# Test 5 – Stale read after reconnect
#
# A slow read was in-flight when a reconnect replaced the client.
# The old read completes late and its result must be discarded –
# _async_update_data must reflect the *new* client's values.
# ============================================================================


@pytest.mark.asyncio
async def test_stale_read_discarded_after_reconnect():
    """A read from an old connection must not overwrite data from the new one."""
    coord = _make_coordinator(max_retries=2, backoff_initial=0.0)

    tag = DummyTag(data_type=coordinator.DataType.WORD, start=0)
    coord._plans_batch = {"topic/a": TagPlan("topic/a", tag)}
    coord._plans_str = {}
    coord._items["topic/a"] = "DB1.DBW0"
    coord._item_scan_intervals["topic/a"] = 0.5
    coord._item_next_read["topic/a"] = 0.0

    # The old client fails; after reconnect the new client succeeds.
    reconnect_happened = False

    class OldClient:
        is_connected = True

        def read(self, tags, optimize=True):
            raise OSError("Connection lost")

        async def disconnect(self):
            OldClient.is_connected = False

    class NewClient:
        is_connected = True

        def read(self, tags, optimize=True):
            return [999]  # fresh value

        async def disconnect(self):
            NewClient.is_connected = False

    coord._client = OldClient()

    async def drop_and_swap():
        nonlocal reconnect_happened
        if coord._client is not None:
            try:
                await coord._client.disconnect()
            except Exception:
                pass
        coord._client = None
        reconnect_happened = True

    coord._drop_connection = drop_and_swap

    async def reconnect_ensure():
        if coord._client is None or not coord._client.is_connected:
            coord._client = NewClient()

    coord._ensure_connected = reconnect_ensure

    async def instant_sleep(seconds):
        pass  # skip backoff delay

    coord._sleep = instant_sleep

    # _retry will: call OldClient.read → OSError → drop (swap) →
    # sleep → ensure (NewClient) → NewClient.read → 999
    result = await coord._async_update_data()

    assert reconnect_happened, "Reconnect should have occurred"
    assert result["topic/a"] == 999, (
        "Data must come from the new client, not from the stale connection"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("second_fails", [False, True])
async def test_overlapping_plc_polls_keep_results_and_errors_isolated(second_fails):
    """Two PLCs in the same HA instance may use identical topics and addresses."""
    hass = coordinator.HomeAssistant()
    first = S7Coordinator(hass, host="plc-a.local", max_retries=0)
    second = S7Coordinator(hass, host="plc-b.local", max_retries=0)

    class FakeClient:
        is_connected = True

        def __init__(self, value, fail=False):
            self.value = value
            self.fail = fail
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = []

        async def read(self, tags, optimize=True):
            self.calls.append((tags, optimize))
            self.entered.set()
            await self.release.wait()
            if self.fail:
                raise OSError("second PLC unavailable")
            return [self.value]

        async def disconnect(self):
            self.is_connected = False

    first_client = FakeClient(42)
    second_client = FakeClient(84, fail=second_fails)
    first._client = first_client
    second._client = second_client
    for coord in (first, second):
        await coord.add_item("value", "DB1,W0")
    first._data_cache = {"value": -1}
    second._data_cache = {"value": -2}
    tasks = [asyncio.create_task(coord._async_update_data()) for coord in (first, second)]
    try:
        await asyncio.wait_for(
            asyncio.gather(first_client.entered.wait(), second_client.entered.wait()),
            timeout=3,
        )
        first_client.release.set()
        assert await asyncio.wait_for(tasks[0], timeout=3) == {"value": 42}
        assert not tasks[1].done()
        assert second._data_cache == {"value": -2}
        assert second.get_topic_read_revision("value") == 0

        second_client.release.set()
        if second_fails:
            with pytest.raises(coordinator.UpdateFailed, match="second PLC unavailable"):
                await asyncio.wait_for(tasks[1], timeout=3)
            assert second._data_cache == {"value": -2}
            assert second.get_topic_read_revision("value") == 0
            assert second.last_health_ok is False
            assert not second_client.is_connected
        else:
            assert await asyncio.wait_for(tasks[1], timeout=3) == {"value": 84}
            assert second.get_topic_read_revision("value") == 1
            assert second.last_health_ok is True
        assert first._data_cache == {"value": 42}
        assert first.get_topic_read_revision("value") == 1
        assert first.last_health_ok is True
        assert first_client.is_connected
        assert len(first_client.calls) == len(second_client.calls) == 1
    finally:
        first_client.release.set()
        second_client.release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await first.async_shutdown()
        await second.async_shutdown()
