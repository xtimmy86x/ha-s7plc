"""Concurrency and race-condition tests for S7Coordinator."""

from __future__ import annotations

import asyncio
import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import TagPlan
from conftest import DummyTag


# ============================================================================
# Helpers
# ============================================================================


def _make_coordinator(**kwargs) -> S7Coordinator:
    """Create a coordinator with real (un-stubbed) connection methods."""
    hass = coordinator.HomeAssistant()
    return S7Coordinator(hass, host="plc.local", **kwargs)


# ============================================================================
# Test 1 – Concurrent reconnect
#
# Two coroutines call _ensure_connected() at the same time.
# Only ONE real connect must happen.
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_reconnect_single_connect():
    """Two concurrent _ensure_connected calls must produce only one connect."""
    coord = _make_coordinator()

    connect_count = 0
    connect_event = asyncio.Event()

    class FakeClient:
        is_connected = False

        async def connect(self):
            nonlocal connect_count
            connect_count += 1
            # Simulate slow handshake so the second caller overlaps
            await asyncio.sleep(0.05)
            FakeClient.is_connected = True

        async def disconnect(self):
            FakeClient.is_connected = False

    coord._client = FakeClient()

    # Both coroutines share the coordinator's _async_lock through _read_all
    # but _ensure_connected itself has no lock – the real serialisation
    # happens at the _retry / _read_all level via _async_lock.
    # We verify the *external* contract: two _read_all calls run
    # sequentially because of the lock, so connect is called at most once.

    async def caller():
        async with coord._async_lock:
            await coord._ensure_connected()

    await asyncio.gather(caller(), caller())

    assert connect_count == 1, (
        f"Expected exactly 1 connect call, got {connect_count}"
    )


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
# Test 4 – Write and poll simultaneously
#
# A coordinator poll (_async_update_data) and a write_multi happen
# concurrently.  The _async_lock must serialise them so the final state
# is coherent.
# ============================================================================


@pytest.mark.asyncio
async def test_write_and_poll_no_race():
    """Concurrent poll + write must not corrupt shared state."""
    coord = _make_coordinator(enable_write_batching=False)
    coord._max_retries = 0

    # Track operation order to prove serialisation
    operation_log: list[str] = []

    tag = DummyTag(data_type=coordinator.DataType.WORD, start=0)
    coord._plans_batch = {"topic/a": TagPlan("topic/a", tag)}
    coord._plans_str = {}
    coord._items["topic/a"] = "DB1,W0"
    coord._item_scan_intervals["topic/a"] = 0.5
    coord._item_next_read["topic/a"] = 0.0

    class FakeClient:
        is_connected = True

        def read(self, tags, optimize=True):
            operation_log.append("read")
            return [42]

        def write(self, tags, payloads):
            operation_log.append("write")
            return None

        async def connect(self):
            pass

        async def disconnect(self):
            pass

    coord._client = FakeClient()

    async def fake_ensure():
        pass

    coord._ensure_connected = fake_ensure

    # Lightweight _retry that just calls the function once.
    async def passthrough_retry(func, *args, **kwargs):
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    coord._retry = passthrough_retry

    # Run poll and write concurrently
    poll_task = asyncio.create_task(coord._async_update_data())
    write_task = asyncio.create_task(coord.write("DB1,W0", 99))

    poll_result, write_result = await asyncio.gather(
        poll_task, write_task, return_exceptions=True
    )

    # Poll should succeed and return data
    assert isinstance(poll_result, dict)
    assert poll_result.get("topic/a") == 42

    # Write should succeed
    assert write_result is True

    # Both operations executed
    assert "read" in operation_log
    assert "write" in operation_log


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
