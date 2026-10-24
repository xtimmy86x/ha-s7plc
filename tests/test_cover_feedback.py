"""Feedback decoding and setup contracts shared by the cover implementations."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.s7plc import cover as cover_platform
from custom_components.s7plc.entity import S7BaseEntity


@pytest.fixture(params=["traditional", "position", "toggle"])
def cover_kind(request):
    return request.param


@pytest.fixture
def setup_cover(fake_hass, mock_coordinator, monkeypatch):
    monkeypatch.setattr(
        cover_platform,
        "get_coordinator_and_device_info",
        lambda entry: (mock_coordinator, {}, "test-device"),
    )

    async def setup(kind, fields):
        item = {"uid": "test-cover", "name": "Test cover"}
        if kind == "position":
            item["position_state_address"] = "DB1,W20"
        else:
            item["open_command_address"] = "DB1,X0.0"
            if kind == "toggle":
                item["toggle_mode"] = True
            else:
                item["close_command_address"] = "DB1,X0.1"
        item.update(fields)
        original = deepcopy(item)
        entities = []
        await cover_platform.async_setup_entry(
            fake_hass, SimpleNamespace(options={"covers": [item]}), entities.extend
        )
        assert item == original
        assert len(entities) == 1
        entities[0].hass = fake_hass
        return entities[0]

    return setup


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["timed", "opening", "closing", "both", "status"])
@pytest.mark.parametrize("scan_interval", [None, 0.25])
async def test_cover_feedback_topic_registration(
    setup_cover, mock_coordinator, cover_kind, mode, scan_interval
):
    """Keep topic names, order, intervals and each cover's feedback selection."""
    fields = {
        "cover_position_feedback": mode,
        "opening_state_address": "DB1,X1.0",
        "closing_state_address": "DB1,X1.1",
        "cover_opening_address": "DB1,X2.0",
        "cover_closing_address": "DB1,X2.1",
        "cover_stopped_address": "DB1,X2.2",
        "cover_status_address": "DB1,W10",
        "scan_interval": scan_interval,
    }
    channels = []
    if cover_kind == "position":
        fields["tilt_state_address"] = "DB1,W22"
        channels.append(("position", "DB1,W20"))
    if mode in {"opening", "both"}:
        channels.append(("opened", "DB1,X1.0"))
    if mode in {"closing", "both"}:
        channels.append(("closed", "DB1,X1.1"))
    if (cover_kind, mode) != ("traditional", "status"):
        channels.extend(
            [("opening", "DB1,X2.0"), ("closing", "DB1,X2.1"), ("stopped", "DB1,X2.2")]
        )
    if cover_kind == "position":
        channels.append(("tilt", "DB1,W22"))
    channels.append(("status", "DB1,W10"))

    entity = await setup_cover(cover_kind, fields)

    assert mock_coordinator.add_item_calls == [
        ((f"cover:{channel}:{address}", address, scan_interval), {})
        for channel, address in channels
    ]
    assert entity._restorable_topics == {
        f"cover:{channel}:{address}" for channel, address in channels
    }
    assert mock_coordinator.refresh_count == 1
    assert not mock_coordinator.write_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_address", [None, ""])
async def test_empty_cover_feedback_does_not_register_topics(
    setup_cover, mock_coordinator, cover_kind, empty_address
):
    entity = await setup_cover(
        cover_kind,
        {
            "opening_state_address": empty_address,
            "closing_state_address": empty_address,
            "cover_opening_address": empty_address,
            "cover_closing_address": empty_address,
            "cover_stopped_address": empty_address,
            "cover_status_address": empty_address,
        },
    )
    expected = (
        [(("cover:position:DB1,W20", "DB1,W20", None), {})]
        if cover_kind == "position"
        else []
    )
    assert mock_coordinator.add_item_calls == expected
    assert entity._get_movement_status() is None
    assert entity._cover_status_values == {
        "open": [],
        "closed": [],
        "opening": [],
        "closing": [],
        "stopped": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (False, False), (True, True), (0, False), (1, True)],
)
async def test_cover_bit_feedback_keeps_unknown_distinct_from_false(
    setup_cover, mock_coordinator, cover_kind, value, expected
):
    entity = await setup_cover(cover_kind, {"cover_opening_address": "DB1,X2.0"})
    topic = "cover:opening:DB1,X2.0"
    assert entity._get_topic_state(None) is None
    assert entity._get_topic_state(topic) is None
    mock_coordinator.data = {topic: value}
    assert entity._get_topic_state(topic) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("invalid", None),
        ({}, None),
        (99, None),
        (0, "open"),
        (1, "closed"),
        (2, "opening"),
        (20, "opening"),
        (3, "closing"),
        (4, "stopped"),
    ],
)
async def test_cover_status_decoding(
    setup_cover, mock_coordinator, cover_kind, value, expected
):
    entity = await setup_cover(
        cover_kind,
        {
            "cover_status_address": "DB1,W10",
            "cover_status_open_values": "0",
            "cover_status_closed_values": "1",
            "cover_status_opening_values": " 2, 20 ",
            "cover_status_closing_values": "3",
            "cover_status_stopped_values": "4",
        },
    )
    assert entity._get_movement_status() is None
    mock_coordinator.data = {"cover:status:DB1,W10": value}
    assert entity._get_movement_status() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conversion", "expected"),
    [
        ({"type": "multiplier", "factor": 0.1}, "opening"),
        ({"type": "expression", "read_expression": "value / 0"}, None),
    ],
)
async def test_cover_status_conversion_and_failure(
    setup_cover, mock_coordinator, cover_kind, conversion, expected
):
    entity = await setup_cover(
        cover_kind,
        {
            "cover_status_address": "DB1,W10",
            "cover_status_opening_values": "2",
            "value_conversions": {"status": conversion},
        },
    )
    mock_coordinator.data = {"cover:status:DB1,W10": 20}
    assert entity._get_movement_status() == expected


@pytest.mark.asyncio
async def test_cover_status_keeps_legacy_mapping_precedence(
    setup_cover, mock_coordinator, cover_kind
):
    """Legacy overlapping maps still match open before movement states."""
    entity = await setup_cover(
        cover_kind,
        {
            "cover_status_address": "DB1,W10",
            "cover_status_open_values": "2",
            "cover_status_opening_values": "2",
            "cover_status_closed_values": None,
            "cover_status_stopped_values": "",
        },
    )
    mock_coordinator.data = {"cover:status:DB1,W10": 2}
    assert entity._get_movement_status() == "open"
    assert entity._cover_status_values["closed"] == []
    assert entity._cover_status_values["stopped"] == []


@pytest.mark.asyncio
async def test_cover_feedback_restores_display_and_prefers_live_values(
    setup_cover, mock_coordinator, cover_kind
):
    entity = await setup_cover(
        cover_kind,
        {
            "availability_mode": "always",
            "cover_opening_address": "DB1,X2.0",
            "cover_status_address": "DB1,W10",
            "cover_status_opening_values": "2",
        },
    )
    bit_topic = "cover:opening:DB1,X2.0"
    status_topic = "cover:status:DB1,W10"
    mock_coordinator.data = {bit_topic: True, status_topic: 2}
    entity.async_get_last_extra_data = AsyncMock(
        return_value=entity.extra_restore_state_data
    )
    mock_coordinator.data = {}
    await S7BaseEntity.async_added_to_hass(entity)
    assert entity._get_topic_state(bit_topic) is True
    assert entity._get_movement_status() == "opening"
    assert not mock_coordinator.data
    assert not mock_coordinator.write_calls

    mock_coordinator.data = {bit_topic: False, status_topic: None}
    assert entity._get_topic_state(bit_topic) is False
    assert entity._get_movement_status() is None
