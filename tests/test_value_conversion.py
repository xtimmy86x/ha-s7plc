"""Tests for the centralized numeric value conversion pipeline."""

from __future__ import annotations

import pytest

from custom_components.s7plc.address import DataType
from custom_components.s7plc.value_conversion import (
    ConversionContext,
    VALUE_CHANNEL_SPECS,
    ValueConversionError,
    convert_from_plc,
    convert_to_plc,
    describe_value_conversion,
    evaluate_expression,
    normalize_value_conversion,
    supports_value_conversion,
    validate_value_conversion,
)


def test_complete_value_channel_catalogue() -> None:
    """Frontend/backend contract includes every genuinely numeric channel."""
    assert VALUE_CHANNEL_SPECS == {
        "sensors": {"value": ("address", None)},
        "numbers": {"value": ("address", "command_address")},
        "selects": {"value": ("address", "command_address")},
        "entity_sync": {"value": (None, "address")},
        "lights": {
            "brightness": ("brightness_state_address", "brightness_command_address")
        },
        "covers": {
            "position": ("position_state_address", "position_command_address"),
            "tilt": ("tilt_state_address", "tilt_command_address"),
            "status": ("cover_status_address", None),
        },
        "climates": {
            "current_temperature": ("current_temperature_address", None),
            "target_temperature": (
                "target_temperature_address",
                "target_temperature_address",
            ),
            "preset_mode": ("preset_mode_address", "preset_mode_address"),
            "hvac_status": ("hvac_status_address", None),
        },
    }


def ctx(data_type=DataType.WORD, direction="bidirectional", channel="value"):
    return ConversionContext(channel, data_type, direction)


def test_none_is_identity():
    assert convert_from_plc(12, None, ctx(direction="read")) == 12
    assert convert_to_plc(12, None, ctx(direction="write")) == 12


def test_multiplier_bidirectional_and_description():
    conversion = {"type": "multiplier", "factor": 10}
    assert convert_from_plc(12, conversion, ctx()) == 120
    assert convert_to_plc(120, conversion, ctx()) == 12
    assert describe_value_conversion(conversion) == "× 10"


def test_multiplier_zero_read_only_but_not_write():
    validate_value_conversion(
        {"type": "multiplier", "factor": 0}, ctx(direction="read")
    )
    with pytest.raises(ValueConversionError, match="zero"):
        validate_value_conversion(
            {"type": "multiplier", "factor": 0}, ctx(direction="write")
        )


@pytest.mark.parametrize("plc_min,plc_max,expected", [(0, 27648, 50), (27648, 0, 50)])
def test_linear_scale_normal_and_inverted(plc_min, plc_max, expected):
    c = {
        "type": "linear_scale",
        "plc_min": plc_min,
        "plc_max": plc_max,
        "ha_min": 0,
        "ha_max": 100,
    }
    assert convert_from_plc(13824, c, ctx()) == expected
    assert convert_to_plc(expected, c, ctx()) == 13824


def test_scale_clamp_and_no_clamp():
    base = {
        "type": "linear_scale",
        "plc_min": 0,
        "plc_max": 100,
        "ha_min": 0,
        "ha_max": 10,
    }
    clamped = {**base, "clamp": True}
    assert convert_from_plc(-10, clamped, ctx()) == 0
    assert convert_from_plc(200, clamped, ctx()) == 10
    assert convert_to_plc(-5, clamped, ctx()) == 0
    assert convert_to_plc(20, clamped, ctx()) == 100
    assert convert_from_plc(50, clamped, ctx()) == 5
    assert convert_to_plc(5, clamped, ctx()) == 50
    assert convert_from_plc(200, {**base, "clamp": False}, ctx()) == 20
    assert convert_to_plc(20, {**base, "clamp": False}, ctx()) == 200
    assert convert_from_plc(200, base, ctx()) == 20


@pytest.mark.parametrize("key", ["plc", "ha"])
def test_zero_intervals_rejected(key):
    c = {
        "type": "linear_scale",
        "plc_min": 0,
        "plc_max": 0 if key == "plc" else 100,
        "ha_min": 1,
        "ha_max": 1 if key == "ha" else 10,
    }
    with pytest.raises(ValueConversionError, match="interval"):
        validate_value_conversion(c, ctx())


@pytest.mark.parametrize(
    "mode,expected", [("floor", 1), ("ceil", 2), ("half_even", 2), ("half_up", 2)]
)
def test_integer_rounding(mode, expected):
    c = {
        "type": "expression",
        "read_expression": "value",
        "write_expression": "value / 2",
        "rounding": mode,
    }
    assert convert_to_plc(3, c, ctx(DataType.INT)) == expected


@pytest.mark.parametrize(
    "data_type,inside,outside",
    [
        (DataType.BYTE, 255, 256),
        (DataType.SINT, 127, 128),
        (DataType.USINT, 255, 256),
        (DataType.WORD, 65535, 65536),
        (DataType.INT, -32768, -32769),
        (DataType.DWORD, 4294967295, 4294967296),
        (DataType.DINT, 2147483647, 2147483648),
    ],
)
def test_integer_datatype_limits(data_type, inside, outside):
    c = {"type": "expression", "read_expression": "value", "write_expression": "value"}
    assert convert_to_plc(inside, c, ctx(data_type)) == inside
    with pytest.raises(ValueConversionError, match="outside"):
        convert_to_plc(outside, c, ctx(data_type))


@pytest.mark.parametrize(
    "text,packed",
    [
        ("00:00:00", 0),
        ("08:30:00", 2096),
        ("12:45:00", 4677),
        ("23:59:00", 9049),
        ("08:30", 2096),
    ],
)
def test_logo_time_bcd(text, packed):
    assert (
        convert_to_plc(text, {"type": "logo_time_bcd"}, ctx(DataType.WORD, "write"))
        == packed
    )


@pytest.mark.parametrize(
    "value", [None, "", "unknown", "unavailable", "24:00", "12:60", "12:30:60", "hello"]
)
def test_logo_time_invalid(value):
    with pytest.raises(ValueConversionError):
        convert_to_plc(value, {"type": "logo_time_bcd"}, ctx(DataType.WORD, "write"))


def test_logo_requires_writable_word():
    with pytest.raises(ValueConversionError, match="WORD"):
        validate_value_conversion({"type": "logo_time_bcd"}, ctx(DataType.INT, "write"))
    with pytest.raises(ValueConversionError, match="WORD"):
        validate_value_conversion({"type": "logo_time_bcd"}, ctx(DataType.WORD, "read"))


def test_expression_both_directions_and_functions():
    c = {
        "type": "expression",
        "read_expression": "clamp(value / 10, 0, 100)",
        "write_expression": "round(value * 10)",
    }
    assert convert_from_plc(500, c, ctx()) == 50
    assert convert_to_plc(50, c, ctx()) == 500


@pytest.mark.parametrize(
    "expression",
    [
        "value.real",
        "value[0]",
        "__import__('os')",
        "(lambda: 1)()",
        "[x for x in [1]]",
        "unknown + 1",
        "2 ** 100",
    ],
)
def test_unsafe_expression_rejected(expression):
    with pytest.raises(ValueConversionError):
        evaluate_expression(expression, 1)


def test_expression_failures():
    with pytest.raises(ValueConversionError):
        evaluate_expression("value / 0", 1)
    with pytest.raises(ValueConversionError):
        evaluate_expression("value * 1e309", 1)
    with pytest.raises(ValueConversionError):
        evaluate_expression("value+" * 100 + "1", 1)


def test_non_numeric_datatypes_are_not_capable():
    assert not supports_value_conversion(DataType.BIT)
    for name in ("STRING", "WSTRING", "CHAR"):
        value = getattr(DataType, name, None)
        if value is not None:
            assert not supports_value_conversion(value)


def test_legacy_normalization_and_precedence():
    assert normalize_value_conversion({"value_multiplier": 10}, "value") == {
        "type": "multiplier",
        "factor": 10,
    }
    scaled = normalize_value_conversion(
        {
            "scale_raw_min": 0,
            "scale_raw_max": 27648,
            "min_value": 0,
            "max_value": 100,
            "value_multiplier": 2,
        },
        "value",
    )
    assert scaled["type"] == "linear_scale"
    brightness = normalize_value_conversion({"brightness_scale": 100}, "brightness")
    assert (
        convert_from_plc(50, brightness, ctx(direction="read", channel="brightness"))
        == 127.5
    )


def test_new_and_legacy_conflict_and_no_double_conversion():
    entity = {
        "value_multiplier": 10,
        "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
    }
    with pytest.raises(ValueConversionError, match="conflict"):
        normalize_value_conversion(entity, "value")
    assert (
        convert_from_plc(
            5, normalize_value_conversion({"value_multiplier": 10}, "value"), ctx()
        )
        == 50
    )


def test_multiple_channels_are_independent():
    entity = {
        "value_conversions": {
            "position": {"type": "multiplier", "factor": 2},
            "tilt": {"type": "multiplier", "factor": 3},
        }
    }
    assert normalize_value_conversion(entity, "position")["factor"] == 2
    assert normalize_value_conversion(entity, "tilt")["factor"] == 3
