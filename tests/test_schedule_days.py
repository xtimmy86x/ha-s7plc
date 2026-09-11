"""Raw BYTE metadata must describe both scalar channels and their HA values."""

import pytest

from custom_components.s7plc.number import S7Number


@pytest.mark.parametrize(
    ("address", "command", "conversion", "expected"),
    [
        ("DB1,BYTE0", "DB1,BYTE1", None, True),
        ("MB0", "MB1", None, True),
        ("DB1,BYTE0", None, None, False),
        ("DB1,BYTE0", "DB1,WORD2", None, False),
        ("DB1,WORD0", "DB1,BYTE2", None, False),
        ("DB1,BYTE0", "DB1,BYTE1", {"type": "multiplier", "factor": 2}, False),
        ("DB1,WORD0", "DB1,WORD2", {"type": "logo_time_bcd"}, False),
    ],
)
def test_number_raw_byte_capability(mock_coordinator, address, command, conversion, expected):
    entity = S7Number(
        mock_coordinator, "Days", "days", {}, "number:days", address, command,
        0, 255, 1, value_conversion=conversion,
    )
    assert entity.extra_state_attributes["s7_raw_byte"] is expected
    if expected:
        assert entity.extra_state_attributes["s7_raw_word"] is False
        assert "s7_time_format" not in entity.extra_state_attributes
