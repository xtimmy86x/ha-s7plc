"""Tests for the native configuration panel helpers."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import FRONTEND_BUILD, FRONTEND_MODULE, VERSION
from custom_components.s7plc.panel import (
    PYS7_VERSION_DATA,
    _configuration_from_yaml,
    _configuration_yaml,
    _canonicalize_logo_addresses,
    _entity_from_message,
    _entry_payload,
    async_setup_panel,
)

PANEL_JAVASCRIPT = Path("custom_components/s7plc/www/s7plc-panel.js")
PANEL_LOADER = "require(\"vm\").runInThisContext(require(\"fs\").readFileSync(\"custom_components/s7plc/www/s7plc-panel.js\",\"utf8\"));"


def test_panel_action_controls_share_height_and_normalize_only_plc_selects() -> None:
    """PLC controls align and use a scoped CSS arrow without changing other selects."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    styles = source.split("get styles(){return `", 1)[1].split("`;}", 1)[0]

    action_size_rule = (
        ".mobile-actions .config-yaml,\n"
        ".mobile-actions select,\n"
        ".summary-actions .config-yaml,\n"
        ".summary-actions select{box-sizing:border-box;height:38px;min-height:38px}"
    )
    selector_normalization_rule = (
        ".mobile-actions select,\n"
        ".summary-actions select{-webkit-appearance:none;-moz-appearance:none;"
        "appearance:none;padding:0 34px 0 13px;line-height:normal;"
        "background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),"
        "linear-gradient(135deg,currentColor 50%,transparent 50%);"
        "background-position:calc(100% - 17px) 50%,calc(100% - 12px) 50%;"
        "background-size:5px 5px,5px 5px;background-repeat:no-repeat}"
    )

    assert action_size_rule in styles
    assert selector_normalization_rule in styles
    assert styles.count("-webkit-appearance:none") == 1
    assert styles.count("-moz-appearance:none") == 1
    assert selector_normalization_rule.count("currentColor 50%") == 2
    assert not re.search(r"(?:^|})select\{[^}]*appearance:none", styles)
    assert ".summary-actions select:hover{background-color:#ffffff26;" in styles
    assert styles.count("line-height:normal") == 1
    assert ".mobile-actions,.summary-actions{display:flex;align-items:center" in styles
    assert ".config-yaml{display:flex;align-items:center" in styles


def test_const_version_matches_manifest() -> None:
    manifest = json.loads(
        Path("custom_components/s7plc/manifest.json").read_text(encoding="utf-8")
    )

    assert VERSION == manifest["version"]


def test_panel_asset_url_is_versioned() -> None:
    assert FRONTEND_MODULE == (
        f"/s7plc_static/s7plc-panel.js"
        f"?v={VERSION}&build={FRONTEND_BUILD}"
    )



@pytest.mark.parametrize(
    ("family", "bad"),
    [
        ("logo_0ba7", "AI9"),
        ("logo_0ba8", "I25"),
        ("logo_0ba8", "Q21"),
        ("logo_9", "I65"),
        ("logo_9", "Q61"),
    ],
)
def test_logo_manual_validation_never_falls_through_to_pys7(family, bad):
    with pytest.raises(ValueError, match="address_out_of_range"):
        _canonicalize_logo_addresses({"address": bad}, family)


def test_logo_manual_validation_keeps_explicit_s7_address():
    assert _canonicalize_logo_addresses(
        {"address": "DB1,INT200"}, "logo_0ba8"
    ) == {"address": "DB1,INT200"}


@pytest.mark.parametrize("address", ["IB10", "QW8", "MD72"])
def test_logo_manual_validation_preserves_compact_pys7_addresses(address):
    assert _canonicalize_logo_addresses(
        {"address": address}, "logo_0ba8"
    ) == {"address": address}


@pytest.mark.parametrize("family", ["logo_0ba7", "logo_0ba8", "logo_9"])
def test_entry_payload_always_includes_profile_for_logo_family(family):
    entry = SimpleNamespace(
        entry_id="logo", title="LOGO", data={"plc_family": family}, options={}
    )

    payload = _entry_payload(entry)

    assert payload["plc_family"] == family
    assert payload["logo_profile"]["family"] == family
    assert payload["logo_profile"]["areas"]
    assert payload["logo_profile"]["vm_areas"]


def test_panel_displays_project_badge_in_banner() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    banner = source.split("  banner(){", 1)[1].split("  panelActions(className){", 1)[0]
    actions = source.split("  panelActions(className){", 1)[1].split("  syncMenuButtons()", 1)[0]
    styles = source.split("get styles(){return `", 1)[1].split("`;}", 1)[0]

    assert "this._panel?.config?.version" in source
    assert 'class="project-badge"' in banner
    assert 'href="https://github.com/xtimmy86x/ha-s7plc"' in banner
    assert 'target="_blank"' in banner
    assert 'rel="noopener noreferrer"' in banner
    assert 'icon="mdi:github" aria-hidden="true"' in banner
    assert "this.t('common.open_project_github')" in banner
    assert "currentVersion=this.integrationVersion" in banner
    assert "currentVersion?`<span>v${this.escape(currentVersion)}</span>`:''" in banner
    assert "@xtimmy86x" in banner
    assert "integration-version" not in actions
    assert "integration-version" not in styles
    assert ".project-badge:focus-visible{outline:2px solid #fff" in styles
    assert ".project-badge{right:7px;bottom:7px;gap:4px" in styles

    for language in ("en", "it", "de", "pl", "cs"):
        translation = json.loads(Path(f"custom_components/s7plc/translations/{language}.json").read_text(encoding="utf-8"))
        assert translation["config_panel"]["common"]["open_project_github"]


def test_connection_details_structural_styles_are_preserved() -> None:
    """Connection details retain the cards, timeline, and row separators."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    styles = source.split("get dialogStyles(){return `", 1)[1].split("`;}", 1)[0]

    assert ".connection-head-text{min-width:0;display:flex;flex:1 1 auto" in styles
    assert ".connection-detail-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in styles
    assert "@media(max-width:650px)" in styles
    assert ".connection-detail-groups{grid-template-columns:minmax(0,1fr)}" in styles
    assert "overflow-wrap:anywhere" in styles
    assert ".connection-detail-group h3{display:flex;align-items:center;gap:7px" in styles
    assert ".connection-detail-group h3 ha-icon{" in styles
    assert ".connection-details .connection-detail-group dl{margin:0;border:1px" in styles
    assert ".connection-detail+.connection-detail{border-top:1px" in styles


def test_compact_selector_descriptions_wrap_long_tokens() -> None:
    """Compact cards wrap unspaced descriptions at their natural height."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert ".control-card small{font-size:10.5px!important;line-height:1.4;" in source
    assert "margin-top:4px;overflow-wrap:anywhere}" in source
    assert ".compact-control-card span{min-width:0;max-width:100%}" in source
    assert (
        ".light-options .control-card,.compact-control-card{min-height:0;"
    ) in source
    assert "grid-auto-rows:max-content" not in source


def test_compact_selectors_preserve_column_layout_on_mobile() -> None:
    """Mobile compact cards retain the layout their centering rules expect."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    mobile_styles = source.rsplit("@media(max-width:650px){", 1)[1].split("}`;}", 1)[0]

    assert ".control-card{min-height:0;flex-direction:row!important}" in mobile_styles
    assert (
        ".control-card.compact-control-card{min-height:110px;"
        "flex-direction:column!important}"
    ) in mobile_styles



def test_address_builder_layout_is_full_width_and_responsive() -> None:
    """Address controls compact naturally without fixed-width overflow."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    dialog_styles = source.split("get dialogStyles(){return `", 1)[1].split("`;}", 1)[0]
    mobile_styles = dialog_styles.rsplit("@media(max-width:650px){", 1)[1]

    assert ".address-builder{grid-column:1/-1;min-width:0" in dialog_styles
    assert ".address-builder{container-type:inline-size" not in dialog_styles
    assert (
        ".address-builder-layout{container-type:inline-size;box-sizing:border-box;"
        "min-width:0;max-width:100%}"
    ) in dialog_styles
    assert (
        ".address-controls{display:grid;grid-template-columns:repeat(auto-fit,"
        "minmax(min(100%,130px),1fr));gap:8px 10px}"
    ) in dialog_styles
    assert (
        "@container(min-width:640px){.address-controls{"
        "grid-template-columns:repeat(5,minmax(0,1fr))}}"
    ) in dialog_styles
    assert ".field-grid{grid-template-columns:1fr}" in mobile_styles
    assert ".address-controls{grid-template-columns:1fr}" in mobile_styles
    assert (
        ".address-guided,.address-controls{box-sizing:border-box;min-width:0;"
        "max-width:100%}"
    ) in dialog_styles
    assert (
        ".address-controls label{box-sizing:border-box;min-width:0;"
        "max-width:100%}"
    ) in dialog_styles
    assert (
        ".address-controls input,.address-controls select,.address-manual input"
        "{box-sizing:border-box;width:100%;min-width:0;max-width:100%}"
    ) in dialog_styles
    assert "width:150px" not in dialog_styles
    assert "min-width:150px" not in dialog_styles


def test_safari_form_control_normalization_is_preserved() -> None:
    """Safari controls share dimensions without removing number spinners."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    styles = source.split("get dialogStyles(){return `", 1)[1].split("`;}", 1)[0]

    assert ".address-controls input,.address-controls select{height:38px}" in styles
    assert (
        ".visual-form input,.visual-form select{width:100%;min-width:0;"
        "background:var(--card-background-color)"
    ) in styles
    assert (
        ".visual-form select{-webkit-appearance:none;-moz-appearance:none;"
        "appearance:none;background-image:linear-gradient(45deg,transparent 50%,"
        "var(--secondary-text-color) 50%),linear-gradient(135deg,"
        "var(--secondary-text-color) 50%,transparent 50%)"
    ) in styles
    assert "background-position:calc(100% - 18px) calc(50% - 3px)," in styles
    assert "background-size:5px 5px,5px 5px;background-repeat:no-repeat;" in styles
    assert "padding-right:30px" in styles

    # Keep native numeric steppers: height, rather than hidden chrome, is the fix.
    assert "::-webkit-inner-spin-button" not in styles
    assert "::-webkit-outer-spin-button" not in styles
    select_rule = styles.split(".visual-form select{-webkit", 1)[1].split("}", 1)[0]
    assert "linear-gradient(" in select_rule
    assert "svg" not in select_rule.lower()
    assert "data:" not in select_rule.lower()






def test_panel_typography_uses_home_assistant_fonts_semantically() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "var(--ha-font-family-body,Roboto,sans-serif)" in source
    assert "@import" not in source and "fonts.googleapis.com" not in source
    assert ".connection-detail dd{min-width:0;max-width:65%;" in source
    assert "font-variant-numeric:tabular-nums" in source
    assert ".connection-detail dd.technical-value{font-family:ui-monospace" in source
    assert "CONNECTION_DETAIL_TECHNICAL_FIELDS.has(key)" in source
    assert ".connection-head-text code{font-family:ui-monospace" in source




def test_connection_diagnostics_controls_are_visible_and_accessible() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert 'icon="mdi:information-outline"' in source
    assert 'class="connection-badge-details"' in source
    assert "this.t('connection_details.title')" in source
    assert "@media(max-width:480px){.connection-badge-details{display:none}}" in source
    assert ".connection-badge:focus-visible" in source
    assert ".connection-badge:active" in source
    assert 'role="status"' in source
    assert 'aria-hidden="true"' in source
    assert ".connection-detail dd.boolean-value{flex:0 0 auto;min-width:max-content;white-space:nowrap;word-break:normal;overflow-wrap:normal}" in source


def test_connection_diagnostics_translations_are_complete() -> None:
    paths = [
        Path("custom_components/s7plc/strings.json"),
        *Path("custom_components/s7plc/translations").glob("*.json"),
    ]

    for path in paths:
        panel = json.loads(path.read_text(encoding="utf-8"))["config_panel"]
        assert panel["connection_details"]["title"]
        assert panel["common"]["unknown"]
        assert panel["common"]["disabled"]
        details = panel["connection_details"]
        for section in ("connection", "configuration", "metrics", "retry", "activity", "other"):
            assert details["sections"][section]
        for field in ("connection_type", "configuration_name", "last_connected",
                      "last_disconnected", "last_error", "manual_disabled",
                      "polling_interval", "last_cycle", "configured_entities",
                      "read_count", "write_count", "communication_errors"):
            assert details["fields"][field]["label"]
        assert details["units"]["seconds"]

    italian = json.loads(
        Path("custom_components/s7plc/translations/it.json").read_text(encoding="utf-8")
    )["config_panel"]
    assert (
        italian["connection_details"]["fields"]["connection_type"]["label"]
        == "Metodo di collegamento"
    )
    assert italian["connection_details"]["sections"]["other"] == "Altri parametri"


def test_panel_supports_batch_entity_deletion() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert 'type="checkbox" data-select="${i}"' in source
    assert "sort((a,b)=>b-a)" in source
    assert "for(const index of sorted)await this._hass.callWS" in source






def test_switch_and_light_editor_section_order_is_explicit() -> None:
    """Primary virtual choices are rendered before PLC addresses."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    switch_start = source.index("if(type==='switches')return section")
    light_start = source.index("if(type==='lights')return section")
    switch_definition = source[switch_start:light_start]
    light_definition = source[
        light_start : source.index("return section('connection'", light_start)
    ]
    assert switch_definition.index("['control_behavior']") < switch_definition.index(
        "['state_address','command_address']"
    )
    assert (
        light_definition.index("['control_behavior']")
        < light_definition.index("['light_mode']")
        < light_definition.index("['state_address','command_address'")
    )
    # Other entity types continue to use the unchanged generic section classifier.
    assert "fields.filter(isAddress)" in source


def test_light_mode_is_virtual_and_dimmer_fields_are_cleaned_on_save() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "delete entity.light_mode" in source
    assert "if(lightMode==='on_off'){delete entity.brightness_state_address;delete entity.brightness_command_address;}" in source
    assert (
        "if(!entity.brightness_state_address)throw Error(this.t('errors.brightness_state_required_error'))"
        in source
    )
    assert '["brightness_scale"' not in source
    assert '["value_multiplier"' not in source
    assert '["scale_raw_min"' not in source
    assert '["scale_raw_max"' not in source
    assert "['brightness_state_address','brightness_command_address'].forEach" in source


def test_panel_control_mode_is_context_aware() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "command!==state" in source
    assert 'selects:[["control_behavior","control",false,["direct","sync"]],["address","text",true],["command_address"]' in source
    assert "const NORMALIZE_ADDRESS=value=>String(value??'').trim().toUpperCase()" in source
    assert "type==='selects'?'address':'state_address'" in source
    assert "sync.disabled=!canSync" in source
    assert "if(!canSync&&sync.checked)" in source
    assert (
        "if(type==='selects')entity.sync_state=form.elements.control_behavior.value==='sync'&&"
        "Boolean(entity.command_address)&&NORMALIZE_ADDRESS(entity.address)!=="
        "NORMALIZE_ADDRESS(entity.command_address);" in source
    )
    assert "sync.disabled=!canSync" in source
    assert "selected!=='pulse'" in source
    assert '[data-field="pulse_duration"]' in source
    assert '["control_behavior","control"]' in source
    assert 'name="sync_state" type="checkbox"' not in source
    assert 'name="pulse_command" type="checkbox"' not in source
    assert "choices||['direct','sync','pulse']" in source
    assert "sync_requires_command" in source
    assert "data-sync-reason" in source


def test_entity_from_visual_editor() -> None:
    entity = {"name": "Temperatura", "address": "DB1,REAL0"}

    assert _entity_from_message({"entity": entity}) == entity


def test_visual_editor_parser_does_not_validate_entity() -> None:
    entity = {"address": "invalid", "unknown": True}

    assert _entity_from_message({"entity": entity}) == entity
    assert _entity_from_message({"entity": entity}) is not entity


def test_entity_from_yaml_editor() -> None:
    assert _entity_from_message(
        {
            "entity_yaml": 'name: "Temperatura sala"\naddress: "DB1,REAL0"\ninvert_state: false'
        }
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


def test_yaml_editor_parser_does_not_validate_entity() -> None:
    assert _entity_from_message(
        {"entity_type": "sensors", "entity_yaml": "address: invalid\nunknown: true"}
    ) == {"address": "invalid", "unknown": True}


def test_complete_configuration_yaml_round_trip() -> None:
    options = {
        "sensors": [{"address": "DB1,REAL0", "name": "Temperature", "uid": "one"}],
        "switches": [{"state_address": "DB1,X4.0", "uid": "two"}],
        "unrelated_option": True,
    }

    saved = _configuration_from_yaml(
        _configuration_yaml(options, "entry-1", "PLC"), options, "entry-1"
    )

    assert saved["sensors"][0]["uid"] == "one"
    assert saved["switches"][0]["uid"] == "two"
    assert saved["unrelated_option"] is True
    assert saved["covers"] == []


@pytest.mark.parametrize(
    "source",
    [
        "- not-a-mapping",
        "unknown: []",
        "sensors: not-a-list",
        "sensors:\n  - invalid-item",
        "sensors:\n  - address: invalid",
        "sensors: []\nsensors: []",
    ],
)
def test_complete_configuration_yaml_rejects_invalid_input(source) -> None:
    with pytest.raises(ValueError):
        _configuration_from_yaml(source, {})


def test_complete_configuration_yaml_replaces_duplicate_uids() -> None:
    saved = _configuration_from_yaml(
        "sensors:\n  - address: DB1,REAL0\n    uid: repeated\n"
        "binary_sensors:\n  - address: DB1,X4.0\n    uid: repeated\n",
        {},
    )

    assert saved["sensors"][0]["uid"] != "repeated"
    assert saved["binary_sensors"][0]["uid"] != "repeated"
    assert saved["binary_sensors"][0]["uid"] != saved["sensors"][0]["uid"]


def test_configuration_backup_metadata_and_uid_import_rules() -> None:
    options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "original"}],
        "unrelated": "preserved",
    }
    backup = _configuration_yaml(options, "source-entry", "Source PLC")
    payload = yaml.safe_load(backup)

    assert payload["s7plc"] == {
        "format_version": 1,
        "source_entry_id": "source-entry",
        "source_title": "Source PLC",
    }
    assert (
        _configuration_from_yaml(backup, options, "source-entry")["sensors"][0]["uid"]
        == "original"
    )
    assert (
        _configuration_from_yaml(backup, options, "other-entry")["sensors"][0]["uid"]
        != "original"
    )
    legacy = "sensors:\n  - address: DB1,REAL0\n    uid: original\n"
    assert (
        _configuration_from_yaml(legacy, options, "source-entry")["sensors"][0]["uid"]
        != "original"
    )


@pytest.mark.parametrize("metadata", ["{}", "{source_entry_id: entry-1}"])
def test_backup_metadata_without_format_version_is_accepted(metadata) -> None:
    saved = _configuration_from_yaml(
        f"s7plc: {metadata}\nsensors:\n  - address: DB1,REAL0\n",
        {},
        "entry-1",
    )

    assert saved["sensors"][0]["address"] == "DB1,REAL0"


def test_supported_backup_format_version_is_accepted() -> None:
    saved = _configuration_from_yaml(
        "s7plc:\n  format_version: 1\nsensors:\n  - address: DB1,REAL0\n", {}
    )

    assert saved["sensors"][0]["address"] == "DB1,REAL0"


@pytest.mark.parametrize("version", ["999", '"1"', "true", "null"])
def test_unsupported_or_invalid_backup_format_version_is_rejected(version) -> None:
    with pytest.raises(ValueError, match="Unsupported S7 PLC backup format version"):
        _configuration_from_yaml(f"s7plc:\n  format_version: {version}\n", {})


@pytest.mark.parametrize("metadata", ["[]", "null", '"invalid"'])
def test_malformed_backup_metadata_is_rejected(metadata) -> None:
    with pytest.raises(ValueError, match="s7plc must be a mapping"):
        _configuration_from_yaml(f"s7plc: {metadata}\n", {})


def test_metadata_less_legacy_configuration_is_accepted() -> None:
    saved = _configuration_from_yaml("sensors:\n  - address: DB1,REAL0\n", {})

    assert saved["sensors"][0]["address"] == "DB1,REAL0"


def test_same_entry_duplicate_uids_are_replaced_safely() -> None:
    source = """s7plc:
  format_version: 1
  source_entry_id: entry-1
sensors:
  - address: DB1,REAL0
    uid: repeated
binary_sensors:
  - address: DB1,X4.0
    uid: repeated
"""
    saved = _configuration_from_yaml(source, {}, "entry-1")

    assert saved["sensors"][0]["uid"] == "repeated"
    assert saved["binary_sensors"][0]["uid"] != "repeated"


async def _save_entity_handler(monkeypatch, options):
    """Set up the panel and return its registered save command and entry."""
    import custom_components.s7plc.panel as panel

    monkeypatch.setattr(panel, "package_version", lambda package: "3.1.1")
    monkeypatch.setattr(panel.vol, "In", lambda values: values, raising=False)
    monkeypatch.setattr(panel.vol, "Any", lambda *values: values, raising=False)
    commands = []
    websocket_api = ModuleType("homeassistant.components.websocket_api")
    websocket_api.websocket_command = lambda schema: lambda func: func
    websocket_api.require_admin = lambda func: func
    websocket_api.async_response = lambda func: func
    websocket_api.async_register_command = lambda hass, func: commands.append(func)
    panel_custom = ModuleType("homeassistant.components.panel_custom")

    async def register_panel(*args, **kwargs):
        return None

    panel_custom.async_register_panel = register_panel
    monkeypatch.setitem(
        sys.modules, "homeassistant.components.websocket_api", websocket_api
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.components.panel_custom", panel_custom
    )
    import homeassistant.components as components

    monkeypatch.setattr(components, "websocket_api", websocket_api, raising=False)
    monkeypatch.setattr(components, "panel_custom", panel_custom, raising=False)

    loader = ModuleType("homeassistant.loader")

    async def get_integration(hass, domain):
        return SimpleNamespace(version="1.0")

    loader.async_get_integration = get_integration
    monkeypatch.setitem(sys.modules, "homeassistant.loader", loader)
    http = ModuleType("homeassistant.components.http")
    http.StaticPathConfig = lambda *args, **kwargs: (args, kwargs)
    monkeypatch.setitem(sys.modules, "homeassistant.components.http", http)

    entry = SimpleNamespace(
        entry_id="entry-1", domain="s7plc", options=options, data={}, title="PLC"
    )
    updates = []
    config_entries = SimpleNamespace(
        async_get_entry=lambda entry_id: entry,
        async_update_entry=lambda entry, **kwargs: updates.append(kwargs["options"]),
    )

    async def register_static_paths(paths):
        return None

    executor_calls = []

    async def add_executor_job(func, *args):
        executor_calls.append((func, args))
        return func(*args)

    hass = SimpleNamespace(
        data={},
        config_entries=config_entries,
        http=SimpleNamespace(async_register_static_paths=register_static_paths),
        async_add_executor_job=add_executor_job,
        executor_calls=executor_calls,
    )
    await async_setup_panel(hass)
    hass.panel_commands = commands
    return commands[1], hass, entry, updates


@pytest.mark.asyncio
async def test_panel_loads_pys7_version_in_executor(monkeypatch) -> None:
    """Load package metadata outside the event loop and expose it to the panel."""
    _, hass, entry, _ = await _save_entity_handler(monkeypatch, {})

    assert len(hass.executor_calls) == 1
    assert hass.executor_calls[0][1] == ("pys7",)
    assert hass.data["s7plc"][PYS7_VERSION_DATA] == "3.1.1"
    assert _entry_payload(entry, hass)["pys7_version"] == "3.1.1"


@pytest.mark.asyncio
async def test_configuration_websocket_commands(monkeypatch) -> None:
    _, hass, entry, updates = await _save_entity_handler(
        monkeypatch,
        {
            "sensors": [{"address": "DB1,REAL0", "uid": "one"}],
            "unrelated": 42,
        },
    )
    get_configuration = hass.panel_commands[4]
    save_configuration = hass.panel_commands[3]
    connection = _Connection()

    await get_configuration(hass, connection, {"id": 1, "entry_id": entry.entry_id})
    backup = connection.result["configuration_yaml"]
    assert yaml.safe_load(backup)["s7plc"]["source_entry_id"] == entry.entry_id

    await save_configuration(
        hass,
        connection,
        {
            "id": 2,
            "entry_id": entry.entry_id,
            "configuration_yaml": "sensors:\n  - address: DB1,REAL4\n",
        },
    )
    assert updates[-1]["unrelated"] == 42
    assert updates[-1]["covers"] == []
    assert "s7plc" not in updates[-1]


@pytest.mark.asyncio
async def test_invalid_full_configuration_is_structured_and_not_saved(
    monkeypatch,
) -> None:
    _, hass, entry, updates = await _save_entity_handler(monkeypatch, {})
    connection = _Connection()

    await hass.panel_commands[3](
        hass,
        connection,
        {
            "id": 1,
            "entry_id": entry.entry_id,
            "configuration_yaml": "climates:\n  - current_temperature_address: invalid\n",
        },
    )

    assert connection.error[0] == "invalid_configuration_entity"
    assert json.loads(connection.error[1]) == {
        "entity_type": "climates",
        "index": 0,
        "error_key": "invalid_address",
    }
    assert updates == []


def test_list_is_lightweight_and_frontend_has_three_yaml_actions() -> None:
    entry = SimpleNamespace(
        entry_id="entry-1", title="PLC", data={}, options={}, runtime_data=None
    )
    assert "configuration_yaml" not in _entry_payload(entry)
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "import_yaml" in source
    assert "export_current_yaml" in source
    assert "download_backup" in source
    assert "s7plc/config/get_configuration" in source


class _Connection:
    def __init__(self):
        self.error = None
        self.result = None

    def send_error(self, msg_id, code, message):
        self.error = (code, message)

    def send_result(self, msg_id, result):
        self.result = result


_SETPOINT_CLIMATE = {
    "control_mode": "setpoint",
    "current_temperature_address": "DB1,REAL0",
    "target_temperature_address": "DB1,REAL4",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("editor", ["visual", "yaml"])
@pytest.mark.parametrize(
    ("entity_type", "entity", "accepted"),
    [
        pytest.param(
            "climates",
            {
                **_SETPOINT_CLIMATE,
                "preset_mode_address": "DB1,BYTE8",
                "preset_mode_bidirectional": False,
                "preset_mode_off_value": 7,
                "preset_mode_heat_value": 7,
            },
            True,
            id="write-only-duplicate-climate-presets",
        ),
        pytest.param(
            "climates",
            {
                **_SETPOINT_CLIMATE,
                "preset_mode_address": "DB1,BYTE8",
                "preset_mode_bidirectional": True,
                "preset_mode_off_value": 7,
                "preset_mode_heat_value": 7,
            },
            False,
            id="bidirectional-duplicate-climate-presets",
        ),
        pytest.param(
            "climates",
            {
                **_SETPOINT_CLIMATE,
                "hvac_status_address": "DB1,BYTE8",
                "hvac_status_off_values": "02",
                "hvac_status_heating_values": "2",
                "hvac_status_cooling_values": "",
            },
            False,
            id="normalized-overlapping-hvac-statuses",
        ),
        pytest.param(
            "sensors",
            {"name": "Bad address", "address": "not a PLC address"},
            False,
            id="invalid-plc-address",
        ),
        *(
            pytest.param(
                entity_type,
                {
                    "state_address": "DB1,X0.0",
                    "command_address": "DB1,X0.1",
                    "sync_state": True,
                    "pulse_command": True,
                },
                False,
                id=f"{entity_type}-sync-pulse-conflict",
            )
            for entity_type in ("switches", "lights")
        ),
        *(
            pytest.param(
                entity_type,
                {
                    "state_address": "DB1,X0.0",
                    "command_address": "DB1,X0.0",
                    "sync_state": True,
                },
                False,
                id=f"{entity_type}-sync-same-address",
            )
            for entity_type in ("switches", "lights")
        ),
        pytest.param(
            "numbers",
            {"address": "DB1,INT0", "min_value": 10, "max_value": 5},
            False,
            id="number-invalid-range",
        ),
        pytest.param(
            "numbers",
            {"address": "DB1,REAL0"},
            False,
            id="real-number-missing-range",
        ),
        pytest.param(
            "numbers",
            {"address": "DB1,LREAL0", "min_value": 0},
            False,
            id="lreal-number-missing-range",
        ),
        pytest.param(
            "covers",
            {"open_command_address": "DB1,X0.0"},
            False,
            id="traditional-cover-missing-close-command",
        ),
        pytest.param(
            "covers",
            {"position_state_address": "DB1,BYTE0"},
            True,
            id="minimum-position-cover",
        ),
        pytest.param(
            "sensors",
            {"address": "DB1,REAL0", "future_field": True},
            False,
            id="unknown-field",
        ),
    ],
)
async def test_panel_and_backend_share_semantic_validation(
    monkeypatch, editor, entity_type, entity, accepted
) -> None:
    """Equivalent panel and backend inputs must have the same outcome."""
    try:
        built_item, _errors = build_entity_item(entity_type, entity, options={})
    except ValueError:
        built_item = None

    assert (built_item is not None) is accepted

    handler, hass, _entry, updates = await _save_entity_handler(monkeypatch, {})
    connection = _Connection()
    payload = (
        {"entity": entity} if editor == "visual" else {"entity_yaml": yaml.dump(entity)}
    )

    await handler(
        hass,
        connection,
        {"id": 1, "entry_id": "entry-1", "entity_type": entity_type, **payload},
    )

    assert (connection.error is None) is accepted
    if accepted:
        saved = dict(updates[0][entity_type][0])
        saved.pop("uid")
        assert saved == built_item
    else:
        assert connection.error[0] == "invalid_entity"
        assert updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize("editor", ["visual", "yaml"])
@pytest.mark.parametrize(
    "entity",
    [
        {"name": "Bad", "address": "invalid"},
        {"name": "Bad", "address": "DB1,REAL0", "unknown": True},
    ],
)
async def test_save_entity_shared_validation_rejects_invalid_input(
    monkeypatch, editor, entity
) -> None:
    handler, hass, _entry, _updates = await _save_entity_handler(monkeypatch, {})
    connection = _Connection()
    payload = (
        {"entity": entity} if editor == "visual" else {"entity_yaml": yaml.dump(entity)}
    )

    await handler(
        hass,
        connection,
        {"id": 1, "entry_id": "entry-1", "entity_type": "sensors", **payload},
    )

    assert connection.error[0] == "invalid_entity"


@pytest.mark.asyncio
@pytest.mark.parametrize("editor", ["visual", "yaml"])
async def test_save_entity_shared_validation_rejects_duplicate_address(
    monkeypatch, editor
) -> None:
    existing = {"name": "First", "address": "DB1,REAL0", "uid": "existing"}
    handler, hass, _entry, _updates = await _save_entity_handler(
        monkeypatch, {"sensors": [existing]}
    )
    connection = _Connection()
    entity = {"name": "Second", "address": "DB1,REAL0"}
    payload = (
        {"entity": entity} if editor == "visual" else {"entity_yaml": yaml.dump(entity)}
    )

    await handler(
        hass,
        connection,
        {"id": 1, "entry_id": "entry-1", "entity_type": "sensors", **payload},
    )

    assert connection.error[0] == "invalid_entity"


@pytest.mark.asyncio
@pytest.mark.parametrize("editor", ["visual", "yaml"])
async def test_save_entity_stores_canonical_builder_item(monkeypatch, editor) -> None:
    handler, hass, _entry, updates = await _save_entity_handler(monkeypatch, {})
    connection = _Connection()
    entity = {"name": "Temp", "address": "DB1,REAL0", "uid": "untrusted"}
    payload = (
        {"entity": entity} if editor == "visual" else {"entity_yaml": yaml.dump(entity)}
    )

    await handler(
        hass,
        connection,
        {"id": 1, "entry_id": "entry-1", "entity_type": "sensors", **payload},
    )

    saved = updates[0]["sensors"][0]
    assert saved["name"] == "Temp"
    assert saved["address"] == "DB1,REAL0"
    assert saved["uid"] != "untrusted"


@pytest.mark.asyncio
async def test_save_entity_canonicalizes_logo_ui_notation(monkeypatch) -> None:
    """The WebSocket boundary stores pyS7 syntax, never LOGO UI notation."""
    handler, hass, entry, updates = await _save_entity_handler(monkeypatch, {})
    entry.data["plc_family"] = "logo_0ba8"
    connection = _Connection()

    await handler(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": entry.entry_id,
            "entity_type": "binary_sensors",
            "entity": {"name": "Input", "address": "I1"},
        },
    )

    assert connection.error is None
    assert updates[0]["binary_sensors"][0]["address"] == "DB1,X1024.0"


@pytest.mark.asyncio
async def test_save_entity_edit_preserves_uid_and_normalizes_climate(
    monkeypatch,
) -> None:
    existing = {
        "name": "Heating",
        "control_mode": "setpoint",
        "current_temperature_address": "DB1,REAL0",
        "target_temperature_address": "DB1,REAL4",
        "uid": "stable-uid",
    }
    handler, hass, _entry, updates = await _save_entity_handler(
        monkeypatch, {"climates": [existing]}
    )
    connection = _Connection()
    edited = {
        **existing,
        "uid": "changed-uid",
        "hvac_status_address": "DB1,BYTE8",
        "hvac_status_heating_values": "02, 3",
        "hvac_status_cooling_values": "",
    }

    await handler(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": "entry-1",
            "entity_type": "climates",
            "index": 0,
            "entity": edited,
        },
    )

    assert connection.error is None
    saved = updates[0]["climates"][0]
    assert saved["uid"] == "stable-uid"
    assert saved["hvac_status_heating_values"] == "2,3"


def test_allowed_fields_match_panel_javascript_catalog() -> None:
    """Every field the visual editor can save must pass backend validation."""
    import re

    from custom_components.s7plc.config_validation import ENTITY_ALLOWED_FIELDS

    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    fields_block = re.search(r"const FIELDS = \{(.*?)\n\};", source, re.DOTALL).group(1)
    common_block = re.search(r"const COMMON = \[(.*?)\n\];", source, re.DOTALL).group(1)
    common = re.findall(r'\["([a-z_]+)"', common_block)
    ui_only = {
        "cover_control_mode",
        "cover_position_feedback",
        "cover_movement_feedback",
        "cover_stop_enabled",
        "cover_tilt_enabled",
        "control_behavior",
        "light_mode",
    }  # virtual UI fields
    for line in fields_block.strip().splitlines():
        entity_type, spec = line.split(":", 1)
        keys = set(
            re.findall(
                r'\["([a-z_]+)"(?:,"(?:text|number|checkbox|select|control|light|cover-selector)"|\])',
                spec,
            )
        ) | set(common)
        expected = keys - ui_only
        allowed = ENTITY_ALLOWED_FIELDS[entity_type.strip()]
        missing = expected - allowed
        assert not missing, f"{entity_type}: fields missing from backend: {missing}"


def test_panel_uses_current_home_assistant_dialog_api() -> None:
    """Ensure editor actions remain visible and can close the current dialog."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert '<ha-dialog-footer slot="footer">' in source
    assert "dialog.headerTitle=" in source
    assert "dialog.open=false" in source
    assert "dialog.close()" not in source


def test_panel_provides_mobile_navigation() -> None:
    """Mobile users can open HA's sidebar without a redundant back button."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "<ha-menu-button" in source
    # HA passes the narrow property to custom panels; the panel must forward
    # hass/narrow to every rendered ha-menu-button.
    assert "set narrow(value)" in source
    assert "b.hass=this._hass;b.narrow=this._narrow" in source
    # The mobile control row is present in the populated and empty render states.
    assert source.count('<div class="mobile-controls">${this.menuButton()}') == 2
    assert '${this.menuButton()}</div><div class="loading">' in source
    assert (
        '<div class="mobile-controls">${this.menuButton()}</div>${this.banner()}'
        in source
    )
    assert "history.back()" not in source
    assert 'id="back"' not in source


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

    payload = _entry_payload(entry)

    assert payload["connected"] is connected
    assert payload["pys7_version"] is None


@pytest.mark.parametrize("enabled", [True, False])
def test_entry_payload_only_exposes_runtime_metrics_when_enabled(enabled) -> None:
    """Configuration, rather than metric truthiness, gates runtime statistics."""
    coordinator = SimpleNamespace(
        is_connected=lambda: True,
        enable_metrics=enabled,
        pys7_metrics_dict={"read_count": 0, "write_count": 0, "total_errors": 0},
        connection_enabled=True,
        last_health_latency=0.0,
        error_count_by_category={},
        update_interval=None,
    )
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="PLC test",
        data={"host": "192.0.2.1", "enable_metrics": enabled},
        options={},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )

    runtime = _entry_payload(entry)["connection_runtime"]

    metric_keys = {
        "last_cycle_seconds",
        "read_count",
        "write_count",
        "communication_errors",
    }
    if enabled:
        assert {key: runtime[key] for key in metric_keys} == {
            "last_cycle_seconds": 0.0,
            "read_count": 0,
            "write_count": 0,
            "communication_errors": 0,
        }
    else:
        assert metric_keys.isdisjoint(runtime)


def test_entry_payload_maps_entity_ids(monkeypatch) -> None:
    """Expose the entity_id of each configured item to the panel."""
    from homeassistant.helpers import entity_registry as er

    registry = SimpleNamespace(
        async_get_entity_id=lambda domain, platform, uid: (
            "binary_sensor.plc_connection"
            if uid == "dev1:connection"
            else f"{domain}.demo"
            if uid == "dev1:sensor:DB1,REAL0"
            else None
        )
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

    hass = SimpleNamespace(data={"s7plc": {PYS7_VERSION_DATA: "3.1.1"}})
    payload = _entry_payload(entry, hass=hass)

    assert payload["pys7_version"] == "3.1.1"
    assert payload["entity_ids"]["sensors"] == ["sensor.demo", None]
    assert payload["entity_ids"]["switches"] == []
    assert payload["connection_entity_id"] == "binary_sensor.plc_connection"


def test_panel_hides_uid_from_entity_summary() -> None:
    """The internal UID is not rendered as a summary chip."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "k==='uid'" in source


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
        assert key in mode_hidden_line, (
            f"{key} missing from MODE_HIDDEN.climates.direct"
        )


def test_panel_uses_autonomous_field_descriptions() -> None:
    """Field help comes from the config flow instead of shorter panel copies."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert (
        "presetValue=key.startsWith('preset_mode_')&&key.endsWith('_value')" in source
    )
    assert "fieldText(type,key,'description')" in source
    assert "options?.step" not in source
    assert "config?.step" not in source
    assert "/s7plc_translations/${language}.json" in source
    assert "${help}</label>" in source
    # Preset values are PLC integer mode codes: step=1, not step=any (which
    # would silently allow decimal input to be truncated).
    assert "presetValue?'step=\"1\"':'step=\"any\"'" in source


def test_panel_translations_use_supported_config_panel_namespace() -> None:
    """Panel strings use HA's validated namespace, never a custom top-level key."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "const TRANSLATIONS" not in source
    assert "const BATCH_TRANSLATIONS" not in source
    entity_types = {
        "sensors",
        "binary_sensors",
        "switches",
        "covers",
        "lights",
        "buttons",
        "numbers",
        "selects",
        "texts",
        "climates",
        "entity_sync",
    }

    for language in ("en", "it", "cs", "de", "pl"):
        translations = json.loads(
            Path(f"custom_components/s7plc/translations/{language}.json").read_text(
                encoding="utf-8"
            )
        )
        assert "panel" not in translations
        panel = translations["config_panel"]
        assert panel["entity_types"].keys() == entity_types
        assert panel["entity_types"]["covers"]["fields"]["cover_control_mode"]
        assert panel["entity_types"]["climates"]["fields"]["control_mode"]
        assert panel["entity_types"]["lights"]["fields"]["light_mode"]


def _translation_paths() -> list[Path]:
    return [
        Path("custom_components/s7plc/strings.json"),
        *sorted(Path("custom_components/s7plc/translations").glob("*.json")),
    ]


def test_translation_files_have_full_key_parity_and_english_alignment() -> None:
    paths = _translation_paths()
    translations = [
        json.loads(path.read_text(encoding="utf-8")) for path in paths
    ]
    expected_shape = _translation_shape(translations[0])
    assert all(_translation_shape(item) == expected_shape for item in translations)
    english = translations[paths.index(Path("custom_components/s7plc/translations/en.json"))]
    assert translations[0] == english


def test_options_translations_only_contain_the_live_connection_flow() -> None:
    legacy_steps = {
        "init", "setup_connection", "setup_entities", "manage_configuration",
        "add", "edit", "remove", "import", "export", "sensors",
        "binary_sensors", "switches", "covers", "covers_traditional",
        "covers_position", "lights", "buttons", "numbers", "texts",
        "climates", "climates_direct", "climates_setpoint", "entity_sync",
        "edit_sensor", "edit_binary_sensor", "edit_switch", "edit_cover",
        "edit_cover_position", "edit_light", "edit_button", "edit_number",
        "edit_text", "edit_climate_direct", "edit_climate_setpoint",
        "edit_writer",
    }
    for path in _translation_paths():
        options = json.loads(path.read_text(encoding="utf-8"))["options"]
        assert set(options["step"]) == {"connection"}
        assert not legacy_steps & options["step"].keys()
        assert "menu_options" not in options
        assert set(options["error"]) == {
            "cannot_connect", "already_configured", "incompatible_family_connection"
        }


def test_panel_backend_validation_errors_have_autonomous_translations() -> None:
    validation_source = Path(
        "custom_components/s7plc/config_validation.py"
    ).read_text(encoding="utf-8")
    marker = 'errors["base"] = "'
    returned_marker = '{"base": "'
    produced_errors = {
        line.split(marker, 1)[1].split('"', 1)[0]
        for line in validation_source.splitlines()
        if marker in line
    } | {
        line.split(returned_marker, 1)[1].split('"', 1)[0]
        for line in validation_source.splitlines()
        if returned_marker in line
    }
    # The panel's fixed climate selector cannot submit an unknown control mode.
    produced_errors.discard("invalid_control_mode")
    assert produced_errors
    for path in _translation_paths():
        panel_errors = json.loads(path.read_text(encoding="utf-8"))["config_panel"][
            "errors"
        ]
        assert produced_errors <= panel_errors.keys()


def test_config_flow_translations_only_contain_config_flow_errors() -> None:
    """Entity validation errors belong to the sidepanel namespace only."""
    entity_errors = {
        "time_unsupported_for_entity",
        "select_requires_integer_type",
        "select_command_type_mismatch",
    }
    for path in _translation_paths():
        translations = json.loads(path.read_text(encoding="utf-8"))
        assert not entity_errors & translations["config"]["error"].keys()
        assert entity_errors <= translations["config_panel"]["errors"].keys()


def test_options_connection_errors_produced_by_backend_are_translated() -> None:
    source = Path("custom_components/s7plc/config_flow.py").read_text(encoding="utf-8")
    options_flow = source[source.index("class S7PLCOptionsFlow"):]
    produced_errors = {
        key
        for key in ("cannot_connect", "already_configured")
        if f'errors["base"] = "{key}"' in options_flow
    }
    assert produced_errors == {"cannot_connect", "already_configured"}
    for path in _translation_paths():
        errors = json.loads(path.read_text(encoding="utf-8"))["options"]["error"]
        assert produced_errors <= errors.keys()


def test_panel_keeps_climate_preset_values_without_preset_mode_address() -> None:
    """Preset values remain visible and saved because they determine which
    HVAC modes are exposed, while bidirectional readback still needs an address."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert (
        "const CLIMATE_PRESET_VALUE_FIELDS = "
        '["preset_mode_off_value","preset_mode_heat_value",'
        '"preset_mode_cool_value","preset_mode_heat_cool_value",'
        '"preset_mode_auto_value","preset_mode_dry_value",'
        '"preset_mode_fan_only_value"]'
    ) in source
    assert (
        "if(!entity.preset_mode_address)delete entity.preset_mode_bidirectional"
        in source
    )
    assert "...CLIMATE_PRESET_VALUE_FIELDS" in source
    assert "CLIMATE_PRESET_VALUE_FIELDS.forEach(k=>delete entity[k])" not in source


def test_panel_preserves_climate_status_values_without_status_address() -> None:
    """Hidden HVAC status mappings survive temporarily clearing the address."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "CLIMATE_STATUS_VALUE_FIELDS" in source
    assert "delete entity.hvac_status_address" in source
    assert "...CLIMATE_STATUS_VALUE_FIELDS" in source
    assert "CLIMATE_STATUS_VALUE_FIELDS.forEach(k=>delete entity[k])" not in source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity",
    [
        pytest.param(
            {
                **_SETPOINT_CLIMATE,
                "preset_mode_address": "DB1,BYTE8",
                "preset_mode_bidirectional": True,
                "preset_mode_off_value": 7,
                "preset_mode_heat_value": 7,
            },
            id="duplicate-bidirectional-preset",
        ),
        pytest.param(
            {
                **_SETPOINT_CLIMATE,
                "hvac_status_address": "DB1,BYTE8",
                "hvac_status_off_values": "02",
                "hvac_status_heating_values": "2",
                "hvac_status_cooling_values": "",
            },
            id="duplicate-normalized-status",
        ),
    ],
)
async def test_panel_backend_rejects_duplicate_climate_values(
    monkeypatch, entity
) -> None:
    """The panel backend is authoritative for climate mapping semantics."""
    handler, hass, _entry, updates = await _save_entity_handler(monkeypatch, {})
    connection = _Connection()

    await handler(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": "entry-1",
            "entity_type": "climates",
            "entity": entity,
        },
    )

    assert connection.error[0] == "invalid_entity"
    assert updates == []


def test_panel_leaves_duplicate_climate_validation_to_backend() -> None:
    """The visual editor must not duplicate authoritative Python validation.

    The parametrized panel save tests above verify that the shared backend builder
    rejects duplicate bidirectional preset and normalized HVAC status values.
    """
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "climate_duplicate_preset_error" not in source
    assert "climate_duplicate_status_error" not in source
    assert "presetSeen" not in source
    assert "statusSeen" not in source


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
    assert "COVER_MOTION_BOOL_FIELDS" not in source


def test_panel_status_values_follow_explicit_movement_mode() -> None:
    """cover_status_open/closed_values and cover_status_opening/closing/
    stopped_values are scoped to whichever selector (position_feedback vs
    movement_feedback) is actually "status" - independently, not tied
    together as one all-or-nothing set."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "if(movementStatus)COVER_STATUS_MOVEMENT_VALUE_FIELDS" in source
    assert "if(positionStatus)COVER_STATUS_POSITION_VALUE_FIELDS" in source
    assert "if(movement==='status'&&control==='position')" not in source
    assert (
        "ui.cover_movement_feedback==='status'&&!entity.cover_status_address" in source
    )


def test_panel_tilt_fields_follow_explicit_virtual_toggle() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert (
        "if(control==='position'&&tilt)['tilt_state_address','tilt_command_address','invert_tilt']"
        in source
    )
    assert "ui.cover_tilt_enabled===false" in source



def test_panel_close_command_address_required_for_traditional() -> None:
    """open_command_address is required for both traditional and toggle
    (a toggle cover only ever has one command address); close_command_address
    is required for traditional only - toggle's single relay has no use for
    it."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert (
        "(ui.cover_control_mode==='traditional'||ui.cover_control_mode==='toggle')"
        "&&!entity.open_command_address"
        in source
    )
    assert (
        "ui.cover_control_mode==='traditional'&&!entity.close_command_address"
        in source
    )
    assert "errors.cover_commands_required_error" in source


def test_panel_toggle_pulse_duration_has_its_own_options_section() -> None:
    """toggle_pulse_duration gets a dedicated "Opcje"/Options section, the
    same treatment switches/lights already give their own pulse_duration
    field, rather than being folded into the "Adresy PLC" section the way
    stop_pulse_duration is for position covers."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    covers_line = next(
        line for line in source.splitlines() if line.strip().startswith("covers:[")
    )
    assert '["toggle_pulse_duration","number"]' in covers_line

    assert (
        "section('cog-outline',this.t('sections.options.title'),"
        "this.t('sections.options.description'),"
        "byKeys(['toggle_pulse_duration']),'cover-options')"
    ) in source

    # syncMode(): visible only in toggle mode, both the field and the
    # section that wraps it.
    assert "if(control==='toggle')visible.add('toggle_pulse_duration');" in source
    assert "'stop_pulse_duration','toggle_pulse_duration'];" in source
    assert (
        "form.querySelector('[data-section=\"cover-options\"]')"
        ".classList.toggle('hidden-field',control!=='toggle');"
    ) in source

    # CLEAN_COVER_ENTITY: dropped whenever leaving toggle mode.
    assert (
        "if(ui.cover_control_mode!==\"toggle\")delete entity.toggle_pulse_duration;"
    ) in source


def test_panel_exposes_toggle_as_a_control_mode_choice() -> None:
    """toggle is presented as a third cover_control_mode choice (radio
    card, same section as traditional/position - "Sterowanie") rather
    than a separate checkbox buried in the connection/addresses section.
    The underlying toggle_mode boolean the backend reads is derived from
    that choice, not from a dedicated form field, and cleared on save
    when a different mode is picked."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    covers_line = next(
        line for line in source.splitlines() if line.strip().startswith("covers:[")
    )
    assert '"toggle_mode"' not in covers_line, (
        "toggle_mode should no longer be its own FIELDS.covers entry"
    )
    assert (
        '["cover_control_mode","cover-selector",true,'
        '["traditional","position","toggle"]]'
    ) in source

    # COVER_UI_FROM_ENTITY infers the "toggle" radio choice from the
    # stored toggle_mode flag when reopening an existing item.
    assert (
        'const control=entity.position_state_address?"position":'
        'entity.toggle_mode?"toggle":"traditional";'
    ) in source

    # On save: toggle_mode is derived from the selected control mode
    # (not read from its own form field), and close_command_address is
    # cleared for toggle covers (single-button, open_command_address only).
    assert "entity.toggle_mode=ui.cover_control_mode==='toggle';" in source
    assert (
        "if(ui.cover_control_mode==='toggle'){delete entity.close_command_address;}"
    ) in source

    # CLEAN_COVER_ENTITY treats toggle like traditional for field
    # governance (it still uses open/close-style addressing, not position).
    assert (
        'const isTraditionalLike=ui.cover_control_mode==="traditional"'
        '||ui.cover_control_mode==="toggle";'
    ) in source


def _leaf_string_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _leaf_string_values(child)
    elif isinstance(value, str):
        yield value


def test_panel_avoids_the_word_toggle_in_user_facing_text() -> None:
    """PR #117 review round 7, point 7: keep toggle_mode as the internal
    key name, but never surface the literal word "toggle" in text a
    normal user actually reads - use "single button"/"single-button"
    wording instead (see label_toggle/description_toggle, the cover mode
    choice label, and the toggle_mode_requires_* error texts)."""
    paths = [
        Path("custom_components/s7plc/strings.json"),
        *sorted(Path("custom_components/s7plc/translations").glob("*.json")),
    ]
    for path in paths:
        panel = json.loads(path.read_text(encoding="utf-8"))["config_panel"]
        for text in _leaf_string_values(panel):
            assert "toggle" not in text.lower(), f"{path}: {text!r}"


def test_toggle_mode_error_texts_describe_actual_mixed_requirement() -> None:
    """PR #117 review round 7, point 6: toggle_mode_requires_feedback used
    to describe only the two pure "all-status" / "all-bits" combinations,
    but _build_cover_item accepts mixed sources too (e.g. a status word
    for movement paired with boolean endstops for the settled position).
    The English text must describe the real requirement instead of a
    fixed value count that no longer matches the implementation."""
    english = json.loads(
        Path("custom_components/s7plc/translations/en.json").read_text(
            encoding="utf-8"
        )
    )["config_panel"]
    errors = english["errors"]
    assert "all 4 status values" not in errors["toggle_mode_requires_feedback"]
    assert "position" in errors["toggle_mode_requires_feedback"]
    assert "movement" in errors["toggle_mode_requires_feedback"]


def test_panel_checkbox_label_can_shrink_to_fit_the_dialog() -> None:
    """Regression test: a checkbox field's label/description span is a
    flex child of .check (display:flex, justify-content:space-between).
    Flex items default to min-width:auto, so a long unbroken label could
    refuse to wrap and push the switch itself past the dialog's right
    edge instead of wrapping onto multiple lines."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert ".visual-form .check>span{min-width:0}" in source


def _translation_shape(value):
    if isinstance(value, dict):
        return {key: _translation_shape(child) for key, child in value.items()}
    return None


def test_config_panel_translation_tree_has_language_parity() -> None:
    paths = [
        Path("custom_components/s7plc/strings.json"),
        *sorted(Path("custom_components/s7plc/translations").glob("*.json")),
    ]
    panels = [
        json.loads(path.read_text(encoding="utf-8"))["config_panel"] for path in paths
    ]
    expected = _translation_shape(panels[0])
    assert all(_translation_shape(panel) == expected for panel in panels)




def test_panel_has_no_flow_step_dependency_or_unresolved_translation_paths() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "flowText" not in source
    assert "flowStep" not in source
    assert "connectionLabel" not in source
    assert "options.step" not in source
    assert "config.step" not in source
    assert "??path;}" not in source


def test_cover_and_climate_modes_have_autonomous_options() -> None:
    for path in Path("custom_components/s7plc/translations").glob("*.json"):
        panel = json.loads(path.read_text(encoding="utf-8"))["config_panel"]
        cover_fields = panel["entity_types"]["covers"]["fields"]
        assert set(cover_fields["cover_control_mode"]["options"]) == {
            "traditional",
            "position",
            "toggle",
        }
        assert set(cover_fields["cover_position_feedback"]["options"]) == {
            "timed", "position", "opening", "closing", "both", "status",
        }
        assert set(cover_fields["cover_movement_feedback"]["options"]) == {
            "none",
            "bits",
            "status",
        }
        assert set(
            panel["entity_types"]["climates"]["fields"]["control_mode"]["options"]
        ) == {"direct", "setpoint"}


def test_cover_endstop_panel_validation_matches_config_builder() -> None:
    """Guard against either side relaxing the two-address requirement."""
    panel = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    backend = Path("custom_components/s7plc/config_validation.py").read_text(
        encoding="utf-8"
    )
    assert "['opening','both'].includes(ui.cover_position_feedback)" in panel
    assert 'feedback_mode in {"opening", "both"}' in backend


def test_cover_editor_sections_are_ordered_and_yaml_remains_raw() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    ordered = [
        "cover-control",
        "cover-position-feedback",
        "cover-movement-feedback",
        "addresses",
        "cover-stop",
        "cover-tilt",
        "ha",
    ]
    positions = [
        source.index(f"'{key}'", source.index("if(type==='covers')return"))
        for key in ordered
    ]
    assert positions == sorted(positions)
    assert "this.toYaml(raw)" in source
    assert "COVER_UI_FROM_ENTITY(raw)" not in source


def test_cover_translation_modes_have_language_parity() -> None:
    paths = [
        Path("custom_components/s7plc/strings.json"),
        *Path("custom_components/s7plc/translations").glob("*.json"),
    ]
    panels = [
        json.loads(path.read_text(encoding="utf-8"))["config_panel"] for path in paths
    ]
    expected_fields = {
        "cover_control_mode",
        "cover_position_feedback",
        "cover_movement_feedback",
        "cover_stop_enabled",
        "cover_tilt_enabled",
    }
    expected_errors = {
        "cover_commands_required_error",
        "cover_position_required_error",
        "cover_endstops_required_error",
        "cover_status_required_error",
        "cover_tilt_required_error",
        "cover_stop_required_error",
    }
    for panel in panels:
        cover = panel["entity_types"]["covers"]
        assert expected_fields <= cover["fields"].keys()
        assert set(cover["modes"]) == {
            "control",
            "position_feedback",
            "movement_feedback",
            "stop",
            "tilt",
        }
        assert expected_errors <= panel["errors"].keys()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_climate_guided_inference_and_cleanup_are_backward_compatible() -> None:
    """Execute Climate projections and intentional cleanup in JavaScript."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}}; global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const infer=CLIMATE_UI_FROM_ENTITY, clean=CLEAN_CLIMATE_ENTITY;
const mappings={{preset_mode_off_value:null,hvac_status_off_values:"",hvac_status_heating_values:"7"}};
console.log(JSON.stringify({{
 heat:infer({{heating_output_address:"Q0.0"}}),
 cool:infer({{cooling_output_address:"Q0.1"}}),
 both:infer({{heating_output_address:"Q0.0",cooling_output_address:"Q0.1"}}),
 partial:clean({{uid:"kept",control_mode:"direct",heating_output_address:"Q0.0",heating_action_address:"I0.0"}},infer({{heating_output_address:"Q0.0",heating_action_address:"I0.0"}})),
 combinations:[{{}},{{on_off_address:"Q0.0"}},{{preset_mode_address:"DB1,B0"}},{{preset_mode_address:"DB1,B0",on_off_address:"Q0.0"}}].map(infer).map(x=>x.climate_mode_control),
 sameAddress:clean({{uid:"kept",control_mode:"setpoint",target_temperature_address:"DB1,R0",preset_mode_address:"DB1,B4",hvac_status_address:"DB1,B4",preset_mode_bidirectional:true,...mappings}},{{...infer({{preset_mode_address:"DB1,B4",hvac_status_address:"DB1,B4"}}),control_mode:"setpoint"}}),
 disableStatus:clean({{control_mode:"setpoint",target_temperature_address:"DB1,R0",hvac_status_address:"DB1,B4",...mappings}},{{...infer({{hvac_status_address:"DB1,B4"}}),control_mode:"setpoint",climate_action_feedback:"inferred"}},["climate_action_feedback"]),
 disableCoded:clean({{control_mode:"setpoint",target_temperature_address:"DB1,R0",preset_mode_address:"DB1,B4",preset_mode_bidirectional:true,...mappings}},{{...infer({{preset_mode_address:"DB1,B4"}}),control_mode:"setpoint",climate_mode_control:"setpoint"}},["climate_mode_control"]),
 toDirect:clean({{uid:"kept",control_mode:"setpoint",target_temperature_address:"DB1,R0",preset_mode_address:"DB1,B4",hvac_status_address:"DB1,B4",...mappings}},{{...infer({{}}),control_mode:"direct"}},["control_mode"])
}}));
"""
    value = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert value["heat"]["climate_direct_function"] == "heat"
    assert value["cool"]["climate_direct_function"] == "cool"
    assert value["both"]["climate_direct_function"] == "heat_cool"
    assert value["partial"]["heating_action_address"] == "I0.0"
    assert value["combinations"] == ["setpoint", "on_off", "coded", "coded_on_off"]
    assert (
        value["sameAddress"]["preset_mode_address"]
        == value["sameAddress"]["hvac_status_address"]
    )
    assert value["sameAddress"]["preset_mode_bidirectional"] is True
    assert value["sameAddress"]["uid"] == "kept"
    assert "hvac_status_address" not in value["disableStatus"]
    assert value["disableStatus"]["hvac_status_off_values"] == ""
    assert "preset_mode_address" not in value["disableCoded"]
    assert value["disableCoded"]["preset_mode_off_value"] is None
    assert value["toDirect"]["uid"] == "kept"
    assert not any(
        key in value["toDirect"]
        for key in ("climate_mode_control", "climate_action_feedback")
    )

def test_panel_layout_translations_are_available_in_every_language() -> None:
    required = {
        "switch_to_tabs",
        "switch_to_sections",
        "expand_section",
        "collapse_section",
        "all_entities",
    }
    files = [
        Path("custom_components/s7plc/strings.json"),
        *Path("custom_components/s7plc/translations").glob("*.json"),
    ]
    for path in files:
        translations = json.loads(path.read_text(encoding="utf-8"))
        assert required <= translations["config_panel"]["layout"].keys(), path
        assert all(translations["config_panel"]["layout"][key] for key in required)

def test_all_visual_plc_addresses_use_reusable_builder() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "if(address&&key!=='source_entity')return this.addressField" in source
    assert "this.initAddressBuilders(form,type)" in source
    assert 'name="${key}" value="${this.escape(value)}"' in source

def test_address_builder_focus_style_only_indicates_real_errors() -> None:
    """Focusing a builder only shows an error outline for explicit errors."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert ".address-builder:focus{outline:none}" in source
    assert (
        '.address-builder[data-address-error]:not([data-address-error=""])'
        "{border-color:var(--error-color)}"
    ) in source
    assert (
        '.address-builder[data-address-error]:not([data-address-error=""]):focus'
        "{outline:2px solid var(--error-color);outline-offset:2px}"
    ) in source
    assert ".address-builder:focus{outline:2px solid var(--error-color)" not in source


def test_italian_address_builder_is_translated() -> None:
    translations = json.loads(
        Path("custom_components/s7plc/translations/it.json").read_text(encoding="utf-8")
    )["config_panel"]["address_builder"]
    assert translations == {
        "guided": "Guidato",
        "manual": "Manuale",
        "area": "Area di memoria",
        "db_number": "Numero DB",
        "data_type": "Tipo di dato",
        "offset": "Offset byte / elemento",
        "bit": "Numero bit",
        "length": "Lunghezza stringa",
        "preview": "Anteprima indirizzo",
        "configure": "Configura indirizzo",
        "invalid": "Questo indirizzo non può essere rappresentato dall’editor guidato. Correggilo manualmente.",
        "incomplete": "Completa tutte le parti obbligatorie dell’indirizzo.",
        "unsupported": "Questa combinazione di area e tipo di dato non è supportata.",
        "logo_area": "Area LOGO!",
        "element_number": "Numero elemento",
        "vm_offset": "Offset VM",
        "logo_address": "Indirizzo LOGO!",
        "internal_address": "Indirizzo interno",
        "invalid_logo_address": "Indirizzo LOGO! non valido",
        "address_out_of_range": "Indirizzo fuori intervallo",
        "address_not_convertible": "Indirizzo non convertibile",
        "not_configured": "Non configurato",
    }




@pytest.mark.parametrize(("source", "expected"), [
    ("binary_sensors:\n  - address: I1\n", "DB1,X1024.0"),
    ("switches:\n  - state_address: Q1\n    command_address: M1\n", "DB1,X1064.0"),
    ("binary_sensors:\n  - address: V0.0\n", "DB1,X0.0"),
    ("sensors:\n  - address: VB0\n", "DB1,BYTE0"),
    ("sensors:\n  - address: VW0\n", "DB1,WORD0"),
    ("sensors:\n  - address: VD0\n", "DB1,DWORD0"),
])
def test_complete_logo_configuration_yaml_canonicalizes_addresses(source, expected):
    saved = _configuration_from_yaml(source, {}, plc_family="logo_0ba8")
    entity = next(saved[key][0] for key in saved if saved[key])
    assert expected in entity.values()


def test_complete_configuration_yaml_preserves_canonical_and_s7_addresses():
    canonical = _configuration_from_yaml(
        "sensors:\n  - address: DB1,REAL0\n", {}, plc_family="logo_0ba8"
    )
    s7 = _configuration_from_yaml(
        "binary_sensors:\n  - address: I1.0\n", {}, plc_family="s7"
    )
    assert canonical["sensors"][0]["address"] == "DB1,REAL0"
    assert s7["binary_sensors"][0]["address"] == "I1.0"


def test_logo_yaml_save_does_not_invent_optional_command_address() -> None:
    saved = _configuration_from_yaml(
        "numbers:\n  - address: DB1,WORD2\n    min_value: 0\n    max_value: 7000\n",
        {},
        plc_family="logo_0ba8",
    )
    assert saved["numbers"][0]["address"] == "DB1,WORD2"
    assert "command_address" not in saved["numbers"][0]



def test_entity_card_mobile_styles_and_translations_are_complete() -> None:
    """Both shared card layouts have compact responsive actions and all labels."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    mobile = source.split("@media(max-width:650px){", 1)[1].split(
        "@media(max-width:500px)", 1
    )[0]

    assert "${this.entityCards(entry,type,matches)}" in source
    assert source.count("this.entityCards(entry,type,matches)") == 2
    assert ".entity-actions{display:none}" in mobile
    assert ".entity-overflow{display:block}" in mobile
    assert (
        ".cards article.overflow-open,.cards article.overflow-open:hover{z-index:100}"
        in source
    )
    assert ".entity-state{display:block" in mobile
    assert ".state-badge{display:none}" not in mobile
    assert "max-width:min(34%,140px)" in mobile
    assert ".details>div{gap:2px}" in mobile
    assert ".entity-leading{display:flex;align-items:center;gap:3px" in source
    assert ".entity-select{box-sizing:border-box;display:grid;place-items:center;" in source
    assert "width:38px;min-height:32px" in source
    assert ".entity-leading{flex-direction:column;gap:4px}" in mobile
    assert ".details{flex:1;min-width:0}" in source
    assert ".details>b{font-size:14px;font-weight:600;overflow:hidden;" in source

    translation_files = [
        Path("custom_components/s7plc/strings.json"),
        *Path("custom_components/s7plc/translations").glob("*.json"),
    ]
    for path in translation_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["config_panel"]["actions"]["more_actions"]




def test_entity_overflow_stacking_hierarchy_stays_above_neighbor_cards() -> None:
    """Transformed hover cards cannot cover an open entity action menu."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    styles = source.split("get styles(){return `", 1)[1].split("`;}", 1)[0]

    def rule(selector: str) -> str:
        match = re.search(
            rf"(?:^|[}}\n])\s*{re.escape(selector)}\{{([^}}]*)\}}", styles
        )
        assert match is not None, f"Missing CSS rule for {selector}"
        return match.group(1)

    cards = rule(".cards")
    article = rule("article")
    hover = rule("article:hover")
    open_card = rule(
        ".cards article.overflow-open,.cards article.overflow-open:hover"
    )
    overflow = rule(".entity-overflow")
    menu = rule(".entity-overflow-menu")

    assert "position:relative" in cards
    assert "isolation:isolate" in cards
    assert "position:relative" in article
    assert "z-index:0" in article
    assert "transform:translateY(-2px)" in hover
    assert "z-index:1" in hover
    assert "z-index:100" in open_card
    assert "position:relative" in overflow
    assert "z-index:101" in menu

    # These ancestors must not clip the absolutely positioned menu. The sections
    # view uses the same .cards hierarchy and its section adds no clipping either.
    for selector in (".cards", "article", ".entity-side", ".entity-overflow", ".entity-section"):
        assert "overflow:hidden" not in rule(selector)


def test_duplicate_translation_keys_match_all_supported_languages() -> None:
    """Every shipped locale exposes the duplicate action and editor copy."""
    files = [
        Path("custom_components/s7plc/strings.json"),
        *sorted(Path("custom_components/s7plc/translations").glob("*.json")),
    ]
    structures = []
    for path in files:
        panel = json.loads(path.read_text(encoding="utf-8"))["config_panel"]
        assert panel["actions"]["duplicate"]
        assert panel["editor"]["duplicate_entity"]
        assert panel["editor"]["configure_duplicate"]
        structures.append((set(panel["actions"]), set(panel["editor"])))
    assert all(structure == structures[0] for structure in structures[1:])

def test_address_mode_controls_are_accessible_responsive_and_translated() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    page_styles = source.split("get styles(){return `", 1)[1].split("`;}", 1)[0]
    dialog_styles = source.split("get dialogStyles(){return `", 1)[1].split("`;}", 1)[0]
    assert 'data-default-address-mode="guided"' in source
    assert 'button type="button" data-apply-address-mode="guided"' in source
    assert 'button type="button" data-apply-address-mode="manual"' in source
    assert "aria-label=\"${this.t('editor.apply_guided_all')}\"" in source
    assert "aria-label=\"${this.t('editor.apply_manual_all')}\"" in source
    assert 'role="status" aria-live="polite"' in source
    assert ".default-address-mode{" in page_styles
    assert ".address-mode-actions button{" in page_styles
    assert ".bulk-address-modes" not in page_styles
    assert ".sr-only" not in page_styles
    assert ".bulk-address-modes{" in dialog_styles
    assert ".bulk-address-modes button{" in dialog_styles
    assert ".sr-only{" in dialog_styles
    assert ".address-mode-actions button,.bulk-address-modes button" not in source
    mobile_dialog_styles = dialog_styles.split("@media(max-width:650px){", 1)[1]
    assert ".bulk-address-modes{justify-content:flex-start}" in mobile_dialog_styles
    assert ".default-address-mode{align-items:stretch;flex-direction:column" in page_styles
    keys = {
        "default_address_mode", "default_address_mode_description", "use_guided",
        "use_manual", "set_all_addresses", "apply_guided_all",
        "apply_manual_all", "mixed_address_mode",
    }
    for language in ("en", "it", "de", "pl", "cs"):
        translation = json.loads(Path(f"custom_components/s7plc/translations/{language}.json").read_text(encoding="utf-8"))
        assert keys <= translation["config_panel"]["editor"].keys()


def test_panel_header_uses_compact_responsive_layout() -> None:
    """The content preceding entity navigation remains compact at each breakpoint."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    page_styles = source.split("get styles(){return `", 1)[1].split("`;}", 1)[0]
    mobile_styles = page_styles.split("@media(max-width:650px){", 1)[1]
    intermediate_styles = page_styles.split(
        "@media(min-width:501px) and (max-width:900px){", 1
    )[1].split("@media(max-width:480px)", 1)[0]

    assert ".hero-banner{position:relative;width:100%;height:150px" in page_styles
    assert ".hero-banner img{display:block;width:100%;height:100%;object-fit:cover" in page_styles
    assert ".summary{position:relative;overflow:hidden;margin:0 0 10px;padding:14px 18px" in page_styles
    assert ".default-address-mode{display:flex;align-items:center;justify-content:space-between" in page_styles
    assert ".hero-banner{height:80px;margin-bottom:8px" in mobile_styles
    assert ".summary{margin-bottom:8px;padding:10px 12px" in mobile_styles
    assert ".address-mode-actions button{flex:1;min-width:0;min-height:40px}" in mobile_styles
    assert ".hero-banner{height:clamp(80px,calc(42.5px + 7.5vw),110px)" in intermediate_styles
    assert ".toolbar,.sections-toolbar{align-items:stretch;flex-direction:column;gap:8px}" in intermediate_styles
    assert (
        ".category-heading,.sections-toolbar>div:first-child,.entity-search{"
        "flex:0 0 auto;width:100%;max-width:none;min-width:0}"
        in intermediate_styles
    )
    assert ".toolbar p{display:block}" in intermediate_styles
    assert (
        ".toolbar-actions{align-self:flex-end;justify-content:flex-end;flex-wrap:wrap}"
        in intermediate_styles
    )
    assert "flex:1 1 220px" not in intermediate_styles
    assert "flex:1 1 250px" not in intermediate_styles
    assert ".category-heading{flex:1 1 220px}" in page_styles
    assert ".entity-search{display:flex;flex:1 1 250px;max-width:360px;min-width:190px" in page_styles
    assert ".entity-search{order:3;flex:1 0 100%;width:100%;max-width:none;min-width:0}" in mobile_styles
    assert (
        "@media(min-width:901px) and (max-width:1199px){"
        ".hero-banner{height:clamp(110px,calc(13.333vw - 10px),150px)}"
        in page_styles
    )
    assert "(100vw - 900px)*.134" not in page_styles

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_value_conversion_editor_is_localized_directional_and_accessible() -> None:
    """Every logical channel has one translated, directional conversion editor."""
    script = r'''
const vm=require("vm"),fs=require("fs");let Panel;
const context={HTMLElement:class{},customElements:{get(){},define:(_,cls)=>Panel=cls}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),context);
const it=JSON.parse(fs.readFileSync(process.argv[2],"utf8")).config_panel;
const panel=new Panel();panel.escape=v=>String(v??"");panel.t=key=>key.split('.').reduce((o,k)=>o?.[k],it)??key;
const specs=vm.runInContext('VALUE_CHANNEL_SPECS',context), rows={};
const entities={
 sensors:{address:'DB1,REAL0'},numbers:{address:'DB1,REAL0',command_address:'DB1,REAL4'},selects:{address:'DB1,BYTE0'},entity_sync:{address:'DB1,REAL0'},lights:{brightness_state_address:'DB1,BYTE0',brightness_command_address:'DB1,BYTE2'},covers:{position_state_address:'DB1,BYTE0',position_command_address:'DB1,BYTE2',cover_status_address:'DB1,BYTE4',tilt_state_address:'DB1,BYTE6',tilt_command_address:'DB1,BYTE8'},climates:{current_temperature_address:'DB1,REAL0',target_temperature_address:'DB1,REAL4',preset_mode_address:'DB1,BYTE8',preset_mode_bidirectional:true,hvac_status_address:'DB1,BYTE10'}};
for(const [type,list] of Object.entries(specs))for(const spec of list)rows[spec.label]=panel.valueConversionRow(type,entities[type],spec);
const summaries=[null,{type:'multiplier',factor:5},{type:'linear_scale',plc_min:0,plc_max:27648,ha_min:0,ha_max:100},{type:'expression'}].map(v=>panel.valueConversionSummary(v));
console.log(JSON.stringify({rows,summaries,directions:['', 'DB1,REAL0', 'DB1,REAL4'].map(write=>panel.valueConversionDirection('DB1,REAL0',write))}));'''
    result = json.loads(subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT),
         "custom_components/s7plc/translations/it.json"],
        check=True, capture_output=True, text=True,
    ).stdout)
    expected_titles = {
        "sensor_value": "Conversione valore sensore",
        "number_value": "Conversione valore number",
        "select_value": "Conversione valore select",
        "sync_value": "Conversione valore sincronizzato",
        "brightness": "Conversione luminosità",
        "position": "Conversione posizione",
        "tilt": "Conversione tilt",
        "cover_status": "Conversione stato cover",
        "current_temperature": "Conversione temperatura corrente",
        "target_temperature": "Conversione temperatura target",
        "preset_mode": "Conversione modalità preset",
        "hvac_status": "Conversione stato HVAC",
    }
    assert set(result["rows"]) == set(expected_titles)
    for channel, title in expected_titles.items():
        assert title in result["rows"][channel]
        assert 'aria-describedby="vc_' in result["rows"][channel]
        assert 'aria-expanded="false"' in result["rows"][channel]
    assert "Position" not in result["rows"]["position"]
    assert ">None<" not in result["rows"]["position"]
    assert result["summaries"] == [
        "Nessuna", "Moltiplicatore × 5", "Scala 0–27648 → 0–100",
        "Espressione personalizzata",
    ]
    assert all("Scale" not in value and "Custom expression" not in value
               for value in result["summaries"])
    assert result["directions"] == ["read", "bidirectional_same", "bidirectional_distinct"]
    assert "Il valore letto dal PLC" in result["rows"]["sensor_value"]
    assert "Il valore di Home Assistant" in result["rows"]["sync_value"]
    assert "indirizzo di stato" in result["rows"]["position"]
    assert "stesso indirizzo PLC" in result["rows"]["target_temperature"]
    assert "data-conversion-direction=\"read\"" in result["rows"]["position"]
    assert "data-conversion-direction=\"write\"" in result["rows"]["position"]


def test_value_conversion_translations_and_responsive_layout_are_complete() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    required = {
        "none", "scale", "expression", "read_expression", "write_expression",
        "expressions_independent", "inverse_automatic", "titles", "directions",
    }
    titles = {
        "sensor_value", "number_value", "select_value", "sync_value", "brightness",
        "position", "tilt", "cover_status", "current_temperature",
        "target_temperature", "preset_mode", "hvac_status",
    }
    for filename in ("strings.json", "translations/en.json", "translations/it.json",
                     "translations/de.json", "translations/pl.json", "translations/cs.json"):
        value = json.loads(Path("custom_components/s7plc", filename).read_text(encoding="utf-8"))["config_panel"]["value_conversion"]
        assert required <= value.keys()
        assert set(value["titles"]) == titles
        assert set(value["directions"]) == {"title", "read", "write", "bidirectional_distinct", "bidirectional_same"}
    assert "VALUE_CONVERSION_SUMMARY" not in source
    assert 'this.t(`value_conversion.titles.${spec.label}`)' in source
    assert "@media(max-width:600px){.value-conversion summary" in source
    assert "overflow-wrap:anywhere" in source
    assert "grid-column:1/-1" in source
    assert "data-conversion-inverse" in source
    assert "['multiplier','linear_scale'].includes(kind)" in source



def test_expression_guidance_translations_and_documentation_are_complete() -> None:
    """Every panel locale and the repository docs expose the same guidance."""
    required = {
        "expression_help", "expression_read_direction",
        "expression_write_direction", "expression_separate", "syntax_examples",
        "example_read", "example_write", "example_clamp", "example_round",
        "expression_safety",
    }
    structures = []
    for filename in ("strings.json", "translations/en.json", "translations/it.json",
                     "translations/de.json", "translations/pl.json", "translations/cs.json"):
        values = json.loads(Path("custom_components/s7plc", filename).read_text(encoding="utf-8"))["config_panel"]["value_conversion"]
        assert required <= values.keys()
        structures.append(set(values))
        for key in required:
            assert values[key] and "value_conversion." not in values[key]
        assert all(token in values["expression_help"] for token in
                   ("`value`", "`+`", "`//`", "`round`", "`clamp`"))
    assert all(keys == structures[0] for keys in structures[1:])
    docs = Path("docs/value-conversions.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    for formula in ("`value / 10`", "`value * 10`", "`clamp(value, 0, 100)`",
                    "`round(value, 1)`", "`clamp(value, minimum, maximum)`"):
        assert formula in docs
    assert "does not derive or automatically invert" in docs
    assert "[Value Conversions](docs/value-conversions.md)" in readme

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_linear_scale_clamp_editor_presentation_and_semantics() -> None:
    """Clamp is a responsive, accessible full-row option with strict booleans."""
    script = r'''
const vm=require("vm"),fs=require("fs");let Panel;
const context={HTMLElement:class{},customElements:{get(){},define:(_,cls)=>Panel=cls}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),context);
const translations=JSON.parse(fs.readFileSync(process.argv[2],"utf8")).config_panel;
const panel=new Panel();panel.escape=v=>String(v??"");panel.t=key=>key.split('.').reduce((o,k)=>o?.[k],translations)??key;
const spec={channel:'value',label:'number_value',read:'address',write:'command_address'};
const row=clamp=>panel.valueConversionRow('numbers',{address:'DB1,REAL0',command_address:'DB1,REAL4',value_conversions:{value:{type:'linear_scale',plc_min:0,plc_max:1000,ha_min:0,ha_max:100,...clamp}}},spec);
console.log(JSON.stringify({truthy:row({clamp:true}),falsey:row({clamp:false}),missing:row({}),strings:['0','false','anything','1','true'].map(value=>panel.checkboxValue(value)),summaries:[true,false,undefined].map(clamp=>panel.valueConversionSummary({type:'linear_scale',plc_min:0,plc_max:1000,ha_min:0,ha_max:100,clamp}))}));'''
    result = json.loads(subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT),
         "custom_components/s7plc/translations/it.json"],
        check=True, capture_output=True, text=True,
    ).stdout)
    assert 'class="conversion-clamp"' in result["truthy"]
    assert '<input name="vc_value_clamp" type="checkbox" checked>' in result["truthy"]
    assert "Limita il risultato all’intervallo configurato" in result["truthy"]
    assert "I valori inferiori o superiori" in result["truthy"]
    assert "type=\"checkbox\" checked" not in result["falsey"]
    assert "type=\"checkbox\" checked" not in result["missing"]
    assert result["strings"] == [False, False, False, True, True]
    assert result["summaries"] == [
        "Scala 0–1000 → 0–100 · Limitata",
        "Scala 0–1000 → 0–100",
        "Scala 0–1000 → 0–100",
    ]


def test_linear_scale_clamp_translations_layout_and_live_update() -> None:
    """Every locale includes clamp feedback and CSS covers mobile/Safari."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    required = {"clamp", "clamp_description", "clamp_preview", "result_clamped",
                "clamped_min", "clamped_max", "clamped_summary"}
    for filename in ("strings.json", "translations/en.json", "translations/it.json",
                     "translations/de.json", "translations/pl.json", "translations/cs.json"):
        values = json.loads(Path("custom_components/s7plc", filename).read_text(encoding="utf-8"))["config_panel"]["value_conversion"]
        assert required <= values.keys()
    assert ".conversion-clamp{grid-column:1/-1" in source
    assert "grid-template-columns:auto minmax(0,1fr)" in source
    assert "align-items:start" in source
    assert ".conversion-clamp input{align-self:start" in source
    assert ".conversion-clamp:focus-within" in source
    assert "input.type==='checkbox')input.addEventListener('change',sync)" in source
    assert "preview.textContent=select.value==='linear_scale'" in source
    assert "clamp:channel==='brightness'||Boolean(read('clamp')?.checked)" in source


def test_entity_card_conversion_chips_have_responsive_layout() -> None:
    """Rendered conversion chips retain their compact responsive styling."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert ".details>div{display:flex;flex-wrap:wrap;min-width:0}" in source
    assert ".details span.conversion-chip{box-sizing:border-box;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere" in source
    assert ".details span.conversion-chip:focus-visible" in source
    assert ".details span{white-space:normal;overflow-wrap:anywhere}" in source
    assert ".details div,.toolbar p{display:none}" not in source
    assert "const allChips=[...conversions,...metadata]" in source
    assert "const visible=allChips.slice(0,ENTITY_CARD_CHIP_LIMIT)" in source
    assert "clamp:channel==='brightness'||" in source
def test_number_limit_copy_and_sensor_fields_are_consistent() -> None:
    """Panel copy presents HA limits and hides meaningless sensor bounds."""
    root = Path(__file__).parents[1]
    catalogs = [
        root / "custom_components/s7plc/strings.json",
        *sorted((root / "custom_components/s7plc/translations").glob("*.json")),
    ]
    field_sets = []
    for catalog in catalogs:
        data = json.loads(catalog.read_text(encoding="utf-8"))
        entities = data["config_panel"]["entity_types"]
        assert "min_value" not in entities["sensors"]["fields"]
        assert "max_value" not in entities["sensors"]["fields"]
        number_fields = entities["numbers"]["fields"]
        field_sets.append(set(number_fields))
        for key in ("min_value", "max_value"):
            copy = number_fields[key]
            visible = f"{copy['label']} {copy['description']}".lower()
            assert "scale" + " min" not in visible
            assert "scale" + " max" not in visible
            assert "scal" not in visible
            assert "raw" not in visible
    assert all(fields == field_sets[0] for fields in field_sets)

    italian = json.loads(catalogs[4].read_text(encoding="utf-8"))
    fields = italian["config_panel"]["entity_types"]["numbers"]["fields"]
    assert fields["min_value"] == {
        "label": "Limite minimo",
        "description": "Valore minimo selezionabile in Home Assistant. Non "
        "modifica né converte il valore letto dal PLC.",
    }
    assert fields["max_value"] == {
        "label": "Limite massimo",
        "description": "Valore massimo selezionabile in Home Assistant. Non "
        "modifica né converte il valore letto dal PLC.",
    }



def test_enum_editor_layout_is_responsive() -> None:
    """The mapping grid keeps its dedicated full-width responsive layout."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert (
        ".conversion-fields>.enum-map-editor{box-sizing:border-box;grid-column:1/-1"
        in source
    )
    assert "grid-template-columns:minmax(110px,1fr) minmax(0,2fr) 44px" in source
    assert "@media(max-width:600px)" in source
    assert (
        ".enum-map-editor .om-row{grid-template-columns:minmax(0,1fr) 44px}" in source
    )
    assert (
        ".enum-map-editor .om-value,.enum-map-editor .om-label{max-width:100%}"
        in source
    )


def test_entity_card_chip_overflow_styles_and_translations_are_complete() -> None:
    """DOM tests cover behavior; catalogs and responsive styling stay complete."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert ".details span.chip-overflow{background:transparent" in source
    assert "white-space:nowrap" in source
    assert ".details>div{display:flex;flex-wrap:wrap;min-width:0}" in source
    assert "@media(max-width:650px)" in source

    root = Path(__file__).parents[1] / "custom_components" / "s7plc"
    for filename in (
        "strings.json",
        "translations/en.json",
        "translations/it.json",
        "translations/de.json",
        "translations/pl.json",
        "translations/cs.json",
    ):
        card = json.loads((root / filename).read_text(encoding="utf-8"))["config_panel"]["entity_card"]
        assert card["hidden_property"]
        assert "{count}" in card["hidden_properties"]
