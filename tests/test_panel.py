"""Tests for the native configuration panel helpers."""

import json
import shutil
import subprocess
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


def test_panel_hides_inactive_editor_mode() -> None:
    """Keep the visual and YAML editors mutually exclusive in the dialog layout."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert '<div class="yaml-editor" style="display:none">' in source
    assert ".visual-form').style.display=mode==='visual'?'flex':'none'" in source
    assert ".yaml-editor').style.display=mode==='yaml'?'block':'none'" in source


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
    setpoint_only_keys = (
        "on_off_address",
        "preset_mode_bidirectional",
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
        "hvac_status_defrosting_values",
    )
    for key in setpoint_only_keys:
        assert key in climates_line, f"{key} missing from climates FIELDS"
        assert key in source, f"{key} missing a translated label"

    # These fields only apply to setpoint control mode, so direct mode must
    # hide every one of them (matches the existing address/mode-address
    # hiding) — regression test for hvac_status_defrosting_values and
    # preset_mode_bidirectional being added to FIELDS.climates but never to
    # MODE_HIDDEN.climates.direct, so they stayed visible (and got saved) in
    # Direct control mode even though they're meaningless there.
    mode_hidden_line = next(
        line
        for line in source.splitlines()
        if "direct:" in line and "on_off_address" in line
    )
    for key in setpoint_only_keys:
        assert key in mode_hidden_line, f"{key} missing from MODE_HIDDEN.climates.direct"


def test_panel_hints_mode_and_status_field_semantics() -> None:
    """preset_mode_*_value and hvac_status_*_values fields explain that
    leaving the field empty hides/skips it (no reserved sentinel value, so
    every PLC integer including -1 stays available), and that status fields
    accept multiple comma-separated values — otherwise this is only
    discoverable via the YAML editor or the docs, not from the visual
    editor itself."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "presetValue=key.startsWith('preset_mode_')&&key.endsWith('_value')" in source
    assert "statusValues=key.startsWith('hvac_status_')&&key.endsWith('_values')" in source
    assert 'preset_value_help:"Leave empty to hide this mode."' in source
    assert "comma-separated" in source
    assert "presetValue?" in source and "statusValues?" in source
    # Preset values are PLC integer mode codes: step=1, not step=any (which
    # would silently allow decimal input to be truncated).
    assert "(presetValue?'step=\"1\"':'step=\"any\"')" in source


def test_panel_hides_climate_preset_values_when_preset_mode_address_unused() -> None:
    """In Setpoint mode, the per-mode preset_mode_*_value fields are
    meaningless without preset_mode_address filled in — dynamically
    hidden (and stripped on save) until it has a value."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "CLIMATE_PRESET_VALUE_FIELDS" in source
    assert (
        "const CLIMATE_PRESET_VALUE_FIELDS = "
        '["preset_mode_off_value","preset_mode_heat_value",'
        '"preset_mode_cool_value","preset_mode_heat_cool_value",'
        '"preset_mode_auto_value","preset_mode_dry_value",'
        '"preset_mode_fan_only_value","preset_mode_bidirectional"]'
    ) in source
    assert (
        "if(!form.elements.preset_mode_address?.value.trim())"
        "{hidden=[...hidden,...CLIMATE_PRESET_VALUE_FIELDS];}"
    ) in source
    # Dynamic hide: the preset-mode-address input triggers a re-sync on input.
    assert "form.elements.preset_mode_address.oninput=syncMode" in source
    assert (
        "if(!entity.preset_mode_address){"
        "CLIMATE_PRESET_VALUE_FIELDS.forEach(k=>delete entity[k]);}"
    ) in source


def test_panel_hides_climate_status_values_when_hvac_status_address_unused() -> None:
    """In Setpoint mode, the per-status hvac_status_*_values fields are
    meaningless without hvac_status_address filled in — dynamically
    hidden (and stripped on save) until it has a value."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "CLIMATE_STATUS_VALUE_FIELDS" in source
    assert (
        "const CLIMATE_STATUS_VALUE_FIELDS = "
        '["hvac_status_off_values","hvac_status_heating_values",'
        '"hvac_status_cooling_values","hvac_status_idle_values",'
        '"hvac_status_drying_values","hvac_status_fan_values",'
        '"hvac_status_preheating_values","hvac_status_defrosting_values"]'
    ) in source
    assert (
        "if(!form.elements.hvac_status_address?.value.trim())"
        "{hidden=[...hidden,...CLIMATE_STATUS_VALUE_FIELDS];}"
    ) in source
    # Dynamic hide: the hvac-status-address input triggers a re-sync on input.
    assert "form.elements.hvac_status_address.oninput=syncMode" in source
    assert (
        "if(!entity.hvac_status_address){"
        "CLIMATE_STATUS_VALUE_FIELDS.forEach(k=>delete entity[k]);}"
    ) in source


def test_panel_rejects_duplicate_climate_values() -> None:
    """In Setpoint mode, saving rejects the same PLC value assigned to two
    different preset modes or two different HVAC statuses, mirroring
    config_flow.py's server-side validation client-side too — otherwise the
    panel would silently accept configs the classic options flow wouldn't."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "climate_duplicate_preset_error" in source
    assert "climate_duplicate_status_error" in source
    assert "presetSeen" in source and "statusSeen" in source


def test_panel_clearing_a_preset_mode_value_stores_null_not_deletes() -> None:
    """Clearing a preset_mode_*_value field must send an explicit null to
    the backend, not silently drop the key. climate.py falls back to a
    non-empty default (0/1/2/3) for OFF/HEAT/COOL/HEAT_COOL when the key is
    entirely absent, so dropping the key on clear would silently re-enable
    a mode the user just tried to disable — the same class of bug fixed in
    config_flow.py's _build_climate_setpoint_item. Regression test."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "presetModeValue" in source
    assert "entity[key]=null" in source
    # The duplicate-value check must also skip nulled-out (cleared) fields,
    # not just genuinely-undefined ones, or two cleared modes would falsely
    # collide as "duplicate" nulls.
    assert "entity[k]===undefined||entity[k]===null" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_legacy_climate_preserves_core_preset_defaults_when_resaved() -> None:
    """Opening a pre-existing (or brand-new) climate in the side panel and
    saving without touching preset_mode_off/heat/cool/heat_cool_value must
    not silently disable those modes.

    Those 4 "core" modes have historical implicit defaults (0/1/2/3) that
    still apply when the key is missing from the stored item entirely (a
    legacy climate configured before these fields existed, or a brand-new
    one). Before this fix, field() rendered a missing key the same as an
    explicitly-cleared one (both blank), so formEntity's null-on-clear
    logic (added to let users actually disable a core mode) would store an
    explicit null for a field the user never touched, wiping out the
    default. Regression test for maintainer feedback on PR #99: runs the
    real field() method in a minimal Node sandbox and asserts the rendered
    input value, not just that certain strings exist in the source.
    """
    cases = [
        # (key, item, expected rendered value)
        ("preset_mode_off_value", {}, "0"),
        ("preset_mode_heat_value", {}, "1"),
        ("preset_mode_cool_value", {}, "2"),
        ("preset_mode_heat_cool_value", {}, "3"),
        # Explicitly disabled (user cleared it) must stay blank, not revert
        # to the default.
        ("preset_mode_off_value", {"preset_mode_off_value": None}, ""),
        ("preset_mode_heat_cool_value", {"preset_mode_heat_cool_value": None}, ""),
        # An explicit value (of any kind) is rendered as-is.
        ("preset_mode_off_value", {"preset_mode_off_value": 5}, "5"),
        # Modes with no historical default (AUTO/DRY/FAN_ONLY) stay blank
        # whether the key is missing or explicitly null - unaffected by
        # this fix, included to pin down the boundary.
        ("preset_mode_auto_value", {}, ""),
        ("preset_mode_auto_value", {"preset_mode_auto_value": None}, ""),
    ]

    script = f"""
    const vm = require('vm');
    global.HTMLElement = class {{}};
    global.customElements = {{ define() {{}} }};
    const fs = require('fs');
    const src = fs.readFileSync({json.dumps(str(PANEL_JAVASCRIPT))}, 'utf8');
    vm.runInThisContext(src + '\\nglobalThis.__Panel = S7PlcConfigurationPanel;', {{filename: 'panel.js'}});
    const panel = new (globalThis.__Panel)();
    panel.t = (k) => k;
    panel.escape = (v) => String(v);

    const cases = {json.dumps(cases)};
    const results = cases.map(([key, item]) => {{
        const html = panel.field([key, 'label', 'number', false], item);
        const m = html.match(/value="([^"]*)"/);
        return m ? m[1] : null;
    }});
    console.log(JSON.stringify(results));
    """

    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = [case[2] for case in cases]
    assert actual == expected, (
        f"field() rendered values {actual}, expected {expected} for cases "
        f"{[(c[0], c[1]) for c in cases]}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_legacy_climate_preserves_core_status_defaults_when_resaved() -> None:
    """Same bug class as the preset-value one above, mirrored on the
    status-matching side: hvac_status_off/heating/cooling_values also carry
    non-empty historical defaults ("0"/"1"/"2"), unlike idle/drying/fan/
    preheating/defrosting which default to "". A never-configured (or
    legacy) climate must show these 3 fields pre-filled with their
    historical default, not blank - otherwise the panel misleadingly shows
    "empty" for a status that climate.py is still actively matching
    internally (e.g. a status address reporting 2 shows "Cooling" even
    though the panel's cooling field looks unconfigured).
    """
    cases = [
        # (key, item, expected rendered value)
        ("hvac_status_off_values", {}, "0"),
        ("hvac_status_heating_values", {}, "1"),
        ("hvac_status_cooling_values", {}, "2"),
        # Explicitly disabled (user cleared it) must stay blank, not revert
        # to the default.
        ("hvac_status_off_values", {"hvac_status_off_values": ""}, ""),
        ("hvac_status_cooling_values", {"hvac_status_cooling_values": ""}, ""),
        # An explicit value (of any kind) is rendered as-is.
        ("hvac_status_cooling_values", {"hvac_status_cooling_values": "5"}, "5"),
        # Statuses with no historical default (IDLE/DRYING/...) stay blank
        # whether the key is missing or explicitly empty - unaffected by
        # this fix, included to pin down the boundary.
        ("hvac_status_idle_values", {}, ""),
        ("hvac_status_idle_values", {"hvac_status_idle_values": ""}, ""),
    ]

    script = f"""
    const vm = require('vm');
    global.HTMLElement = class {{}};
    global.customElements = {{ define() {{}} }};
    const fs = require('fs');
    const src = fs.readFileSync({json.dumps(str(PANEL_JAVASCRIPT))}, 'utf8');
    vm.runInThisContext(src + '\\nglobalThis.__Panel = S7PlcConfigurationPanel;', {{filename: 'panel.js'}});
    const panel = new (globalThis.__Panel)();
    panel.t = (k) => k;
    panel.escape = (v) => String(v);

    const cases = {json.dumps(cases)};
    const results = cases.map(([key, item]) => {{
        const html = panel.field([key, 'label', 'text', false], item);
        const m = html.match(/value="([^"]*)"/);
        return m ? m[1] : null;
    }});
    console.log(JSON.stringify(results));
    """

    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = [case[2] for case in cases]
    assert actual == expected, (
        f"field() rendered values {actual}, expected {expected} for cases "
        f"{[(c[0], c[1]) for c in cases]}"
    )


def test_panel_clearing_a_core_status_value_stores_empty_string_not_deletes() -> None:
    """Clearing hvac_status_off/heating/cooling_values must send an
    explicit empty string to the backend, not silently drop the key -
    same reasoning as the preset-value null fix, since these 3 fields also
    have non-empty historical defaults ("0"/"1"/"2")."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "statusCoreValue=key in CLIMATE_STATUS_CORE_DEFAULTS" in source
    assert "else if(statusCoreValue)entity[key]=''" in source
    assert (
        "const CLIMATE_STATUS_CORE_DEFAULTS = "
        '{hvac_status_off_values:"0",hvac_status_heating_values:"1",'
        'hvac_status_cooling_values:"2"}'
    ) in source