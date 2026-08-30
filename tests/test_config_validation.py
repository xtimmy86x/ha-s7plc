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
    assert "value_multiplier" not in item
    assert item["value_conversions"]["value"] == {
        "type": "multiplier",
        "factor": pytest.approx(expected),
    }


def test_legacy_conversions_are_canonical_before_builders(monkeypatch) -> None:
    """Every builder receives canonical input and never persists legacy keys."""
    seen: list[dict[str, Any]] = []
    sensor_builder = EntityConfigBuilder._build_sensor_item
    light_builder = EntityConfigBuilder._build_light_item

    def capture_sensor(self, user_input, **kwargs):
        seen.append(dict(user_input))
        return sensor_builder(self, user_input, **kwargs)

    def capture_light(self, user_input, **kwargs):
        seen.append(dict(user_input))
        return light_builder(self, user_input, **kwargs)

    monkeypatch.setattr(EntityConfigBuilder, "_build_sensor_item", capture_sensor)
    monkeypatch.setattr(EntityConfigBuilder, "_build_light_item", capture_light)

    sensor, sensor_errors = build_entity_item(
        "sensors",
        {"address": "DB1,REAL0", "value_multiplier": 2},
        options={},
    )
    light, light_errors = build_entity_item(
        "lights",
        {
            "state_address": "DB1,X0.0",
            "brightness_state_address": "DB1,W2",
            "brightness_scale": 1000,
        },
        options={},
    )
    canonical, canonical_errors = build_entity_item(
        "sensors",
        {
            "address": "DB1,REAL4",
            "value_conversions": {"value": {"type": "multiplier", "factor": 3}},
        },
        options={},
    )

    assert sensor_errors == light_errors == canonical_errors == {}
    assert sensor["value_conversions"]["value"] == {
        "type": "multiplier",
        "factor": 2,
    }
    assert light["value_conversions"]["brightness"]["plc_max"] == 1000
    assert canonical["value_conversions"]["value"] == {
        "type": "multiplier",
        "factor": 3,
    }
    legacy_fields = {
        "value_multiplier",
        "brightness_scale",
        "scale_raw_min",
        "scale_raw_max",
    }
    assert all(not legacy_fields & entity.keys() for entity in seen)
    assert all(not legacy_fields & entity.keys() for entity in (sensor, light, canonical))


@pytest.mark.parametrize("legacy_maximum", [0, -1, "invalid", 65536])
def test_build_light_normalizes_invalid_legacy_brightness_scale(
    legacy_maximum: Any,
) -> None:
    """The 7.x input boundary preserves the former safe default behavior."""
    item, errors = build_entity_item(
        "lights",
        {
            "state_address": "DB1,X0.0",
            "brightness_state_address": "DB1,W2",
            "brightness_scale": legacy_maximum,
        },
        options={},
    )

    assert errors == {}
    assert item is not None
    assert "brightness_scale" not in item
    assert item["value_conversions"]["brightness"]["plc_max"] == 255


def test_build_number_preserves_home_assistant_limits() -> None:
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
    assert item["min_value"] == -99999.0
    assert item["max_value"] == 99999.0


@pytest.mark.parametrize(
    ("limits", "expected"),
    [
        ({}, {}),
        ({"min_value": 10}, {"min_value": 10.0}),
        ({"max_value": 60000}, {"max_value": 60000.0}),
        (
            {"min_value": -10, "max_value": 70000},
            {"min_value": -10.0, "max_value": 70000.0},
        ),
    ],
)
def test_build_number_validates_effective_limits_without_persisting_fallbacks(
    limits: dict[str, float], expected: dict[str, float]
) -> None:
    """Missing limits use datatype bounds only for effective validation."""
    item, errors = build_entity_item(
        "numbers", {"address": "DB1,W0", **limits}, options={}
    )

    assert errors == {}
    assert item is not None
    assert {key: item[key] for key in expected} == expected
    for key in {"min_value", "max_value"} - set(expected):
        assert key not in item


@pytest.mark.parametrize(
    "limits",
    [
        {"min_value": 70000},
        {"max_value": -1},
    ],
)
def test_build_number_rejects_single_limit_outside_effective_range(
    limits: dict[str, float],
) -> None:
    """A lone explicit bound must be consistent with the datatype fallback."""
    item, errors = build_entity_item(
        "numbers", {"address": "DB1,W0", **limits}, options={}
    )

    assert item is None
    assert errors == {"base": "invalid_range"}


def test_build_number_uses_state_address_datatype_for_limit_fallback() -> None:
    """A different command datatype cannot change state-side HA defaults."""
    item, errors = build_entity_item(
        "numbers",
        {
            "address": "DB1,W0",
            "command_address": "DB1,REAL4",
            "min_value": 70000,
        },
        options={},
    )

    assert item is None
    assert errors == {"base": "invalid_range"}


@pytest.mark.parametrize("data_type", ["REAL", "LREAL"])
@pytest.mark.parametrize(
    ("limits", "valid"),
    [
        ({}, False),
        ({"min_value": -10}, False),
        ({"max_value": 10}, False),
        ({"min_value": -10, "max_value": 10}, True),
    ],
)
def test_build_float_number_requires_both_home_assistant_limits(
    data_type: str, limits: dict[str, float], valid: bool
) -> None:
    """REAL/LREAL require a practical explicit HA operating interval."""
    item, errors = build_entity_item(
        "numbers", {"address": f"DB1,{data_type}0", **limits}, options={}
    )

    if valid:
        assert errors == {}
        assert item is not None
        assert item["min_value"] == -10.0
        assert item["max_value"] == 10.0
    else:
        assert item is None
        assert errors == {"base": "min_max_required_for_real"}


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
    """Plain traditional covers (no toggle_mode) keep the pre-existing
    coupling: a status word chosen for position feedback is authoritative
    for movement too, so separately configured movement bits are still
    discarded - unlike toggle_mode, which treats the two as independent
    sources (see test_toggle_mode_keeps_movement_bits_with_status_position
    below). Extending independence to plain traditional covers would need
    a matching S7Cover._get_feedback_movement() runtime change, which is
    out of scope (position mode has its own independent runtime instead -
    see test_position_cover_movement_bits_survive_status_position_feedback)."""
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


def test_toggle_mode_keeps_movement_bits_with_status_position() -> None:
    """toggle_mode itself keeps the independent-source model: a status word
    chosen for position feedback does not discard separately configured
    movement bits (contrast with the plain-traditional test above)."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "toggle_mode": True,
            "cover_position_feedback": "status",
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "1",
            "cover_status_closed_values": "2",
            "cover_opening_address": "DB1,X2.0",
            "cover_closing_address": "DB1,X2.1",
        },
        options={},
    )
    assert not errors
    assert item["cover_opening_address"] == "DB1,X2.0"
    assert item["cover_closing_address"] == "DB1,X2.1"


_TOGGLE_COVER_BASE = {
    "open_command_address": "DB1,X0.0",
    "toggle_mode": True,
    "cover_status_address": "DB1,B10",
    "cover_status_open_values": "0",
    "cover_status_closed_values": "1",
    "cover_status_opening_values": "2",
    "cover_status_closing_values": "3",
    "cover_status_stopped_values": "4",
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


def test_cover_toggle_mode_key_only_persisted_when_true() -> None:
    """PR #117 review round 7, point 8: don't change every existing
    traditional cover's persisted shape just because toggle_mode exists -
    only write the key when the feature is actually enabled, matching
    every other optional cover field."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {"open_command_address": "DB1,X0.0", "close_command_address": "DB1,X0.1"},
        options={},
    )
    assert not errors
    assert "toggle_mode" not in item

    item, errors = build_entity_item(CONF_COVERS, _TOGGLE_COVER_BASE, options={})
    assert not errors
    assert item["toggle_mode"] is True


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


def test_toggle_mode_with_status_address_requires_stopped_mapping() -> None:
    """A status-word toggle_mode setup must map "stopped" explicitly, so a
    genuine mid-travel stop can be told apart from a missing/unmatched
    status value (maintainer review point 2)."""
    without_stopped = {
        k: v for k, v in _TOGGLE_COVER_BASE.items() if k != "cover_status_stopped_values"
    }
    item, errors = build_entity_item(CONF_COVERS, without_stopped, options={})
    assert item is None
    assert errors == {"base": "toggle_mode_requires_stopped_mapping"}

    # The bit-based alternative (no cover_status_address) is unaffected.
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


def test_toggle_mode_stopped_mapping_not_required_when_status_is_position_only() -> None:
    """PR #117 review round 3, point 3: the "stopped" mapping requirement
    must be tied to whether the status word is the *selected motion
    source*, not merely to cover_status_address's presence. Here the status
    word only carries open/closed (position), while opening/closing/
    stopped come from bits (movement) - status has no need for a "stopped"
    value since it never drives motion detection."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            "open_command_address": "DB1,X0.0",
            "toggle_mode": True,
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "0",
            "cover_status_closed_values": "1",
            "cover_opening_address": "DB1,X1.0",
            "cover_closing_address": "DB1,X1.1",
        },
        options={},
    )
    assert not errors
    assert item is not None
    assert "cover_status_stopped_values" not in item


_POSITION_COVER_BASE = {
    "position_state_address": "DB1,B0",
}


def test_position_cover_gets_same_feedback_selector_as_traditional() -> None:
    """Position-mode covers accept opening_state_address/closing_state_address
    and the movement bits, same as traditional/toggle covers."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "both",
            "opening_state_address": "DB1,X1.0",
            "closing_state_address": "DB1,X1.1",
            "cover_opening_address": "DB1,X2.0",
            "cover_closing_address": "DB1,X2.1",
            "cover_stopped_address": "DB1,X2.2",
        },
        options={},
    )
    assert not errors
    assert item["cover_position_feedback"] == "both"
    assert item["opening_state_address"] == "DB1,X1.0"
    assert item["closing_state_address"] == "DB1,X1.1"
    assert item["cover_opening_address"] == "DB1,X2.0"
    assert item["cover_closing_address"] == "DB1,X2.1"
    assert item["cover_stopped_address"] == "DB1,X2.2"


def test_position_cover_status_feedback_requires_matching_fields() -> None:
    """cover_position_feedback="status" requires cover_status_address plus
    an open/closed value mapping - that's the only mapping is_closed can
    actually resolve through for position covers."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {**_POSITION_COVER_BASE, "cover_position_feedback": "status"},
        options={},
    )
    assert item is None
    assert errors == {"base": "cover_status_required"}

    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "status",
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "1",
        },
        options={},
    )
    assert not errors
    assert item["cover_position_feedback"] == "status"
    assert item["cover_status_address"] == "DB1,B10"


def test_position_cover_explicit_status_rejects_movement_only_mapping() -> None:
    """An explicit cover_position_feedback="status" with only a
    movement mapping (opening/closing/stopped, no open/closed) must be
    rejected - is_closed can never resolve through it, so accepting it
    would silently fall back to the raw position value at runtime instead
    of the status word the user explicitly asked for (PR #124 review,
    third round). Contrast with the legacy inferred shape (no explicit
    selector), which correctly infers "position" instead - see
    test_position_cover_legacy_movement_only_status_infers_position_not_status."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "status",
            "cover_status_address": "DB1,B10",
            "cover_status_opening_values": "1",
            "cover_status_closing_values": "2",
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "cover_status_required"}


def test_position_cover_opening_closing_feedback_requires_state_address() -> None:
    """cover_position_feedback in {"opening","closing","both"} requires the
    matching end-stop address, same as traditional covers."""
    # "opening" needs opening_state_address; omitting it errors even though
    # closing_state_address (irrelevant to this mode) is present.
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "opening",
            "closing_state_address": "DB1,X1.1",
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "state_addresses_required"}

    # "closing" needs closing_state_address.
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "closing",
            "opening_state_address": "DB1,X1.0",
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "state_addresses_required"}

    # "both" needs both - only one supplied still errors.
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "both",
            "opening_state_address": "DB1,X1.0",
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "state_addresses_required"}


def test_position_cover_movement_bits_survive_status_position_feedback() -> None:
    """Movement bits are an independent source and survive regardless of
    the position_feedback choice - the user decides which sources to wire
    up, same as traditional/toggle covers now."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_position_feedback": "status",
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "1",
            "cover_opening_address": "DB1,X2.0",
            "cover_closing_address": "DB1,X2.1",
        },
        options={},
    )
    assert not errors
    assert item["cover_opening_address"] == "DB1,X2.0"
    assert item["cover_closing_address"] == "DB1,X2.1"


def test_position_cover_legacy_without_selector_infers_status_from_cover_status_address() -> None:
    """A legacy position cover with only cover_status_address (no
    persisted selector, no end-stop addresses) is not required to also
    have a status word, since feedback_mode infers "status" for it -
    unlike a cover with no signal at all, which infers "position" and
    needs nothing."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_status_address": "DB1,B10",
            "cover_status_open_values": "1",
        },
        options={},
    )
    assert not errors
    assert "cover_position_feedback" not in item
    assert item["cover_status_address"] == "DB1,B10"


def test_position_cover_legacy_movement_only_status_infers_position_not_status() -> None:
    """A legacy position cover whose cover_status_address is configured
    only for movement (opening/closing/stopped values, no open/closed) was
    never a position source - is_closed always fell back to the raw
    position value for this shape. feedback_mode must infer "position",
    not "status", so no open/closed mapping becomes newly required and the
    entity keeps saving through the visual editor (PR #124 review, point 2)."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {
            **_POSITION_COVER_BASE,
            "cover_status_address": "DB1,B10",
            "cover_status_opening_values": "1",
            "cover_status_closing_values": "2",
            "cover_status_stopped_values": "3",
        },
        options={},
    )
    assert not errors
    assert "cover_position_feedback" not in item
    assert item["cover_status_address"] == "DB1,B10"
    assert item["cover_status_opening_values"] == "1"


def test_position_cover_default_feedback_is_position_not_timed() -> None:
    """Position covers have a continuous 0-100 reading of their own, so
    the "no separate source" concept is named "position", not "timed" -
    "timed" only means something for traditional covers, which have no
    live position signal to fall back on."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {**_POSITION_COVER_BASE, "cover_position_feedback": "position"},
        options={},
    )
    assert not errors
    assert item["cover_position_feedback"] == "position"


def test_position_cover_legacy_timed_value_normalizes_to_position() -> None:
    """A position cover saved with the legacy "timed" value (briefly
    conflated with traditional covers' concept) is normalized to
    "position" - the two behave identically at runtime, but persisting
    "timed" going forward would be a misleading label."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {**_POSITION_COVER_BASE, "cover_position_feedback": "timed"},
        options={},
    )
    assert not errors
    assert item["cover_position_feedback"] == "position"


def test_cover_toggle_pulse_duration_uses_shared_validation_helper() -> None:
    """toggle_pulse_duration goes through the same parse_pulse_duration()
    helper as switches/lights (0.1-60s range, falls back to the default on
    invalid input) instead of a bare float(...) conversion - maintainer
    review point 3."""
    item, errors = build_entity_item(
        CONF_COVERS,
        {**_TOGGLE_COVER_BASE, "toggle_pulse_duration": "not-a-number"},
        options={},
    )
    assert not errors
    assert item["toggle_pulse_duration"] == 0.5  # DEFAULT_PULSE_DURATION

    item, errors = build_entity_item(
        CONF_COVERS,
        {**_TOGGLE_COVER_BASE, "toggle_pulse_duration": 999},
        options={},
    )
    assert not errors
    assert item["toggle_pulse_duration"] == 0.5  # out of 0.1-60s range

    item, errors = build_entity_item(
        CONF_COVERS,
        {**_TOGGLE_COVER_BASE, "toggle_pulse_duration": 2.34},
        options={},
    )
    assert not errors
    assert item["toggle_pulse_duration"] == 2.3  # rounded to 1 decimal
