"""Contracts for PLC payload preparation, independent of entity conversions."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.s7plc.plc.address import DataType
from custom_components.s7plc.plc.payload import prepare_payload


@pytest.mark.parametrize(
    ("datatype", "value", "expected"),
    [
        (DataType.BIT, False, False),
        (DataType.BYTE, 2.5, 2),
        (DataType.WORD, 2.5, 2),
        (DataType.DWORD, 2.5, 2),
        (DataType.INT, -3.5, -4),
        (DataType.DINT, -2.5, -2),
        (DataType.USINT, 3.5, 4),
        (DataType.SINT, -3.5, -4),
        (DataType.INT, True, 1),
        (DataType.REAL, True, 1.0),
        (DataType.LREAL, 7, 7.0),
        (DataType.STRING, "hello", "hello"),
        (DataType.WSTRING, "温度", "温度"),
    ],
)
def test_payload_preserves_value_and_python_type(datatype, value, expected):
    """Keep half-even rounding and existing bool-as-numeric acceptance."""
    result = prepare_payload(SimpleNamespace(data_type=datatype), value)

    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    "value",
    [timedelta(milliseconds=-250), timedelta(microseconds=1501)],
)
def test_time_payload_is_passed_through_without_rescaling_or_rounding(value):
    """Semantic conversion and driver precision remain outside this helper."""
    assert prepare_payload(SimpleNamespace(data_type=DataType.TIME), value) is value


@pytest.mark.parametrize(
    ("datatype", "value", "message"),
    [
        (DataType.BIT, 1, "BIT address target requires bool value, got int"),
        (DataType.TIME, 1.5, "TIME address target requires timedelta value, got float"),
        (
            DataType.WSTRING,
            42,
            "STRING/WSTRING address target requires str value, got int",
        ),
        (DataType.REAL, "1", "REAL address target requires numeric value, got str"),
        (DataType.INT, "1", "INT address target requires numeric value, got str"),
        (
            DataType.CHAR,
            "a",
            "CHAR arrays not supported for write at target, use STRING instead",
        ),
    ],
)
def test_payload_preserves_validation_errors(datatype, value, message):
    """Keep exception classes and address-specific messages unchanged."""
    with pytest.raises(ValueError) as error:
        prepare_payload(SimpleNamespace(data_type=datatype), value, "target")

    assert str(error.value) == message
