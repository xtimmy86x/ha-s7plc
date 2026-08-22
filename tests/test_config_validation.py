"""Tests for the public entity configuration validation API."""

from typing import Any

import pytest

from custom_components.s7plc.config_validation import (
    EntityConfigBuilder,
    build_entity_item,
    validate_entity_fields,
)
from custom_components.s7plc.const import (
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_COVERS,
    CONF_ENTITY_SYNC,
    CONF_INVERT_STATE,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SOURCE_ENTITY,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
)


@pytest.mark.parametrize(
    ("entity", "expected_method"),
    [
        ({}, "_build_cover_item"),
        (
            {CONF_POSITION_STATE_ADDRESS: ""},
            "_build_cover_item",
        ),
        (
            {CONF_POSITION_STATE_ADDRESS: "DB1,DBW0"},
            "_build_cover_position_item",
        ),
    ],
)
def test_build_entity_item_dispatches_cover(
    monkeypatch: pytest.MonkeyPatch,
    entity: dict[str, Any],
    expected_method: str,
) -> None:
    monkeypatch.setattr(
        EntityConfigBuilder,
        expected_method,
        lambda self, item, *, skip_idx=None: ({"builder": expected_method}, {}),
    )

    assert build_entity_item(CONF_COVERS, entity, options={}) == (
        {"builder": expected_method},
        {},
    )


@pytest.mark.parametrize(
    ("control_mode", "expected_method"),
    [
        (CONTROL_MODE_DIRECT, "_build_climate_direct_item"),
        (CONTROL_MODE_SETPOINT, "_build_climate_setpoint_item"),
    ],
)
def test_build_entity_item_dispatches_climate(
    monkeypatch: pytest.MonkeyPatch,
    control_mode: str,
    expected_method: str,
) -> None:
    monkeypatch.setattr(
        EntityConfigBuilder,
        expected_method,
        lambda self, item, *, skip_idx=None: ({"builder": expected_method}, {}),
    )

    assert build_entity_item(
        CONF_CLIMATES,
        {CONF_CLIMATE_CONTROL_MODE: control_mode},
        options={},
    ) == (
        {"builder": expected_method},
        {},
    )


def test_validate_entity_fields_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match=r"Unknown field\(s\) for covers: surprise"):
        validate_entity_fields(CONF_COVERS, {"surprise": True})


def test_validate_entity_fields_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValueError, match="Unknown entity type: widgets"):
        validate_entity_fields("widgets", {})


def test_build_entity_sync_preserves_invert_state() -> None:
    """Test the entity sync builder accepts and stores state inversion."""
    item, errors = build_entity_item(
        CONF_ENTITY_SYNC,
        {
            "address": "DB1,X0.0",
            CONF_SOURCE_ENTITY: "binary_sensor.test",
            CONF_INVERT_STATE: True,
        },
        options={},
    )

    assert errors == {}
    assert item is not None
    assert item[CONF_INVERT_STATE] is True


def test_build_entity_item_rejects_invalid_climate_control_mode() -> None:
    item, errors = build_entity_item(
        CONF_CLIMATES,
        {CONF_CLIMATE_CONTROL_MODE: "invalid"},
        options={},
    )

    assert item is None
    assert errors == {"base": "invalid_control_mode"}


@pytest.mark.parametrize(
    ("value_multiplier", "expected"),
    [("0.25", 0.25), ("1,5", 1.5)],
)
def test_build_sensor_normalizes_value_multiplier(
    value_multiplier: str, expected: float
) -> None:
    item, errors = build_entity_item(
        "sensors",
        {"address": "DB1,REAL0", "value_multiplier": value_multiplier},
        options={},
    )

    assert errors == {}
    assert item is not None
    assert item["value_multiplier"] == pytest.approx(expected)


def test_build_number_clamps_limits_to_plc_type_range() -> None:
    item, errors = build_entity_item(
        "numbers",
        {
            "address": "DB1,I2",
            "min_value": -99999,
            "max_value": 99999,
            "step": 1,
        },
        options={},
    )

    assert errors == {}
    assert item is not None
    assert item["min_value"] == -32768.0
    assert item["max_value"] == 32767.0


def test_build_climate_setpoint_rejects_decimal_preset_value() -> None:
    item, errors = build_entity_item(
        CONF_CLIMATES,
        {
            CONF_CLIMATE_CONTROL_MODE: CONTROL_MODE_SETPOINT,
            "current_temperature_address": "DB1,REAL0",
            "target_temperature_address": "DB1,REAL4",
            "preset_mode_heat_value": "2.7",
        },
        options={},
    )

    assert item is None
    assert errors == {"base": "invalid_integer"}
