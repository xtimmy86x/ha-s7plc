"""Alarm groups: validation, byte ordering, shared reads, identity and backups."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from custom_components.s7plc.alarms import (
    AlarmRange,
    active_alarms,
    normalize_alarm_group,
)
from custom_components.s7plc.binary_sensor import S7AlarmPresenceSensor
from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.export import build_export_payload
from custom_components.s7plc.helpers import (
    build_entity_area_map,
    build_expected_unique_ids,
    ensure_item_uids,
)
from custom_components.s7plc.panel import _configuration_from_yaml, _entity_ids_payload
from custom_components.s7plc.plc.address import DataType
from custom_components.s7plc.restore import decode_values, encode_values
from custom_components.s7plc.sensor import S7AlarmCountSensor


def group(**kwargs):
    return normalize_alarm_group(
        {
            "uid": "group-a",
            "name": "Machine",
            "start_address": "DB1,X0.0",
            "end_address": "DB1,X100.7",
            **kwargs,
        }
    )


def sample(item, value=0):
    return {
        topic: [value] * tag.length if tag.length > 1 else value
        for topic, tag in AlarmRange.parse(
            item["start_address"], item["end_address"]
        ).blocks(item["uid"])
    }


def test_example_is_808_bits_and_one_101_byte_tag():
    region = AlarmRange.parse("DB1,0.0", "DB1,100.7")
    assert region.last - region.first + 1 == 808
    [(topic, tag)] = region.blocks("a")
    assert (tag.data_type, tag.start, tag.length) == (DataType.BYTE, 0, 101)
    assert topic == "alarm_group:a:0"


@pytest.mark.parametrize(
    "first,last",
    [
        ("DB1,X0.6", "DB1,X0.5"),
        ("DB1,X0.0", "DB2,X0.1"),
        ("DB1,B0", "DB1,X1.1"),
        ("M0.1", "M0.0"),
        ("MB0", "M0.1"),
        ("DB1,X0.0", "DB1,X1024.0"),
        ("bad", "DB1,X1.1"),
        ("DB1,X0.8", "DB1,X1.1"),
    ],
)
def test_invalid_ranges_rejected(first, last):
    item, errors = build_entity_item(
        "alarm_groups", {"start_address": first, "end_address": last}, options={}
    )
    assert item is None
    assert errors == {"base": "alarm_range_invalid"}


def test_partial_bytes_order_active_low_and_exclusions():
    item = group(
        start_address="db3,0.6",
        end_address="DB3,X1.2",
        alarms=[
            {"address": "DB3,X0.7", "description": "Motor"},
            {"address": "DB3,X1.1", "enabled": False},
        ],
    )
    topic = next(iter(sample(item)))
    data = {topic: (0b10000001, 0b10000011)}
    assert active_alarms(item, data) == [
        {"address": "DB3,X0.7", "description": "Motor"},
        {"address": "DB3,X1.0", "description": "DB3,X1.0"},
    ]
    item["active_value"] = 0
    assert [r["address"] for r in active_alarms(item, data)] == ["DB3,X0.6", "DB3,X1.2"]


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        [{"address": "DB2,X0.0"}],
        [{"address": "DB1,X101.0"}],
        [{"address": "DB1,X0.0", "enabled": 0}],
        [{"address": "DB1,X0.0", "description": "x" * 256}],
        [{"address": "DB1,X0.0"}, {"address": "db1,0.0"}],
        [{"address": "DB1,X0.0", "unknown": True}],
    ],
)
def test_invalid_mapping_rejected(rows):
    with pytest.raises(ValueError, match="alarm_mapping_invalid"):
        group(alarms=rows)


@pytest.mark.parametrize("value", [True, 2, "yes", None])
def test_invalid_active_value_rejected(value):
    with pytest.raises(ValueError, match="alarm_active_value_invalid"):
        group(active_value=value)


def test_large_range_all_chunks_required():
    item = group(start_address="DB4,X7.3", end_address="DB4,X1007.2")
    blocks = AlarmRange.parse(item["start_address"], item["end_address"]).blocks(
        item["uid"]
    )
    assert [tag.length for _, tag in blocks] == [200] * 5 + [1]
    data = sample(item, 255)
    assert len(active_alarms(item, data)) == 8000
    data.pop(blocks[-1][0])
    assert active_alarms(item, data) is None


@pytest.mark.parametrize("value", [None, [], [256], [True], [-1], "0", [0.0]])
def test_invalid_bytes_never_clear_alarms(value):
    item = group(end_address="DB1,X0.7")
    assert active_alarms(item, {"alarm_group:group-a:0": value}) is None


def test_entities_share_state_and_become_unavailable(mock_coordinator):
    item = group(end_address="DB1,X0.7")
    count = S7AlarmCountSensor(mock_coordinator, item, {"name": "PLC"})
    presence = S7AlarmPresenceSensor(
        mock_coordinator, item, {"name": "PLC"}, presence=True
    )
    assert (count.native_value, presence.is_on) == (None, None)
    assert not count.available and not presence.available
    mock_coordinator.data = sample(item, 0b10000001)
    assert (count.native_value, presence.is_on) == (2, True)
    assert count.available and presence.available
    assert count.extra_state_attributes["active_alarms"][1]["address"] == "DB1,X0.7"
    mock_coordinator.last_update_success = False
    assert not count.available and not presence.available
    mock_coordinator.last_update_success = True
    mock_coordinator.data = sample(item)
    assert (count.native_value, presence.is_on) == (0, False)
    mock_coordinator._connected = False
    assert not count.available and not presence.available


@pytest.mark.asyncio
async def test_group_blocks_one_schedule_and_unrelated_scalar_not_overridden():
    coord = S7Coordinator(MagicMock(), host="plc.local")
    item = group(end_address="DB1,X400.7", scan_interval=2)
    await coord.add_item("sensor:DB1,B0", "DB1,B0")
    await coord.add_alarm_group(item)
    coord._build_tag_cache()
    blocks = AlarmRange.parse(item["start_address"], item["end_address"]).blocks(
        item["uid"]
    )
    assert len({coord._item_next_read[topic] for topic, _ in blocks}) == 1
    assert all(coord._item_scan_intervals[topic] == 2 for topic, _ in blocks)
    assert coord._plans_batch["sensor:DB1,B0"].tag.length == 1
    assert [coord._plans_batch[topic].tag.length for topic, _ in blocks] == [
        200,
        200,
        1,
    ]
    # Two groups covering the same range share the actual read tags per batch.
    await coord.add_alarm_group({**item, "uid": "second"})
    coord._build_tag_cache()
    read = AsyncMock(return_value=[0, (0,) * 200, (0,) * 200, 0])
    coord._read_executor._read_tags = read
    result = await coord._read_executor.read_batch(list(coord._plans_batch.values()))
    assert len(read.call_args.args[0]) == 4
    assert len(result) == 7


@pytest.mark.asyncio
async def test_merker_group_registers_and_reads_multiple_blocks():
    coord = S7Coordinator(MagicMock(), host="plc.local")
    item = group(start_address="M0.0", end_address="M400.7", scan_interval=2)
    await coord.add_item("sensor:MB0", "MB0")
    await coord.add_alarm_group(item)
    coord._build_tag_cache()
    blocks = AlarmRange.parse(item["start_address"], item["end_address"]).blocks(
        item["uid"]
    )
    assert [topic for topic, _ in blocks] == [
        "alarm_group:group-a:0",
        "alarm_group:group-a:200",
        "alarm_group:group-a:400",
    ]
    assert [coord._items[topic] for topic, _ in blocks] == ["MB0", "MB200", "MB400"]
    assert len({coord._item_next_read[topic] for topic, _ in blocks}) == 1
    assert all(coord._item_scan_intervals[topic] == 2 for topic, _ in blocks)
    plans = [coord._plans_batch[topic] for topic, _ in blocks]
    assert [plan.tag.length for plan in plans] == [200, 200, 1]
    assert [plan.tag.start for plan in plans] == [0, 200, 400]
    assert {plan.tag.memory_area.name for plan in plans} == {"MERKER"}
    assert coord._plans_batch["sensor:MB0"].tag.length == 1

    read = AsyncMock(return_value=[0, (0b1,) * 200, (0,) * 200, 0b10000000])
    coord._read_executor._read_tags = read
    result = await coord._read_executor.read_batch(list(coord._plans_batch.values()))
    read_tags = read.call_args.args[0]
    assert len(read_tags) == 4
    assert {tag.memory_area.name for tag in read_tags} == {"MERKER"}
    active = active_alarms(item, result)
    assert len(active) == 201
    assert active[0]["address"] == "M0.0"
    assert active[-1]["address"] == "M400.7"


@pytest.mark.asyncio
async def test_platform_setup_creates_exactly_two_entities_and_registers_once(
    monkeypatch,
):
    from custom_components.s7plc import binary_sensor, sensor

    item = group()
    coord = S7Coordinator(MagicMock(), host="plc.local")
    coord.async_request_refresh = AsyncMock()
    entry = SimpleNamespace(options={"alarm_groups": [item]})
    for module in (sensor, binary_sensor):
        monkeypatch.setattr(
            module,
            "get_coordinator_and_device_info",
            lambda entry: (coord, {"name": "PLC"}, "dev"),
        )
    add_count, add_presence = MagicMock(), MagicMock()
    await binary_sensor.async_setup_entry(None, entry, add_presence)
    await sensor.async_setup_entry(None, entry, add_count)
    assert len(coord._items) == 1
    assert (
        len(
            [
                e
                for e in add_count.call_args.args[0]
                if isinstance(e, S7AlarmCountSensor)
            ]
        )
        == 1
    )
    assert (
        len(
            [
                e
                for e in add_presence.call_args.args[0]
                if isinstance(e, S7AlarmPresenceSensor)
            ]
        )
        == 1
    )


def test_both_identities_and_areas_survive_range_edits_and_backups():
    options = {"alarm_groups": [group(area="factory")]}
    ids = build_expected_unique_ids("dev", options)
    assert {"group-a", "group-a:active"} <= ids
    assert build_entity_area_map("dev", options) == {
        "group-a": "factory",
        "group-a:active": "factory",
    }
    exported = build_export_payload(options)
    restored = _configuration_from_yaml(yaml.safe_dump(exported), {})
    ensure_item_uids("dev", restored)
    assert restored["alarm_groups"][0]["start_address"] == "DB1,X0.0"
    assert restored["alarm_groups"][0]["alarms"] == []
    options["alarm_groups"][0]["end_address"] = "DB1,X2.3"
    assert build_expected_unique_ids("dev", options) == ids
    assert "group-a:active" not in build_expected_unique_ids("dev", {})


def test_panel_resolves_primary_count_uid(monkeypatch):
    from homeassistant.helpers import entity_registry as er

    lookup = MagicMock(
        side_effect=lambda domain, platform, uid: (
            f"{domain}.count" if uid == "group-a" else None
        )
    )
    monkeypatch.setattr(
        er, "async_get", lambda hass: SimpleNamespace(async_get_entity_id=lookup)
    )
    payload = _entity_ids_payload(
        None, SimpleNamespace(options={"alarm_groups": [group()]})
    )
    assert payload["alarm_groups"] == ["sensor.count"]


def test_block_restore_roundtrip_and_malformed_bytes():
    item = group()
    data = sample(item, 128)
    assert decode_values(encode_values(data)) == data
    assert decode_values({"alarm_group:a:0": {"byte_array": [False, 256]}}) == {}
    assert decode_values({"sensor:a": {"byte_array": [1]}}) == {}


@pytest.mark.parametrize("optimized", [False, True])
def test_blocks_fit_real_pys7_minimum_pdu(optimized):
    from pyS7.requests import prepare_optimized_requests, prepare_requests

    tags = [tag for _, tag in AlarmRange.parse("DB1,X0.0", "DB1,X1023.7").blocks("a")]
    if optimized:
        requests, _ = prepare_optimized_requests(tags, max_pdu=240)
    else:
        requests = prepare_requests(tags, max_pdu=240)
    assert requests
    assert sum(tag.length for request in requests for tag in request) == 1024
    assert all(sum(tag.size() for tag in request) <= 212 for request in requests)


def test_alarm_range_supports_merker_area():
    region = AlarmRange.parse("M8.0", "M9.7")
    assert (region.first, region.last) == (64, 79)
    assert region.address(64) == "M8.0"
    assert region.address(79) == "M9.7"
    (topic, tag), = region.blocks("flags")
    assert topic == "alarm_group:flags:8"
    assert (tag.memory_area.name, tag.start, tag.length) == ("MERKER", 8, 2)


def test_alarm_range_rejects_mixed_areas():
    for start, end in (("M8.0", "DB1,X9.7"), ("DB1,X0.0", "M9.7")):
        with pytest.raises(ValueError, match="alarm_range_invalid"):
            AlarmRange.parse(start, end)


def test_merker_alarm_group_decodes_bits_and_rejects_foreign_rows():
    item = normalize_alarm_group(
        {
            "uid": "flags",
            "start_address": "m8.0",
            "end_address": "M9.7",
            "alarms": [{"address": "M8.1", "description": "Valve low"}],
        }
    )
    assert item["start_address"] == "M8.0"
    assert item["end_address"] == "M9.7"
    topic = "alarm_group:flags:8"
    assert active_alarms(item, {topic: [0b00000010, 0b10000000]}) == [
        {"address": "M8.1", "description": "Valve low"},
        {"address": "M9.7", "description": "M9.7"},
    ]
    with pytest.raises(ValueError, match="alarm_mapping_invalid"):
        normalize_alarm_group(
            {
                "uid": "flags",
                "start_address": "M8.0",
                "end_address": "M9.7",
                "alarms": [{"address": "DB1,X8.1"}],
            }
        )
