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


def test_visual_editor_rejects_invalid_addresses() -> None:
    with pytest.raises(ValueError, match="Invalid address for command_address"):
        _entity_from_message(
            {"entity": {"state_address": "DB1,X0.0", "command_address": "DB1,FOO0"}}
        )


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


def test_yaml_editor_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate key"):
        _entity_from_message(
            {"entity_yaml": 'address: "DB1,REAL0"\nname: "A"\naddress: "DB1,REAL4"'}
        )


def test_yaml_editor_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unknown field.*adress"):
        _entity_from_message(
            {
                "entity_type": "sensors",
                "entity_yaml": 'adress: "DB1,REAL0"\nname: "Typo"',
            }
        )


def test_yaml_editor_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="required"):
        _entity_from_message(
            {"entity_type": "sensors", "entity_yaml": 'name: "No address"'}
        )


@pytest.mark.parametrize(
    ("entity_type", "entity_yaml", "bad_field"),
    [
        ("sensors", 'address: "DB1,FOO0"\nname: "Temp"', "address"),
        ("sensors", "address: 42", "address"),
        (
            "switches",
            'state_address: "DB1,X0.0"\ncommand_address: "not an address"',
            "command_address",
        ),
        (
            "covers",
            'open_command_address: "DB1,X0.9"\nclose_command_address: "DB1,X0.1"',
            "open_command_address",
        ),
        (
            "climates",
            'control_mode: setpoint\ncurrent_temperature_address: "REAL0"\n'
            'target_temperature_address: "DB1,REAL4"\nmin_temp: 5',
            "current_temperature_address",
        ),
        ("entity_sync", 'source_entity: sensor.power\naddress: "DB1"', "address"),
    ],
)
def test_yaml_editor_rejects_invalid_addresses(
    entity_type, entity_yaml, bad_field
) -> None:
    with pytest.raises(ValueError, match=f"Invalid address for {bad_field}"):
        _entity_from_message(
            {"entity_type": entity_type, "entity_yaml": entity_yaml}
        )


@pytest.mark.parametrize(
    ("entity_type", "entity_yaml"),
    [
        ("sensors", 'address: "DB1,REAL0"\nname: "Temp"\ndevice_class: temperature'),
        ("switches", 'state_address: "DB1,X0.0"\ncommand_address: "DB1,X0.1"'),
        ("covers", 'open_command_address: "DB1,X0.0"\nclose_command_address: "DB1,X0.1"'),
        (
            "climates",
            'control_mode: setpoint\ncurrent_temperature_address: "DB1,REAL0"\n'
            'target_temperature_address: "DB1,REAL4"\nmin_temp: 5',
        ),
        ("entity_sync", 'source_entity: sensor.power\naddress: "DB1,REAL0"'),
    ],
)
def test_yaml_editor_accepts_valid_fields(entity_type, entity_yaml) -> None:
    entity = _entity_from_message(
        {"entity_type": entity_type, "entity_yaml": entity_yaml}
    )
    assert isinstance(entity, dict) and entity


def test_allowed_fields_cover_every_entity_type() -> None:
    from custom_components.s7plc.const import OPTION_KEYS
    from custom_components.s7plc.panel import _ALLOWED_FIELDS

    assert set(_ALLOWED_FIELDS) == set(OPTION_KEYS)


def test_allowed_fields_match_panel_javascript_catalog() -> None:
    """Every field the visual editor can save must pass backend validation."""
    import re

    from custom_components.s7plc.panel import _ALLOWED_FIELDS

    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    fields_block = re.search(r"const FIELDS = \{(.*?)\n\};", source, re.DOTALL).group(1)
    common_block = re.search(r"const COMMON = \[(.*?)\n\];", source, re.DOTALL).group(1)
    common = re.findall(r'\["([a-z_]+)"', common_block)
    ui_only = {"cover_mode"}  # never stored (see formEntity)
    for line in fields_block.strip().splitlines():
        entity_type, spec = line.split(":", 1)
        keys = set(re.findall(r'\["([a-z_]+)"', spec)) | set(common)
        expected = keys - ui_only
        allowed = _ALLOWED_FIELDS[entity_type.strip()]
        missing = expected - allowed
        assert not missing, f"{entity_type}: fields missing from backend: {missing}"


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


def test_panel_hides_uid_from_entity_summary() -> None:
    """The internal UID is not rendered as a summary chip."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "k!=='uid'" in source


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


def test_panel_uses_config_flow_field_descriptions() -> None:
    """Field help comes from the config flow instead of shorter panel copies."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "presetValue=key.startsWith('preset_mode_')&&key.endsWith('_value')" in source
    assert "this.flowText(type,item,key,'data_description')" in source
    assert "/s7plc_translations/${language}.json" in source
    assert "${help}</label>" in source
    # Preset values are PLC integer mode codes: step=1, not step=any (which
    # would silently allow decimal input to be truncated).
    assert "(presetValue?'step=\"1\"':'step=\"any\"')" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_config_flow_translations_cover_every_visible_panel_field() -> None:
    """Every panel field has the config flow's label and help in every locale."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    prefix = source.split("class S7PlcConfigurationPanel", 1)[0]
    script = (
        "const vm=require('vm');"
        "const context={};vm.createContext(context);"
        "vm.runInContext(process.argv[1] + "
        "'\\nglobalThis.result={FIELDS,MODE_HIDDEN};',context);"
        "process.stdout.write(JSON.stringify(context.result));"
    )
    result = subprocess.run(
        ["node", "-e", script, prefix],
        check=True,
        capture_output=True,
        text=True,
    )
    panel_config = json.loads(result.stdout)
    fields = panel_config["FIELDS"]
    hidden = panel_config["MODE_HIDDEN"]
    steps = {
        "sensors": [("sensors", None)],
        "binary_sensors": [("binary_sensors", None)],
        "switches": [("switches", None)],
        "covers": [
            ("covers_traditional", "traditional"),
            ("covers_position", "position"),
        ],
        "lights": [("lights", None)],
        "buttons": [("buttons", None)],
        "numbers": [("numbers", None)],
        "texts": [("texts", None)],
        "climates": [
            ("climates_direct", "direct"),
            ("climates_setpoint", "setpoint"),
        ],
        "entity_sync": [("entity_sync", None)],
    }

    for language in ("en", "it", "cs", "de", "pl"):
        translation_path = Path(
            f"custom_components/s7plc/translations/{language}.json"
        )
        flow_steps = json.loads(translation_path.read_text(encoding="utf-8"))[
            "options"
        ]["step"]
        for entity_type, entity_steps in steps.items():
            all_keys = {field[0] for field in fields[entity_type]}
            for step, mode in entity_steps:
                visible_keys = all_keys - {"cover_mode", "control_mode"}
                if mode:
                    visible_keys -= set(hidden[entity_type][mode])
                labels = flow_steps[step]["data"]
                descriptions = flow_steps[step]["data_description"]
                assert visible_keys <= labels.keys(), (language, step, "data")
                assert visible_keys <= descriptions.keys(), (
                    language,
                    step,
                    "data_description",
                )


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


def test_panel_exposes_cover_status_and_tilt_fields() -> None:
    """The visual editor lets you configure the traditional cover's
    real-time movement status — either 3 separate boolean addresses, or a
    single climate-style status address + per-status values (available in
    both Basic and Advanced modes, taking priority over the booleans in
    Basic when configured) — and the position cover's tilt control
    (tilt_state/command_address, invert_tilt)."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    covers_line = next(
        line for line in source.splitlines() if line.strip().startswith("covers:[")
    )
    for key in (
        "cover_opening_address",
        "cover_closing_address",
        "cover_stopped_address",
        "cover_status_address",
        "cover_status_open_values",
        "cover_status_closed_values",
        "cover_status_opening_values",
        "cover_status_closing_values",
        "cover_status_stopped_values",
        "tilt_state_address",
        "tilt_command_address",
        "invert_tilt",
    ):
        assert key in covers_line, f"{key} missing from covers FIELDS"
        assert key in source, f"{key} missing a translated label"

    # cover_status_address precedes the end-stop and boolean status fields
    # in field order (right after close_command_address), so it's the
    # visually-first, "primary" way to configure movement status.
    assert covers_line.index('"cover_status_address"') < covers_line.index(
        '"opening_state_address"'
    )
    assert covers_line.index('"cover_status_address"') < covers_line.index(
        '"cover_opening_address"'
    )

    # Position mode hides the traditional-only boolean status fields, but
    # not cover_status_address (available in both modes). Match on the
    # MODE_HIDDEN array's own "position:"/"traditional:" line prefix, not
    # just any line containing those substrings — the per-locale
    # fields:{...} translation dicts also contain "cover_opening_address"
    # (as a label key) and "position:" (inside "invert_position:"), so a
    # loose substring match would silently pick the wrong line.
    position_hidden_line = next(
        line
        for line in source.splitlines()
        if line.strip().startswith("position:") and "cover_opening_address" in line
    )
    assert "cover_closing_address" in position_hidden_line
    assert "cover_stopped_address" in position_hidden_line
    assert "cover_status_address" not in position_hidden_line

    # Traditional mode hides only the position-only tilt fields;
    # cover_status_address and its value fields are available there too.
    traditional_hidden_line = next(
        line
        for line in source.splitlines()
        if line.strip().startswith("traditional:") and "tilt_state_address" in line
    )
    assert "tilt_command_address" in traditional_hidden_line
    assert "invert_tilt" in traditional_hidden_line
    assert "cover_status_address" not in traditional_hidden_line
    assert "cover_status_open_values" not in traditional_hidden_line
    assert "cover_status_closed_values" not in traditional_hidden_line
    assert "cover_status_opening_values" not in traditional_hidden_line
    assert "cover_status_closing_values" not in traditional_hidden_line
    assert "cover_status_stopped_values" not in traditional_hidden_line


def test_panel_keeps_boolean_status_fields_when_status_address_used() -> None:
    """cover_status_address does NOT hide or strip the end-stop and boolean
    movement-status addresses (or use_state_topics): the backend still
    falls back to them (e.g. is_closed via opening/closing_state_address)
    whenever the status word doesn't directly answer open/closed, so using
    a status word for movement together with physical end-stops is a valid
    configuration and the editor must not force them apart."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "COVER_BOOL_STATUS_FIELDS" not in source


def test_panel_hides_status_value_fields_when_status_address_unused() -> None:
    """In either cover mode, the cover_status_*_values fields are
    meaningless without cover_status_address filled in — dynamically
    hidden (and stripped on save) until it has a value."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "COVER_STATUS_VALUE_FIELDS" in source
    assert (
        "const COVER_STATUS_VALUE_FIELDS = "
        '["cover_status_open_values","cover_status_closed_values",'
        '"cover_status_opening_values","cover_status_closing_values",'
        '"cover_status_stopped_values"]'
    ) in source
    assert "if(!statusAddr){hidden=[...hidden,...COVER_STATUS_VALUE_FIELDS];}" in source
    assert (
        "if(!entity.cover_status_address){"
        "COVER_STATUS_VALUE_FIELDS.forEach(k=>delete entity[k]);}"
    ) in source


def test_panel_hides_invert_tilt_when_tilt_state_address_unused() -> None:
    """In Position mode, invert_tilt has nothing to invert without
    tilt_state_address filled in — dynamically hidden (and stripped on
    save) until it has a value."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "COVER_TILT_INVERT_FIELDS" in source
    assert (
        'const COVER_TILT_INVERT_FIELDS = ["invert_tilt"];'
    ) in source
    assert (
        "if(sel.value==='position'&&!form.elements.tilt_state_address?.value.trim())"
        "{hidden=[...hidden,...COVER_TILT_INVERT_FIELDS];}"
    ) in source
    # Dynamic hide: the tilt-state-address input triggers a re-sync on input.
    assert "form.elements.tilt_state_address.oninput=syncMode" in source
    assert (
        "if(mode==='position'&&!entity.tilt_state_address){"
        "COVER_TILT_INVERT_FIELDS.forEach(k=>delete entity[k]);}"
    ) in source


def test_panel_covers_bool_addresses_use_bool_placeholder() -> None:
    """Cover open/close command and end-stop/status addresses are all
    single PLC bits, not REAL values — they must not show the generic
    REAL-flavored address example/help used by numeric address fields."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "const BOOL_FIELDS" in source
    bool_fields_line = next(
        line
        for line in source.splitlines()
        if line.strip().startswith("covers: [") and "open_command_address" in line
    )
    for key in (
        "open_command_address",
        "close_command_address",
        "opening_state_address",
        "closing_state_address",
        "cover_opening_address",
        "cover_closing_address",
        "cover_stopped_address",
        "stop_command_address",
    ):
        assert key in bool_fields_line, f"{key} missing from covers BOOL_FIELDS"

    # Fields not on that list (e.g. numeric position) stay untouched.
    assert "position_state_address" not in bool_fields_line
    assert "position_command_address" not in bool_fields_line

    assert "boolAddress=BOOL_FIELDS[type]?.includes(key)" in source
    assert "address_example_bool" in source
    assert "address_help_bool" in source


def test_panel_close_command_address_required_for_traditional() -> None:
    """close_command_address is required in the editor's save validation
    for traditional covers, same as the config flow."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert (
        "const needed=mode==='position'?'position_state_address':"
        "'open_command_address';if(!entity[needed]||(mode==='traditional'"
        "&&!entity.close_command_address))throw "
        "Error(this.t('cover_required_error'));"
    ) in source
