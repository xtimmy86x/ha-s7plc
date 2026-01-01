from __future__ import annotations

import struct

import pytest

import asyncio

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import StringPlan, TagPlan


class DummyCoordinatorClient:
    def __init__(self, values):
        self._values = values
        self.calls = []

    def read(self, tags, optimize=True):
        self.calls.append((list(tags), optimize))
        result = self._values.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class DummyTag:
    def __init__(
        self,
        memory_area="DB",
        db_number=1,
        data_type=None,
        start=0,
        bit_offset=0,
        length=1,
    ):
        self.memory_area = memory_area
        self.db_number = db_number
        self.data_type = data_type
        self.start = start
        self.bit_offset = bit_offset
        self.length = length


def make_coordinator(monkeypatch, **kwargs):
    hass = coordinator.HomeAssistant()
    coord = S7Coordinator(hass, host="plc.local", **kwargs)
    # Avoid interacting with a real S7 client
    monkeypatch.setattr(coord, "_ensure_connected", lambda: None)
    monkeypatch.setattr(coord, "_drop_connection", lambda: None)
    return coord


def test_retry_retries_until_success(monkeypatch):
    coord = make_coordinator(monkeypatch)

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


def test_retry_raises_after_exhaustion(monkeypatch):
    coord = make_coordinator(monkeypatch)
    coord._max_retries = 1

    drop_calls = 0

    def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._drop_connection = fake_drop

    with pytest.raises(RuntimeError):
        coord._retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert drop_calls == 2


def test_retry_handles_struct_error(monkeypatch):
    coord = make_coordinator(monkeypatch)
    coord._max_retries = 0

    drop_calls = 0

    def fake_drop():
        nonlocal drop_calls
        drop_calls += 1

    coord._drop_connection = fake_drop

    with pytest.raises(RuntimeError):
        coord._retry(lambda: (_ for _ in ()).throw(struct.error()))

    assert drop_calls == 1


def test_read_batch_deduplicates_tags(monkeypatch):
    coord = make_coordinator(monkeypatch)

    tag_a = DummyTag(data_type=coordinator.DataType.WORD, start=0)
    tag_b = DummyTag(data_type=coordinator.DataType.DINT, start=4)

    plans = [
        TagPlan("topic/a", tag_a, lambda v: v + 1),
        TagPlan("topic/b", DummyTag(data_type=coordinator.DataType.WORD, start=0)),
        TagPlan("topic/c", tag_b, lambda v: v * 2),
    ]

    client = DummyCoordinatorClient([[10, 5]])
    coord._client = client
    coord._retry = lambda func: func()

    results = coord._read_batch(plans)

    assert client.calls == [([tag_a, tag_b], True)]
    assert results == {
        "topic/a": 11,
        "topic/b": 10,
        "topic/c": 10,
    }


def test_read_batch_raises_on_error(monkeypatch):
    coord = make_coordinator(monkeypatch)

    tag = DummyTag(data_type=coordinator.DataType.WORD)
    plans = [TagPlan("topic/a", tag), TagPlan("topic/b", tag)]

    client = DummyCoordinatorClient([OSError("boom")])
    coord._client = client
    coord._retry = lambda func: func()

    with pytest.raises(OSError):
        coord._read_batch(plans)


def test_async_update_data_respects_item_scan_interval(monkeypatch):
    coord = make_coordinator(monkeypatch)

    plan = TagPlan("topic/a", DummyTag())
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


def test_read_all_raises_update_failed_on_connection_error(monkeypatch):
    coord = make_coordinator(monkeypatch)

    def raise_connect():
        raise RuntimeError("connect boom")

    coord._ensure_connected = raise_connect

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_all([], [])

    assert "connect boom" in str(err.value)


def test_read_all_raises_update_failed_on_read_error(monkeypatch):
    coord = make_coordinator(monkeypatch)
    plans = [TagPlan("topic/a", DummyTag())]

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

    
def test_read_strings_raises_on_timeout(monkeypatch, caplog):
    coord = make_coordinator(monkeypatch)

    plans = [
        StringPlan("topic/a", 1, 0),
        StringPlan("topic/b", 2, 0),
    ]

    times = iter([10.0, 60.0])
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: next(times))

    read_calls = []

    def fake_read(db, start):
        read_calls.append((db, start))
        return "value"

    coord._read_s7_string = fake_read

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_strings(plans, deadline=50.0)

    assert "timeout" in str(err.value).lower()
    assert read_calls == [(1, 0)]
    assert any("String read timeout" in message for message in caplog.messages)


def test_read_strings_raises_on_error(monkeypatch, caplog):
    coord = make_coordinator(monkeypatch)

    plans = [StringPlan("topic/a", 1, 0)]

    def fake_read(db, start):
        raise RuntimeError("boom")

    coord._read_s7_string = fake_read
    monkeypatch.setattr(coordinator.time, "monotonic", lambda: 0.0)

    with pytest.raises(coordinator.UpdateFailed) as err:
        coord._read_strings(plans, deadline=50.0)

    assert "boom" in str(err.value)
    assert any("String read error" in message for message in caplog.messages)


def test_read_all_propagates_string_failures(monkeypatch):
    coord = make_coordinator(monkeypatch)

    plans = [StringPlan("topic/a", 1, 0)]

    coord._read_batch = lambda plans: {}
    coord._read_strings = lambda plans, deadline: (_ for _ in ()).throw(
        coordinator.UpdateFailed("timeout")
    )

    with pytest.raises(coordinator.UpdateFailed):
        coord._read_all([], plans)


def test_read_one_handles_bit_string_and_scalars(monkeypatch):
    coord = make_coordinator(monkeypatch)

    # String path
    string_tag = DummyTag(
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
    bit_tag = DummyTag(data_type=coordinator.DataType.BIT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: bit_tag)
    coord._retry = lambda func: [1]
    assert coord._read_one("BIT") is True

    # REAL post-processing
    real_tag = DummyTag(data_type=coordinator.DataType.REAL)
    monkeypatch.setattr(coordinator, "parse_tag", lambda addr: real_tag)
    coord._retry = lambda func: [1.234]
    assert coord._read_one("REAL") == pytest.approx(1.2)

def test_write_number_handles_numeric_types(monkeypatch):
    coord = make_coordinator(monkeypatch)

    writes: list[tuple[list[DummyTag], list[float | int]]] = []

    class DummyClient:
        def write(self, tags, values):
            writes.append((tags, values))

    coord._client = DummyClient()
    coord._retry = lambda func: func()

    int_tag = DummyTag(data_type=coordinator.DataType.INT)
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: int_tag)

    assert coord.write_number("DB1,W0", 12.6)
    assert writes == [([int_tag], [13])]

    writes.clear()
    real_tag = DummyTag(data_type=coordinator.DataType.REAL)
    coord._write_tags.clear()
    monkeypatch.setattr(coordinator, "parse_tag", lambda address: real_tag)

    assert coord.write_number("DB1,D4", 7.25)
    assert writes[0][0] == [real_tag]
    assert writes[0][1][0] == pytest.approx(7.25)


def test_write_number_rejects_non_numeric(monkeypatch):
    coord = make_coordinator(monkeypatch)

    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: DummyTag(data_type=coordinator.DataType.BIT),
    )

    with pytest.raises(ValueError):
        coord.write_number("Q0.0", 1)

    monkeypatch.setattr(
        coordinator,
        "parse_tag",
        lambda address: DummyTag(data_type=coordinator.DataType.CHAR, length=1),
    )

    with pytest.raises(ValueError):
        coord.write_number("DB1,B0", 65)