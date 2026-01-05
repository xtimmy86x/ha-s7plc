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

    assert address.get_numeric_limits(int_type) == (-32768, 32767)
    assert address.get_numeric_limits(dint_type) == (-2147483648, 2147483647)
    assert address.get_numeric_limits(real_type) is None