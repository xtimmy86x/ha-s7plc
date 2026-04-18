"""Tests for S7Coordinator - Refactored with fixtures."""

from __future__ import annotations

import struct
import pytest
import asyncio

from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import StringPlan, TagPlan
from conftest import DummyTag


# ============================================================================
# Helper Functions
# ============================================================================


def make_coordinator(monkeypatch, **kwargs):
    """Factory function to create a coordinator for testing."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local", **kwargs)

    # Async no-ops for connection methods
    async def _noop():
        pass

    monkeypatch.setattr(coord, "_ensure_connected", _noop)
    monkeypatch.setattr(coord, "_drop_connection", _noop)
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


@pytest.mark.asyncio
async def test_retry_retries_until_success(coord_factory):
    """Test retry mechanism retries until success."""
    coord = coord_factory()

    sleep_calls: list[float] = []
    ensure_calls = 0
    drop_calls = 0

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    async def fake_ensure():
        nonlocal ensure_calls
        ensure_calls += 1

    async def fake_drop():
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

    result = await coord._retry(flaky)

    assert result == "ok"
    assert ensure_calls == 2
    assert drop_calls == 1
    assert sleep_calls == [coord._backoff_initial]


@pytest.mark.asyncio
async def test_retry_raises_after_exhaustion(coord_factory):
    """Test retry mechanism raises after exhausting retries."""
    coord = coord_factory()
    coord._max_retries = 1

    drop_calls = 0
    sleep_calls = []

    async def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    coord._drop_connection = fake_drop
    coord._sleep = fake_sleep

    with pytest.raises(RuntimeError):
        await coord._retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert drop_calls == 2


@pytest.mark.asyncio
async def test_retry_handles_struct_error(coord_factory):
    """Test retry mechanism handles struct errors."""
    coord = coord_factory()
    coord._max_retries = 0

    drop_calls = 0

    async def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._drop_connection = fake_drop

    with pytest.raises(RuntimeError):
        await coord._retry(lambda: (_ for _ in ()).throw(struct.error()))

    assert drop_calls == 1


# ============================================================================
# Batch Reading Tests
# ============================================================================


@pytest.mark.asyncio
async def test_read_batch_deduplicates_tags(coord_factory, dummy_tag, dummy_client):
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

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry

    results = await coord._read_batch(plans)

    assert client.calls == [([tag_a, tag_b], True)]
    assert results == {
        "topic/a": 11,
        "topic/b": 10,
        "topic/c": 10,
    }


@pytest.mark.asyncio
async def test_read_batch_raises_on_error(coord_factory, dummy_tag, dummy_client):
    """Test read batch raises on client error."""
    coord = coord_factory()

    tag = dummy_tag(data_type=coordinator.DataType.WORD)
    plans = [TagPlan("topic/a", tag), TagPlan("topic/b", tag)]

    client = dummy_client([OSError("boom")])
    coord._client = client

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry

    with pytest.raises(OSError):
        await coord._read_batch(plans)


# ============================================================================
# Update Data Tests
# ============================================================================


@pytest.mark.asyncio
async def test_async_update_data_respects_item_scan_interval(coord_factory, dummy_tag):
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

    async def fake_read_all(plans_batch, plans_str):
        read_calls.append((plans_batch, plans_str))
        return results

    coord._read_all = fake_read_all

    data_first = await coord._async_update_data()
    assert data_first == results
    assert coord._data_cache == results
    assert read_calls == [([plan], [])]
    coord._item_next_read["topic/a"] += 100.0

    data_second = await coord._async_update_data()
    assert data_second == results
    assert len(read_calls) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_read_all_raises_update_failed_on_connection_error(coord_factory):
    """Test read_all raises UpdateFailed on connection error."""
    coord = coord_factory()

    async def raise_connect():
        raise RuntimeError("connect boom")

    coord._ensure_connected = raise_connect

    with pytest.raises(coordinator.UpdateFailed) as err:
        await coord._read_all([], [])

    assert "connect boom" in str(err.value)


@pytest.mark.asyncio
async def test_read_all_raises_update_failed_on_read_error(coord_factory, dummy_tag):
    """Test read_all raises UpdateFailed on read error."""
    coord = coord_factory()
    plans = [TagPlan("topic/a", dummy_tag())]

    drop_calls: list[bool] = []

    async def fake_drop():
        drop_calls.append(True)

    coord._drop_connection = fake_drop

    async def raise_read(plans):
        raise RuntimeError("read boom")

    coord._read_batch = raise_read

    with pytest.raises(coordinator.UpdateFailed) as err:
        await coord._read_all(plans, [])

    assert drop_calls == [True]
    assert "read boom" in str(err.value)

    
# ============================================================================
# String Reading Tests
# ============================================================================


@pytest.mark.asyncio
async def test_read_strings_raises_on_timeout(coord_factory, monkeypatch, caplog):
    """Test read_strings raises on timeout."""
    coord = coord_factory()

    plans = [
        StringPlan("topic/a", 1, 0, 254),
        StringPlan("topic/b", 2, 0, 254),
    ]

    times = iter([10.0, 60.0])
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: next(times, 999.0))

    read_calls = []

    async def fake_read(db, start, length, is_wstring=False):
        read_calls.append((db, start))
        return "value"

    coord._read_s7_string = fake_read

    with pytest.raises(coordinator.UpdateFailed) as err:
        await coord._read_strings(plans, deadline=50.0)

    assert "timeout" in str(err.value).lower()
    assert read_calls == [(1, 0)]
    assert any("String read timeout" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_read_strings_raises_on_error(coord_factory, monkeypatch, caplog):
    """Test read_strings raises on read error."""
    coord = coord_factory()

    plans = [StringPlan("topic/a", 1, 0, 254)]

    async def fake_read(db, start, length, is_wstring=False):
        raise RuntimeError("boom")

    coord._read_s7_string = fake_read
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: 0.0)

    with pytest.raises(coordinator.UpdateFailed) as err:
        await coord._read_strings(plans, deadline=50.0)

    assert "boom" in str(err.value)
    assert any("String read error" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_read_all_propagates_string_failures(coord_factory):
    """Test read_all propagates string reading failures."""
    coord = coord_factory()

    plans = [StringPlan("topic/a", 1, 0, 254)]

    async def fake_read_batch(plans):
        return {}

    async def fake_read_strings(plans, deadline):
        raise coordinator.UpdateFailed("timeout")

    coord._read_batch = fake_read_batch
    coord._read_strings = fake_read_strings

    with pytest.raises(coordinator.UpdateFailed):
        await coord._read_all([], plans)


# ============================================================================
# Read One Tests
# ============================================================================


@pytest.mark.asyncio
async def test_read_one_handles_bit_string_and_scalars(coord_factory, dummy_tag, monkeypatch):
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

    async def fake_read_s7_string(db, start, length, is_wstring=False):
        return "test"

    coord._read_s7_string = fake_read_s7_string
    assert await coord._read_one("STRING") == "test"

    # Bit normalization
    bit_tag = dummy_tag(data_type=coordinator.DataType.BIT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: bit_tag)

    async def mock_retry_bit(func):
        return [1]

    coord._retry = mock_retry_bit
    assert await coord._read_one("BIT") is True

    # REAL post-processing
    real_tag = DummyTag(data_type=coordinator.DataType.REAL)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: real_tag)

    async def mock_retry_real(func):
        return [1.234]

    coord._retry = mock_retry_real
    assert await coord._read_one("REAL") == pytest.approx(1.2)


# ============================================================================
# Write Tests
# ============================================================================


@pytest.mark.asyncio
async def test_write_handles_numeric_types(coord_factory, dummy_tag, monkeypatch):
    """Test write() handles different numeric types correctly."""
    coord = coord_factory()

    writes: list[tuple[list[DummyTag], list[float | int]]] = []

    class DummyClient:
        def write(self, tags, values):
            writes.append((tags, values))

    coord._client = DummyClient()

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry

    int_tag = dummy_tag(data_type=coordinator.DataType.INT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: int_tag)

    assert await coord.write("DB1,W0", 12.6)
    assert writes == [([int_tag], [13])]

    writes.clear()
    real_tag = dummy_tag(data_type=coordinator.DataType.REAL)
    coord._tag_cache.clear()
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: real_tag)

    assert await coord.write("DB1,D4", 7.25)
    assert writes[0][0] == [real_tag]
    assert writes[0][1][0] == pytest.approx(7.25)

    # Test USINT (unsigned 8-bit): value should be rounded to int
    writes.clear()
    usint_tag = dummy_tag(data_type=coordinator.DataType.USINT)
    coord._tag_cache.clear()
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: usint_tag)

    assert await coord.write("DB1,USI0", 200.9)
    assert writes == [([usint_tag], [201])]

    # Test SINT (signed 8-bit): value should be rounded to int
    writes.clear()
    sint_tag = dummy_tag(data_type=coordinator.DataType.SINT)
    coord._tag_cache.clear()
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: sint_tag)

    assert await coord.write("DB1,SI0", -50.4)
    assert writes == [([sint_tag], [-50])]


@pytest.mark.asyncio
async def test_write_validates_type_match(coord_factory, dummy_tag, monkeypatch):
    """Test write() validates that value type matches address data type."""
    coord = coord_factory()

    # Test BIT requires bool
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.BIT),
    )

    with pytest.raises(ValueError, match="BIT address .* requires bool"):
        await coord.write("Q0.0", 1)

    # Test STRING/WSTRING require str
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.STRING, length=10),
    )

    with pytest.raises(ValueError, match="STRING/WSTRING address .* requires str"):
        await coord.write("DB1,S0.10", 42)


@pytest.mark.asyncio
async def test_write_accepts_string_types(coord_factory, dummy_tag, monkeypatch):
    """Test write() accepts STRING and WSTRING data types."""
    coord = coord_factory()

    # Test STRING
    string_tag = dummy_tag(data_type=coordinator.DataType.STRING, length=50)
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: string_tag)

    async def mock_write_retry_hello(address, tag, payload):
        return payload == "hello"

    coord._write_with_retry = mock_write_retry_hello

    assert await coord.write("DB1,S0.50", "hello") is True

    # Test WSTRING
    wstring_tag = dummy_tag(data_type=coordinator.DataType.WSTRING, length=100)
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: wstring_tag)

    async def mock_write_retry_world(address, tag, payload):
        return payload == "world"

    coord._write_with_retry = mock_write_retry_world

    assert await coord.write("DB1,WS0.100", "world") is True


@pytest.mark.asyncio
async def test_write_rejects_type_mismatch(coord_factory, dummy_tag, monkeypatch):
    """Test write() rejects mismatched value and address types."""
    coord = coord_factory()

    # Test BIT rejection of string
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.BIT),
    )

    with pytest.raises(ValueError, match="BIT address .* requires bool"):
        await coord.write("Q0.0", "test")

    # Test WORD rejection of string
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.WORD),
    )

    with pytest.raises(ValueError, match="WORD address .* requires numeric"):
        await coord.write("DB1,W0", "test")

    # Test USINT rejection of string
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.USINT),
    )

    with pytest.raises(ValueError, match="USINT address .* requires numeric"):
        await coord.write("DB1,USI0", "test")

    # Test SINT rejection of string
    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: dummy_tag(data_type=coordinator.DataType.SINT),
    )

    with pytest.raises(ValueError, match="SINT address .* requires numeric"):
        await coord.write("DB1,SI0", "test")


# ============================================================================
# Connection Tests
# ============================================================================


def test_is_connected_no_client():
    """Test is_connected when no client exists."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    assert coord.is_connected() is False


def test_is_connected_client_no_socket(monkeypatch):
    """Test is_connected when client exists but not connected."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    # Mock client that is not connected
    mock_client = type('MockClient', (), {'is_connected': False})()
    coord._client = mock_client
    
    assert coord.is_connected() is False


def test_is_connected_with_socket(monkeypatch):
    """Test is_connected when client is connected."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    # Mock client that is connected
    mock_client = type('MockClient', (), {'is_connected': True})()
    coord._client = mock_client
    
    assert coord.is_connected() is True


@pytest.mark.asyncio
async def test_connect_calls_ensure_connected(monkeypatch):
    """Test connect method calls _ensure_connected."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    connected = []

    async def fake_ensure():
        connected.append(True)

    monkeypatch.setattr(coord, "_ensure_connected", fake_ensure)
    
    await coord.connect()
    assert len(connected) == 1


@pytest.mark.asyncio
async def test_disconnect_calls_drop_connection(monkeypatch):
    """Test disconnect method calls _drop_connection."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    
    disconnected = []

    async def fake_drop():
        disconnected.append(True)

    monkeypatch.setattr(coord, "_drop_connection", fake_drop)
    
    await coord.disconnect()
    assert len(disconnected) == 1


# -- _drop_connection unit tests ------------------------------------------

@pytest.mark.asyncio
async def test_drop_connection_no_client():
    """_drop_connection does nothing when _client is None."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    coord._client = None
    await coord._drop_connection()          # should not raise


@pytest.mark.asyncio
async def test_drop_connection_calls_disconnect(monkeypatch):
    """_drop_connection calls client.disconnect() when client exists."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")
    calls = []

    class MC:
        async def disconnect(self):
            calls.append(True)

    coord._client = MC()
    await coord._drop_connection()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_drop_connection_already_disconnected():
    """_drop_connection tolerates client whose disconnect() is a no-op."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")

    class MC:
        async def disconnect(self):
            pass

    coord._client = MC()
    await coord._drop_connection()          # should not raise


@pytest.mark.asyncio
async def test_drop_connection_attribute_error():
    """_drop_connection handles AttributeError from pyS7 race condition."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")

    class MC:
        async def disconnect(self):
            raise AttributeError("'NoneType' object has no attribute 'close'")

    coord._client = MC()
    await coord._drop_connection()          # should not raise


@pytest.mark.asyncio
async def test_drop_connection_os_error():
    """_drop_connection handles OSError from socket issues."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")

    class MC:
        async def disconnect(self):
            raise OSError("socket closed")

    coord._client = MC()
    await coord._drop_connection()          # should not raise


@pytest.mark.asyncio
async def test_drop_connection_runtime_error():
    """_drop_connection handles RuntimeError."""
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local")

    class MC:
        async def disconnect(self):
            raise RuntimeError("something went wrong")

    coord._client = MC()
    await coord._drop_connection()          # should not raise


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
    coord._tag_cache = {"fake": None}
    
    asyncio.run(coord.add_item("sensor:DB1,REAL0", "DB1,REAL0"))
    
    # Cache should be cleared
    assert len(coord._plans_batch) == 0
    assert len(coord._plans_str) == 0
    assert len(coord._tag_cache) == 0


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


@pytest.mark.asyncio
async def test_write_multi_empty_list(coord_factory):
    """Test write_multi with empty list returns empty dict."""
    coord = coord_factory()
    
    result = await coord.write_multi([])
    
    assert result == {}


@pytest.mark.asyncio
async def test_write_multi_single_write(coord_factory, monkeypatch):
    """Test write_multi with single write."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry
    
    result = await coord.write_multi([('DB1,X0.0', True)])
    
    coord._client.write.assert_called_once()
    tags, payloads = coord._client.write.call_args[0]
    assert len(tags) == 1
    assert payloads == [True]
    assert result == {'DB1,X0.0': True}


@pytest.mark.asyncio
async def test_write_multi_multiple_writes(coord_factory, monkeypatch):
    """Test write_multi with multiple writes in single batch."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry
    
    writes = [
        ('DB1,X0.0', True),
        ('DB1,W10', 42),
        ('DB1,REAL20', 3.14),
    ]
    
    result = await coord.write_multi(writes)
    
    # Should be single batch write
    coord._client.write.assert_called_once()
    tags, payloads = coord._client.write.call_args[0]
    assert len(tags) == 3
    assert payloads == [True, 42, 3.14]
    assert result == {
        'DB1,X0.0': True,
        'DB1,W10': True,
        'DB1,REAL20': True,
    }


@pytest.mark.asyncio
async def test_write_multi_type_conversion(coord_factory, monkeypatch):
    """Test write_multi performs correct type conversion."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry
    
    writes = [
        ('DB1,X0.0', True),         # bool
        ('DB1,W10', 42.7),          # int from float
        ('DB1,REAL20', 3.14),       # real
        ('DB1,S0.254', 'test'),     # string
    ]
    
    await coord.write_multi(writes)
    
    coord._client.write.assert_called_once()
    tags, payloads = coord._client.write.call_args[0]
    assert payloads[0] is True           # bool
    assert payloads[1] == 43             # rounded to int
    assert payloads[2] == 3.14           # float
    assert payloads[3] == 'test'         # string


@pytest.mark.asyncio
async def test_write_multi_invalid_address(coord_factory):
    """Test write_multi handles invalid address gracefully."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()

    async def mock_retry(func):
        return func()

    coord._retry = mock_retry
    
    writes = [
        ('DB1,X0.0', True),
        ('INVALID', 42),
    ]
    
    result = await coord.write_multi(writes)
    
    # Valid write should succeed, invalid should fail
    assert result['DB1,X0.0'] is True
    assert result['INVALID'] is False


@pytest.mark.asyncio
async def test_write_multi_type_mismatch(coord_factory):
    """Test write_multi handles type mismatch."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()
    
    writes = [
        ('DB1,X0.0', 42),  # bool address with int value
    ]
    
    result = await coord.write_multi(writes)
    
    assert result['DB1,X0.0'] is False


@pytest.mark.asyncio
async def test_write_multi_write_error(coord_factory, monkeypatch):
    """Test write_multi marks all as failed on write error."""
    from unittest.mock import MagicMock
    
    coord = coord_factory()
    coord._client = MagicMock()
    coord._client.write.side_effect = OSError("Connection failed")
    
    # Mock _sleep to avoid real delays during retry
    async def fake_sleep(seconds):
        pass

    coord._sleep = fake_sleep
    
    writes = [
        ('DB1,X0.0', True),
        ('DB1,W10', 42),
    ]
    
    result = await coord.write_multi(writes)
    
    # All should fail
    assert result['DB1,X0.0'] is False
    assert result['DB1,W10'] is False


@pytest.mark.asyncio
async def test_write_batched_creates_notification_on_error(coord_factory, monkeypatch):
    """Test write_batched creates persistent notification on write failures."""
    from unittest.mock import MagicMock, AsyncMock
    
    coord = coord_factory()
    coord._client = MagicMock()
    
    # Mock write_multi to return failures
    async def mock_write_multi(writes):
        return {addr: False for addr, _ in writes}
    
    monkeypatch.setattr(coord, 'write_multi', mock_write_multi)
    
    # Mock services.async_call
    coord.hass.services.async_call = AsyncMock()
    
    results = await asyncio.gather(
        coord.write_batched('DB1,X0.0', True),
        coord.write_batched('DB1,W10', 42),
        return_exceptions=True,
    )
    assert len(results) == 2
    assert all(isinstance(result, HomeAssistantError) for result in results)
    
    # Verify notification service was called
    coord.hass.services.async_call.assert_called_once()
    call_args = coord.hass.services.async_call.call_args
    assert call_args[0][0] == 'persistent_notification'
    assert call_args[0][1] == 'create'
    assert 'DB1,X0.0' in call_args[0][2]['message']
    assert 'DB1,W10' in call_args[0][2]['message']


@pytest.mark.asyncio
async def test_write_batched_no_notification_on_success(coord_factory, monkeypatch):
    """Test write_batched does not create notification on success."""
    from unittest.mock import MagicMock, AsyncMock
    
    coord = coord_factory()
    coord._client = MagicMock()
    
    # Mock write_multi to return success
    async def mock_write_multi(writes):
        return {addr: True for addr, _ in writes}
    
    monkeypatch.setattr(coord, 'write_multi', mock_write_multi)
    
    # Mock services.async_call
    coord.hass.services.async_call = AsyncMock()
    
    await asyncio.gather(
        coord.write_batched('DB1,X0.0', True),
        coord.write_batched('DB1,W10', 42),
    )
    
    # Verify no notification was created
    coord.hass.services.async_call.assert_not_called()
