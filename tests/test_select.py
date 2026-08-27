"""Tests for the S7 PLC select entity."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_OPTIONS_MAP,
    CONF_SELECTS,
)
from custom_components.s7plc.select import S7Select, parse_options_map

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
async def test_select_option_writes_value(pump_select, mock_coordinator):
    await pump_select.async_select_option("Pump B")
    assert ("write_batched", "DB1,B10", 2) in mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_select_option_unknown_raises(pump_select):
    with pytest.raises(HomeAssistantError):
        await pump_select.async_select_option("Pump C")


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


@pytest.mark.parametrize("address", ["DB1,X0.0", "DB1,R0", "DB1,LR0"])
def test_build_select_item_rejects_non_integer_types(address):
    item, errors = _build({CONF_ADDRESS: address, CONF_OPTIONS_MAP: "0:Off;1:On"})
    assert item is None
    assert errors == {"base": "select_requires_integer_type"}


def test_build_select_item_duplicate_address():
    existing = {CONF_SELECTS: [{CONF_ADDRESS: "DB1,B0"}]}
    item, errors = _build(
        {CONF_ADDRESS: "DB1,B0", CONF_OPTIONS_MAP: "0:Off;1:On"},
        options=existing,
    )
    assert item is None
    assert errors == {"base": "duplicate_entry"}
