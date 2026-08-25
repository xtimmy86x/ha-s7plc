"""Tests for the public entity configuration validation API."""

from typing import Any

import pytest

from custom_components.s7plc.config_validation import (
    EntityConfigBuilder,
    build_entity_item,
    validate_entity_fields,
)


def test_entity_availability_policy_validation() -> None:
    """Availability defaults are omitted and BIT policies validate their address."""
    base = {"uid": "stable", "address": "DB1,X0.0"}
    item, errors = build_entity_item("binary_sensors", base, options={})
    assert not errors and "availability_mode" not in item

    item, errors = build_entity_item(
        "binary_sensors",
        {**base, "availability_mode": "bit", "availability_address": " db1,x10.0 "},
        options={},
    )
    assert not errors
    assert item["availability_address"] == "DB1,X10.0"

    for invalid in (
        {**base, "availability_mode": "bit"},
        {**base, "availability_mode": "bit", "availability_address": "DB1,INT10"},
        {**base, "availability_mode": "unknown"},
    ):
        assert build_entity_item("binary_sensors", invalid, options={})[0] is None


def test_non_bit_availability_clears_stale_address() -> None:
    item, errors = build_entity_item(
        "binary_sensors",
        {
            "uid": "stable",
            "address": "DB1,X0.0",
            "availability_mode": "always",
            "availability_address": "DB1,X10.0",
        },
        options={},
    )
    assert not errors
    assert item["availability_mode"] == "always"
    assert "availability_address" not in item
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

@pytest.mark.parametrize(
    ("extra", "expected_mode", "expected_use_state"),
    [
        ({"cover_position_feedback": "timed"}, "timed", False),
        ({"cover_position_feedback": "opening", "opening_state_address": "DB1,X1.0"}, "opening", True),
        ({"cover_position_feedback": "closing", "closing_state_address": "DB1,X1.1"}, "closing", True),
        ({"cover_position_feedback": "both", "opening_state_address": "DB1,X1.0", "closing_state_address": "DB1,X1.1"}, "both", True),
        ({"cover_position_feedback": "status", "cover_status_address": "DB1,B10", "cover_status_open_values": "1"}, "status", False),
    ],
)
def test_traditional_cover_explicit_feedback_modes_keep_operate_time(
    extra: dict[str, Any], expected_mode: str, expected_use_state: bool
) -> None:
    """All explicit modes retain the operational safety timeout."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {"open_command_address": "DB1,X0.0", "close_command_address": "DB1,X0.1", "operate_time": 120, **extra},
        options={},
    )
    assert not errors
    assert item["cover_position_feedback"] == expected_mode
    assert item["use_state_topics"] is expected_use_state
    assert item["operate_time"] == 120


def test_legacy_hybrid_cover_builder_preserves_independent_feedback() -> None:
    """A legacy status word remains movement feedback beside its end-stop."""
    source = {
        "open_command_address": "DB1,X0.0",
        "close_command_address": "DB1,X0.1",
        "opening_state_address": "DB1,X1.0",
        "use_state_topics": True,
        "cover_status_address": "DB1,B10",
        "cover_status_opening_values": "2",
        "operate_time": 120,
    }
    item, errors = build_entity_item(CONF_COVERS, source, options={})
    assert not errors
    assert "cover_position_feedback" not in item
    assert item["use_state_topics"] is True
    assert item["opening_state_address"] == "DB1,X1.0"
    assert item["cover_status_address"] == "DB1,B10"
    assert item["cover_status_opening_values"] == "2"
    assert item["operate_time"] == 120


@pytest.mark.parametrize(
    ("mode", "state_fields"),
    [
        ("timed", {}),
        ("opening", {"opening_state_address": "DB1,X1.0"}),
        ("closing", {"closing_state_address": "DB1,X1.1"}),
        (
            "both",
            {
                "opening_state_address": "DB1,X1.0",
                "closing_state_address": "DB1,X1.1",
            },
        ),
    ],
)
def test_explicit_feedback_preserves_status_word_for_movement(
    mode: str, state_fields: dict[str, str]
) -> None:
    """An explicit position source does not discard status-word movement."""
    source = {
        "open_command_address": "DB1,X0.0",
        "close_command_address": "DB1,X0.1",
        "cover_position_feedback": mode,
        "cover_status_address": "DB1,B10",
        "cover_status_opening_values": "2",
        "cover_status_closing_values": "3",
        "operate_time": 120,
        **state_fields,
    }
    item, errors = build_entity_item(CONF_COVERS, source, options={})
    assert not errors
    assert item["cover_position_feedback"] == mode
    assert item["cover_status_address"] == "DB1,B10"
    assert item["cover_status_opening_values"] == "2"
    assert item["cover_status_closing_values"] == "3"
    assert item["operate_time"] == 120
    for key, value in state_fields.items():
        assert item[key] == value


def test_explicit_feedback_rejects_status_mapping_without_address() -> None:
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "cover_position_feedback": "timed",
            "cover_status_opening_values": "2",
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "cover_status_required"}


def test_explicit_status_builder_removes_incompatible_feedback_only() -> None:
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "cover_position_feedback": "status",
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "1",
            "opening_state_address": "DB1,X1.0",
            "cover_opening_address": "DB1,X2.0",
            "operate_time": 120,
        },
        options={},
    )
    assert not errors
    assert item["operate_time"] == 120
    assert "opening_state_address" not in item
    assert "cover_opening_address" not in item


_TOGGLE_COVER_BASE = {
    "open_command_address": "DB1,X0.0",
    "toggle_mode": True,
    "cover_status_address": "DB1,B10",
    "cover_status_open_values": "0",
    "cover_status_closed_values": "1",
    "cover_status_opening_values": "2",
    "cover_status_closing_values": "3",
}


def test_cover_toggle_pulse_duration_defaults_and_persists() -> None:
    item, errors = build_entity_item(CONF_COVERS, _TOGGLE_COVER_BASE, options={})
    assert not errors
    assert item["toggle_pulse_duration"] == 0.5

    item, errors = build_entity_item(
        CONF_COVERS,
        {**_TOGGLE_COVER_BASE, "toggle_pulse_duration": 1.5},
        options={},
    )
    assert not errors
    assert item["toggle_pulse_duration"] == 1.5


def test_cover_toggle_pulse_duration_absent_when_not_toggle_mode() -> None:
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "close_command_address": "DB1,X0.1",
            "toggle_pulse_duration": 2.0,
        },
        options={},
    )
    assert not errors
    assert "toggle_pulse_duration" not in item


def test_toggle_mode_requires_real_feedback() -> None:
    """toggle_mode can't fall back to a simulated timer like the
    two-address mode does - it needs both motion and settled-state
    feedback, whether via a status word or the boolean alternatives."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {"open_command_address": "DB1,X0.0", "toggle_mode": True},
        options={},
    )
    assert item is None
    assert errors == {"base": "toggle_mode_requires_feedback"}

    item, errors = build_entity_item(CONF_COVERS, _TOGGLE_COVER_BASE, options={})
    assert not errors
    assert item is not None

    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "toggle_mode": True,
            "cover_opening_address": "DB1,X1.0",
            "cover_closing_address": "DB1,X1.1",
            "use_state_topics": True,
            "opening_state_address": "DB1,X1.2",
            "closing_state_address": "DB1,X1.3",
        },
        options={},
    )
    assert not errors
    assert item is not None
