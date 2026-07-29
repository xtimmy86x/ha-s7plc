"""Tests for S7 address helper functions."""

from __future__ import annotations

from custom_components.s7plc import address

def test_map_address_to_tag():
    """``map_address_to_tag``"""

    string_tag = "DB1,S10.2" # S7 string at DB1, offset 10, length 2

    S7_Tag = address.S7Tag(
                memory_area=address.MemoryArea.DB,
                db_number=1,
                data_type=address.DataType.STRING,
                start=10,
                bit_offset=0,
                length=2,
                    )

    assert address.parse_tag(string_tag) == S7_Tag


def test_parse_tag_invalid_address():
    """``parse_tag`` with invalid address"""

    invalid_address = "DB1,DBS10.2" # Should not use DB after comma

    try:
        address.parse_tag(invalid_address)
    except ValueError as err:
        assert str(err) == f"Invalid address: {invalid_address}"
    else:
        assert False, "Expected ValueError was not raised"


def test_get_numeric_limits():
    """``get_numeric_limits``"""

    int_type = address.DataType.INT
    dint_type = address.DataType.DINT
    real_type = address.DataType.REAL
    usint_type = address.DataType.USINT
    sint_type = address.DataType.SINT

    assert address.get_numeric_limits(int_type) == (-32768, 32767)
    assert address.get_numeric_limits(dint_type) == (-2147483648, 2147483647)
    assert address.get_numeric_limits(real_type) is None
    assert address.get_numeric_limits(usint_type) == (0, 255)
    assert address.get_numeric_limits(sint_type) == (-128, 127)


# ============================================================================
# parse_address_and_scale
# ============================================================================


def test_parse_address_and_scale_no_suffix_returns_unchanged():
    """A plain address with no Scale(...) suffix is returned unchanged."""
    assert address.parse_address_and_scale("DB6,B23") == ("DB6,B23", None)
    assert address.parse_address_and_scale(None) == (None, None)


def test_parse_address_and_scale_extracts_inline_scale():
    """Scale(raw_min,raw_max,scale_min,scale_max) is split off and parsed."""
    result = address.parse_address_and_scale("DB6,B23 Scale(0,1,0,10)")
    assert result == ("DB6,B23", (0.0, 1.0, 0.0, 10.0))


def test_parse_address_and_scale_all_zero_is_a_noop_placeholder():
    """Scale(0,0,0,0) is a valid no-op placeholder: it passes validation but
    is treated exactly like no Scale(...) suffix at all (scale is None),
    not as a literal all-zero scale (which would divide by zero and always
    resolve to 0)."""
    result = address.parse_address_and_scale("DB6,B23 Scale(0,0,0,0)")
    assert result == ("DB6,B23", None)


def test_parse_address_and_scale_is_case_insensitive_and_tolerates_spacing():
    result = address.parse_address_and_scale(
        "  DB6,B23   scale( -10.5 , 20 , 0 , 100 )  "
    )
    assert result == ("DB6,B23", (-10.5, 20.0, 0.0, 100.0))


def test_parse_address_and_scale_rejects_wrong_argument_count():
    try:
        address.parse_address_and_scale("DB6,B23 Scale(0,1,0)")
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError was not raised"


def test_parse_address_and_scale_rejects_non_numeric_argument():
    try:
        address.parse_address_and_scale("DB6,B23 Scale(a,1,0,10)")
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError was not raised"


def test_parse_address_and_scale_rejects_comma_decimals_inside_scale():
    """Decimals inside Scale() must use '.', not ',' (which separates args)."""
    try:
        address.parse_address_and_scale("DB6,B23 Scale(0,5,1,0,10)")
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError was not raised"


# ============================================================================
# format_address_with_scale
# ============================================================================


def test_format_address_with_scale_whole_numbers():
    """Whole numbers are formatted without a trailing '.0'."""
    result = address.format_address_with_scale(
        "DB6,B23", (0.0, 1.0, 0.0, 10.0)
    )
    assert result == "DB6,B23 Scale(0,1,0,10)"


def test_format_address_with_scale_decimal_numbers():
    result = address.format_address_with_scale(
        "DB1,REAL0", (-10.5, 20.0, 0.0, 100.0)
    )
    assert result == "DB1,REAL0 Scale(-10.5,20,0,100)"


def test_format_address_with_scale_round_trips_with_parse():
    original = "DB6,B23"
    scale = (0.0, 1.0, 0.0, 10.0)
    formatted = address.format_address_with_scale(original, scale)
    parsed_address, parsed_scale = address.parse_address_and_scale(formatted)
    assert parsed_address == original
    assert parsed_scale == scale