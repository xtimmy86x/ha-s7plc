from __future__ import annotations

import pytest

from custom_components.s7plc import coordinator
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import StringPlan, TagPlan


class DummyCoordinatorClient:
    def __init__(self, values):
        self._values = values
        self.calls = []

    def read(self, tags, optimize=False):
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

    assert client.calls == [([tag_a, tag_b], False)]
    assert results == {
        "topic/a": 11,
        "topic/b": 10,
        "topic/c": 10,
    }


def test_read_batch_populates_defaults_on_error(monkeypatch):
    coord = make_coordinator(monkeypatch)

    tag = DummyTag(data_type=coordinator.DataType.WORD)
    plans = [TagPlan("topic/a", tag), TagPlan("topic/b", tag)]

    client = DummyCoordinatorClient([OSError("boom")])
    coord._client = client
    coord._retry = lambda func: func()

    results = coord._read_batch(plans)

    assert results == {"topic/a": None, "topic/b": None}


def test_read_strings_respects_deadline(monkeypatch):
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

    results = coord._read_strings(plans, deadline=50.0)

    assert read_calls == [(1, 0)]
    assert results["topic/a"] == "value"
    assert results["topic/b"] is None


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