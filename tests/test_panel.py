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
                {
                    "name": "Temp",
                    "address": "DB1,REAL0",
                    "uid": "dev1:sensor:DB1,REAL0",
                },
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


def test_panel_exposes_climate_mode_and_status_fields() -> None:
    """The visual editor lets you configure the HVAC mode <-> PLC value
    mapping (setpoint control mode), not just the mode/status addresses —
    these fields didn't exist yet when the panel was first built."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    climates_line = next(
        line for line in source.splitlines() if line.strip().startswith("climates:[")
    )
    for key in (
        "on_off_address",
        "preset_mode_off_value",
        "preset_mode_heat_value",
        "preset_mode_cool_value",
        "preset_mode_heat_cool_value",
        "preset_mode_auto_value",
        "preset_mode_dry_value",
        "preset_mode_fan_only_value",
        "hvac_status_off_values",
        "hvac_status_heating_values",
        "hvac_status_cooling_values",
        "hvac_status_idle_values",
        "hvac_status_drying_values",
        "hvac_status_fan_values",
        "hvac_status_preheating_values",
    ):
        assert key in climates_line, f"{key} missing from climates FIELDS"
        assert key in source, f"{key} missing a translated label"

    # These fields only apply to setpoint control mode, so direct mode must
    # hide them (matches the existing address/mode-address hiding).
    mode_hidden_line = next(
        line
        for line in source.splitlines()
        if "direct:" in line and "on_off_address" in line
    )
    assert "preset_mode_off_value" in mode_hidden_line
    assert "hvac_status_off_values" in mode_hidden_line


def test_panel_hints_mode_and_status_field_semantics() -> None:
    """preset_mode_*_value and hvac_status_*_values fields explain that -1
    hides/skips, and that status fields accept multiple comma-separated
    values — otherwise this is only discoverable via the YAML editor or
    the docs, not from the visual editor itself."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "presetValue=key.startsWith('preset_mode_')&&key.endsWith('_value')" in source
    assert "statusValues=key.startsWith('hvac_status_')&&key.endsWith('_values')" in source
    assert 'preset_value_help:"Set to -1 to hide this mode."' in source
    assert "comma-separated" in source
    assert "presetValue?" in source and "statusValues?" in source


def test_panel_drops_retired_scaling_fields() -> None:
    """Sensors/numbers/lights no longer expose the separate scale fields
    that were folded into the address field's inline Scale(...) syntax;
    only numbers' min_value/max_value survive, since those double as the
    Number entity's plain HA-facing bounds independent of scaling."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    sensors_line = next(
        line for line in source.splitlines() if line.strip().startswith("sensors:[")
    )
    numbers_line = next(
        line for line in source.splitlines() if line.strip().startswith("numbers:[")
    )
    lights_line = next(
        line for line in source.splitlines() if line.strip().startswith("lights:[")
    )

    for retired in ("value_multiplier", "scale_raw_min", "scale_raw_max"):
        assert retired not in sensors_line
        assert retired not in numbers_line
    assert "min_value" not in sensors_line
    assert "max_value" not in sensors_line
    assert "min_value" in numbers_line
    assert "max_value" in numbers_line
    assert "brightness_scale" not in lights_line


def test_panel_shows_scale_hint_only_on_scalable_fields() -> None:
    """The Scale(...) hint appears only next to fields that actually accept
    it, keyed by (entity type, field), not blindly on every address field."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "const SCALE_FIELDS" in source
    assert 'scale_help:"Optional scaling' in source
    assert "scalable?' '+this.t('scale_help')" in source
