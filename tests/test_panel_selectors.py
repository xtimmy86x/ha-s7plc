"""Panel unit suggestions accept nullable Home Assistant unit catalogs."""

from enum import StrEnum

import pytest
from homeassistant.components import number, sensor

from custom_components.s7plc.panel import _selector_options


class AreaUnit(StrEnum):
    """Match the string-enum units returned by Home Assistant."""

    SQUARE_METERS = "m²"


@pytest.mark.parametrize(
    "sensor_units,number_units,expected",
    [
        (
            {"unitless": {None}, "temperature": {"°C"}, "unspecified": None},
            {"area": {AreaUnit.SQUARE_METERS, None}, "temperature": {"°C"}},
            ["m²", "°C"],
        ),
        ({"unitless": {None}}, {"unspecified": None, "empty": set()}, []),
    ],
)
def test_unit_suggestions_skip_none_and_normalize_string_enums(
    monkeypatch, sensor_units, number_units, expected
):
    monkeypatch.setattr(sensor, "DEVICE_CLASS_UNITS", sensor_units)
    monkeypatch.setattr(number, "DEVICE_CLASS_UNITS", number_units)

    units = _selector_options()["units"]

    assert units == expected
    assert all(type(unit) is str for unit in units)
