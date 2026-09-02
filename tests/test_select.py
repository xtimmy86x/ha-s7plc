"""Tests for the S7 PLC select entity."""

import asyncio

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_OPTIONS_MAP,
    CONF_SELECTS,
    CONF_SYNC_STATE,
)
from custom_components.s7plc.select import (
    S7Select,
    async_setup_entry,
    parse_options_map,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def device_info():
    """Device info dict."""
    return {
        "identifiers": {("s7plc", "test_device")},
        "name": "Test PLC",
        "manufacturer": "Siemens",
        "model": "S7-1200",
    }


@pytest.fixture
def pump_select(mock_coordinator, device_info):
    """A select mapping a lead-pump register."""
    return S7Select(
        coordinator=mock_coordinator,
        name="Lead Pump Mode",
        unique_id="lead_pump_mode",
        device_info=device_info,
        topic="select:DB1,B0",
        address="DB1,B0",
        command_address="DB1,B10",
        options_map={0: "Off", 1: "Pump A", 2: "Pump B"},
    )


# ============================================================================
# parse_options_map
# ============================================================================


def test_parse_options_map_valid():
    assert parse_options_map("0:Off;1:Pump A;2:Pump B") == {
        0: "Off",
        1: "Pump A",
        2: "Pump B",
    }


def test_parse_options_map_whitespace_newlines_and_negative():
    assert parse_options_map(" -1 : Fault \n 0:Off ; \n 5 : Auto ") == {
        -1: "Fault",
        0: "Off",
        5: "Auto",
    }


def test_parse_options_map_label_keeps_extra_colons():
    assert parse_options_map("1:Mode: eco") == {1: "Mode: eco"}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        ";;",
        "Off",  # no colon
        "x:Off",  # non-integer value
        "1.5:Half",  # non-integer value
        "1:",  # empty label
        "1:On;1:Off",  # duplicate value
        "1:On;2:On",  # duplicate label
    ],
)
def test_parse_options_map_invalid(raw):
    assert parse_options_map(raw) is None


@pytest.mark.parametrize("raw", ["1:Line one\nLine two", "1:One;broken label"])
def test_parse_options_map_rejects_separator_in_label(raw):
    assert parse_options_map(raw) is None


# ============================================================================
# Entity behavior
# ============================================================================


def test_select_entity_initialization(pump_select):
    assert pump_select._attr_unique_id == "lead_pump_mode"
    assert pump_select._address == "DB1,B0"
    assert pump_select._command_address == "DB1,B10"
    assert pump_select.options == ["Off", "Pump A", "Pump B"]


def test_select_current_option(pump_select, mock_coordinator):
    mock_coordinator.data = {"select:DB1,B0": 1}
    assert pump_select.current_option == "Pump A"


def test_select_current_option_unmapped_value(pump_select, mock_coordinator):
    mock_coordinator.data = {"select:DB1,B0": 99}
    assert pump_select.current_option is None


def test_select_current_option_no_data(pump_select, mock_coordinator):
    mock_coordinator.data = {}
    assert pump_select.current_option is None


def test_select_current_option_non_integer(pump_select, mock_coordinator):
    mock_coordinator.data = {"select:DB1,B0": "garbage"}
    assert pump_select.current_option is None


@pytest.mark.asyncio
async def test_select_option_writes_value(pump_select, mock_coordinator, monkeypatch):
    monkeypatch.setattr(
        "custom_components.s7plc.entity.time.monotonic", lambda: 5.0
    )
    await pump_select.async_select_option("Pump B")
    assert ("write_batched", "DB1,B10", 2) in mock_coordinator.write_calls
    assert pump_select._pending_command_time == 5.0


@pytest.mark.asyncio
async def test_select_option_unknown_raises(pump_select):
    with pytest.raises(HomeAssistantError):
        await pump_select.async_select_option("Pump C")


@pytest.mark.asyncio
async def test_time_select_read_write_and_unmapped(mock_coordinator, device_info):
    topic = "select:DB1,TIME0"
    entity = S7Select(
        mock_coordinator,
        "Delay",
        "delay",
        device_info,
        topic,
        "DB1,TIME0",
        "DB1,TIME4",
        {0: "Off", 10: "Short", 60: "Long"},
    )
    mock_coordinator.data = {topic: timedelta(seconds=10)}
    assert entity.current_option == "Short"
    mock_coordinator.data = {topic: timedelta(milliseconds=10500)}
    assert entity.current_option is None

    await entity.async_select_option("Long")
    assert ("write_batched", "DB1,TIME4", timedelta(seconds=60)) in (
        mock_coordinator.write_calls
    )


@pytest.mark.asyncio
async def test_select_option_no_command_address(mock_coordinator, device_info):
    select = S7Select(
        coordinator=mock_coordinator,
        name="Read Only",
        unique_id="read_only",
        device_info=device_info,
        topic="select:DB1,B0",
        address="DB1,B0",
        command_address=None,
        options_map={0: "Off", 1: "On"},
    )
    with pytest.raises(HomeAssistantError):
        await select.async_select_option("On")


def test_select_extra_state_attributes(pump_select):
    attrs = pump_select.extra_state_attributes
    assert attrs["s7_command_address"] == "DB1,B10"
    assert attrs["options_map"] == {"0": "Off", "1": "Pump A", "2": "Pump B"}
    assert "sync_state" not in attrs


def test_select_sync_extra_state_attribute(mock_coordinator, device_info):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-attrs",
        device_info,
        "select:DB1,B0",
        "DB1,B0",
        "DB1,B10",
        {0: "Off", 1: "On"},
        sync_state=True,
    )
    assert entity.extra_state_attributes["sync_state"] is True


@pytest.mark.asyncio
async def test_select_sync_same_address_case_insensitive_is_inactive(
    mock_coordinator, device_info, fake_hass
):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-same",
        device_info,
        "select:DB1,B0",
        "DB1,B0",
        "db1,b0",
        {0: "Off", 1: "On"},
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    mock_coordinator.data[entity._topic] = 1
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert entity._sync_state is False
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_select_sync_disabled_never_writes(
    mock_coordinator, device_info, fake_hass
):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-disabled",
        device_info,
        "select:DB1,B0",
        "DB1,B0",
        "DB1,B10",
        {0: "Off", 1: "On"},
        sync_state=False,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    mock_coordinator.data[entity._topic] = 1
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_select_sync_bidirectional_conversion_pipeline(
    mock_coordinator, device_info, fake_hass
):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-conversion",
        device_info,
        "select:DB1,W0",
        "DB1,W0",
        "DB1,W10",
        {0: "Off", 10: "Manual", 100: "Automatic"},
        value_conversion={"type": "multiplier", "factor": 10},
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    mock_coordinator.data[entity._topic] = 10
    entity._handle_coordinator_update()
    entity._handle_coordinator_update()
    await asyncio.sleep(0)
    assert entity.current_option == "Automatic"
    assert mock_coordinator.write_calls == [("write_batched", "DB1,W10", 10)]


@pytest.mark.asyncio
async def test_select_external_candidate_change_restarts_debounce(
    mock_coordinator, device_info, fake_hass
):
    """A different valid select sample replaces, rather than confirms, a candidate."""
    entity = S7Select(
        mock_coordinator, "Mode", "candidate-restart", device_info,
        "select:DB1,B0", "DB1,B0", "DB1,B10",
        {0: "Off", 1: "Manual", 2: "Automatic"}, sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()

    mock_coordinator.data[entity._topic] = 1
    entity._handle_coordinator_update()
    mock_coordinator.data[entity._topic] = 2
    entity._handle_coordinator_update()
    assert entity._last_state == 0
    assert entity._external_candidate == 2
    assert entity._external_candidate_count == 1

    entity._handle_coordinator_update()
    await asyncio.sleep(0)
    assert entity._last_state == 2
    assert mock_coordinator.write_calls == [("write_batched", "DB1,B10", 2)]


@pytest.mark.asyncio
async def test_select_rejected_command_realigns_canonical_unchanged_feedback(
    mock_coordinator, device_info, fake_hass, monkeypatch
):
    """Rejected select commands use the canonical value and write conversion."""
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-rejected",
        device_info,
        "select:DB1,W0",
        "DB1,W0",
        "DB1,W10",
        {10: "Manual", 100: "Automatic"},
        value_conversion={"type": "multiplier", "factor": 10},
        sync_state=True,
    )
    entity.hass = fake_hass
    # Raw 1 maps to canonical 10 and is only recorded on initial discovery.
    mock_coordinator.data = {entity._topic: 1}
    entity.async_write_ha_state()
    assert mock_coordinator.write_calls == []
    now = [10.0]
    monkeypatch.setattr(
        "custom_components.s7plc.entity.time.monotonic", lambda: now[0]
    )

    entity._set_pending_command(100)
    for _ in range(10):
        entity.async_write_ha_state()
    assert entity._pending_command == 100
    assert mock_coordinator.write_calls == []

    now[0] = 11.999
    entity.async_write_ha_state()
    assert entity._pending_command == 100
    assert mock_coordinator.write_calls == []

    now[0] = 12.001
    entity.async_write_ha_state()
    await asyncio.sleep(0)

    assert entity._pending_command is None
    assert entity._last_state == 10
    assert mock_coordinator.write_calls == [("write_batched", "DB1,W10", 1)]

    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == [("write_batched", "DB1,W10", 1)]


@pytest.mark.asyncio
async def test_select_realignment_write_error_is_consumed(
    mock_coordinator_failing, device_info, fake_hass, caplog, monkeypatch
):
    """A failed corrective write is logged by its background task."""
    entity = S7Select(
        mock_coordinator_failing,
        "Mode",
        "mode-realignment-error",
        device_info,
        "select:DB1,B0",
        "DB1,B0",
        "DB1,B10",
        {0: "Off", 1: "On"},
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator_failing.data = {entity._topic: 0}
    entity.async_write_ha_state()
    now = [10.0]
    monkeypatch.setattr(
        "custom_components.s7plc.entity.time.monotonic", lambda: now[0]
    )
    entity._set_pending_command(1)

    entity.async_write_ha_state()
    assert entity._pending_command == 1
    now[0] = 12.001
    entity.async_write_ha_state()
    await asyncio.sleep(0)

    assert entity._pending_command is None
    assert "Failed to sync command address" in caplog.text


@pytest.mark.asyncio
async def test_select_invalid_feedback_does_not_resolve_pending_command(
    mock_coordinator, device_info, fake_hass, monkeypatch
):
    """Unavailable and unmapped feedback remain inert after the settle window."""
    entity = S7Select(
        mock_coordinator, "Mode", "mode-candidates", device_info,
        "select:DB1,B0", "DB1,B0", "DB1,B10",
        {0: "Off", 1: "Manual", 2: "Automatic", 3: "Requested"},
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    now = [10.0]
    monkeypatch.setattr(
        "custom_components.s7plc.entity.time.monotonic", lambda: now[0]
    )
    entity._set_pending_command(3)
    now[0] = 12.001

    for invalid_feedback in (None, 99):
        mock_coordinator.data[entity._topic] = invalid_feedback
        entity.async_write_ha_state()
        assert entity._pending_command == 3
        assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_select_sync_conversion_error_does_not_write(
    mock_coordinator, device_info, fake_hass
):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode-bad-conversion",
        device_info,
        "select:DB1,W0",
        "DB1,W0",
        "DB1,W10",
        {0: "Off", 1: "On"},
        value_conversion={
            "type": "expression",
            "read_expression": "value",
            "write_expression": "1 / 0",
        },
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    mock_coordinator.data[entity._topic] = 1
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_select_sync_initial_external_echo_override_and_unmapped(
    mock_coordinator, device_info, fake_hass, monkeypatch
):
    entity = S7Select(
        mock_coordinator,
        "Mode",
        "mode",
        device_info,
        "select:DB1,B0",
        "DB1,B0",
        "DB1,B10",
        {0: "Off", 10: "Manual", 100: "Automatic"},
        sync_state=True,
    )
    entity.hass = fake_hass

    mock_coordinator.data = {entity._topic: 0}
    entity.async_write_ha_state()
    assert entity._last_state == 0
    assert mock_coordinator.write_calls == []

    mock_coordinator.data[entity._topic] = 100
    entity._handle_coordinator_update()
    entity._handle_coordinator_update()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == [("write_batched", "DB1,B10", 100)]
    now = [10.0]
    monkeypatch.setattr(
        "custom_components.s7plc.entity.time.monotonic", lambda: now[0]
    )

    await entity.async_select_option("Manual")
    mock_coordinator.write_calls.clear()
    mock_coordinator.data[entity._topic] = 10
    entity._handle_coordinator_update()
    await asyncio.sleep(0)
    assert entity._pending_command is None
    assert mock_coordinator.write_calls == []

    await entity.async_select_option("Manual")
    mock_coordinator.write_calls.clear()
    mock_coordinator.data[entity._topic] = 100
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == []
    now[0] = 12.001
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == [("write_batched", "DB1,B10", 100)]

    mock_coordinator.write_calls.clear()
    mock_coordinator.data[entity._topic] = 99
    entity.async_write_ha_state()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == []


@pytest.mark.asyncio
async def test_time_select_sync_uses_timedelta(
    mock_coordinator, device_info, fake_hass
):
    entity = S7Select(
        mock_coordinator,
        "Delay",
        "delay-sync",
        device_info,
        "select:DB1,TIME0",
        "DB1,TIME0",
        "DB1,TIME4",
        {0: "Off", 10: "Short"},
        sync_state=True,
    )
    entity.hass = fake_hass
    mock_coordinator.data = {entity._topic: timedelta(0)}
    entity.async_write_ha_state()
    mock_coordinator.data[entity._topic] = timedelta(seconds=10)
    entity._handle_coordinator_update()
    entity._handle_coordinator_update()
    await asyncio.sleep(0)
    assert mock_coordinator.write_calls == [
        ("write_batched", "DB1,TIME4", timedelta(seconds=10))
    ]


@pytest.mark.asyncio
async def test_async_setup_entry_uses_options_and_default_command_address(
    fake_hass, mock_coordinator, device_info
):
    entry = MagicMock()
    entry.options = {
        CONF_SELECTS: [
            {
                CONF_ADDRESS: "DB1,B0",
                CONF_OPTIONS_MAP: "0:Off;10:Manual;100:Automatic",
                "uid": "mode-uid",
            }
        ]
    }
    add_entities = MagicMock()
    configure_availability = AsyncMock()
    with (
        patch(
            "custom_components.s7plc.select.get_coordinator_and_device_info",
            return_value=(mock_coordinator, device_info, "device"),
        ),
        patch(
            "custom_components.s7plc.select.async_configure_entity_availability",
            configure_availability,
        ),
    ):
        await async_setup_entry(fake_hass, entry, add_entities)

    entities = add_entities.call_args.args[0]
    assert len(entities) == 1
    assert entities[0].options == ["Off", "Manual", "Automatic"]
    assert entities[0]._command_address == "DB1,B0"
    assert mock_coordinator.add_item_calls[0][0] == (
        "select:DB1,B0",
        "DB1,B0",
        None,
    )
    configure_availability.assert_awaited_once_with(
        entities, entry.options[CONF_SELECTS]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("configured", "expected"), [(True, True), (None, False)])
async def test_async_setup_entry_propagates_sync_state(
    fake_hass, mock_coordinator, device_info, configured, expected
):
    item = {
        CONF_ADDRESS: "DB1,B0",
        CONF_COMMAND_ADDRESS: "DB1,B10",
        CONF_OPTIONS_MAP: "0:Off;1:On",
        "uid": "mode-sync-uid",
    }
    if configured is not None:
        item[CONF_SYNC_STATE] = configured
    entry = MagicMock()
    entry.options = {CONF_SELECTS: [item]}
    add_entities = MagicMock()
    with (
        patch(
            "custom_components.s7plc.select.get_coordinator_and_device_info",
            return_value=(mock_coordinator, device_info, "device"),
        ),
        patch(
            "custom_components.s7plc.select.async_configure_entity_availability",
            AsyncMock(),
        ),
    ):
        await async_setup_entry(fake_hass, entry, add_entities)
    assert add_entities.call_args.args[0][0]._sync_state is expected


# ============================================================================
# Config validation (build_entity_item)
# ============================================================================


def _build(entity, options=None):
    return build_entity_item(CONF_SELECTS, entity, options=options or {})


def test_build_select_item_valid():
    item, errors = _build(
        {
            CONF_ADDRESS: " DB1,B0 ",
            CONF_COMMAND_ADDRESS: "DB1,B10",
            CONF_OPTIONS_MAP: " 0 : Off ; 1:Pump A;2:Pump B",
        }
    )
    assert not errors
    assert item[CONF_ADDRESS] == "DB1,B0"
    assert item[CONF_COMMAND_ADDRESS] == "DB1,B10"
    # Normalized string form
    assert item[CONF_OPTIONS_MAP] == "0:Off;1:Pump A;2:Pump B"
    assert item[CONF_SYNC_STATE] is False


def test_build_select_item_accepts_sync_state():
    item, errors = _build(
        {
            CONF_ADDRESS: "DB1,B0",
            CONF_COMMAND_ADDRESS: "DB1,B10",
            CONF_OPTIONS_MAP: "0:Off;1:On",
            CONF_SYNC_STATE: True,
        }
    )
    assert not errors
    assert item[CONF_SYNC_STATE] is True


@pytest.mark.parametrize(
    ("command", "sync_state", "expected_error"),
    [
        ("DB1,B10", True, None),
        (None, True, "sync_same_address"),
        ("DB1,B0", True, "sync_same_address"),
        ("db1,b0", True, "sync_same_address"),
        (None, False, None),
    ],
)
def test_build_select_item_sync_address_validation(command, sync_state, expected_error):
    config = {
        CONF_ADDRESS: "DB1,B0",
        CONF_OPTIONS_MAP: "0:Off;1:On",
        CONF_SYNC_STATE: sync_state,
    }
    if command is not None:
        config[CONF_COMMAND_ADDRESS] = command
    item, errors = _build(config)
    if expected_error:
        assert item is None
        assert errors == {"base": expected_error}
    else:
        assert not errors
        assert item[CONF_SYNC_STATE] is sync_state


def test_build_select_item_invalid_map():
    item, errors = _build({CONF_ADDRESS: "DB1,B0", CONF_OPTIONS_MAP: "nonsense"})
    assert item is None
    assert errors == {"base": "invalid_options_map"}


def test_build_select_item_missing_map():
    item, errors = _build({CONF_ADDRESS: "DB1,B0"})
    assert item is None
    assert errors == {"base": "invalid_options_map"}


def test_build_select_item_value_out_of_range_for_byte():
    item, errors = _build(
        {CONF_ADDRESS: "DB1,B0", CONF_OPTIONS_MAP: "0:Off;300:Overflow"}
    )
    assert item is None
    assert errors == {"base": "options_map_out_of_range"}


def test_build_select_item_negative_ok_for_signed_int():
    item, errors = _build(
        {CONF_ADDRESS: "DB1,I0", CONF_OPTIONS_MAP: "-1:Fault;0:Off;1:On"}
    )
    assert not errors
    assert item[CONF_OPTIONS_MAP] == "-1:Fault;0:Off;1:On"


def test_build_select_item_non_consecutive_byte_mapping():
    item, errors = _build(
        {CONF_ADDRESS: "DB1,B0", CONF_OPTIONS_MAP: "0:Off;10:Manual;100:Automatic"}
    )
    assert not errors
    assert item[CONF_OPTIONS_MAP] == "0:Off;10:Manual;100:Automatic"


@pytest.mark.parametrize("address", ["DB1,X0.0", "DB1,R0", "DB1,LR0"])
def test_build_select_item_rejects_non_integer_types(address):
    item, errors = _build({CONF_ADDRESS: address, CONF_OPTIONS_MAP: "0:Off;1:On"})
    assert item is None
    assert errors == {"base": "select_requires_integer_type"}


@pytest.mark.parametrize("address", ["DB1,X10.0", "DB1,R10", "DB1,LR10"])
def test_build_select_item_rejects_unsupported_command_type(address):
    item, errors = _build(
        {
            CONF_ADDRESS: "DB1,B0",
            CONF_COMMAND_ADDRESS: address,
            CONF_OPTIONS_MAP: "0:Off;1:On",
        }
    )
    assert item is None
    assert errors == {"base": "select_requires_integer_type"}


def test_build_select_item_accepts_different_fitting_integer_command_type():
    item, errors = _build(
        {
            CONF_ADDRESS: "DB1,B0",
            CONF_COMMAND_ADDRESS: "DB1,I10",
            CONF_OPTIONS_MAP: "0:Off;1:Manual;2:Auto",
        }
    )
    assert not errors
    assert item[CONF_COMMAND_ADDRESS] == "DB1,I10"


def test_build_select_item_rejects_command_value_out_of_range():
    item, errors = _build(
        {
            CONF_ADDRESS: "DB1,W0",
            CONF_COMMAND_ADDRESS: "DB1,B10",
            CONF_OPTIONS_MAP: "0:Off;300:Mode A",
        }
    )
    assert item is None
    assert errors == {"base": "options_map_out_of_range"}


def test_build_select_item_rejects_invalid_command_address():
    item, errors = _build(
        {
            CONF_ADDRESS: "DB1,B0",
            CONF_COMMAND_ADDRESS: "not an address",
            CONF_OPTIONS_MAP: "0:Off",
        }
    )
    assert item is None
    assert errors == {"base": "invalid_address"}


@pytest.mark.parametrize(
    ("state", "command", "expected_error"),
    [
        ("DB1,TIME0", "DB1,TIME4", None),
        ("DB1,TIME0", "DB1,D4", "select_command_type_mismatch"),
        ("DB1,D0", "DB1,TIME4", "select_command_type_mismatch"),
    ],
)
def test_build_select_item_time_command_compatibility(state, command, expected_error):
    item, errors = _build(
        {
            CONF_ADDRESS: state,
            CONF_COMMAND_ADDRESS: command,
            CONF_OPTIONS_MAP: "0:Off;10:Short;60:Long",
        }
    )
    if expected_error:
        assert item is None
        assert errors == {"base": expected_error}
    else:
        assert not errors
        assert item[CONF_OPTIONS_MAP] == "0:Off;10:Short;60:Long"


@pytest.mark.parametrize("value", [-2147484, 2147484])
def test_build_select_item_time_range(value):
    item, errors = _build({CONF_ADDRESS: "DB1,TIME0", CONF_OPTIONS_MAP: f"{value}:Out"})
    assert item is None
    assert errors == {"base": "options_map_out_of_range"}


def test_build_select_item_duplicate_address():
    existing = {CONF_SELECTS: [{CONF_ADDRESS: "DB1,B0"}]}
    item, errors = _build(
        {CONF_ADDRESS: "DB1,B0", CONF_OPTIONS_MAP: "0:Off;1:On"},
        options=existing,
    )
    assert item is None
    assert errors == {"base": "duplicate_entry"}
