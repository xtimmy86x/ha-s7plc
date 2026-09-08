"""Read contracts exercised through real planning, retry and cache publication."""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.s7plc import coordinator as coordinator_module
from custom_components.s7plc.address import DataType, MemoryArea, S7Tag
from custom_components.s7plc.coordinator import S7Coordinator

pytestmark = pytest.mark.asyncio


class ReadClient:
    """Return scripted driver results without replacing coordinator methods."""

    def __init__(self, responses):
        self.is_connected = True
        self.responses = deque(responses)
        self.calls = []

    async def read(self, tags, *, optimize=True):
        self.calls.append((tuple(tags), optimize))
        response = self.responses.popleft()
        if callable(response):
            response = response()
        if isinstance(response, Exception):
            raise response
        return response

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False


class Clock:
    """Advance coordinator deadlines without changing asyncio's clock."""

    def __init__(self):
        self.now = 10.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(
        coordinator_module, "time", SimpleNamespace(monotonic=clock.monotonic)
    )
    return clock


@pytest_asyncio.fixture
async def make_reader():
    coordinators = []

    def create(responses, **kwargs):
        coord = S7Coordinator(
            HomeAssistant(), host="plc.local", max_retries=0, **kwargs
        )
        client = ReadClient(responses)
        coord._client = client
        coordinators.append(coord)
        return coord, client

    yield create
    for coord in coordinators:
        await coord.async_shutdown()


@pytest.mark.parametrize("optimize", [True, False])
@pytest.mark.parametrize(
    ("address", "datatype", "db", "start", "length", "value"),
    [
        ("DB2,S4.12", DataType.STRING, 2, 4, 12, "caffè"),
        ("DB3,WS6.24", DataType.WSTRING, 3, 6, 24, "温度 🌡"),
        ("DB4,S10.12", DataType.STRING, 4, 10, 12, ""),
        ("DB5,WS12.24", DataType.WSTRING, 5, 12, 24, ""),
    ],
)
async def test_string_poll_builds_driver_tag_and_preserves_value(
    make_reader, optimize, address, datatype, db, start, length, value
):
    coord, client = make_reader([[value]], optimize_read=optimize)
    await coord.add_item("label", address)

    assert await coord._async_update_data() == {"label": value}

    expected = S7Tag(MemoryArea.DB, db, datatype, start, 0, length)
    assert client.calls == [((expected,), optimize)]
    assert coord.get_topic_read_revision("label") == 1
    assert coord.last_health_ok is True


async def test_mixed_poll_deduplicates_and_preserves_per_topic_precision_and_time(
    make_reader,
):
    duration = timedelta(milliseconds=-250)
    coord, client = make_reader([[12.34567, 9.87654321, duration], ["Ready"], ["運転"]])
    await coord.add_item("rounded", "DB1,R0", real_precision=1)
    await coord.add_item("precise", "DB1,R0", real_precision=3)
    await coord.add_item("double", "DB1,LREAL8", real_precision=2)
    await coord.add_item("duration", "DB1,TIME16")
    await coord.add_item("label", "DB1,S24.12")
    await coord.add_item("wide_label", "DB1,WS40.12")

    result = await coord._async_update_data()

    assert result == {
        "rounded": 12.3,
        "precise": 12.346,
        "double": 9.88,
        "duration": duration,
        "label": "Ready",
        "wide_label": "運転",
    }
    assert isinstance(result["duration"], timedelta)
    assert client.calls == [
        (
            (
                S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1),
                S7Tag(MemoryArea.DB, 1, DataType.LREAL, 8, 0, 1),
                S7Tag(MemoryArea.DB, 1, DataType.TIME, 16, 0, 1),
            ),
            True,
        ),
        ((S7Tag(MemoryArea.DB, 1, DataType.STRING, 24, 0, 12),), True),
        ((S7Tag(MemoryArea.DB, 1, DataType.WSTRING, 40, 0, 12),), True),
    ]
    assert all(coord.get_topic_read_revision(topic) == 1 for topic in result)


async def prime_mixed_poll(coord):
    await coord.add_item("scalar", "DB1,W0")
    await coord.add_item("first", "DB1,S4.12")
    await coord.add_item("second", "DB1,WS20.12")
    assert await coord._async_update_data() == {
        "scalar": 1,
        "first": "old first",
        "second": "old second",
    }


@pytest.mark.parametrize("failing_string", ["first", "second"])
async def test_string_error_does_not_publish_partial_poll(
    make_reader, clock, failing_string
):
    coord, client = make_reader([[1], ["old first"], ["old second"]])
    await prime_mixed_poll(coord)
    previous = dict(coord._data_cache)
    due_before = dict(coord._item_next_read)
    clock.advance(1)
    client.responses.append([2])
    if failing_string == "second":
        client.responses.append(["new first"])
    client.responses.append(OSError("PLC string read failed"))

    with pytest.raises(UpdateFailed, match="PLC string read failed"):
        await coord._async_update_data()

    assert coord._data_cache == previous
    assert coord._item_next_read == due_before
    assert all(coord.get_topic_read_revision(topic) == 1 for topic in previous)
    assert coord.last_health_ok is False
    assert not client.is_connected
    assert len(client.calls) == (5 if failing_string == "first" else 6)


@pytest.mark.parametrize("exceeds_during", ["scalar", "first_string"])
async def test_expired_budget_prevents_next_string_without_publishing_partial_data(
    make_reader, clock, exceeds_during
):
    coord, client = make_reader([[1], ["old first"], ["old second"]], op_timeout=0.5)
    await prime_mixed_poll(coord)
    previous = dict(coord._data_cache)
    clock.advance(1)

    def slow_response():
        clock.advance(0.501)
        return [2] if exceeds_during == "scalar" else ["new first"]

    if exceeds_during == "scalar":
        client.responses.extend([slow_response, ["must not read first"]])
    else:
        client.responses.extend([[2], slow_response, ["must not read second"]])

    with pytest.raises(UpdateFailed, match="String read timeout"):
        await coord._async_update_data()

    assert coord._data_cache == previous
    assert all(coord.get_topic_read_revision(topic) == 1 for topic in previous)
    assert coord.last_health_ok is False
    assert len(client.calls) == (4 if exceeds_during == "scalar" else 5)
    assert len(client.responses) == 1


@pytest.mark.parametrize(("address", "value"), [("DB1,W0", 42), ("DB1,WS4.12", "完了")])
async def test_last_read_may_complete_after_cooperative_deadline(
    make_reader, clock, caplog, address, value
):
    def slow_response():
        clock.advance(0.75)
        return [value]

    coord, client = make_reader([slow_response], op_timeout=0.5)
    await coord.add_item("value", address)

    assert await coord._async_update_data() == {"value": value}

    assert len(client.calls) == 1
    assert coord.get_topic_read_revision("value") == 1
    assert coord.last_health_ok is True
    assert "Batch read timeout reached" in caplog.text


async def test_read_budget_starts_after_connection_finishes(make_reader, clock):
    coord, client = make_reader([["first"], ["second"]], op_timeout=0.5)
    client.is_connected = False

    async def connect():
        clock.advance(5)
        client.is_connected = True

    client.connect = connect
    await coord.add_item("first", "DB1,S0.12")
    await coord.add_item("second", "DB1,WS20.12")

    assert await coord._async_update_data() == {"first": "first", "second": "second"}
    assert len(client.calls) == 2
    assert coord.last_health_ok is True


async def test_same_address_keeps_independent_scan_intervals_and_revisions(
    make_reader, clock
):
    coord, client = make_reader([[1.2345], [2.3456], [3.4567]])
    await coord.add_item("fast", "DB1,R0", scan_interval=0.5, real_precision=1)
    await coord.add_item("slow", "DB1,R0", scan_interval=2, real_precision=3)

    assert await coord._async_update_data() == {"fast": 1.2, "slow": 1.234}
    clock.advance(0.5)
    assert await coord._async_update_data() == {"fast": 2.3, "slow": 1.234}
    assert coord.get_topic_read_revision("fast") == 2
    assert coord.get_topic_read_revision("slow") == 1
    clock.advance(1.5)
    assert await coord._async_update_data() == {"fast": 3.5, "slow": 3.457}
    assert coord.get_topic_read_revision("fast") == 3
    assert coord.get_topic_read_revision("slow") == 2
    assert all(len(tags) == 1 for tags, _ in client.calls)
    assert len(client.calls) == 3
