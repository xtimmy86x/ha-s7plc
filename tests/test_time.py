"""Siemens TIME datatype integration tests."""

from datetime import timedelta
import math
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.address import (
    DataType,
    TIME_MAX_SECONDS,
    TIME_MIN_SECONDS,
    get_numeric_limits,
    seconds_to_time,
    time_to_seconds,
)
from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.number import S7Number
from custom_components.s7plc.sensor import S7Sensor


@pytest.mark.parametrize(
    ("milliseconds", "seconds"),
    [
        (0, 0),
        (1, 0.001),
        (999, 0.999),
        (1000, 1),
        (1500, 1.5),
        (-250, -0.25),
        (-(2**31), TIME_MIN_SECONDS),
        (2**31 - 1, TIME_MAX_SECONDS),
    ],
)
def test_time_sensor_reads_seconds(mock_coordinator, milliseconds, seconds):
    topic = "sensor:DB1,TIME0"
    mock_coordinator.data = {topic: timedelta(milliseconds=milliseconds)}
    entity = S7Sensor(
        mock_coordinator, "Timer", "timer", {}, topic, "DB1,TIME0", None, None
    )
    assert entity.native_value == seconds
    assert entity._attr_device_class == SensorDeviceClass.DURATION
    assert entity._attr_native_unit_of_measurement == "s"
    assert entity._attr_suggested_display_precision == 3


def test_time_sensor_multiplier_applies_once(mock_coordinator):
    topic = "sensor:DB1,TIME0"
    mock_coordinator.data = {topic: timedelta(milliseconds=1500)}
    entity = S7Sensor(
        mock_coordinator,
        "Timer",
        "timer",
        {},
        topic,
        "DB1,TIME0",
        "temperature",
        2,
        "ms",
    )
    assert entity.native_value == 3.0
    assert entity._attr_device_class == SensorDeviceClass.DURATION
    assert entity._attr_native_unit_of_measurement == "s"


@pytest.mark.parametrize(
    ("seconds", "milliseconds"),
    [
        (0, 0),
        (0.001, 1),
        (1.5, 1500),
        (2.345, 2345),
        (-0.25, -250),
        (TIME_MIN_SECONDS, -(2**31)),
        (TIME_MAX_SECONDS, 2**31 - 1),
        (0.0015, 2),
        (0.0025, 2),
    ],
)
@pytest.mark.asyncio
async def test_time_number_writes_timedelta(mock_coordinator, seconds, milliseconds):
    mock_coordinator.write_batched = AsyncMock()
    mock_coordinator.async_request_refresh = AsyncMock()
    entity = S7Number(
        mock_coordinator,
        "Timer",
        "timer",
        {},
        "number:DB1,TIME0",
        "DB1,TIME0",
        "DB1,TIME0",
        None,
        None,
        None,
    )
    await entity.async_set_native_value(seconds)
    payload = mock_coordinator.write_batched.await_args.args[1]
    assert isinstance(payload, timedelta)
    assert time_to_seconds(payload) == milliseconds / 1000


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, 2147483.648, -2147483.649]
)
@pytest.mark.asyncio
async def test_time_number_rejects_invalid_values(mock_coordinator, value):
    mock_coordinator.write_batched = AsyncMock()
    entity = S7Number(
        mock_coordinator,
        "Timer",
        "timer",
        {},
        "number:DB1,TIME0",
        "DB1,TIME0",
        "DB1,TIME0",
        None,
        None,
        None,
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(value)
    mock_coordinator.write_batched.assert_not_awaited()


def test_time_number_defaults_and_configured_seconds(mock_coordinator):
    default = S7Number(
        mock_coordinator,
        "Timer",
        "timer",
        {},
        "number:DB1,TIME0",
        "DB1,TIME0",
        None,
        None,
        None,
        None,
    )
    assert default._attr_native_min_value == TIME_MIN_SECONDS
    assert default._attr_native_max_value == TIME_MAX_SECONDS
    assert default._attr_native_step == 0.001

    configured = S7Number(
        mock_coordinator,
        "Timer",
        "timer2",
        {},
        "number:DB1,TIME0",
        "DB1,TIME0",
        None,
        -1.5,
        2.5,
        0.005,
    )
    assert (
        configured._attr_native_min_value,
        configured._attr_native_max_value,
        configured._attr_native_step,
    ) == (-1.5, 2.5, 0.005)


@pytest.mark.asyncio
async def test_time_number_multiplier_round_trip(mock_coordinator):
    topic = "number:DB1,TIME0"
    mock_coordinator.data = {topic: timedelta(milliseconds=1500)}
    mock_coordinator.write_batched = AsyncMock()
    mock_coordinator.async_request_refresh = AsyncMock()
    entity = S7Number(
        mock_coordinator,
        "Timer",
        "timer",
        {},
        topic,
        "DB1,TIME0",
        "DB1,TIME0",
        None,
        None,
        None,
        value_multiplier=2,
    )
    assert entity.native_value == 3
    await entity.async_set_native_value(3)
    assert mock_coordinator.write_batched.await_args.args[1] == timedelta(
        milliseconds=1500
    )


def test_time_conversion_and_limits():
    assert get_numeric_limits(DataType.TIME) == (TIME_MIN_SECONDS, TIME_MAX_SECONDS)
    assert seconds_to_time(2.345) == timedelta(milliseconds=2345)


def test_time_configuration_sensor_number_and_select():
    for entity_type in ("sensors", "numbers"):
        item, errors = build_entity_item(
            entity_type,
            {"address": "DB1,TIME0", "min_value": -1, "max_value": 2}
            if entity_type == "numbers"
            else {"address": "DB1,TIME0"},
            options={},
        )
        assert not errors
        assert item["address"] == "DB1,TIME0"
    item, errors = build_entity_item(
        "selects",
        {"address": "DB1,TIME0", "options_map": "0:Off;10:Short"},
        options={},
    )
    assert not errors
    assert item["options_map"] == "0:Off;10:Short"
    unsupported_addresses = {
        "binary_sensors": "address",
        "switches": "state_address",
        "covers": "open_command_address",
        "lights": "state_address",
        "buttons": "address",
        "texts": "address",
        "climates": "current_temperature_address",
        "entity_sync": "address",
    }
    for entity_type, address_key in unsupported_addresses.items():
        entity = {address_key: "DB1,TIME0"}
        if entity_type == "entity_sync":
            entity["source_entity"] = "sensor.source"
        _, errors = build_entity_item(entity_type, entity, options={})
        assert errors == {"base": "time_unsupported_for_entity"}


def test_side_panel_does_not_suggest_time_addresses():
    source = Path("custom_components/s7plc/www/s7plc-panel.js").read_text()
    assert "TIME_ENTITY_TYPES" not in source
    assert "timeList" not in source
    assert "timeOptions" not in source
    assert "address-types" not in source
    assert 'value="DB1,TIME0"' not in source
