"""Read contracts exercised through real planning, retry and cache publication."""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyS7.errors import S7CommunicationError, S7ProtocolError

from custom_components.s7plc import coordinator as coordinator_module
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plc.address import DataType, MemoryArea, S7Tag

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
        kwargs.setdefault("max_retries", 0)
        coord = S7Coordinator(HomeAssistant(), host="plc.local", **kwargs)
        client = ReadClient(responses)
        coord._connection.client = client
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


def string_decode_error(wrappers):
    """Match direct, regular and chunked pyS7 decoding failures."""
    error = UnicodeDecodeError("utf-16-be", b"\xd8\x00", 0, 2, "unexpected end")
    for wrapper in wrappers:
        outer = wrapper("Malformed string payload")
        outer.__cause__ = error
        error = outer
    return error


@pytest.mark.parametrize("failing_string", ["first", "second"])
@pytest.mark.parametrize(
    "wrappers",
    [
        (),
        (S7ProtocolError,),
        (S7CommunicationError,),
        (S7ProtocolError, S7CommunicationError),
    ],
    ids=["direct", "regular", "chunked", "nested"],
)
async def test_decode_error_isolates_topic_without_retry_and_recovers_next_poll(
    make_reader, clock, failing_string, wrappers
):
    coord, client = make_reader([[1], ["old first"], ["old second"]], max_retries=3)
    client.connect = AsyncMock(wraps=client.connect)
    client.disconnect = AsyncMock(wraps=client.disconnect)
    coord._connection.sleep = AsyncMock()
    await prime_mixed_poll(coord)
    clock.advance(1)
    error = string_decode_error(wrappers)
    client.responses.extend(
        [
            [2],
            error if failing_string == "first" else ["new first"],
            error if failing_string == "second" else ["new second"],
        ]
    )
    expected = {"scalar": 2, "first": "new first", "second": "new second"}
    expected[failing_string] = None

    assert await coord._async_update_data() == expected
    assert len(client.calls) == 6
    assert coord.last_health_ok is True
    assert client.is_connected
    client.disconnect.assert_not_awaited()
    client.connect.assert_not_awaited()
    coord._connection.sleep.assert_not_awaited()
    assert all(coord.get_topic_read_revision(topic) == 2 for topic in expected)

    # Do not retain the previous text or retry before its configured interval.
    assert await coord._async_update_data() == expected
    assert len(client.calls) == 6
    clock.advance(1)
    client.responses.extend([[3], ["recovered first"], ["recovered second"]])
    assert await coord._async_update_data() == {
        "scalar": 3,
        "first": "recovered first",
        "second": "recovered second",
    }
    assert all(coord.get_topic_read_revision(topic) == 3 for topic in expected)
    client.disconnect.assert_not_awaited()


@pytest.mark.parametrize("wrappers", [(), (S7ProtocolError,), (S7CommunicationError,)])
async def test_ad_hoc_decode_error_preserves_connection(make_reader, wrappers):
    error = string_decode_error(wrappers)
    coord, client = make_reader([error, ["recovered"]], max_retries=3)
    client.disconnect = AsyncMock(wraps=client.disconnect)
    coord._connection.sleep = AsyncMock()

    with pytest.raises(RuntimeError, match="Failed to read DB1,WS0.12") as caught:
        await coord._read_one("DB1,WS0.12")

    assert caught.value.__cause__ is error
    client.disconnect.assert_not_awaited()
    coord._connection.sleep.assert_not_awaited()
    assert await coord._read_one("DB1,WS0.12") == "recovered"
    assert len(client.calls) == 2


async def test_protocol_error_message_does_not_make_it_a_local_decode_error(
    make_reader,
):
    error = S7ProtocolError("Malformed read response: 'ascii' codec can't decode byte")
    coord, client = make_reader([error])
    client.disconnect = AsyncMock(wraps=client.disconnect)
    await coord.add_item("label", "DB1,S0.12")

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    client.disconnect.assert_awaited_once()
    assert coord.last_health_ok is False
    assert coord._data_cache == {}


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


@pytest.mark.parametrize("optimize", [True, False])
async def test_binary_comparisons_share_read_and_keep_independent_schedules(
    make_reader, clock, monkeypatch, optimize
):
    from unittest.mock import AsyncMock, Mock
    from custom_components.s7plc import binary_sensor

    coord, client = make_reader([[16], [12], [20]], optimize_read=optimize)
    monkeypatch.setattr(coord, "async_request_refresh", AsyncMock())
    monkeypatch.setattr(binary_sensor, "get_coordinator_and_device_info",
                        lambda entry: (coord, {}, "device"))
    entry = SimpleNamespace(options={"binary_sensors": [
        {"uid": "high", "address": "DB1,I10", "comparison_operator": "gt",
         "comparison_value": 15, "scan_interval": 1},
        {"uid": "low", "address": "DB1,I10", "comparison_operator": "lt",
         "comparison_value": 15, "scan_interval": 2},
    ]})
    added = Mock()
    await binary_sensor.async_setup_entry(None, entry, added)
    _, high, low = added.call_args.args[0]
    await coord.add_item("sensor:DB1,I10", "DB1,I10", 1)
    assert high._topic != low._topic
    assert coord.get_scan_interval(high._topic) == 1
    assert coord.get_scan_interval(low._topic) == 2
    coord.data = await coord._async_update_data()
    assert high.is_on is True and low.is_on is False
    assert coord.data["sensor:DB1,I10"] == 16
    assert len(client.calls) == 1 and len(client.calls[0][0]) == 1

    clock.advance(1)
    coord.data = await coord._async_update_data()
    assert high.is_on is False and low.is_on is False  # Slow comparison still has 16.
    assert coord.data["sensor:DB1,I10"] == 12
    assert coord.get_topic_read_revision(high._topic) == 2
    assert coord.get_topic_read_revision(low._topic) == 1

    clock.advance(1)
    coord.data = await coord._async_update_data()
    assert high.is_on is True and low.is_on is False
    assert coord.get_topic_read_revision(low._topic) == 2
    assert all(len(tags) == 1 for tags, _ in client.calls)

    # A configuration reload after deleting the first comparison keeps the
    # surviving UID/topic and its polling interval, independent of list index.
    await coord.async_shutdown()
    remaining = entry.options["binary_sensors"][1]
    fresh_coord, fresh_client = make_reader([[10]])
    monkeypatch.setattr(fresh_coord, "async_request_refresh", AsyncMock())
    monkeypatch.setattr(binary_sensor, "get_coordinator_and_device_info",
                        lambda entry: (fresh_coord, {}, "device"))
    entry.options["binary_sensors"] = [remaining]
    await binary_sensor.async_setup_entry(None, entry, added)
    survivor = added.call_args.args[0][1]
    assert survivor._topic == low._topic
    assert survivor._attr_unique_id == low._attr_unique_id
    assert fresh_coord.get_scan_interval(survivor._topic) == 2
    fresh_coord.data = await fresh_coord._async_update_data()
    assert survivor.is_on is True
    assert len(fresh_client.calls[0][0]) == 1
