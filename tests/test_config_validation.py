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
    CONF_POSITION_STATE_ADDRESS,
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


def test_build_entity_item_rejects_invalid_climate_control_mode() -> None:
    item, errors = build_entity_item(
        CONF_CLIMATES,
        {CONF_CLIMATE_CONTROL_MODE: "invalid"},
        options={},
    )

    assert item is None
    assert errors == {"base": "invalid_control_mode"}