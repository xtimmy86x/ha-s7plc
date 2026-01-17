"""Tests for S7Coordinator - Refactored with fixtures."""

from __future__ import annotations

import struct
import pytest
import asyncio

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import StringPlan, TagPlan
from conftest import DummyCoordinatorClient, DummyTag


# ============================================================================
# Helper Functions
# ============================================================================


def make_coordinator(monkeypatch, **kwargs):
    """Factory function to create a coordinator for testing."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local", **kwargs)
    # Avoid interacting with a real S7 client
    monkeypatch.setattr(coord, "_ensure_connected", lambda: None)
    monkeypatch.setattr(coord, "_drop_connection", lambda: None)
    return coord


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def coord_factory(monkeypatch):
    """Factory fixture for creating coordinators."""
    def _create_coordinator(**kwargs):
        return make_coordinator(monkeypatch, **kwargs)
    return _create_coordinator


# ============================================================================
# Retry Mechanism Tests
# ============================================================================


def test_retry_retries_until_success(coord_factory):
    """Test retry mechanism retries until success."""
    coord = coord_factory()

    sleep_calls: list[float] = []
    ensure_calls = 0
    drop_calls = 0

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    def fake_ensure():
        nonlocal ensure_calls
        ensure_calls += 1

    def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._sleep = fake_sleep
    coord._ensure_connected = fake_ensure
    coord._drop_connection = fake_drop

    attempts = []

    def flaky():
        attempts.append("call")
        if len(attempts) < 2:
            raise RuntimeError("fail")
        return "ok"

    result = coord._retry(flaky)

    assert result == "ok"
    assert ensure_calls == 2
    assert drop_calls == 1
    assert sleep_calls == [coord._backoff_initial]


def test_retry_raises_after_exhaustion(coord_factory):
    """Test retry mechanism raises after exhausting retries."""
    coord = coord_factory()
    coord._max_retries = 1

    drop_calls = 0

    def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._drop_connection = fake_drop

    with pytest.raises(RuntimeError):
        coord._retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert drop_calls == 2


def test_retry_handles_struct_error(coord_factory):
    """Test retry mechanism handles struct errors."""
    coord = coord_factory()
    coord._max_retries = 0

    drop_calls = 0

    def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._drop_connection = fake_drop

    with pytest.raises(RuntimeError):
        coord._retry(lambda: (_ for _ in ()).throw(struct.error()))

    assert drop_calls == 1


# ============================================================================
# Batch Reading Tests
# ============================================================================


def test_read_batch_deduplicates_tags(coord_factory, dummy_tag, dummy_client):
    """Test read batch deduplicates identical tags."""
    coord = coord_factory()

    tag_a = dummy_tag(data_type=coordinator.DataType.WORD, start=0)
    tag_b = dummy_tag(data_type=coordinator.DataType.DINT, start=4)

    plans = [
        TagPlan("topic/a", tag_a, lambda v: v + 1),
        TagPlan("topic/b", dummy_tag(data_type=coordinator.DataType.WORD, start=0)),
        TagPlan("topic/c", tag_b, lambda v: v * 2),
    ]

    client = dummy_client([[10, 5]])
    coord._client = client
    coord._retry = lambda func: func()

    results = coord._read_batch(plans)

    assert client.calls == [([tag_a, tag_b], True)]
    assert results == {
        "topic/a": 11,
        "topic/b": 10,
        "topic/c": 10,
    }


def test_read_batch_raises_on_error(coord_factory, dummy_tag, dummy_client):
    """Test read batch raises on client error."""
    coord = coord_factory()

    tag = dummy_tag(data_type=coordinator.DataType.WORD)
    plans = [TagPlan("topic/a", tag), TagPlan("topic/b", tag)]

    client = dummy_client([OSError("boom")])
    coord._client = client
    coord._retry = lambda func: func()

    with pytest.raises(OSError):
        coord._read_batch(plans)


# ============================================================================
# Update Data Tests
# ============================================================================


def test_async_update_data_respects_item_scan_interval(coord_factory, dummy_tag):
    """Test async update respects item-specific scan intervals."""
    coord = coord_factory()

    plan = TagPlan("topic/a", dummy_tag())
    coord._plans_batch = {"topic/a": plan}
    coord._plans_str = {}
    coord._items["topic/a"] = "DB1,X0.0"
    coord._item_scan_intervals["topic/a"] = 2.0
    coord._item_next_read["topic/a"] = 0.0
    coord._data_cache.clear()

    coord._update_min_interval_locked()
    assert coord.update_interval.total_seconds() == pytest.approx(2.0)

    results = {"topic/a": 7}
    read_calls: list[tuple[list[TagPlan], list[StringPlan]]] = []

    def fake_read_all(plans_batch, plans_str):
        read_calls.append((plans_batch, plans_str))
        return results

    coord._read_all = fake_read_all

    async def fake_async_add_executor_job(func, *args):
        return func(*args)

    coord.hass.async_add_executor_job = fake_async_add_executor_job

    data_first = asyncio.run(coord._async_update_data())
    assert data_first == results
    assert coord._data_cache == results
    assert read_calls == [([plan], [])]
    coord._item_next_read["topic/a"] += 100.0

    data_second = asyncio.run(coord._async_update_data())
    assert data_second == results
    assert len(read_calls) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_read_all_raises_update_failed_on_connection_error(coord_factory):
    """Test read_all raises UpdateFailed on connection error."""
    coord = coord_factory()

    def raise_connect():
        raise RuntimeError("connect boom")

    coord._ensure_connected = raise_connect

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_all([], [])

    assert "connect boom" in str(err.value)


def test_read_all_raises_update_failed_on_read_error(coord_factory, dummy_tag):
    """Test read_all raises UpdateFailed on read error."""
    coord = coord_factory()
    plans = [TagPlan("topic/a", dummy_tag())]

    drop_calls: list[bool] = []

    def fake_drop():
        drop_calls.append(True)

    coord._drop_connection = fake_drop

    def raise_read(plans):
        raise RuntimeError("read boom")

    coord._read_batch = raise_read

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_all(plans, [])

    assert drop_calls == [True]
    assert "read boom" in str(err.value)

    
# ============================================================================
# String Reading Tests
# ============================================================================


def test_read_strings_raises_on_timeout(coord_factory, monkeypatch, caplog):
    """Test read_strings raises on timeout."""
    coord = coord_factory()

    plans = [
        StringPlan("topic/a", 1, 0),
        StringPlan("topic/b", 2, 0),
    ]

    times = iter([10.0, 60.0])
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: next(times))

    read_calls = []

    def fake_read(db, start, is_wstring=False):
        read_calls.append((db, start))
        return "value"

    coord._read_s7_string = fake_read

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_strings(plans, deadline=50.0)

    assert "timeout" in str(err.value).lower()
    assert read_calls == [(1, 0)]
    assert any("String read timeout" in message for message in caplog.messages)


def test_read_strings_raises_on_error(coord_factory, monkeypatch, caplog):
    """Test read_strings raises on read error."""
    coord = coord_factory()

    plans = [StringPlan("topic/a", 1, 0)]

    def fake_read(db, start, is_wstring=False):
        raise RuntimeError("boom")

    coord._read_s7_string = fake_read
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: 0.0)

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_strings(plans, deadline=50.0)

    assert "boom" in str(err.value)
    assert any("String read error" in message for message in caplog.messages)


def test_read_all_propagates_string_failures(coord_factory):
    """Test read_all propagates string reading failures."""
    coord = coord_factory()

    plans = [StringPlan("topic/a", 1, 0)]

    coord._read_batch = lambda plans: {}
    coord._read_strings = lambda plans, deadline: (_ for _ in ()).throw(
        coordinator.UpdateFailed("timeout")
    )

    with pytest.raises(coordinator.UpdateFailed):
        coord._read_all([], plans)


# ============================================================================
# Read One Tests
# ============================================================================


def test_read_one_handles_bit_string_and_scalars(coord_factory, dummy_tag, monkeypatch):
    """Test read_one handles different data types correctly."""
    coord = coord_factory()

    # String path
    string_tag = dummy_tag(
        data_type=coordinator.DataType.CHAR,
        length=8,
        db_number=1,
        start=2,
    )

    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda addr: string_tag,
    )

    coord._read_s7_string = lambda db, start: "test"
    assert coord._read_one("STRING") == "test"

    # Bit normalization
    bit_tag = dummy_tag(data_type=coordinator.DataType.BIT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: bit_tag)
    coord._retry = lambda func: [1]
    assert coord._read_one("BIT") is True

    # REAL post-processing
    real_tag = DummyTag(data_type=coordinator.DataType.REAL)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: real_tag)
    coord._retry = lambda func: [1.234]
    assert coord._read_one("REAL") == pytest.approx(1.2)


# ============================================================================
# Write Tests
# ============================================================================


def test_write_number_handles_numeric_types(coord_factory, dummy_tag, monkeypatch):
    """Test write_number handles different numeric types correctly."""
    coord = coord_factory()

    writes: list[tuple[list[DummyTag], list[float | int]]] = []

    class DummyClient:
        def write(self, tags, values):
            writes.append((tags, values))

    coord._client = DummyClient()
    coord._retry = lambda func: func()

    int_tag = dummy_tag(data_type=coordinator.DataType.INT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: int_tag)

    assert coord.write_number("DB1,W0", 12.6)
    assert writes == [([int_tag], [13])]

    writes.clear()
    real_tag = dummy_tag(data_type=coordinator.DataType.REAL)
    coord._write_tags.clear()
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: real_tag)

    assert coord.write_number("DB1,D4", 7.25)
    assert writes[0][0] == [real_tag]
    assert writes[0][1][0] == pytest.approx(7.25)


def test_write_number_rejects_non_numeric(coord_factory, dummy_tag, monkeypatch):
    """Test write_number rejects non-numeric data types."""
    coord = coord_factory()

    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.BIT),
    )

    with pytest.raises(ValueError):
        coord.write_number("Q0.0", 1)

    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.CHAR, length=10),
    )

    with pytest.raises(ValueError):
        coord.write_number("DB1,STRING", 42)


# ============================================================================
# Connection Tests
# ============================================================================


def test_is_connected_no_client():
    """Test is_connected when no client exists."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    assert coord.is_connected() is False


def test_is_connected_client_no_socket(monkeypatch):
    """Test is_connected when client exists but no socket."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    # Mock client without socket
    mock_client = type('MockClient', (), {})()
    coord._client = mock_client
    
    assert coord.is_connected() is False


def test_is_connected_with_socket(monkeypatch):
    """Test is_connected when client has socket."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    # Mock client with socket
    mock_client = type('MockClient', (), {'socket': object()})()
    coord._client = mock_client
    
    assert coord.is_connected() is True


def test_connect_calls_ensure_connected(monkeypatch):
    """Test connect method calls _ensure_connected."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    connected = []
    monkeypatch.setattr(coord, "_ensure_connected", lambda: connected.append(True))
    
    coord.connect()
    assert len(connected) == 1


def test_disconnect_calls_drop_connection(monkeypatch):
    """Test disconnect method calls _drop_connection."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    disconnected = []
    monkeypatch.setattr(coord, "_drop_connection", lambda: disconnected.append(True))
    
    coord.disconnect()
    assert len(disconnected) == 1


def test_host_property():
    """Test host property returns correct host."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="192.168.1.100")
    
    assert coord.host == "192.168.1.100"


# ============================================================================
# Item Management Tests
# ============================================================================


def test_add_item_basic(coord_factory):
    """Test add_item stores item correctly."""
    coord = coord_factory()
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0"))
    
    assert "sensor:DB1,REAL0" in coord._items
    assert coord._items["sensor:DB1,REAL0"] == "DB1,REAL0"


def test_add_item_with_scan_interval(coord_factory):
    """Test add_item stores custom scan interval."""
    coord = coord_factory()
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0", scan_interval=2.5))
    
    assert coord._item_scan_intervals["sensor:DB1,REAL0"] == 2.5


def test_add_item_with_real_precision(coord_factory):
    """Test add_item stores real precision."""
    coord = coord_factory()
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0", real_precision=2))
    
    assert coord._item_real_precisions["sensor:DB1,REAL0"] == 2


def test_add_item_clears_real_precision_when_none(coord_factory):
    """Test add_item removes precision when set to None."""
    coord = coord_factory()
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0", real_precision=2))
    assert "sensor:DB1,REAL0" in coord._item_real_precisions
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0", real_precision=None))
    assert "sensor:DB1,REAL0" not in coord._item_real_precisions


def test_add_item_invalidates_cache(coord_factory, monkeypatch):
    """Test add_item invalidates plans cache."""
    coord = coord_factory()
    
    # Add some fake plans
    coord._plans_batch = {"fake": None}
    coord._plans_str = {"fake": None}
    coord._write_tags = {"fake": None}
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0"))
    
    # Cache should be cleared
    assert len(coord._plans_batch) == 0
    assert len(coord._plans_str) == 0
    assert len(coord._write_tags) == 0


def test_normalize_scan_interval_none_uses_default(coord_factory):
    """Test _normalize_scan_interval uses default when None."""
    coord = coord_factory(scan_interval=5.0)
    
    result = coord._normalize_scan_interval(None)
    assert result == 5.0


def test_normalize_scan_interval_negative_uses_default(coord_factory):
    """Test _normalize_scan_interval uses default for negative values."""
    coord = coord_factory(scan_interval=5.0)
    
    result = coord._normalize_scan_interval(-1.0)
    assert result == 5.0


def test_normalize_scan_interval_zero_uses_default(coord_factory):
    """Test _normalize_scan_interval uses default for zero."""
    coord = coord_factory(scan_interval=5.0)
    
    result = coord._normalize_scan_interval(0)
    assert result == 5.0


def test_normalize_scan_interval_enforces_minimum(coord_factory):
    """Test _normalize_scan_interval enforces minimum."""
    coord = coord_factory()
    
    # MIN_SCAN_INTERVAL is 0.05
    result = coord._normalize_scan_interval(0.01)
    assert result == 0.05


def test_normalize_scan_interval_accepts_valid(coord_factory):
    """Test _normalize_scan_interval accepts valid values."""
    coord = coord_factory()
    
    result = coord._normalize_scan_interval(2.5)
    assert result == 2.5


def test_normalize_scan_interval_converts_int(coord_factory):
    """Test _normalize_scan_interval converts integers."""
    coord = coord_factory()
    
    result = coord._normalize_scan_interval(3)
    assert result == 3.0


def test_normalize_scan_interval_invalid_type_uses_default(coord_factory):
    """Test _normalize_scan_interval handles invalid types."""
    coord = coord_factory(scan_interval=5.0)
    
    result = coord._normalize_scan_interval("invalid")
    assert result == 5.0


def test_update_min_interval_locked_no_items(coord_factory):
    """Test _update_min_interval_locked with no items uses default."""
    coord = coord_factory(scan_interval=5.0)
    
    coord._update_min_interval_locked()
    
    assert coord.update_interval.total_seconds() == 5.0


def test_update_min_interval_locked_finds_minimum(coord_factory):
    """Test _update_min_interval_locked finds minimum interval."""
    coord = coord_factory()
    
    coord._item_scan_intervals = {
        "topic1": 5.0,
        "topic2": 2.0,
        "topic3": 10.0,
    }
    
    coord._update_min_interval_locked()
    
    assert coord.update_interval.total_seconds() == 2.0


def test_update_min_interval_locked_enforces_minimum(coord_factory):
    """Test _update_min_interval_locked enforces MIN_SCAN_INTERVAL."""
    coord = coord_factory()
    
    coord._item_scan_intervals = {
        "topic1": 0.01,  # Below minimum
    }
    
    coord._update_min_interval_locked()
    
    assert coord.update_interval.total_seconds() == 0.05


# ============================================================================
# PDU Limit Tests
# ============================================================================


def test_get_pdu_limit_default(coord_factory):
    """Test _get_pdu_limit with default PDU size."""
    coord = coord_factory()
    coord._client = type('MockClient', (), {'pdu_length': 240})()
    
    result = coord._get_pdu_limit()
    assert result == 210  # 240 - 30


def test_get_pdu_limit_fallback_to_pdu_size(coord_factory):
    """Test _get_pdu_limit falls back to pdu_size."""
    coord = coord_factory()
    coord._client = type('MockClient', (), {'pdu_size': 480})()
    
    result = coord._get_pdu_limit()
    assert result == 450  # 480 - 30


def test_get_pdu_limit_minimum(coord_factory):
    """Test _get_pdu_limit enforces minimum of 1."""
    coord = coord_factory()
    coord._client = type('MockClient', (), {'pdu_length': 20})()
    
    result = coord._get_pdu_limit()
    assert result == 1  # max(1, 20 - 30)


def test_get_pdu_limit_no_attributes(coord_factory):
    """Test _get_pdu_limit with no pdu attributes defaults to 240."""
    coord = coord_factory()
    coord._client = type('MockClient', (), {})()
    
    result = coord._get_pdu_limit()
    assert result == 210  # 240 - 30 (default)


def test_get_pdu_limit_cached(coord_factory, monkeypatch):
    """Test _get_pdu_limit caches result for performance."""
    coord = coord_factory()
    
    # Remove the monkeypatch for _drop_connection so we can test cache invalidation
    monkeypatch.undo()
    
    # Create a mock client with a counter to track attribute access
    access_count = {"count": 0}
    
    class MockClient:
        def __init__(self):
            self.socket = None  # Instance attribute
        
        def disconnect(self):
            """Mock disconnect method."""
            pass
        
        @property
        def pdu_length(self):
            access_count["count"] += 1
            return 480
    
    coord._client = MockClient()
    
    # First call should access attribute
    result1 = coord._get_pdu_limit()
    assert result1 == 450  # 480 - 30
    assert access_count["count"] == 1
    
    # Second call should use cache, not access attribute again
    result2 = coord._get_pdu_limit()
    assert result2 == 450
    assert access_count["count"] == 1  # Still 1, not 2
    
    # After dropping connection, cache should be invalidated
    coord._drop_connection()
    assert coord._pdu_limit_cache is None  # Cache cleared
    
    # Reassign client and test cache is recalculated
    coord._client = MockClient()
    result3 = coord._get_pdu_limit()
    assert result3 == 450
    assert access_count["count"] == 2  # Accessed again after cache clear
    assert access_count["count"] == 2  # Now 2, cache was invalidated
