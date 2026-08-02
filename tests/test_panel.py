"""Tests for the native configuration panel helpers."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.s7plc.panel import _entity_from_message, _entry_payload


PANEL_JAVASCRIPT = Path("custom_components/s7plc/www/s7plc-panel.js")


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


def test_panel_uses_current_home_assistant_dialog_api() -> None:
    """Ensure editor actions remain visible and can close the current dialog."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert '<ha-dialog-footer slot="footer">' in source
    assert "dialog.headerTitle=" in source
    assert "dialog.open=false" in source
    assert "dialog.close()" not in source


@pytest.mark.parametrize("connected", [True, False])
def test_entry_payload_includes_connection_status(connected) -> None:
    """Expose the coordinator connection state to the panel."""
    coordinator = SimpleNamespace(is_connected=lambda: connected)
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="PLC test",
        data={"host": "192.0.2.1"},
        options={},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )

    assert _entry_payload(entry)["connected"] is connected


def test_entry_payload_maps_entity_ids(monkeypatch) -> None:
    """Expose the entity_id of each configured item to the panel."""
    from homeassistant.helpers import entity_registry as er

    registry = SimpleNamespace(
        async_get_entity_id=lambda domain, platform, uid: f"{domain}.demo"
        if uid == "dev1:sensor:DB1,REAL0"
        else None
    )
    monkeypatch.setattr(er, "async_get", lambda hass: registry)
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="PLC test",
        data={"host": "192.0.2.1"},
        options={
            "sensors": [
                {"name": "Temp", "address": "DB1,REAL0"},
                {"name": "Broken"},
            ]
        },
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(is_connected=lambda: True),
            device_id="dev1",
        ),
    )

    payload = _entry_payload(entry, hass=object())

    assert payload["entity_ids"]["sensors"] == ["sensor.demo", None]
    assert payload["entity_ids"]["switches"] == []


def test_panel_renders_current_state_badges() -> None:
    """The panel shows the live state of every configured entity."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "state-badge" in source
    assert "entry.entity_ids?.[type]?.[i]" in source
    assert "this.updateStates()" in source