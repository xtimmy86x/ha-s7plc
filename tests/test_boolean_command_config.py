"""Shared configuration behavior for switch and light boolean commands."""

from copy import deepcopy
from typing import Any

import pytest

from custom_components.s7plc.config_validation import build_entity_item


@pytest.fixture(params=["switches", "lights"])
def entity_type(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.mark.parametrize(
    ("mode", "expected_mode"),
    [
        ({}, {}),
        ({"sync_state": True}, {"sync_state": True}),
        (
            {"pulse_command": True},
            {"pulse_command": True, "pulse_duration": 0.9},
        ),
        ({"single_fire_command": True}, {"single_fire_command": True}),
    ],
    ids=["direct", "sync", "pulse", "single-fire"],
)
def test_boolean_command_modes_preserve_normalization(
    entity_type: str, mode: dict[str, Any], expected_mode: dict[str, Any]
) -> None:
    """Both platforms produce the same settings without changing their input."""
    config = {
        "address": "DB9,X0.0",
        "state_address": " db1,x0.0 ",
        "command_address": " db1,x0.1 ",
        "name": "Output",
        "area": "workshop",
        "scan_interval": "0.25",
        "pulse_duration": 0.86,
        "single_fire_command": False,
        **mode,
    }
    original = deepcopy(config)
    expected = {
        "state_address": "db1,x0.0",
        "command_address": "db1,x0.1",
        "name": "Output",
        "area": "workshop",
        "sync_state": False,
        "pulse_command": False,
        "scan_interval": 0.25,
        **expected_mode,
    }

    assert build_entity_item(entity_type, config, options={}) == (expected, {})
    assert build_entity_item(entity_type, expected, options={}) == (expected, {})
    assert config == original


@pytest.mark.parametrize("state_address", [None, ""])
def test_boolean_command_accepts_legacy_address(
    entity_type: str, state_address: str | None
) -> None:
    """Empty state addresses still fall back to the old address field."""
    assert build_entity_item(
        entity_type,
        {
            "address": " DB1,X0.0 ",
            "state_address": state_address,
            "command_address": "",
            "name": "",
            "area": "__none__",
        },
        options={},
    ) == (
        {"state_address": "DB1,X0.0", "sync_state": False, "pulse_command": False},
        {},
    )


@pytest.mark.parametrize("stored_key", ["state_address", "address"])
def test_boolean_command_duplicates_are_scoped_and_allow_editing(
    entity_type: str, stored_key: str
) -> None:
    """Editing skips only its own row and other platforms do not conflict."""
    other_type = "lights" if entity_type == "switches" else "switches"
    options = {
        entity_type: [{stored_key: " db1,x0.0 "}, {stored_key: "DB1,X1.0"}],
        other_type: [{stored_key: "DB1,X0.0"}],
    }
    original = deepcopy(options)
    config = {"state_address": "DB1,X0.0"}
    assert build_entity_item(entity_type, config, options=options) == (
        None,
        {"base": "duplicate_entry"},
    )
    # A duplicate remains the first error even if the command is invalid.
    assert build_entity_item(
        entity_type, {**config, "command_address": "invalid"}, options=options
    ) == (None, {"base": "duplicate_entry"})
    assert build_entity_item(entity_type, config, options=options, skip_idx=0) == (
        {**config, "sync_state": False, "pulse_command": False},
        {},
    )
    assert build_entity_item(
        entity_type,
        {"state_address": "DB1,X1.0"},
        options=options,
        skip_idx=0,
    ) == (None, {"base": "duplicate_entry"})
    assert options == original


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"state_address": "invalid"}, "invalid_address"),
        ({"state_address": " "}, "invalid_address"),
        ({"command_address": "invalid"}, "invalid_address"),
        (
            {"command_address": "invalid", "sync_state": True, "pulse_command": True},
            "invalid_address",
        ),
        ({"sync_state": True, "pulse_command": True}, "sync_pulse_conflict"),
        ({"single_fire_command": True, "sync_state": True}, "single_fire_conflict"),
        (
            {"single_fire_command": True, "pulse_command": True},
            "single_fire_conflict",
        ),
        (
            {"single_fire_command": True, "sync_state": True, "pulse_command": True},
            "single_fire_conflict",
        ),
        ({"sync_state": True, "command_address": None}, "sync_same_address"),
        (
            {"sync_state": True, "command_address": " db1,x0.0 "},
            "sync_same_address",
        ),
    ],
)
def test_boolean_command_validation_errors(
    entity_type: str, fields: dict[str, Any], error: str
) -> None:
    """Keep the public error codes and command-mode validation order."""
    config = {
        "address": "DB9,X0.0",
        "state_address": "DB1,X0.0",
        "command_address": "DB1,X0.1",
        **fields,
    }
    original = deepcopy(config)
    assert build_entity_item(entity_type, config, options={}) == (None, {"base": error})
    assert config == original


@pytest.mark.parametrize(
    ("duration", "expected_duration"),
    [
        # An empty field keeps the platform default instead of persisting it.
        (None, None),
        ("", None),
        (0.1, 0.1),
        ("2.34", 2.3),
    ],
)
def test_boolean_command_pulse_duration_normalization(
    entity_type: str,
    duration: Any,
    expected_duration: float | None,
) -> None:
    expected = {
        "state_address": "DB1,X0.0",
        "sync_state": False,
        "pulse_command": True,
    }
    if expected_duration is not None:
        expected["pulse_duration"] = expected_duration

    assert build_entity_item(
        entity_type,
        {
            "state_address": "DB1,X0.0",
            "pulse_command": True,
            "pulse_duration": duration,
        },
        options={},
    ) == (expected, {})


@pytest.mark.parametrize("duration", ["invalid", 0, -1, 61, True])
def test_boolean_command_rejects_invalid_pulse_duration(
    entity_type: str, duration: Any
) -> None:
    """Out-of-range pulses are reported instead of silently becoming 0.5 s."""
    assert build_entity_item(
        entity_type,
        {
            "state_address": "DB1,X0.0",
            "pulse_command": True,
            "pulse_duration": duration,
        },
        options={},
    ) == (None, {"base": "invalid_pulse_duration"})


@pytest.mark.parametrize(
    ("interval", "expected_interval"),
    [
        (None, None),
        ("", None),
        ("invalid", None),
        (0, None),
        (-1, None),
        (7200, 3600.0),
        (0.01, 0.05),
        ("0.25", 0.25),
    ],
)
def test_boolean_command_scan_interval_normalization(
    entity_type: str,
    interval: Any,
    expected_interval: float | None,
) -> None:
    expected = {
        "state_address": "DB1,X0.0",
        "sync_state": False,
        "pulse_command": True,
        "pulse_duration": 2.0,
    }
    if expected_interval is not None:
        expected["scan_interval"] = expected_interval

    assert build_entity_item(
        entity_type,
        {
            "state_address": "DB1,X0.0",
            "pulse_command": True,
            "pulse_duration": 2,
            "scan_interval": interval,
        },
        options={},
    ) == (expected, {})


@pytest.mark.parametrize(
    "mode",
    [{}, {"sync_state": True}, {"pulse_command": True}, {"single_fire_command": True}],
)
@pytest.mark.parametrize("brightness_command", [None, " DB1,W4 "])
def test_light_adds_brightness_to_boolean_command(
    mode: dict[str, bool], brightness_command: str | None
) -> None:
    """Dimmer addresses extend the boolean settings; command omission is kept."""
    config = {
        "state_address": "DB1,X0.0",
        "command_address": "DB1,X0.1",
        "brightness_state_address": " DB1,W2 ",
        "brightness_command_address": brightness_command,
        "scan_interval": "0.25",
        **mode,
    }
    original = deepcopy(config)
    expected = {
        "state_address": "DB1,X0.0",
        "command_address": "DB1,X0.1",
        "sync_state": False,
        "pulse_command": False,
        "scan_interval": 0.25,
        "brightness_state_address": "DB1,W2",
        **mode,
    }
    if brightness_command is not None:
        expected["brightness_command_address"] = "DB1,W4"

    assert build_entity_item("lights", config, options={}) == (expected, {})
    assert config == original


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"brightness_state_address": "invalid"}, "invalid_address"),
        ({"brightness_command_address": "invalid"}, "invalid_address"),
        (
            {"brightness_state_address": "invalid", "sync_state": True},
            "sync_same_address",
        ),
    ],
)
def test_light_validates_brightness_after_boolean_command(
    fields: dict[str, Any], error: str
) -> None:
    assert build_entity_item(
        "lights",
        {
            "state_address": "DB1,X0.0",
            "brightness_state_address": "DB1,W2",
            **fields,
        },
        options={},
    ) == (None, {"base": error})


def test_light_ignores_brightness_command_without_state() -> None:
    """A brightness command alone does not enable dimming."""
    assert build_entity_item(
        "lights",
        {"state_address": "DB1,X0.0", "brightness_command_address": "invalid"},
        options={},
    ) == (
        {"state_address": "DB1,X0.0", "sync_state": False, "pulse_command": False},
        {},
    )
