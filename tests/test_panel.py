"""Tests for the native configuration panel helpers."""

import pytest

from custom_components.s7plc.panel import _entity_from_message


def test_entity_from_visual_editor() -> None:
    entity = {"name": "Temperatura", "address": "DB1,REAL0"}

    assert _entity_from_message({"entity": entity}) == entity


def test_entity_from_yaml_editor() -> None:
    assert _entity_from_message(
        {"entity_yaml": 'name: "Temperatura sala"\naddress: "DB1,REAL0"\ninvert_state: false'}
    ) == {
        "name": "Temperatura sala",
        "address": "DB1,REAL0",
        "invert_state": False,
    }


@pytest.mark.parametrize(
    "message",
    [
        {},
        {"entity_yaml": ""},
        {"entity_yaml": "- not\n- a mapping"},
        {"entity_yaml": "[invalid"},
        {"entity_yaml": "1: numeric key"},
    ],
)
def test_entity_from_message_rejects_invalid_input(message) -> None:
    with pytest.raises(ValueError):
        _entity_from_message(message)