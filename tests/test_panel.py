"""Tests for the native configuration panel helpers."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.panel import (
    PYS7_VERSION_DATA,
    _configuration_from_yaml,
    _configuration_yaml,
    _canonicalize_logo_addresses,
    _entity_from_message,
    _entry_payload,
    _versioned_asset_url,
    async_setup_panel,
)

PANEL_JAVASCRIPT = Path("custom_components/s7plc/www/s7plc-panel.js")
PANEL_LOADER = "require(\"vm\").runInThisContext(require(\"fs\").readFileSync(\"custom_components/s7plc/www/s7plc-panel.js\",\"utf8\"));"


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


def test_panel_asset_url_uses_manifest_version() -> None:
    manifest = json.loads(
        Path("custom_components/s7plc/manifest.json").read_text(encoding="utf-8")
    )

    assert _versioned_asset_url(
        "/s7plc_static/s7plc-panel.js", manifest["version"]
    ) == (f"/s7plc_static/s7plc-panel.js?v={manifest['version']}")


def test_panel_displays_integration_version() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "this._panel?.config?.version" in source
    assert 'class="integration-version"' in source


def test_connection_details_structural_styles_are_preserved() -> None:
    """Connection details retain the cards, timeline, and row separators."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    styles = source.split("get dialogStyles(){return `", 1)[1].split("`;}", 1)[0]

    assert ".connection-head-text{min-width:0;display:flex;flex-direction:column" in styles
    assert ".availability-title{display:flex;" in styles
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in styles
    assert ".connection-detail-group h3{display:flex;align-items:center;gap:7px" in styles
    assert ".connection-detail-group h3 ha-icon{" in styles
    assert ".connection-details .connection-detail-group dl{margin:0;border:1px" in styles
    assert ".connection-detail+.connection-detail{border-top:1px" in styles


def test_compact_selector_descriptions_wrap_long_tokens() -> None:
    """Compact cards wrap unspaced descriptions without changing their sizing."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert ".control-card small{font-size:10.5px!important;line-height:1.45;" in source
    assert "margin-top:6px;overflow-wrap:anywhere}" in source
    assert ".compact-control-card span{min-width:0;max-width:100%}" in source
    assert (
        ".light-options .control-card,.compact-control-card{min-height:110px;"
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_entity_editor_requests_viewport_bounded_desktop_width() -> None:
    """Only the entity editor requests the wider Home Assistant dialog size."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r"""
const vm = require("vm");
let Panel;
const properties = {};
const attributes = {};
const form = {dataset: {}, elements: {}, querySelector: () => null, querySelectorAll: () => []};
const dialog = {
    style: {setProperty: (name, value) => properties[name] = value},
    setAttribute: (name, value) => attributes[name] = value,
    querySelector: selector => selector === "form" ? form : {},
    querySelectorAll: () => [],
    addEventListener() {},
};
const context = {
    HTMLElement: class {},
    customElements: {get() {}, define: (_, cls) => Panel = cls},
    document: {createElement: tag => tag === "ha-dialog" ? dialog : {}, body: {appendChild() {}}},
};
vm.createContext(context);
vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
const panel = new Panel();
panel.entryId = "entry";
panel.entries = [{entry_id: "entry", entities: {sensors: []}}];
panel.editorSections = () => "";
panel.initAddressBuilders = () => {};
panel.openEditor(null, "sensors");
process.stdout.write(JSON.stringify({properties, attributes}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)], check=True, capture_output=True, text=True
    )

    assert json.loads(result.stdout) == {
        "attributes": {"width": "large"},
        "properties": {
            "--ha-dialog-width-lg": "1200px",
            "--ha-dialog-max-width": "min(1200px,96vw)",
            "--mdc-dialog-max-width": "min(1200px,96vw)",
            "--mdc-dialog-min-width": "min(1200px,96vw)",
            "--dialog-content-padding": "0",
        },
    }

    # The modern large preset is scoped to openEditor; other dialogs retain their sizes.
    assert source.count("setAttribute('width','large')") == 1
    assert source.count("--ha-dialog-width-lg") == 1
    assert "min-width:1200px" not in source


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
        "minmax(min(100%,150px),1fr));gap:10px 12px}"
    ) in dialog_styles
    assert (
        "@container(min-width:850px){.address-controls{"
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_address_builders_use_inner_query_container_and_hidden_controls() -> None:
    """S7 and LOGO keep semantic fieldsets while isolating WebKit containment."""
    script = f'''global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();panel.escape=value=>String(value??"");panel.t=key=>key;
panel.entries=[{{entry_id:"s7",plc_family:"s7"}}];panel.entryId="s7";
const s7=panel.addressField("address","DB1,X0.0","Address","",true,"sensors");
const profile={{family:"logo_0ba8",areas:[{{name:"I",first:1,last:24,vm_offset:1024,data_type:"X"}}],vm_areas:[{{name:"V",first:0,last:850,data_type:"X",width:1,bit_min:0,bit_max:7}}]}};
const logo=panel.logoAddressField("address","DB1,X1024.0","Address","",true,"binary_sensors",profile);
console.log(JSON.stringify({{s7,logo}}));'''
    markup = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    for builder in markup.values():
        assert builder.startswith('<fieldset class="address-builder"')
        assert "</legend><div class=\"address-builder-layout\">" in builder
        assert builder.endswith("</div></fieldset>")
        assert 'class="address-guided"' in builder
    assert "data-db-number hidden" not in markup["s7"]
    assert "data-bit hidden" not in markup["s7"]
    assert "data-length hidden" not in markup["s7"]
    assert "data-logo-bit hidden" in markup["logo"]
    assert 'class="address-manual" hidden' in markup["logo"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_registration_is_idempotent() -> None:
    """Repeated resource loads reuse the existing custom element registration."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r"""
const vm = require("vm");
const definitions = new Map();
const customElements = {
    get: name => definitions.get(name),
    define: (name, element) => {
        if (definitions.has(name)) throw new Error(`duplicate definition: ${name}`);
        definitions.set(name, element);
    },
};
for (let load = 0; load < 2; load++) {
    const context = {HTMLElement: class {}, customElements};
    vm.createContext(context);
    vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
}
process.stdout.write(String(definitions.size));
"""

    result = subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "1"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_editor_updates_availability_visibility_without_writing_value() -> None:
    """Only BIT availability shows its address, including with a getter-only value."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r"""
const vm = require("vm");
let Panel;
const availabilityInput = {
    get value() { return "DB1,X0.0"; },
    set required(value) { this.isRequired = value; },
};
const classes = new Set();
const field = {classList: {
    toggle: (name, force) => force ? classes.add(name) : classes.delete(name),
}};
const availabilityModes = ["connection", "always", "bit"].map(value => ({
    value,
    checked: value === "connection",
}));
const selectMode = value => availabilityModes.forEach(mode => mode.checked = mode.value === value);
const form = {
    dataset: {},
    elements: {availability_address: availabilityInput, availability_mode: {}},
    querySelector: selector => selector.includes(":checked")
        ? availabilityModes.find(mode => mode.checked)
        : field,
    querySelectorAll: selector => selector === 'input[name="availability_mode"]'
        ? availabilityModes
        : [],
};
const button = {};
const dialog = {
    style: {setProperty() {}},
    setAttribute() {},
    querySelector: selector => selector === "form" ? form : button,
    querySelectorAll: () => [],
    addEventListener() {},
};
const context = {
    HTMLElement: class {},
    customElements: {define: (_, cls) => { Panel = cls; }},
    document: {createElement: () => dialog, body: {appendChild() {}}},
};
vm.createContext(context);
vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
const panel = new Panel();
panel.entryId = "entry";
panel.entries = [{entry_id: "entry", entities: {sensors: []}}];
panel.editorSections = () => "";
panel.openEditor(null, "sensors");
const state = () => ({
    hidden: field.hidden,
    hiddenClass: classes.has("hidden-field"),
    required: availabilityInput.isRequired,
});
const initial = state();
selectMode("bit");
availabilityModes.find(mode => mode.checked).onchange();
const bit = state();
selectMode("always");
availabilityModes.find(mode => mode.checked).onchange();
const always = state();
process.stdout.write(JSON.stringify({initial, bit, always}));
"""

    result = subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "initial": {"hidden": True, "hiddenClass": True, "required": False},
        "bit": {"hidden": False, "hiddenClass": False, "required": True},
        "always": {"hidden": True, "hiddenClass": True, "required": False},
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_every_editor_renders_one_availability_address_in_ha_details() -> None:
    """Availability has one input while ordinary PLC addresses keep their section."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel = new S7PlcConfigurationPanel();
panel.t = key => key;
panel.fieldText = (_type, key, part) => `${{key}}.${{part}}`;
panel.escape = value => String(value ?? "");
panel.entries = [];
const result = {{}};
for (const type of TYPES) {{
  const markup = panel.editorSections(type, panel.inferred({{}}, type));
  const fields = [...markup.matchAll(/data-field="availability_address"/g)].length;
  const inputs = [...markup.matchAll(/name="availability_address"/g)].length;
  const ha = markup.match(/<section[^>]*data-section="ha"[\\s\\S]*?<\\/section>/)?.[0]\n    || markup.slice(markup.lastIndexOf('<section class="form-section"'));
  result[type] = {{fields, inputs, inHa: ha.includes('data-field="availability_address"')}};
}}
const section = (type, key, sectionKey="addresses") => {{
  const markup = panel.editorSections(type, panel.inferred({{}}, type));
  const addresses = markup.match(new RegExp(`<section[^>]*data-section="${{sectionKey}}"[\\\\s\\\\S]*?<\\\\/section>`))?.[0]\n    || markup.split('<section class="form-section"')[1] || "";
  return addresses.includes(`data-field="${{key}}"`);
}};
console.log(JSON.stringify({{result, ordinary: {{
  sensor: section("sensors", "address"),
  light: section("lights", "state_address"),
  cover: section("covers", "open_command_address"),
  climate: section("climates", "current_temperature_address", "climate-temperature"),
}}}}));
"""
    value = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert set(value["result"]) == {
        "sensors", "binary_sensors", "switches", "covers", "lights", "buttons",
        "numbers", "selects", "texts", "climates", "entity_sync",
    }
    assert all(item == {"fields": 1, "inputs": 1, "inHa": True} for item in value["result"].values())
    assert all(value["ordinary"].values())


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_climate_availability_visibility_is_independent_of_climate_options() -> None:
    """Every Climate recalculation derives availability solely from its mode."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const optionChanges = [
  {{control_mode:"direct", direct_function:"heat", direct_feedback:"inferred", mode_control:"setpoint", action_feedback:"inferred"}},
  {{control_mode:"direct", direct_function:"cool", direct_feedback:"plc", mode_control:"coded", action_feedback:"plc"}},
  {{control_mode:"direct", direct_function:"heat_cool", direct_feedback:"inferred", mode_control:"on_off", action_feedback:"inferred"}},
  {{control_mode:"setpoint", direct_function:"heat", direct_feedback:"plc", mode_control:"coded_on_off", action_feedback:"plc"}},
];
const visible = (availability_mode, options) => CLIMATE_EDITOR_VISIBILITY({{...options, availability_mode}}).fields.has("availability_address");
console.log(JSON.stringify(Object.fromEntries(["connection", "always", "bit"].map(mode => [mode, optionChanges.map(options => visible(mode, options))]))));
"""
    value = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert value == {
        "connection": [False] * 4,
        "always": [False] * 4,
        "bit": [True] * 4,
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_entity_cards_use_type_specific_main_address_without_duplicate_chips() -> None:
    """Card summaries share the backend-compatible main-address precedence."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = rf"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
global.document = {{createElement:()=>{{
  let value="";
  return {{set textContent(next){{value=String(next);}},get innerHTML(){{return value.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");}}}};
}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key==="common.entity"?"Entity":key;
panel.bt=key=>key;
panel.fieldText=(type,key)=>key;
panel.type="covers";
panel.entries=[];
panel.selectedIndices=new Set();
const render=(type,items)=>{{
  panel.type=type;
  const html=panel.entityCards({{entities:{{[type]:items}}}});
  return [...html.matchAll(/<div class="details"><b>(.*?)<\/b><code>(.*?)<\/code><div>(.*?)<\/div><\/div>/g)]
    .map(match=>({{title:match[1],address:match[2],chips:match[3]}}));
}};
console.log(JSON.stringify({{
  named:render("covers",[{{name:"Kitchen blind",open_command_address:"DB1,X0.0"}}]),
  traditional:render("covers",[{{open_command_address:"DB1,X0.1",close_command_address:"DB1,X0.2"}}]),
  position:render("covers",[{{position_state_address:"DB1,BYTE2",position_command_address:"DB1,BYTE3"}}]),
  mixed:render("covers",[{{position_state_address:"DB1,BYTE4",open_command_address:"DB1,X0.4"}}]),
  missing:render("covers",[{{close_command_address:"DB1,X0.5"}}]),
  unchanged:{{
    sensor:render("sensors",[{{address:"DB2,REAL0"}}]),
    switch:render("switches",[{{state_address:"DB2,X4.0",command_address:"DB2,X4.1"}}]),
    climate:render("climates",[{{current_temperature_address:"DB2,REAL6"}}]),
    sync:render("entity_sync",[{{source_entity:"sensor.source",address:"DB2,X10.0"}}])
  }},
  escaped:render("covers",[
    {{name:"<configured & name>",open_command_address:"DB<1>&X0",close_command_address:"<chip & value>"}},
    {{position_state_address:"<DB & position>"}}
  ])
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert result["named"][0]["title"] == "Kitchen blind"
    assert result["named"][0]["address"] == "DB1,X0.0"
    assert "DB1,X0.0" not in result["named"][0]["chips"]
    assert result["traditional"][0]["title"] == "DB1,X0.1"
    assert result["traditional"][0]["address"] == "DB1,X0.1"
    assert "DB1,X0.1" not in result["traditional"][0]["chips"]
    assert result["position"][0]["title"] == "DB1,BYTE2"
    assert result["position"][0]["address"] == "DB1,BYTE2"
    assert "DB1,BYTE2" not in result["position"][0]["chips"]
    assert result["mixed"][0]["title"] == "DB1,BYTE4"
    assert result["mixed"][0]["address"] == "DB1,BYTE4"
    assert "DB1,BYTE4" not in result["mixed"][0]["chips"]
    assert result["missing"][0]["title"] == "Entity 1"
    assert result["missing"][0]["address"] == "—"

    assert result["unchanged"] == {
        "sensor": [{"title": "DB2,REAL0", "address": "DB2,REAL0", "chips": ""}],
        "switch": [
            {
                "title": "DB2,X4.0",
                "address": "DB2,X4.0",
                "chips": "<span>command_address: DB2,X4.1</span>",
            }
        ],
        "climate": [
            {"title": "DB2,REAL6", "address": "DB2,REAL6", "chips": ""}
        ],
        "sync": [
            {
                "title": "DB2,X10.0",
                "address": "DB2,X10.0",
                "chips": "<span>source_entity: sensor.source</span>",
            }
        ],
    }
    assert result["escaped"] == [
        {
            "title": "&lt;configured &amp; name&gt;",
            "address": "DB&lt;1&gt;&amp;X0",
            "chips": "<span>close_command_address: &lt;chip &amp; value&gt;</span>",
        },
        {
            "title": "&lt;DB &amp; position&gt;",
            "address": "&lt;DB &amp; position&gt;",
            "chips": "",
        },
    ]


def test_connection_badge_opens_read_only_connection_details() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert 'type="button" class="connection-badge' in source
    assert ".connection-badge').onclick=()=>this.openConnectionDetails(entry)" in source
    assert "connectionDetailGroups(data)" in source
    assert "pys7_version:entry.pys7_version" in source
    assert "Object.entries(entry.data)" not in source
    assert 'class="connection-detail"' in source
    assert "openConnectionDetails(entry)" in source
    details_source = source[
        source.index("  openConnectionDetails(entry){") : source.index("  field(")
    ]
    assert "input name=" not in details_source


def test_panel_typography_uses_home_assistant_fonts_semantically() -> None:
    """Normal UI values inherit HA typography; only technical data is mono."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "var(--ha-font-family-body,Roboto,sans-serif)" in source
    assert "@import" not in source
    assert "fonts.googleapis.com" not in source
    assert (
        ".connection-detail dd{margin:0;font-size:13px;font-family:inherit;"
        "font-weight:500" in source
    )
    assert "font-variant-numeric:tabular-nums" in source
    assert ".connection-detail dd.technical-value{font-family:ui-monospace" in source
    assert "key==='local_tsap'||key==='remote_tsap'" in source
    assert ".connection-head-text code{font-family:ui-monospace" in source
    assert ".details code{" in source and "font-family:ui-monospace" in source
    assert ".visual-form input.mono{font-family:ui-monospace" in source
    assert ".yaml-editor textarea{" in source
    assert ".configuration-editor textarea{" in source
    assert "@media(max-width:650px)" in source


def test_connection_performance_uses_write_batching_key() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    performance_group = next(
        line for line in source.splitlines() if '{key:"performance"' in line
    )
    assert '"enable_write_batching"' in performance_group
    assert "group_writes" not in source


def test_connection_detail_groups_are_ordered_dynamic_and_lossless() -> None:
    """The executable helper owns ordering and mode-specific filtering."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const simplify=data=>connectionDetailGroups(data).map(group=>({{
  key:group.key,fields:group.fields.map(field=>field.key)
}}));
console.log(JSON.stringify({{
 rack:simplify({{future_option:42,port:102,slot:1,name:"S7 PLC",rack:0,
   enable_write_batching:true,connection_type:"rack_slot",host:"192.168.100.89",
    pys7_connection_type:"pg",pys7_version:"3.1.1",scan_interval:1,operation_timeout:5,
   optimize_read:true,enable_metrics:false,max_retries:3,
   retry_backoff_initial:0.5,retry_backoff_max:2,local_tsap:"ignored"}}),
 tsap:simplify({{slot:9,remote_tsap:"03.02",rack:9,connection_type:"tsap",
    local_tsap:"01.00",pys7_connection_type:"op",pys7_version:"3.1.1"}}),
 incomplete:simplify({{host:"plc.local",new_setting:"kept"}}),
 empty:simplify(null)
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert result["rack"] == [
        {
            "key": "connection",
            "fields": [
                "pys7_version",
                "pys7_connection_type",
                "connection_type",
                "rack",
                "slot",
            ],
        },
        {
            "key": "performance",
            "fields": [
                "scan_interval",
                "operation_timeout",
                "optimize_read",
                "enable_write_batching",
                "enable_metrics",
            ],
        },
        {
            "key": "retry",
            "fields": [
                "max_retries",
                "retry_backoff_initial",
                "retry_backoff_max",
            ],
        },
        {"key": "other", "fields": ["future_option"]},
    ]
    assert result["tsap"] == [
        {
            "key": "connection",
            "fields": [
                "pys7_version",
                "pys7_connection_type",
                "connection_type",
                "local_tsap",
                "remote_tsap",
            ],
        }
    ]
    assert result["incomplete"] == [{"key": "other", "fields": ["new_setting"]}]
    assert result["empty"] == []


def test_connection_values_preserve_dotted_versions() -> None:
    """Literal versions must not be reduced to their final dotted segment."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.panelTranslations={{config_panel:{{connection_details:{{values:{{yes:"Yes",pg:"PG profile"}}}}}}}};
console.log(JSON.stringify([
  panel.connectionValue("3.1.1"),
  panel.connectionValue(true),
  panel.connectionValue("pg")
]));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert result == ["3.1.1", "Yes", "PG profile"]


def test_connection_availability_calculations_cover_unknown_and_transitions() -> None:
    """Timeline excludes unknown time and counts only on-to-off transitions."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const hour = 3600000, now = Date.parse("2026-08-21T12:00:00Z");
const history = [
  {{state:"on",last_changed:"2026-08-20T14:00:00Z"}},
  {{state:"off",last_changed:"2026-08-20T18:00:00Z"}},
  {{state:"unavailable",last_changed:"2026-08-20T20:00:00Z"}},
  {{state:"on",last_changed:"2026-08-20T21:00:00Z"}},
  {{state:"off",last_changed:"2026-08-21T02:00:00Z"}},
  {{state:"on",last_changed:"2026-08-21T03:00:00Z"}}
];
const result=BUILD_CONNECTION_AVAILABILITY(history,now,24*hour);
console.log(JSON.stringify({{durations:result.durations,availability:result.availability,disconnects:result.disconnects,currentUptime:result.currentUptime,last:result.lastDisconnection}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["durations"] == {
        "connected": 18 * 3_600_000,
        "disconnected": 3 * 3_600_000,
        "unknown": 3 * 3_600_000,
    }
    assert result["availability"] == pytest.approx(18 / 21 * 100)
    assert result["disconnects"] == 2
    assert result["currentUptime"] == 9 * 3_600_000
    assert result["last"]["end"] - result["last"]["start"] == 3_600_000


def test_connection_availability_does_not_invent_initial_state() -> None:
    """Incomplete recorder data stays unknown until the first actual event."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const now=Date.parse("2026-08-21T12:00:00Z"),hour=3600000;
const result=BUILD_CONNECTION_AVAILABILITY([{{state:"on",last_changed:"2026-08-21T10:00:00Z"}}],now,24*hour);
console.log(JSON.stringify(result));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["durations"]["unknown"] == 22 * 3_600_000
    assert result["durations"]["connected"] == 2 * 3_600_000
    assert result["availability"] == 100
    assert result["disconnects"] == 0


def test_connection_duration_prefers_live_state_and_handles_edge_cases() -> None:
    """Live last_changed wins, while absent/invalid states degrade safely."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const hour=3600000,now=Date.parse("2026-08-21T12:00:00Z");
const historical={{currentUptime:2*hour}};
const apply=state=>APPLY_LIVE_CONNECTION_DURATION(historical,state,now);
console.log(JSON.stringify({{
  longUptime:apply({{state:"on",last_changed:"2026-08-19T06:00:00Z"}}),
  absent:apply(undefined),
  invalid:apply({{state:"on",last_changed:"not-a-date"}}),
  off:apply({{state:"off",last_changed:"2026-08-21T07:00:00Z"}}),
  unknown:apply({{state:"unknown",last_changed:"2026-08-21T07:00:00Z"}}),
  unavailable:apply({{state:"unavailable",last_changed:"2026-08-21T07:00:00Z"}})
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert result["longUptime"]["currentUptime"] == 54 * 3_600_000
    assert result["absent"]["currentUptime"] == 2 * 3_600_000
    assert result["invalid"]["currentUptime"] == 2 * 3_600_000
    assert result["off"]["currentUptime"] is None
    assert result["off"]["currentDowntime"] == 5 * 3_600_000
    assert result["unknown"]["currentUptime"] is None
    assert result["unavailable"]["currentUptime"] is None


def test_connection_popup_status_uses_live_sensor_before_snapshot() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
console.log(JSON.stringify([
  LIVE_CONNECTION_STATUS({{state:"on"}},false),
  LIVE_CONNECTION_STATUS({{state:"off"}},true),
  LIVE_CONNECTION_STATUS({{state:"unknown"}},true),
  LIVE_CONNECTION_STATUS({{state:"unavailable"}},true),
  LIVE_CONNECTION_STATUS(undefined,true),
  LIVE_CONNECTION_STATUS(undefined,false)
]));
"""
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout) == [
        "connected",
        "disconnected",
        "unknown",
        "unknown",
        "connected",
        "disconnected",
    ]


def test_connection_diagnostics_controls_are_visible_and_accessible() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert 'icon="mdi:information-outline"' in source
    assert 'class="connection-badge-details"' in source
    assert "this.t('connection_details.title')" in source
    assert "@media(max-width:480px){.connection-badge-details{display:none}}" in source
    assert ".connection-badge:focus-visible" in source
    assert ".connection-badge:active" in source
    assert '<span tabindex="0" class="timeline-segment' in source


def test_connection_badge_aria_label_is_localized_and_refreshed() -> None:
    """Initial rendering and live refresh use the same label for every status."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert 'aria-label="${this.connectionBadgeAriaLabel(status)}"' in source
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>({{"common.connected":"Connected","common.disconnected":"Disconnected","common.unknown":"Unknown","connection_details.help":"Show connection details"}}[key]);
panel._loaded=true;panel.entryId="plc";panel.querySelector=()=>badge;
const labels=[],badge={{classList:{{toggle() {{}}}},setAttribute:(name,value)=>{{if(name==="aria-label")labels.push(value);}}}};
const statuses=[true,false,null];let index=0;
panel._hass={{callWS:async()=>[{{entry_id:"plc",connected:statuses[index++]}}]}};
(async()=>{{
  const initial=statuses.map(value=>panel.connectionBadgeAriaLabel(value===true?"connected":value===false?"disconnected":"unknown"));
  for(let i=0;i<statuses.length;i++)await panel.refreshConnectionStatus();
  console.log(JSON.stringify({{initial,labels}}));
}})();
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    expected = [
        "Connected · Show connection details",
        "Disconnected · Show connection details",
        "Unknown · Show connection details",
    ]
    assert result == {"initial": expected, "labels": expected}


def test_connection_history_fallback_preserves_only_valid_live_duration() -> None:
    """Missing history keeps a valid live uptime/downtime without invented stats."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
console.debug=()=>{{}};
{PANEL_LOADER}
const now=Date.parse("2026-08-21T12:00:00Z");Date.now=()=>now;
const panel=new S7PlcConfigurationPanel();
panel.t=key=>({{
  "availability.current_uptime":"Current uptime",
  "availability.current_downtime":"Current downtime",
  "availability.history_unavailable":"Historical data is not available.",
  "availability.day_short":"d","availability.hour_short":"h","availability.minute_short":"m"
}}[key]||key);
const states={{
  on:{{state:"on",last_changed:"2026-08-18T05:00:00Z"}},
  off:{{state:"off",last_changed:"2026-08-21T11:42:00Z"}},
  unknown:{{state:"unknown",last_changed:"2026-08-21T11:00:00Z"}},
  unavailable:{{state:"unavailable",last_changed:"2026-08-21T11:00:00Z"}},
  missing:{{state:"on"}},invalid:{{state:"off",last_changed:"invalid"}}
}};
const run=async(name,history,entity=true)=>{{
  const container={{innerHTML:""}};panel._hass={{states:entity?{{"binary_sensor.connection":states[name]}}:{{}},callApi:async()=>{{if(history==="error")throw Error("history");return history;}}}};
  await panel.loadConnectionAvailability({{querySelector:()=>container}},entity?{{connection_entity_id:"binary_sensor.connection"}}:{{}});
  return container.innerHTML;
}};
(async()=>console.log(JSON.stringify({{
  emptyOn:await run("on",[[]]),errorOff:await run("off","error"),noEntity:await run("on",null,false),
  unknown:await run("unknown",[[]]),unavailable:await run("unavailable",[[]]),missing:await run("missing",[[]]),invalid:await run("invalid",[[]])
}})))();
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert "Current uptime" in result["emptyOn"]
    assert "3d 7h" in result["emptyOn"]
    assert "Current downtime" in result["errorOff"]
    assert "18m" in result["errorOff"]
    for key, markup in result.items():
        assert "Historical data is not available." in markup
        assert "connection-timeline" not in markup
        assert "availability.percentage" not in markup
        assert "availability.disconnections" not in markup
        if key not in {"emptyOn", "errorOff"}:
            assert "availability-stats" not in markup


def test_connection_diagnostics_translations_are_complete() -> None:
    paths = [
        Path("custom_components/s7plc/strings.json"),
        *Path("custom_components/s7plc/translations").glob("*.json"),
    ]

    for path in paths:
        panel = json.loads(path.read_text(encoding="utf-8"))["config_panel"]
        assert panel["connection_details"]["title"]
        assert panel["common"]["unknown"]
        assert panel["availability"]["current_downtime"]
        assert list(panel["connection_details"]["sections"]) == [
            "connection",
            "performance",
            "retry",
            "other",
        ]
        assert panel["connection_details"]["fields"]["connection_type"]["label"]
        assert panel["connection_details"]["fields"]["pys7_connection_type"]["label"]

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


def test_panel_control_mode_mapping_preserves_backend_format() -> None:
    """The graphical mode must remain a view over the legacy boolean keys."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const fixtures = [
  {{}},
  {{sync_state: true}},
  {{pulse_command: true}},
  {{sync_state: true, pulse_command: true}}
];
console.log(JSON.stringify({{
  loaded: fixtures.map(CONTROL_MODE_FROM_ENTITY),
  saved: ["direct", "sync", "pulse"].map(mode =>
    APPLY_CONTROL_MODE({{name: "unchanged", unrelated: 42}}, mode))
}}));
"""
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    behavior = json.loads(result.stdout)

    assert behavior["loaded"] == ["direct", "sync", "pulse", "pulse"]
    assert behavior["saved"] == [
        {
            "name": "unchanged",
            "unrelated": 42,
            "sync_state": False,
            "pulse_command": False,
        },
        {
            "name": "unchanged",
            "unrelated": 42,
            "sync_state": True,
            "pulse_command": False,
        },
        {
            "name": "unchanged",
            "unrelated": 42,
            "sync_state": False,
            "pulse_command": True,
        },
    ]


def test_panel_light_mode_inference_uses_only_brightness_state_address() -> None:
    """The virtual mode follows the backend's actual dimmer requirement."""
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate the panel helpers")
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    prefix = source.split("const CONNECTION_WINDOW_MS", 1)[0]
    script = (
        prefix
        + "\nconsole.log(JSON.stringify([{}, {brightness_scale: 10}, {brightness_command_address: 'DB1,W2'}, {brightness_state_address: 'DB1,W0'}].map(LIGHT_MODE_FROM_ENTITY)));"
    )
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout) == ["on_off", "on_off", "on_off", "dimmable"]


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
    assert (
        "if(lightMode==='on_off'){delete entity.brightness_state_address;delete entity.brightness_command_address;delete entity.brightness_scale;}"
        in source
    )
    assert (
        "if(!entity.brightness_state_address)throw Error(this.t('errors.brightness_state_required_error'))"
        in source
    )
    assert "if(entity.brightness_scale==null)entity.brightness_scale=255" in source
    assert 'min="1" max="65535"' in source
    assert (
        "['brightness_state_address','brightness_command_address','brightness_scale'].forEach"
        in source
    )


def test_panel_control_mode_is_context_aware() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "command!==state" in source
    assert "sync.disabled=!canSync" in source
    assert "selected!=='pulse'" in source
    assert '[data-field="pulse_duration"]' in source
    assert '["control_behavior","control"]' in source
    assert 'name="sync_state" type="checkbox"' not in source
    assert 'name="pulse_command" type="checkbox"' not in source


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


def test_configuration_editor_handles_load_download_and_repeated_clicks() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "configuration_load_error" in source
    assert "configuration_download_error" in source
    assert "textarea.disabled=!!loadError" in source
    assert "if(backupLoading)return" in source
    assert "if(saveLoading)return" in source
    assert "backupButton.disabled=true" in source
    assert "saveButton.disabled=true" in source


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

    payload = _entry_payload(entry)

    assert payload["connected"] is connected
    assert payload["pys7_version"] is None


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
    assert "presetValue?'step=\"1\"':key==='brightness_scale'" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize(
    ("locale", "responses", "expected_urls", "expected_title", "expected_field"),
    [
        (
            "it-IT",
            ["it"],
            ["/s7plc_translations/it.json"],
            "Configurazione S7 PLC",
            "Nome",
        ),
        (
            "fr-FR",
            ["en"],
            ["/s7plc_translations/en.json"],
            "S7 PLC configuration",
            "Name",
        ),
        (
            "de-DE",
            [],
            [
                "/s7plc_translations/de.json",
                "/s7plc_translations/en.json",
            ],
            "S7 PLC configuration",
            "Name",
        ),
    ],
)
def test_panel_translation_loading_and_fallbacks(
    locale: str,
    responses: list[str],
    expected_urls: list[str],
    expected_title: str,
    expected_field: str | None,
) -> None:
    """External JSON is canonical, with locale and fetch failures kept safe."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    payloads = {
        language: json.loads(
            Path(f"custom_components/s7plc/translations/{language}.json").read_text(
                encoding="utf-8"
            )
        )
        for language in responses
    }
    script = r"""
const vm=require('vm'); let Panel; const urls=[];
const payloads=JSON.parse(process.argv[2]);
const context={HTMLElement:class{},customElements:{define:(_,cls)=>Panel=cls},console,
  fetch:async url=>{urls.push(url);const language=url.match(/\/([^/]+)\.json$/)[1];
    if(!(language in payloads))return {ok:false,status:503};
    return {ok:true,json:async()=>payloads[language]};}};
vm.createContext(context);vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'),context);
(async()=>{const panel=new Panel();panel._hass={locale:{language:process.argv[3]}};
  await panel.loadPanelTranslations();
  process.stdout.write(JSON.stringify({urls,title:panel.t('common.title'),
    field:panel.fieldText('sensors','name','label')??null}));})();
"""

    result = subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT), json.dumps(payloads), locale],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "urls": expected_urls,
        "title": expected_title,
        "field": expected_field,
    }


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_translates_backend_validation_errors() -> None:
    """Known flow errors are translated while unknown messages remain readable."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    translations = json.loads(
        Path("custom_components/s7plc/translations/it.json").read_text(encoding="utf-8")
    )
    script = (
        "const vm=require('vm');"
        "let Panel;"
        "const context={HTMLElement:class{},customElements:{define:(_,cls)=>Panel=cls}};"
        "vm.createContext(context);vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'),context);"
        "const panel=new Panel();panel.panelTranslations=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(process.argv.slice(3).map(key=>panel.flowError(key))));"
    )

    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(PANEL_JAVASCRIPT),
            json.dumps(translations),
            "invalid_address",
            "duplicate_entry",
            "Unknown field(s) for sensors: pippo",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == [
        "Formato indirizzo non valido.",
        "Questo elemento è già presente.",
        "Unknown field(s) for sensors: pippo",
    ]


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_bool_addresses_use_bool_placeholder() -> None:
    """Boolean PLC address fields use the BOOL-specific placeholder."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    prefix = source.split("class S7PlcConfigurationPanel", 1)[0]

    script = (
        "const vm=require('vm');"
        "const context={};vm.createContext(context);"
        "vm.runInContext(process.argv[1] + "
        "'\\nglobalThis.result=BOOL_FIELDS;',context);"
        "process.stdout.write(JSON.stringify(context.result));"
    )

    result = subprocess.run(
        ["node", "-e", script, prefix],
        check=True,
        capture_output=True,
        text=True,
    )

    bool_fields = json.loads(result.stdout)

    assert set(bool_fields["binary_sensors"]) == {
        "address",
    }

    assert set(bool_fields["switches"]) == {
        "state_address",
        "command_address",
    }

    assert set(bool_fields["lights"]) == {
        "state_address",
        "command_address",
    }

    assert set(bool_fields["buttons"]) == {
        "address",
    }

    assert set(bool_fields["covers"]) == {
        "open_command_address",
        "close_command_address",
        "opening_state_address",
        "closing_state_address",
        "cover_opening_address",
        "cover_closing_address",
        "cover_stopped_address",
        "stop_command_address",
    }

    assert set(bool_fields["climates"]) == {
        "heating_output_address",
        "cooling_output_address",
        "heating_action_address",
        "cooling_action_address",
        "on_off_address",
    }

    # Numeric cover addresses must not accidentally become BOOL.
    assert "position_state_address" not in bool_fields["covers"]
    assert "position_command_address" not in bool_fields["covers"]

    assert "boolAddress=BOOL_FIELDS[type]?.includes(key)" in source
    assert "address_example_bool" in source

    english = json.loads(
        Path("custom_components/s7plc/translations/en.json").read_text(encoding="utf-8")
    )
    assert english["config_panel"]["common"]["address_example_bool"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_text_addresses_use_string_placeholder() -> None:
    """Text entity PLC addresses use a STRING-specific placeholder."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    prefix = source.split("class S7PlcConfigurationPanel", 1)[0]

    script = (
        "const vm=require('vm');"
        "const context={};vm.createContext(context);"
        "vm.runInContext(process.argv[1] + "
        "'\\nglobalThis.result=STRING_FIELDS;',context);"
        "process.stdout.write(JSON.stringify(context.result));"
    )

    result = subprocess.run(
        ["node", "-e", script, prefix],
        check=True,
        capture_output=True,
        text=True,
    )

    string_fields = json.loads(result.stdout)

    assert set(string_fields["texts"]) == {
        "address",
        "command_address",
    }

    assert "stringAddress=STRING_FIELDS[type]?.includes(key)" in source
    assert "address_example_string" in source

    for language in ("en", "it", "cs", "de", "pl"):
        translations = json.loads(
            Path(f"custom_components/s7plc/translations/{language}.json").read_text(
                encoding="utf-8"
            )
        )

        assert translations["config_panel"]["common"]["address_example_string"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_address_placeholders_match_plc_data_type() -> None:
    """Manual address examples match the field's supported PLC data types."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = """
const vm = require('vm');
let Panel;
const context = {HTMLElement: class {}, customElements: {define: (_, cls) => Panel = cls}};
vm.createContext(context);
vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
const panel = new Panel();
panel.fieldText = () => 'Label';
panel.escape = value => String(value);
panel.t = key => ({
  'common.address_example': 'REAL',
  'common.address_example_bool': 'BOOL',
  'common.address_example_integer': 'INTEGER',
  'common.address_example_string': 'STRING'
}[key] || key);
const placeholder = (type, key) => panel.field([key], {}, type)
  .match(/placeholder="([^"]*)"/)[1];
process.stdout.write(JSON.stringify({
  textAddress: placeholder('texts', 'address'),
  textCommandAddress: placeholder('texts', 'command_address'),
  boolAddress: placeholder('covers', 'open_command_address'),
  selectAddress: placeholder('selects', 'address'),
  selectCommandAddress: placeholder('selects', 'command_address'),
  genericAddress: placeholder('sensors', 'address')
}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "textAddress": "STRING",
        "textCommandAddress": "STRING",
        "boolAddress": "BOOL",
        "selectAddress": "INTEGER",
        "selectCommandAddress": "INTEGER",
        "genericAddress": "REAL",
    }

    expected = {
        "en": ("e.g. DB1,S0.254", "e.g. DB1,W0"),
        "it": ("es. DB1,S0.254", "es. DB1,W0"),
        "de": ("z. B. DB1,S0.254", "z. B. DB1,W0"),
        "pl": ("np. DB1,S0.254", "np. DB1,W0"),
        "cs": ("např. DB1,S0.254", "např. DB1,W0"),
    }
    strings = json.loads(
        Path("custom_components/s7plc/strings.json").read_text(encoding="utf-8")
    )
    assert (
        strings["config_panel"]["common"]["address_example_string"]
        == expected["en"][0]
    )
    assert strings["config_panel"]["common"]["address_example_integer"] == expected["en"][1]
    for language, (string_example, integer_example) in expected.items():
        translations = json.loads(
            Path(f"custom_components/s7plc/translations/{language}.json").read_text(
                encoding="utf-8"
            )
        )
        assert (
            translations["config_panel"]["common"]["address_example_string"]
            == string_example
        )
        assert (
            translations["config_panel"]["common"]["address_example_integer"]
            == integer_example
        )


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


def test_panel_hides_close_and_operate_time_in_toggle_control_mode() -> None:
    """toggle is a third cover_control_mode choice (alongside
    traditional/position), not a separate checkbox layered onto
    traditional. Selecting it pulses open_command_address for a fixed
    short duration instead of using close_command_address or the
    timer-based operate_time, so neither field is shown for that mode."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert (
        "control==='position'?['position_state_address','position_command_address',"
        "'invert_position']:control==='toggle'?['open_command_address']:"
        "['open_command_address','close_command_address']"
    ) in source
    assert "if(control==='traditional')visible.add('operate_time')" in source


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


def test_fields_contain_only_technical_metadata_and_have_panel_text() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    if shutil.which("node") is None:
        pytest.skip("node is required to evaluate FIELDS")
    script = f"""
global.HTMLElement = class {{}}; global.customElements = {{define() {{}}}};
{PANEL_LOADER}
console.log(JSON.stringify(FIELDS));
"""
    fields = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    english = json.loads(
        Path("custom_components/s7plc/translations/en.json").read_text(encoding="utf-8")
    )["config_panel"]
    technical_kinds = {
        "text",
        "number",
        "checkbox",
        "select",
        "control",
        "light",
        "cover-selector",
        "climate-selector",
        "options-map",
    }
    for entity_type, definitions in fields.items():
        for definition in definitions:
            assert len(definition) <= 4
            assert len(definition) == 1 or definition[1] in technical_kinds
            key = definition[0]
            text = english["entity_types"][entity_type]["fields"].get(key) or english[
                "common"
            ]["fields"].get(key)
            assert text and text["label"] and text["description"]


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_cover_virtual_modes_and_cleanup_follow_backend_precedence() -> None:
    """Cover UI projections are deterministic and virtual fields never persist."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const infer = COVER_UI_FROM_ENTITY;
const clean = (entity, ui) => CLEAN_COVER_ENTITY(entity, ui);
const mixed={{uid:"kept",name:"Legacy",position_state_address:"DB1,B0",open_command_address:"Q0.0",cover_status_address:"DB1,B10",cover_opening_address:"I0.0",tilt_command_address:"DB1,B2",stop_command_address:"Q0.2"}};
console.log(JSON.stringify({{
 traditional:infer({{open_command_address:"Q0.0"}}),
 position:infer(mixed),
 timed:infer({{}}).cover_position_feedback,
 endstops:infer({{opening_state_address:"I0.0",closing_state_address:"I0.1",use_state_topics:true}}).cover_position_feedback,
 legacyEndstop:infer({{opening_state_address:"I0.0"}}).cover_position_feedback,
 statusWins:infer(mixed).cover_movement_feedback,
 bits:infer({{cover_closing_address:"I0.1"}}).cover_movement_feedback,
 toTraditional:clean(mixed,{{cover_control_mode:"traditional",cover_position_feedback:"timed",cover_movement_feedback:"none",cover_stop_enabled:false,cover_tilt_enabled:false}}),
 traditionalTimedStatus:clean({{uid:"timed",open_command_address:"Q0.0",close_command_address:"Q0.1",cover_status_address:"DB1,B10",cover_status_opening_values:"1",cover_status_closing_values:"2"}},{{cover_control_mode:"traditional",cover_position_feedback:"timed",cover_movement_feedback:"status",cover_stop_enabled:false,cover_tilt_enabled:false}}),
 traditionalEndstopStatus:clean({{uid:"endstop",open_command_address:"Q0.0",close_command_address:"Q0.1",opening_state_address:"I0.0",cover_status_address:"DB1,B10",cover_status_open_values:"3",cover_status_stopped_values:"4"}},{{cover_control_mode:"traditional",cover_position_feedback:"opening",cover_movement_feedback:"status",cover_stop_enabled:false,cover_tilt_enabled:false}}),
 toPosition:clean({{uid:"kept",position_state_address:"DB1,B0",open_command_address:"Q0.0",close_command_address:"Q0.1",opening_state_address:"I0.0",closing_state_address:"I0.1",operate_time:20,use_state_topics:true,cover_opening_address:"I0.2",cover_status_address:"DB1,B10",cover_status_open_values:"1",stop_command_address:"Q0.2",tilt_state_address:"DB1,B2",feedback_mode:"status",cover_mode:"position"}},{{cover_control_mode:"position",cover_position_feedback:"timed",cover_movement_feedback:"status",cover_stop_enabled:false,cover_tilt_enabled:false}}),
 toggleStatusPositionBitsMovement:clean({{uid:"mixed",open_command_address:"Q0.0",cover_status_address:"DB1,B10",cover_status_open_values:"1",cover_status_closed_values:"2",cover_opening_address:"I0.0",cover_closing_address:"I0.1"}},{{cover_control_mode:"toggle",cover_position_feedback:"status",cover_movement_feedback:"bits",cover_stop_enabled:false,cover_tilt_enabled:false}}),
 traditionalStatusPositionBitsMovement:clean({{uid:"mixed",open_command_address:"Q0.0",close_command_address:"Q0.1",cover_status_address:"DB1,B10",cover_status_open_values:"1",cover_status_closed_values:"2",cover_opening_address:"I0.0",cover_closing_address:"I0.1"}},{{cover_control_mode:"traditional",cover_position_feedback:"status",cover_movement_feedback:"bits",cover_stop_enabled:false,cover_tilt_enabled:false}})
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-"],
            input=script,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert result["traditional"]["cover_control_mode"] == "traditional"
    assert result["position"]["cover_control_mode"] == "position"
    assert result["timed"] == "timed"
    assert result["endstops"] == "both"
    assert result["legacyEndstop"] == "opening"
    # "mixed" is a legacy position cover with cover_status_address but no
    # value mapping at all (neither open/closed nor opening/closing/
    # stopped), and no opening/closing_state_address - the status word
    # isn't usable as a position or movement source without any mapping,
    # so position_feedback infers "position" and movement_feedback prefers
    # the separately configured bits, the only source that's actually
    # usable here (PR #124 review, points 2 and 3).
    assert result["statusWins"] == "bits"
    assert result["bits"] == "bits"
    assert result["traditional"]["cover_stop_enabled"] == "disabled"
    assert result["traditional"]["cover_tilt_enabled"] == "disabled"
    assert result["position"]["cover_stop_enabled"] == "enabled"
    assert result["position"]["cover_tilt_enabled"] == "enabled"
    traditional = result["toTraditional"]
    assert traditional["uid"] == "kept" and traditional["name"] == "Legacy"
    assert (
        "position_state_address" not in traditional
        and "tilt_command_address" not in traditional
    )
    assert (
        "cover_status_address" not in traditional
        and "stop_command_address" not in traditional
    )
    assert traditional["use_state_topics"] is False
    timed_status = result["traditionalTimedStatus"]
    assert timed_status["cover_status_address"] == "DB1,B10"
    assert timed_status["cover_status_opening_values"] == "1"
    assert timed_status["cover_status_closing_values"] == "2"
    assert timed_status["cover_position_feedback"] == "timed"
    endstop_status = result["traditionalEndstopStatus"]
    assert endstop_status["opening_state_address"] == "I0.0"
    assert endstop_status["cover_status_address"] == "DB1,B10"
    # Plain traditional covers keep the pre-existing coupling: movement
    # feedback being "status" makes the whole cover_status_address+value
    # set authoritative together, regardless of position feedback - so
    # cover_status_open_values (nominally a *position* value field) still
    # survives here even though position feedback is "opening", not
    # "status". This is the pre-existing, unsplit behavior - see
    # toggleStatusPositionBitsMovement below for toggle_mode's independent
    # (split) scoping instead (PR #117 review round 4, point 1).
    assert endstop_status["cover_status_open_values"] == "3"
    assert endstop_status["cover_status_stopped_values"] == "4"
    assert endstop_status["cover_position_feedback"] == "opening"
    # toggle_mode: position=status + movement=bits keeps BOTH sources -
    # neither one silently discards the other (PR #117 review round 3,
    # point 2).
    toggle_mixed = result["toggleStatusPositionBitsMovement"]
    assert toggle_mixed["cover_status_address"] == "DB1,B10"
    assert toggle_mixed["cover_status_open_values"] == "1"
    assert toggle_mixed["cover_status_closed_values"] == "2"
    assert toggle_mixed["cover_opening_address"] == "I0.0"
    assert toggle_mixed["cover_closing_address"] == "I0.1"
    # Plain traditional: the same combination still can't keep both - the
    # old exclusive switch treats movement_feedback=="bits" as authoritative
    # over the whole status word, so cover_status_address (and its
    # position-feedback value fields) get dropped too, not just kept-but-
    # unused (round 4, point 1 - the preserved, intentional limitation).
    traditional_mixed = result["traditionalStatusPositionBitsMovement"]
    assert "cover_status_address" not in traditional_mixed
    assert "cover_status_open_values" not in traditional_mixed
    position = result["toPosition"]
    assert position["uid"] == "kept" and position["cover_status_address"] == "DB1,B10"
    for key in (
        "open_command_address",
        "close_command_address",
        "opening_state_address",
        "closing_state_address",
        "operate_time",
        "use_state_topics",
        "cover_opening_address",
        "stop_command_address",
        "tilt_state_address",
        "cover_mode",
        "feedback_mode",
    ):
        assert key not in position


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_cover_rendered_form_saves_without_use_state_topics_input() -> None:
    """Regression for #113: save the fields rendered by the real cover editor."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
panel.fieldText=(type,key,part)=>`${{key}}.${{part}}`;
panel.escape=value=>String(value);
panel.entries=[];
const makeRenderedForm=(original,overrides={{}})=>{{
  const initial={{...original,...COVER_UI_FROM_ENTITY(original),...overrides}};
  const markup=panel.editorSections("covers",initial);
  const names=new Set([...markup.matchAll(/ name="([^"]+)"/g)].map(match=>match[1]));
  const elements={{}};
  for(const key of names){{
    const kind=FIELDS.covers.find(field=>field[0]===key)?.[1];
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,markup,reportValidity:()=>true}};
}};
const save=(original,overrides={{}})=>{{
  const form=makeRenderedForm(original,overrides);
  return {{entity:panel.formEntity(form,original,"covers"),hasDerivedInput:"use_state_topics" in form.elements,markup:form.markup}};
}};
const details={{uid:"cover-1",name:"Blind",area:"living",device_class:"blind",scan_interval:2}};
const commands={{open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1"}};
const timed=save({{...details}},commands);
const endstops=save({{...details}},{{...commands,cover_position_feedback:"both",opening_state_address:"DB1,X0.2",closing_state_address:"DB1,X0.3"}});
const position=save({{...details}},{{cover_control_mode:"position",position_state_address:"DB1,BYTE0"}});
const edited=save({{...details,...commands,use_state_topics:true,opening_state_address:"DB1,X0.2",closing_state_address:"DB1,X0.3"}},{{name:"Edited"}});
console.log(JSON.stringify({{timed,endstops,position,edited,virtual:COVER_VIRTUAL_FIELDS}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    for saved in ("timed", "endstops", "position", "edited"):
        assert result[saved]["hasDerivedInput"] is False
        assert 'name="use_state_topics"' not in result[saved]["markup"]
        assert not set(result[saved]["entity"]) & set(result["virtual"])
        for key in ("uid", "area", "device_class", "scan_interval"):
            assert result[saved]["entity"][key] == result["timed"]["entity"][key]

    assert result["timed"]["entity"]["use_state_topics"] is False
    assert result["timed"]["entity"]["name"] == "Blind"
    assert result["endstops"]["entity"]["use_state_topics"] is True
    assert "use_state_topics" not in result["position"]["entity"]
    assert result["edited"]["entity"]["use_state_topics"] is True
    assert result["edited"]["entity"]["name"] == "Edited"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_cover_editor_radio_markup_and_form_submission_regressions() -> None:
    """Exercise the radio values and the same formEntity path used by Save."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
panel.fieldText=(type,key,part)=>`${{key}}.${{part}}`;
panel.escape=value=>String(value);
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,reportValidity:()=>true}};
}};
const save=(original,overrides={{}})=>panel.formEntity(makeForm(original,overrides),original,"covers");
const stop={{position_state_address:"DB1,BYTE0",stop_command_address:"DB1,X10.0",stop_pulse_duration:0.5}};
const tilt={{position_state_address:"DB1,BYTE0",tilt_state_address:"DB1,BYTE2",tilt_command_address:"DB1,BYTE4",invert_tilt:true}};
const opening={{open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1",opening_state_address:"DB1,X0.2"}};
const closing={{open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1",closing_state_address:"DB1,X0.3"}};
const markup=entity=>{{const ui=infer(entity);return {{
  stop:panel.field(FIELDS.covers.find(field=>field[0]==="cover_stop_enabled"),ui,"covers"),
  tilt:panel.field(FIELDS.covers.find(field=>field[0]==="cover_tilt_enabled"),ui,"covers")
}};}};
const virtual=COVER_VIRTUAL_FIELDS;
const switchedToTraditional=save({{uid:"same",name:"Legacy",area:"living",device_class:"blind",scan_interval:2,...stop,...tilt}},{{cover_control_mode:"traditional",cover_position_feedback:"timed",open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1"}});
const switchedToPosition=save({{uid:"same",name:"Legacy",open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1",opening_state_address:"DB1,X0.2",operate_time:20,use_state_topics:false,cover_opening_address:"DB1,X0.4",cover_closing_address:"DB1,X0.5",cover_stopped_address:"DB1,X0.6"}},{{cover_control_mode:"position",position_state_address:"DB1,BYTE0",cover_position_feedback:"timed",cover_movement_feedback:"none"}});
console.log(JSON.stringify({{
  inferred:{{none:infer({{}}),stop:infer(stop),tiltState:infer(tilt),tiltCommand:infer({{tilt_command_address:"DB1,BYTE4"}})}},
  markup:{{none:markup({{}}),stop:markup(stop),tilt:markup(tilt)}},
  unchanged:{{stop:save(stop),tilt:save(tilt)}},
  disabled:{{stop:save(stop,{{cover_stop_enabled:"disabled"}}),tilt:save(tilt,{{cover_tilt_enabled:"disabled"}})}},
  endstops:{{opening:save(opening),closing:save(closing)}},
  switched:{{traditional:switchedToTraditional,position:switchedToPosition}},
  hasVirtual:[save(stop),save(tilt),switchedToTraditional,switchedToPosition].some(entity=>virtual.some(key=>key in entity))
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-"],
            input=script,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    inferred = result["inferred"]
    assert inferred["none"]["cover_stop_enabled"] == "disabled"
    assert inferred["stop"]["cover_stop_enabled"] == "enabled"
    assert inferred["none"]["cover_tilt_enabled"] == "disabled"
    assert inferred["tiltState"]["cover_tilt_enabled"] == "enabled"
    # A command-only legacy value deterministically exposes tilt controls; the
    # existing state-address validation still applies if the user saves it.
    assert inferred["tiltCommand"]["cover_tilt_enabled"] == "enabled"
    assert 'value="disabled" checked' in result["markup"]["none"]["stop"]
    assert 'value="disabled" checked' in result["markup"]["none"]["tilt"]
    assert 'value="enabled" checked' in result["markup"]["stop"]["stop"]
    assert 'value="enabled" checked' in result["markup"]["tilt"]["tilt"]

    assert result["unchanged"]["stop"]["stop_command_address"] == "DB1,X10.0"
    assert result["unchanged"]["stop"]["stop_pulse_duration"] == 0.5
    assert result["unchanged"]["tilt"]["tilt_state_address"] == "DB1,BYTE2"
    assert result["unchanged"]["tilt"]["tilt_command_address"] == "DB1,BYTE4"
    assert result["unchanged"]["tilt"]["invert_tilt"] is True
    assert "stop_command_address" not in result["disabled"]["stop"]
    assert "stop_pulse_duration" not in result["disabled"]["stop"]
    assert "tilt_state_address" not in result["disabled"]["tilt"]
    assert "tilt_command_address" not in result["disabled"]["tilt"]
    assert "invert_tilt" not in result["disabled"]["tilt"]

    # Legacy single-end-stop configurations infer and retain their exact mode.
    assert result["endstops"]["opening"]["opening_state_address"] == "DB1,X0.2"
    assert "closing_state_address" not in result["endstops"]["opening"]
    assert "use_state_topics" not in result["endstops"]["opening"]
    assert result["endstops"]["closing"]["closing_state_address"] == "DB1,X0.3"
    assert "opening_state_address" not in result["endstops"]["closing"]
    assert "use_state_topics" not in result["endstops"]["closing"]

    traditional = result["switched"]["traditional"]
    for key in (
        "position_state_address",
        "position_command_address",
        "invert_position",
        "tilt_state_address",
        "tilt_command_address",
        "invert_tilt",
        "stop_command_address",
        "stop_pulse_duration",
    ):
        assert key not in traditional
    assert traditional["uid"] == "same"
    assert traditional["name"] == "Legacy"
    assert traditional["area"] == "living"
    assert traditional["device_class"] == "blind"
    assert traditional["scan_interval"] == 2

    position = result["switched"]["position"]
    for key in (
        "open_command_address",
        "close_command_address",
        "opening_state_address",
        "closing_state_address",
        "operate_time",
        "use_state_topics",
        "cover_opening_address",
        "cover_closing_address",
        "cover_stopped_address",
    ):
        assert key not in position
    assert result["hasVirtual"] is False


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_cover_endstop_mode_round_trip_matches_backend_validation() -> None:
    """End-stop mode is explicit and, like the backend, requires both inputs."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,dataset:{{coverFeedbackChanged:Object.prototype.hasOwnProperty.call(overrides,"cover_position_feedback")?"true":""}},reportValidity:()=>true}};
}};
const save=(original,overrides={{}})=>panel.formEntity(makeForm(original,overrides),original,"covers");
const error=(original,overrides={{}})=>{{try{{save(original,overrides);return null;}}catch(err){{return err.message;}}}};
const commands={{open_command_address:"DB1,X0.0",close_command_address:"DB1,X0.1"}};
const both={{...commands,opening_state_address:"DB1,X0.2",closing_state_address:"DB1,X0.3"}};
const persisted={{...both,use_state_topics:true}};
const stale={{...both,use_state_topics:false}};
const legacy={{...commands,opening_state_address:"DB1,X0.2",use_state_topics:true}};
console.log(JSON.stringify({{
  inferred:{{persisted:infer(persisted),stale:infer(stale),legacy:infer(legacy)}},
  roundTrip:save(persisted),
  created:save(commands,{{cover_position_feedback:"both",opening_state_address:"DB1,X0.2",closing_state_address:"DB1,X0.3"}}),
  timedStale:save(stale),
  timedFromEndstops:save(persisted,{{cover_position_feedback:"timed"}}),
  endstopsFromTimed:save(stale,{{cover_position_feedback:"both"}}),
  missing:{{opening:error(commands,{{cover_position_feedback:"both",opening_state_address:"DB1,X0.2"}}),closing:error(commands,{{cover_position_feedback:"both",closing_state_address:"DB1,X0.3"}}),legacy:error(legacy)}}
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert result["inferred"]["persisted"]["cover_position_feedback"] == "both"
    assert result["inferred"]["legacy"]["cover_position_feedback"] == "opening"
    assert result["inferred"]["stale"]["cover_position_feedback"] == "timed"
    for key in ("roundTrip", "created", "endstopsFromTimed"):
        assert result[key]["use_state_topics"] is True
        assert result[key]["opening_state_address"] == "DB1,X0.2"
        assert result[key]["closing_state_address"] == "DB1,X0.3"
    assert result["timedStale"]["use_state_topics"] is False
    assert result["timedStale"]["opening_state_address"] == "DB1,X0.2"
    assert result["timedStale"]["closing_state_address"] == "DB1,X0.3"
    for key in ("timedFromEndstops",):
        assert result[key]["use_state_topics"] is False
        assert "opening_state_address" not in result[key]
        assert "closing_state_address" not in result[key]
    assert result["missing"]["opening"] == "errors.cover_endstop_closed_required_error"
    assert result["missing"]["closing"] == "errors.cover_endstop_open_required_error"
    assert result["missing"]["legacy"] is None


def test_position_cover_endstop_and_movement_bits_round_trip() -> None:
    """Position-mode covers get the same end-stop/movement-bit feedback
    parity as traditional/toggle: the "Pozycja" section and the "bits"
    movement option are no longer traditional/toggle-exclusive."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,dataset:{{coverFeedbackChanged:Object.prototype.hasOwnProperty.call(overrides,"cover_position_feedback")?"true":""}},reportValidity:()=>true}};
}};
const save=(original,overrides={{}})=>panel.formEntity(makeForm(original,overrides),original,"covers");
const error=(original,overrides={{}})=>{{try{{save(original,overrides);return null;}}catch(err){{return err.message;}}}};
const positionBase={{position_state_address:"DB1,B0"}};
const positionBoth={{...positionBase,opening_state_address:"DB1,X0.2",closing_state_address:"DB1,X0.3"}};
console.log(JSON.stringify({{
  inferred:infer(positionBoth),
  roundTrip:save(positionBoth,{{cover_position_feedback:"both"}}),
  bitsRoundTrip:save({{...positionBase,cover_opening_address:"DB1,X2.0",cover_closing_address:"DB1,X2.1"}},{{cover_movement_feedback:"bits"}}),
  missing:{{opening:error(positionBase,{{cover_position_feedback:"both",opening_state_address:"DB1,X0.2"}}),closing:error(positionBase,{{cover_position_feedback:"both",closing_state_address:"DB1,X0.3"}})}}
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["inferred"]["cover_position_feedback"] == "both"
    assert result["roundTrip"]["opening_state_address"] == "DB1,X0.2"
    assert result["roundTrip"]["closing_state_address"] == "DB1,X0.3"
    assert result["bitsRoundTrip"]["cover_opening_address"] == "DB1,X2.0"
    assert result["bitsRoundTrip"]["cover_closing_address"] == "DB1,X2.1"
    assert result["missing"]["opening"] == "errors.cover_endstop_closed_required_error"
    assert result["missing"]["closing"] == "errors.cover_endstop_open_required_error"


def test_position_cover_feedback_section_and_bits_option_always_visible() -> None:
    """syncMode() no longer hides the "Pozycja" section or the "bits"
    movement-feedback option card for control==='position'."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert (
        'form.querySelector(\'[data-section="cover-position-feedback"]\').classList.toggle(\'hidden-field\',control===\'position\')'
        not in source
    )
    assert (
        'form.querySelector(\'input[name="cover_movement_feedback"][value="bits"]\').closest(\'.control-card\').classList.toggle(\'hidden-field\',control===\'position\')'
        not in source
    )


def test_position_cover_default_feedback_uses_position_not_timed_concept() -> None:
    """Position covers have a continuous 0-100 reading of their own, so the
    "no separate source" concept is called "position", not "timed" - a
    legacy entity persisted with "timed" (from before the two were split)
    normalizes to "position" on save, and the "timed" card stays hidden
    for position mode while "position" stays hidden everywhere else."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,dataset:{{coverFeedbackChanged:Object.prototype.hasOwnProperty.call(overrides,"cover_position_feedback")?"true":""}},reportValidity:()=>true}};
}};
const save=(original,overrides={{}})=>panel.formEntity(makeForm(original,overrides),original,"covers");
console.log(JSON.stringify({{
  freshPosition:infer({{position_state_address:"DB1,B0"}}).cover_position_feedback,
  legacyTimedPosition:infer({{position_state_address:"DB1,B0",cover_position_feedback:"timed"}}).cover_position_feedback,
  freshTraditional:infer({{open_command_address:"Q0.0"}}).cover_position_feedback,
  roundTripPosition:save({{position_state_address:"DB1,B0"}},{{cover_position_feedback:"position"}}).cover_position_feedback,
  legacySaveNormalizes:save({{position_state_address:"DB1,B0",cover_position_feedback:"timed"}}).cover_position_feedback,
  roundTripTraditional:save({{open_command_address:"Q0.0",close_command_address:"Q0.1"}},{{cover_position_feedback:"timed"}}).cover_position_feedback
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["freshPosition"] == "position"
    assert result["legacyTimedPosition"] == "position"
    assert result["freshTraditional"] == "timed"
    assert result["roundTripPosition"] == "position"
    assert result["legacySaveNormalizes"] == "position"
    assert result["roundTripTraditional"] == "timed"
    assert (
        "form.querySelector('input[name=\"cover_position_feedback\"][value=\"timed\"]')"
        ".closest('.control-card').classList.toggle('hidden-field',"
        "control==='toggle'||control==='position')"
    ) in source
    assert (
        "form.querySelector('input[name=\"cover_position_feedback\"][value=\"position\"]')"
        ".closest('.control-card').classList.toggle('hidden-field',control!=='position')"
    ) in source


def test_position_cover_legacy_movement_only_status_saves_without_new_required_fields() -> None:
    """A legacy position cover whose cover_status_address only carries
    opening/closing/stopped values (no open/closed) must keep saving
    through the visual editor without requiring a new open/closed mapping
    - position_feedback infers "position" (not "status") for it, leaving
    the status word to movement_feedback alone (PR #124 review, point 2)."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,dataset:{{coverFeedbackChanged:""}},reportValidity:()=>true}};
}};
const legacy={{
  position_state_address:"DB1,B0",
  cover_status_address:"DB1,B10",
  cover_status_opening_values:"1",
  cover_status_closing_values:"2",
  cover_status_stopped_values:"3"
}};
console.log(JSON.stringify({{
  inferred:infer(legacy),
  saved:panel.formEntity(makeForm(legacy),legacy,"covers")
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["inferred"]["cover_position_feedback"] == "position"
    assert result["inferred"]["cover_movement_feedback"] == "status"
    saved = result["saved"]
    assert saved["cover_status_address"] == "DB1,B10"
    assert saved["cover_status_opening_values"] == "1"
    assert saved["cover_position_feedback"] == "position"


def test_position_cover_legacy_position_only_status_saves_without_new_required_fields() -> None:
    """Symmetric counterpart: a legacy position cover whose
    cover_status_address only carries open/closed values (no opening/
    closing/stopped) must keep saving through the visual editor without
    requiring a new movement mapping - movement_feedback infers "none"
    (not "status") for it, since the status word has no movement mapping
    to offer; position_feedback correctly keeps claiming "status" for
    itself (PR #124 review round 2, point 1)."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>key;
const infer=COVER_UI_FROM_ENTITY;
const makeForm=(original,overrides={{}})=>{{
  const initial={{...original,...infer(original),...overrides}},elements={{}};
  for(const [key,kind] of FIELDS.covers){{
    const checkbox=kind==="checkbox";
    elements[key]={{type:checkbox?"checkbox":kind==="number"?"number":"text",value:String(initial[key]??""),checked:checkbox?Boolean(initial[key]):false}};
  }}
  return {{elements,dataset:{{coverFeedbackChanged:""}},reportValidity:()=>true}};
}};
const legacy={{
  position_state_address:"DB1,B0",
  cover_status_address:"DB1,B10",
  cover_status_open_values:"1",
  cover_status_closed_values:"2"
}};
console.log(JSON.stringify({{
  inferred:infer(legacy),
  saved:panel.formEntity(makeForm(legacy),legacy,"covers")
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result["inferred"]["cover_position_feedback"] == "status"
    assert result["inferred"]["cover_movement_feedback"] == "none"
    saved = result["saved"]
    assert saved["cover_status_address"] == "DB1,B10"
    assert saved["cover_status_open_values"] == "1"
    assert saved["cover_position_feedback"] == "status"


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

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_climate_guided_visibility_validation_and_selector_icons() -> None:
    """Execute Climate visibility, save validation, and selector rendering."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}}; global.customElements = {{define() {{}}}};
{PANEL_LOADER}
const visibility=values=>{{const result=CLIMATE_EDITOR_VISIBILITY(values);return {{fields:[...result.fields],sections:[...result.sections]}};}};
const direct=visibility({{control_mode:"direct",direct_function:"heat",direct_feedback:"inferred",mode_control:"setpoint",action_feedback:"plc"}});
const inferred=visibility({{control_mode:"setpoint",mode_control:"setpoint",action_feedback:"inferred"}});
const plc=visibility({{control_mode:"setpoint",mode_control:"coded",action_feedback:"plc"}});
const panel=Object.create(S7PlcConfigurationPanel.prototype);
panel.fieldText=(_type,key,part)=>`${{key}}.${{part}}`;panel.escape=value=>String(value);panel.t=key=>key;
const falseMarkup=panel.field(["preset_mode_bidirectional","climate-selector",true,["false","true"]],{{preset_mode_bidirectional:false}},"climates");
const trueMarkup=panel.field(["preset_mode_bidirectional","climate-selector",true,["false","true"]],{{preset_mode_bidirectional:true}},"climates");
const makeForm=selected=>{{const elements={{}};for(const [key,kind] of FIELDS.climates)elements[key]={{type:kind==="checkbox"?"checkbox":kind==="number"?"number":"text",value:"",checked:false}};Object.assign(elements.current_temperature_address,{{value:"DB1,REAL0"}});Object.assign(elements.heating_output_address,{{value:"Q0.0"}});Object.assign(elements.target_temperature_address,{{value:"DB1,REAL4"}});Object.assign(elements.preset_mode_address,{{value:"DB1,BYTE8"}});Object.assign(elements.preset_mode_bidirectional,{{value:selected.bidirectional}});return {{elements,dataset:{{climateChanged:"control_mode"}},reportValidity:()=>true,querySelector:selector=>{{const name=selector.match(/name=\"([^\"]+)/)?.[1];return name?{{value:selected[name]}}:null;}}}};}};
const original={{uid:"kept",control_mode:"setpoint",current_temperature_address:"DB1,REAL0",target_temperature_address:"DB1,REAL4",hvac_status_address:"DB1,BYTE8"}};
const directEntity=panel.formEntity(makeForm({{control_mode:"direct",climate_direct_function:"heat",climate_direct_feedback:"inferred",climate_mode_control:"setpoint",climate_action_feedback:"plc",bidirectional:"false"}}),original,"climates");
let statusError="";try{{panel.formEntity(makeForm({{control_mode:"setpoint",climate_direct_function:"heat",climate_direct_feedback:"inferred",climate_mode_control:"setpoint",climate_action_feedback:"plc",bidirectional:"true"}}),{{current_temperature_address:"DB1,REAL0",target_temperature_address:"DB1,REAL4"}},"climates");}}catch(error){{statusError=error.message;}}
const booleanFalse=panel.formEntity(makeForm({{control_mode:"setpoint",climate_direct_function:"heat",climate_direct_feedback:"inferred",climate_mode_control:"coded",climate_action_feedback:"inferred",bidirectional:"false"}}),{{}},"climates").preset_mode_bidirectional;
const booleanTrue=panel.formEntity(makeForm({{control_mode:"setpoint",climate_direct_function:"heat",climate_direct_feedback:"inferred",climate_mode_control:"coded",climate_action_feedback:"inferred",bidirectional:"true"}}),{{}},"climates").preset_mode_bidirectional;
console.log(JSON.stringify({{direct,inferred,plc,falseMarkup,trueMarkup,directEntity,statusError,booleanFalse,booleanTrue}}));
"""
    value = json.loads(
        subprocess.run(
            ["node", "-"],
            input=script,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    status_fields = {"hvac_status_address"} | {
        f"hvac_status_{status}_values"
        for status in (
            "off",
            "heating",
            "cooling",
            "idle",
            "drying",
            "fan",
            "preheating",
            "defrosting",
        )
    }
    assert "climate-action-feedback" not in value["direct"]["sections"]
    assert "climate-direct-feedback" in value["direct"]["sections"]
    assert "climate_action_feedback" not in value["direct"]["fields"]
    assert status_fields.isdisjoint(value["direct"]["fields"])
    assert "climate-action-feedback" in value["inferred"]["sections"]
    assert status_fields.isdisjoint(value["inferred"]["fields"])
    assert status_fields <= set(value["plc"]["fields"])
    assert "climate-mode-feedback" in value["plc"]["sections"]
    assert "hvac_status_address" not in value["directEntity"]
    assert value["directEntity"]["uid"] == "kept"
    assert value["statusError"] == "errors.climate_status_required_error"
    assert "mdi:history" in value["falseMarkup"]
    assert "mdi:sync" in value["trueMarkup"]
    assert "mdi:undefined" not in value["falseMarkup"] + value["trueMarkup"]
    assert value["booleanFalse"] is False
    assert value["booleanTrue"] is True

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_layout_modes_persistence_and_sections_rendering() -> None:
    """The alternate layout is presentation-only, persistent, and complete."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = rf"""
global.HTMLElement = class {{}};
global.customElements = {{get(){{}},define(){{}}}};
global.localStorage = {{getItem(){{return this.value}},setItem(_key,value){{this.value=value;}}}};
global.document = {{createElement:()=>{{
  let value="";
  return {{set textContent(next){{value=String(next);}},get innerHTML(){{return value.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");}}}};
}}}};
{PANEL_LOADER}
const entities=Object.fromEntries(TYPES.map(type=>[type,[]]));
entities.sensors=[{{name:"Temperature",address:"DB1,REAL0"}},{{name:"Pressure",address:"DB1,REAL4"}}];
entities.switches=[{{name:"Pump",state_address:"DB1,X8.0"}}];
const entry={{entities,entity_ids:{{}},selector_options:{{}}}};
const panel=new S7PlcConfigurationPanel();
panel.t=key=>({{"common.entity":"Entity","common.entities":"entities","actions.add":"Add"}}[key]||key);
panel.bt=key=>key; panel.fieldText=(type,key)=>key;
panel.selectedIndices=new Set(); panel.expandedSections=new Set(TYPES); panel._viewMode="tabs";
let rendered=0; panel.render=()=>rendered++;
const defaultMode=panel.readViewMode();
panel.setViewMode("sections");
const stored=global.localStorage?.value??null;
const sections=panel._renderSectionsView(entry);
panel.expandedSections.delete("switches");
const collapsed=panel._renderSectionsView(entry);
global.localStorage={{getItem:()=>"invalid",setItem(_key,value){{this.value=value;}}}};
const invalid=panel.readViewMode();
global.localStorage={{getItem(){{throw Error("blocked")}},setItem(){{throw Error("blocked")}}}};
const inaccessible=panel.readViewMode(); panel.setViewMode("tabs");
console.log(JSON.stringify({{defaultMode,stored,invalid,inaccessible,rendered,
 sectionCount:(sections.match(/data-section-type=/g)||[]).length,
 sensorCount:sections.includes("2 entities"),empty:sections.includes('data-section-type="binary_sensors"'),
 addSensor:sections.includes('data-add="sensors"'),expanded:sections.includes('aria-expanded="true"'),
 collapsed:collapsed.includes('data-section-toggle="switches"')&&collapsed.includes('aria-expanded="false"')&&!collapsed.includes('data-entity-type="switches"'),
 title:sections.includes('title="layout.collapse_section"'),aria:sections.includes('aria-label="layout.collapse_section: entity_types.sensors.label"')
}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )
    assert result == {
        "defaultMode": "tabs",
        "stored": "sections",
        "invalid": "tabs",
        "inaccessible": "tabs",
        "rendered": 2,
        "sectionCount": 11,
        "sensorCount": True,
        "empty": True,
        "addSensor": True,
        "expanded": True,
        "collapsed": True,
        "title": True,
        "aria": True,
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_panel_layout_toggle_labels_each_action_and_remains_responsive() -> None:
    """The layout control exposes the translated action in every accessible label."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement = class {{}};
global.customElements = {{get(){{}},define(){{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>({{
  "layout.switch_to_sections":"Switch to all-entities view",
  "layout.switch_to_tabs":"Switch to category view"
}}[key]||key);
panel._viewMode="tabs";const categories=panel.layoutToggle();
panel._viewMode="sections";const allEntities=panel.layoutToggle();
console.log(JSON.stringify({{categories,allEntities}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    categories = result["categories"]
    assert '<ha-icon icon="mdi:view-sequential"></ha-icon>' in categories
    assert '<span>Switch to all-entities view</span>' in categories
    assert 'title="Switch to all-entities view"' in categories
    assert 'aria-label="Switch to all-entities view"' in categories
    assert "<ha-tooltip>Switch to all-entities view</ha-tooltip>" in categories

    all_entities = result["allEntities"]
    assert '<ha-icon icon="mdi:tab"></ha-icon>' in all_entities
    assert '<span>Switch to category view</span>' in all_entities
    assert 'title="Switch to category view"' in all_entities
    assert 'aria-label="Switch to category view"' in all_entities
    assert "<ha-tooltip>Switch to category view</ha-tooltip>" in all_entities

    assert "@media(max-width:500px)" in source
    responsive = source[source.index("@media(max-width:500px)") :]
    responsive = responsive[: responsive.index("@media(max-width:480px)")]
    assert ".layout-toggle span{display:none}" in responsive
    assert ".layout-toggle{display:none}" not in responsive


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_sections_batch_delete_groups_and_deletes_the_global_selection() -> None:
    """The sections toolbar deletes every valid selection with one lifecycle."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = rf"""
global.HTMLElement = class {{}};
global.customElements = {{get(){{}},define(){{}}}};
const dialogs=[];
const makeDialog=()=>{{
  const primary={{disabled:false}},secondary={{disabled:false}},alert={{style:{{}}}};
  return {{primary,secondary,alert,open:false,addEventListener(){{}},remove(){{}},
    querySelector(selector){{return selector==='[slot=primaryAction]'?primary:selector==='[slot=secondaryAction]'?secondary:alert;}}}};
}};
global.document = {{body:{{appendChild(dialog){{dialogs.push(dialog);}}}},createElement:tag=>{{
  if(tag==='ha-dialog')return makeDialog();
  let value='';return {{set textContent(next){{value=String(next);}},get innerHTML(){{return value;}}}};
}}}};
{source}
const entities=Object.fromEntries(TYPES.map(type=>[type,[]]));
entities.sensors=[{{name:'A'}},{{name:'B'}}];entities.switches=[{{name:'C'}}];
const entry={{entities,entity_ids:{{}}}};
const panel=new S7PlcConfigurationPanel();panel._viewMode='sections';panel.expandedSections=new Set(TYPES);
panel.t=key=>key;panel.bt=(key,values={{}})=>key+(values.count===undefined?'':` ${{values.count}}`);panel.fieldText=()=>'';
panel.selectedIndices=new Set(['sensors:2','switches:0','sensors:5','sensors:2','covers:1','bad','unknown:3','lights:-1','texts:1.5','buttons:2:3',4]);
const grouped=panel.groupedSelectedIndices();const markup=panel._renderSectionsView(entry);
const bulkSpan={{textContent:''}},bulkButton={{hidden:true,querySelector:()=>bulkSpan}};
panel.querySelector=selector=>selector==='[data-batch-delete-global]'?bulkButton:null;panel.updateBulkAction();
const calls=[],states=[];panel.entryId='entry';panel._hass={{callWS:async message=>{{states.push(panel.selectedIndices.size);calls.push(message);}}}};
let reloads=0;panel.load=async()=>{{reloads++;states.push(panel.selectedIndices.size);}};
panel.removeGroupedSelection();const dialog=dialogs.at(-1);const operation=dialog.primary.onclick();dialog.primary.onclick();await operation;

const failed=new S7PlcConfigurationPanel();failed._viewMode='sections';failed.selectedIndices=new Set(['sensors:1','sensors:0','switches:0']);
failed.t=key=>key;failed.bt=(key,values={{}})=>`${{key}} ${{values.count}}`;failed.entryId='entry';
let failedCalls=0,failedReloads=0;failed._hass={{callWS:async()=>{{failedCalls++;if(failedCalls===2)throw Error('PLC offline');}}}};
failed.load=async()=>{{failedReloads++;}};failed.removeGroupedSelection();const failedDialog=dialogs.at(-1);await failedDialog.primary.onclick();
await failedDialog.primary.onclick();const failureAfterSecondClick={{calls:failedCalls,reloads:failedReloads,open:failedDialog.open}};
failedDialog.secondary.onclick();
console.log(JSON.stringify({{grouped,markup:{{global:markup.includes('data-batch-delete-global'),sectionBatch:markup.includes('data-batch-delete=')}},
  bulk:{{hidden:bulkButton.hidden,text:bulkSpan.textContent}},calls,reloads,states,dialogs:dialogs.length,selection:[...panel.selectedIndices],
  failure:{{calls:failedCalls,reloads:failedReloads,selection:[...failed.selectedIndices],openBeforeClose:failureAfterSecondClick.open,
    openAfterClose:failedDialog.open,error:failedDialog.alert.textContent,shown:failedDialog.alert.style.display,
    deleteDisabled:failedDialog.primary.disabled,secondaryDisabled:failedDialog.secondary.disabled,afterSecondClick:failureAfterSecondClick}}}}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "--input-type=module", "-"],
            input=script,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert result["grouped"] == {
        "sensors": [5, 2],
        "switches": [0],
        "covers": [1],
    }
    assert result["markup"] == {"global": True, "sectionBatch": False}
    assert result["bulk"] == {"hidden": False, "text": "delete_selected (4)"}
    assert result["calls"] == [
        {"type": "s7plc/config/delete_entity", "entry_id": "entry", "entity_type": "sensors", "index": 5},
        {"type": "s7plc/config/delete_entity", "entry_id": "entry", "entity_type": "sensors", "index": 2},
        {"type": "s7plc/config/delete_entity", "entry_id": "entry", "entity_type": "switches", "index": 0},
        {"type": "s7plc/config/delete_entity", "entry_id": "entry", "entity_type": "covers", "index": 1},
    ]
    assert result["reloads"] == 1
    assert result["states"] == [10, 10, 10, 10, 0]
    assert result["dialogs"] == 2
    assert result["selection"] == []
    assert result["failure"] == {
        "calls": 2,
        "reloads": 1,
        "selection": [],
        "openBeforeClose": True,
        "openAfterClose": False,
        "error": "errors.delete_entities_error PLC offline",
        "shown": "block",
        "deleteDisabled": True,
        "secondaryDisabled": False,
        "afterSecondClick": {"calls": 2, "reloads": 1, "open": True},
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_batch_delete_empty_selection_and_tabs_behavior() -> None:
    """An empty global selection is inert and tabs keep category deletion."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f"""
global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};
let dialogs=0;global.document={{body:{{appendChild(){{dialogs++;}}}},createElement:()=>({{}})}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();panel._viewMode='sections';panel.selectedIndices=new Set();panel.removeGroupedSelection();
panel._viewMode='tabs';panel.selectedIndices=new Set([3,1,3]);
console.log(JSON.stringify({{dialogs,indices:panel.selectedIndicesFor('sensors')}}));
"""
    result = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert result == {"dialogs": 0, "indices": [3, 1]}


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

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_guided_address_grammar_round_trips_every_supported_type() -> None:
    """The browser grammar mirrors current pyS7 tokens and canonical forms."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    cases = [
        "DB1,X10.3", "I3.0", "Q2.6", "M7.1", "DB36,B2", "DB1,USINT2",
        "DB1,SINT2", "DB102,C4", "DB17,W4", "DB10,I3", "DB51,DW6",
        "DB103,DI3", "DB21,R14", "DB21,LR14", "DB1,TIME4",
        "DB102,S10.15", "DB2,WS0.128", "IB10", "QW8", "MD72",
    ]
    script = f'''global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}\nconsole.log(JSON.stringify(process.argv.slice(1).map(value=>{{const parsed=PARSE_S7_ADDRESS(value);return [parsed.error,SERIALIZE_S7_ADDRESS(parsed)];}})));'''
    result = json.loads(subprocess.run(["node", "-e", script, *cases], check=True, capture_output=True, text=True).stdout)
    assert all(not error for error, _ in result)
    # Aliases intentionally serialize to the builder's stable short-token spelling.
    assert [value for _, value in result] == [
        "DB1,X10.3", "I3.0", "Q2.6", "M7.1", "DB36,B2", "DB1,USINT2",
        "DB1,SINT2", "DB102,C4", "DB17,W4", "DB10,I3", "DB51,DW6",
        "DB103,DI3", "DB21,R14", "DB21,LR14", "DB1,TIME4",
        "DB102,S10.15", "DB2,WS0.128", "IB10", "QW8", "MDW72",
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_guided_address_validation_and_field_restrictions() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = f'''global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}\nconsole.log(JSON.stringify({{
      badBit:PARSE_S7_ADDRESS("DB1,X0.8").error,
      missingLength:PARSE_S7_ADDRESS("DB1,S0").error,
      timeArea:PARSE_S7_ADDRESS("MTIME0").error,
      malformed:PARSE_S7_ADDRESS("DB1,").error,
      empty:PARSE_S7_ADDRESS("").empty,
      boolean:ADDRESS_TYPES_FOR_FIELD("binary_sensors","address"),
      text:ADDRESS_TYPES_FOR_FIELD("texts","address"),
      select:ADDRESS_TYPES_FOR_FIELD("selects","address"),
      optional:SERIALIZE_S7_ADDRESS({{empty:true}})
    }}));'''
    value = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert value == {"badBit":"invalid", "missingLength":"incomplete", "timeArea":"unsupported", "malformed":"invalid", "empty":True, "boolean":["BIT"], "text":["STRING","WSTRING"], "select":["BYTE","USINT","SINT","WORD","INT","DWORD","DINT","TIME"], "optional":""}


def test_all_visual_plc_addresses_use_reusable_builder() -> None:
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    assert "if(address&&key!=='source_entity')return this.addressField" in source
    assert "this.initAddressBuilders(form,type)" in source
    assert 'name="${key}" value="${this.escape(value)}"' in source

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_address_builder_serialization_and_visibility_behaviour() -> None:
    """Structured address helpers distinguish missing values and expose fields."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r'''
const vm = require("vm");
const context = {HTMLElement: class {}, customElements: {define() {}}};
vm.createContext(context);
vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8') + `
const values = {
  visibility: [
    ADDRESS_FIELD_VISIBILITY("DB", "BIT"),
    ADDRESS_FIELD_VISIBILITY("I", "STRING"),
    ADDRESS_FIELD_VISIBILITY("Q", "WSTRING"),
    ADDRESS_FIELD_VISIBILITY("M", "INT"),
  ],
  emptyDb: SERIALIZE_S7_ADDRESS({area:"DB",dbNumber:"",dataType:"INT",offset:"0"}),
  emptyOffset: SERIALIZE_S7_ADDRESS({area:"M",dataType:"INT",offset:""}),
  emptyBit: SERIALIZE_S7_ADDRESS({area:"M",dataType:"BIT",offset:"0",bit:""}),
  emptyLength: SERIALIZE_S7_ADDRESS({area:"DB",dbNumber:"1",dataType:"STRING",offset:"0",length:""}),
  zeros: SERIALIZE_S7_ADDRESS({area:"DB",dbNumber:"0",dataType:"BIT",offset:"0",bit:"0"}),
};
globalThis.result = JSON.stringify(values);`, context);
process.stdout.write(context.result);
'''
    result = json.loads(subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)], check=True, capture_output=True, text=True
    ).stdout)
    assert result["visibility"] == [
        {"dbNumber": True, "bit": True, "length": False},
        {"dbNumber": False, "bit": False, "length": True},
        {"dbNumber": False, "bit": False, "length": True},
        {"dbNumber": False, "bit": False, "length": False},
    ]
    assert result["emptyDb"] == {"error": "incomplete"}
    assert result["emptyOffset"] == {"error": "incomplete"}
    assert result["emptyBit"] == {"error": "incomplete"}
    assert result["emptyLength"] == {"error": "incomplete"}
    assert result["zeros"] == "DB0,X0.0"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_required_address_builder_blocks_submission_and_gets_focus() -> None:
    """Builder validity is explicit because hidden inputs cannot constrain forms."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r'''
const vm = require("vm"); let Panel;
const context = {HTMLElement: class {}, customElements: {define: (_, cls) => Panel = cls}};
vm.createContext(context); vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
let focused = 0, scrolled = 0;
const hidden = {value: ""};
const field = {dataset: {required: "true", addressError: "incomplete"},
  querySelector: () => hidden, focus: () => focused++, scrollIntoView: () => scrolled++};
const form = {querySelectorAll: () => [field]};
const panel = new Panel();
process.stdout.write(JSON.stringify({valid: panel.validateAddressBuilders(form), focused, scrolled}));
'''
    value = json.loads(subprocess.run(
        ["node", "-e", script, str(PANEL_JAVASCRIPT)], check=True, capture_output=True, text=True
    ).stdout)
    assert value == {"valid": False, "focused": 1, "scrolled": 1}


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_entity_sync_builder_accepts_binary_and_numeric_addresses() -> None:
    """Entity sync keeps numeric types and supports existing binary addresses."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")
    script = r'''
const vm = require("vm");
let Panel;
const context = {
  HTMLElement: class {},
  customElements: {define: (_, cls) => Panel = cls},
};
vm.createContext(context);
vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'), context);
const panel = new Panel();
panel.escape = value => String(value ?? "");
panel.t = key => key;
const allowed = vm.runInContext(
  'ADDRESS_TYPES_FOR_FIELD("entity_sync", "address")', context
);
const addresses = ["DB1,X0.0", "I0.0", "Q1.3", "M7.1"];
const results = addresses.map(address => {
  const parsed = vm.runInContext(
    `PARSE_S7_ADDRESS(${JSON.stringify(address)})`, context
  );
  const html = panel.addressField("address", address, "Address", "", true, "entity_sync");
  const hidden = {value: address};
  const field = {
    dataset: {required: "true", addressError: ""},
    querySelector: () => hidden,
  };
  const form = {querySelectorAll: () => [field]};
  return {
    address,
    dataType: parsed.dataType,
    supported: !parsed.error && allowed.includes(parsed.dataType),
    guided: html.includes('data-address-mode="guided" class="active"'),
    validForSave: panel.validateAddressBuilders(form),
  };
});
process.stdout.write(JSON.stringify({allowed, results}));
'''
    value = json.loads(
        subprocess.run(
            ["node", "-e", script, str(PANEL_JAVASCRIPT)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    assert value["allowed"] == [
        "BIT",
        "BYTE",
        "USINT",
        "SINT",
        "WORD",
        "INT",
        "DWORD",
        "DINT",
        "REAL",
        "LREAL",
    ]
    assert not {"TIME", "STRING", "WSTRING"} & set(value["allowed"])
    assert value["results"] == [
        {
            "address": address,
            "dataType": "BIT",
            "supported": True,
            "guided": True,
            "validForSave": True,
        }
        for address in ["DB1,X0.0", "I0.0", "Q1.3", "M7.1"]
    ]

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_builder_profiles_preview_reverse_hidden_and_s7_fallback() -> None:
    """Every selected entry chooses its profile while S7 markup stays unchanged."""
    script = f'''
global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};
{PANEL_LOADER}
const profile=(family,start,last)=>({{family,areas:[{{name:"I",first:1,last,vm_offset:start,data_type:"X"}}]}});
const panel=new S7PlcConfigurationPanel();panel.escape=v=>String(v??"");panel.t=k=>k;
panel.entries=[
 {{entry_id:"s7",plc_family:"s7"}},
 {{entry_id:"a7",plc_family:"logo_0ba7",logo_profile:profile("logo_0ba7",923,24)}},
 {{entry_id:"a8",plc_family:"logo_0ba8",logo_profile:profile("logo_0ba8",1024,24)}},
 {{entry_id:"nine",plc_family:"logo_9",logo_profile:profile("logo_9",6024,64)}}];
const html=id=>{{panel.entryId=id;return panel.addressField("address",id==="nine"?"DB1,X6024.0":"DB1,X1024.0","Address","",true,"sensors");}};
const p9=panel.entries[3].logo_profile;
console.log(JSON.stringify({{
 s7:!html("s7").includes("data-logo-builder"),a7:html("a7").includes("data-logo-builder"),
 a8:html("a8").includes("data-logo-builder"),nine:html("nine").includes("data-logo-builder"),
 forward:LOGO_TO_S7(p9,"I1"),reverse:S7_TO_LOGO(p9,"DB1,X6024.0"),
 out:LOGO_TO_S7(p9,"I65"),reserved:S7_TO_LOGO(p9,"DB1,X6032.0"),
 markup:html("nine")
}}));'''
    value = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)
    assert value["s7"] and value["a7"] and value["a8"] and value["nine"]
    assert value["forward"]["canonical"] == "DB1,X6024.0"
    assert value["reverse"]["symbol"] == "I1"
    assert value["out"]["error"] == "address_out_of_range"
    assert value["reserved"] is None
    assert 'type="hidden" name="address" value="DB1,X6024.0"' in value["markup"]
    assert "address_builder.logo_address" in value["markup"]
    assert "address_builder.internal_address" in value["markup"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_plc_family_connection_group_translation_and_legacy_fallback() -> None:
    script = f'''
global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();panel.panelTranslations={{config_panel:{{connection_details:{{values:{{s7:"SIMATIC S7",logo_9:"LOGO! 9"}}}}}}}};
const simplify=value=>connectionDetailGroups(value).map(g=>[g.key,g.fields.map(f=>f.key)]);
console.log(JSON.stringify({{groups:simplify({{plc_family:"logo_9",pys7_version:"3.1.1",connection_type:"rack_slot",rack:0,slot:1}}),translated:panel.connectionValue("logo_9"),legacy:panel.connectionValue("s7")}}));'''
    value = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)
    connection = dict(value["groups"])["connection"]
    assert connection == ["plc_family", "pys7_version", "connection_type", "rack", "slot"]
    assert not any(key == "other" for key, _fields in value["groups"])
    assert value["translated"] == "LOGO! 9"
    assert value["legacy"] == "SIMATIC S7"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_vm_helpers_and_builder_datatype_filtering() -> None:
    """VM helpers and guided reconstruction stay aligned."""
    script = f"""
global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};
{PANEL_LOADER}
const vmAreas=[{{name:"V",first:0,last:850,data_type:"X",width:1,bit_min:0,bit_max:7}},{{name:"VB",first:0,last:850,data_type:"BYTE",width:1}},{{name:"VW",first:0,last:849,data_type:"WORD",width:2}},{{name:"VD",first:0,last:847,data_type:"DWORD",width:4}}];
const profile={{family:"logo_0ba8",vm_last_byte:850,areas:[],vm_areas:vmAreas}};
const panel=new S7PlcConfigurationPanel();panel.escape=v=>String(v??"");panel.t=k=>k;panel.entries=[{{entry_id:"logo",plc_family:"logo_0ba8",logo_profile:profile}}];panel.entryId="logo";
const html=value=>panel.addressField("address",value,"Address","",false,"entity_sync");
console.log(JSON.stringify({{forward:["V0.0","V850.7","VB850","VW849","VD847"].map(v=>LOGO_TO_S7(profile,v)),invalid:["V0","V0.8","VB0.0","VW850","VD848","VB-1"].map(v=>LOGO_TO_S7(profile,v).error),reverse:["DB1,X0.0","DB1,BYTE10","DB1,WORD20","DB1,DWORD30"].map(v=>S7_TO_LOGO(profile,v)?.symbol),candidates:["V0.0","V0.8","VW850","IB10","QW8","MD72","DB1,X0.0"].map(v=>LOGO_ADDRESS_CANDIDATE(profile,v)),byte:html("DB1,BYTE10"),word:html("DB1,WORD20"),dword:html("DB1,DWORD30"),bit:html("DB1,X10.3"),empty:html("")}}));"""
    value = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)
    assert [item["canonical"] for item in value["forward"]] == [
        "DB1,X0.0", "DB1,X850.7", "DB1,BYTE850", "DB1,WORD849", "DB1,DWORD847"
    ]
    assert all(value["invalid"])
    assert value["reverse"] == ["V0.0", "VB10", "VW20", "VD30"]
    assert value["candidates"] == [True, True, True, False, False, False, False]
    for name, expected in (("byte", "VB"), ("word", "VW"), ("dword", "VD"), ("bit", "V")):
        assert f'<option value="{expected}" selected>' in value[name]
        assert "address_builder.vm_offset" in value[name]
    assert "data-logo-bit hidden" not in value["bit"]
    assert "data-logo-bit hidden" in value["byte"]
    assert 'type="hidden" name="address" value=""' in value["empty"]

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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_text_address_fields_are_manual_only_and_preserve_values():
    script = f'''global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const profile={{family:"logo_0ba8",areas:[{{name:"I",first:1,last:24,vm_offset:1024,data_type:"X"}}],vm_areas:[]}};
const panel=new S7PlcConfigurationPanel();panel.escape=v=>String(v??"");panel.t=k=>k;panel.entries=[{{entry_id:"logo",plc_family:"logo_0ba8",logo_profile:profile}}];panel.entryId="logo";
console.log(JSON.stringify(["","DB1,S0.20","DB1,WS0.20"].map(value=>panel.addressField("address",value,"Address","",true,"texts"))));'''
    values = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)
    for value, markup in zip(("", "DB1,S0.20", "DB1,WS0.20"), values, strict=True):
        assert 'data-address-mode="guided" disabled' in markup
        assert 'data-address-mode="manual" class="active"' in markup
        assert 'class="address-guided" hidden' in markup
        assert f'value="{value}"' in markup


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_manual_to_guided_keeps_valid_nonconvertible_address():
    script = f'''global.HTMLElement=class {{}};global.Event=class {{constructor(type){{this.type=type}}}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const profile={{family:"logo_0ba8",areas:[],vm_areas:[]}};const panel=new S7PlcConfigurationPanel();panel.t=k=>k;panel.entries=[{{entry_id:"logo",logo_profile:profile}}];panel.entryId="logo";
const results=["DB1,REAL0","DB1,TIME0","IB10"].map(value=>{{const hidden={{value}},manual={{value,addEventListener(){{}},dispatchEvent(){{}}}},guided={{hidden:true}},manualBox={{hidden:false}},area={{value:"",addEventListener(){{}}}},number={{value:"1",addEventListener(){{}}}},bit={{value:"0",addEventListener(){{}}}},numberText={{textContent:""}},bitBox={{hidden:true}},logoPreview={{textContent:""}},internalPreview={{textContent:""}},error={{textContent:"",hidden:true}},buttons=["guided","manual"].map(mode=>({{dataset:{{addressMode:mode}},classList:{{toggle(){{}}}}}}));const map=new Map([["input[type=\\"hidden\\"]",hidden],["[data-address-manual]",manual],[".address-guided",guided],[".address-manual",manualBox],["[data-logo-area]",area],["[data-logo-number]",number],["[data-logo-number-text]",numberText],["[data-logo-bit]",bitBox],["[data-logo-bit-input]",bit],["[data-logo-preview]",logoPreview],["[data-internal-preview]",internalPreview],[".address-error",error]]);const field={{dataset:{{required:"false",addressError:""}},querySelector:s=>map.get(s),querySelectorAll:s=>s==="[data-address-mode]"?buttons:[]}};panel.initLogoAddressBuilders({{querySelectorAll:s=>s==="[data-logo-builder]"?[field]:[]}});buttons[0].onclick();return {{value:hidden.value,error:error.textContent,addressError:field.dataset.addressError,guidedHidden:guided.hidden}};}});console.log(JSON.stringify(results));'''
    results = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)
    assert results == [
        {"value": value, "error": "", "addressError": "", "guidedHidden": True}
        for value in ("DB1,REAL0", "DB1,TIME0", "IB10")
    ]

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_manual_input_preserves_progress_and_resets_only_when_requested() -> None:
    """Manual LOGO input never erases incomplete or invalid text while typing."""
    script = f'''global.HTMLElement=class {{}};global.Event=class {{constructor(type){{this.type=type}}}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const profile={{family:"logo_0ba8",areas:[],vm_areas:[{{name:"V",first:0,last:850,data_type:"X",width:1,bit_min:0,bit_max:7}},{{name:"VW",first:0,last:849,data_type:"WORD",width:2}}]}};
const panel=new S7PlcConfigurationPanel();panel.t=k=>k;panel.entries=[{{entry_id:"logo",logo_profile:profile}}];panel.entryId="logo";
const listeners={{}},element=(value="")=>({{value,disabled:false,hidden:false,textContent:"",min:"",max:"",addEventListener(type,fn){{listeners[this.id+type]=fn;}},dispatchEvent(event){{listeners[this.id+event.type]?.();}}}});
const hidden=element(),manual=element(),guided=element(),manualBox=element(),area=element(),number=element(),numberText=element(),bitBox=element(),bit=element(),logo=element(),internal=element(),error=element();manual.id="manual";area.id="area";number.id="number";bit.id="bit";
let active="";const buttons=["guided","manual"].map(mode=>({{dataset:{{addressMode:mode}},classList:{{toggle(_name,on){{if(on)active=mode;}}}}}}));
const map=new Map([["input[type=\\"hidden\\"]",hidden],["[data-address-manual]",manual],[".address-guided",guided],[".address-manual",manualBox],["[data-logo-area]",area],["[data-logo-number]",number],["[data-logo-number-text]",numberText],["[data-logo-bit]",bitBox],["[data-logo-bit-input]",bit],["[data-logo-preview]",logo],["[data-internal-preview]",internal],[".address-error",error]]);
const field={{dataset:{{required:"false",logoGuided:"true",addressError:""}},querySelector:s=>map.get(s),querySelectorAll:s=>s==="[data-address-mode]"?buttons:[]}};
panel.initLogoAddressBuilders({{querySelectorAll:s=>s==="[data-logo-builder]"?[field]:[]}});buttons[1].onclick();
const snapshot=()=>({{manual:manual.value,hidden:hidden.value,logo:logo.textContent,internal:internal.textContent,error:field.dataset.addressError,mode:active}});
const type=value=>{{manual.value=value;manual.dispatchEvent(new Event("input"));return snapshot();}};
const vm=["V","VW","VW2"].map(type),real=["D","DB","DB1,","DB1,R","DB1,REAL0"].map(type),out=[type("VW9999"),type("VW99"),type("VW2")];
type("DB1,REAL0");buttons[0].onclick();const nonconvertible=snapshot();
area.value="";area.dispatchEvent(new Event("change"));const reset=snapshot();
console.log(JSON.stringify({{vm,real,out,nonconvertible,reset}}));'''
    result = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)

    for state, typed in zip(result["vm"], ("V", "VW", "VW2"), strict=True):
        assert state["manual"] == typed
        assert state["mode"] == "manual"
    for state in result["vm"][:-1]:
        assert state["hidden"] == ""
        assert state["logo"] == ""
        assert state["internal"] == ""
        assert state["error"]
    assert result["vm"][-1] == {
        "manual": "VW2", "hidden": "DB1,WORD2", "logo": "VW2",
        "internal": "DB1,WORD2", "error": "", "mode": "manual",
    }
    for state, typed in zip(
        result["real"], ("D", "DB", "DB1,", "DB1,R", "DB1,REAL0"), strict=True
    ):
        assert state["manual"] == typed
        assert state["mode"] == "manual"
    for state in result["real"][:-1]:
        assert state["hidden"] == ""
        assert state["logo"] == ""
        assert state["internal"] == ""
        assert state["error"]
    assert result["real"][-1] == {
        "manual": "DB1,REAL0", "hidden": "DB1,REAL0", "logo": "",
        "internal": "DB1,REAL0", "error": "", "mode": "manual",
    }
    assert result["out"][0] == {
        "manual": "VW9999", "hidden": "", "logo": "VW9999",
        "internal": "", "error": "address_out_of_range", "mode": "manual",
    }
    assert result["out"][-1]["hidden"] == "DB1,WORD2"
    assert result["out"][-1]["error"] == ""
    assert result["nonconvertible"] == {
        "manual": "DB1,REAL0", "hidden": "DB1,REAL0", "logo": "",
        "internal": "DB1,REAL0", "error": "", "mode": "manual",
    }
    assert result["reset"] == {
        "manual": "", "hidden": "", "logo": "", "internal": "",
        "error": "", "mode": "manual",
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_logo_builder_empty_area_dom_events_and_validation() -> None:
    """Empty LOGO fields stay empty and only generate after an area event."""
    script = f'''global.HTMLElement=class {{}};global.Event=class {{constructor(type){{this.type=type}}}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const profile={{family:"logo_0ba8",areas:[{{name:"AI",first:1,last:8,vm_offset:1032,data_type:"INT"}}],vm_areas:[{{name:"VW",first:0,last:849,data_type:"WORD",width:2}}]}};
const panel=new S7PlcConfigurationPanel();panel.t=k=>k;panel.escape=v=>String(v??"");panel.entries=[{{entry_id:"logo",plc_family:"logo_0ba8",logo_profile:profile}}];panel.entryId="logo";
function builder(required=false,initial=""){{
 const listeners={{}},element=(value="")=>({{value,disabled:false,hidden:false,textContent:"",min:"",max:"",addEventListener(type,fn){{listeners[this.id+type]=fn;}},dispatchEvent(event){{listeners[this.id+event.type]?.();}},classList:{{toggle(){{}}}}}});
 const hidden=element(initial),manual=element(initial),guided=element(),manualBox=element(),area=element(),number=element(),numberText=element(),bitBox=element(),bit=element(),logo=element(),internal=element(),error=element();
 area.id="area";number.id="number";bit.id="bit";manual.id="manual";
 const buttons=["guided","manual"].map(mode=>({{dataset:{{addressMode:mode}},classList:{{toggle(){{}}}}}}));
 const map=new Map([["input[type=\\"hidden\\"]",hidden],["[data-address-manual]",manual],[".address-guided",guided],[".address-manual",manualBox],["[data-logo-area]",area],["[data-logo-number]",number],["[data-logo-number-text]",numberText],["[data-logo-bit]",bitBox],["[data-logo-bit-input]",bit],["[data-logo-preview]",logo],["[data-internal-preview]",internal],[".address-error",error]]);
 const field={{dataset:{{required:String(required),logoGuided:"true",addressError:""}},querySelector:s=>map.get(s),querySelectorAll:s=>s==="[data-address-mode]"?buttons:[],focus(){{}},scrollIntoView(){{}}}};
 const form={{querySelectorAll:s=>s==="[data-logo-builder]"?[field]:s==="[data-address-builder]"?[field]:[]}};
 panel.initLogoAddressBuilders(form);
 const snapshot=()=>({{area:area.value,number:number.value,numberDisabled:number.disabled,bitDisabled:bit.disabled,hidden:hidden.value,logo:logo.textContent,internal:internal.textContent,error:field.dataset.addressError,valid:panel.validateAddressBuilders(form)}});
 const initialState=snapshot();area.value="AI";area.dispatchEvent(new Event("change"));const selected=snapshot();area.value="";area.dispatchEvent(new Event("change"));return {{initial:initialState,selected,cleared:snapshot()}};
}}
const existing=builder(false,"DB1,WORD2").initial;
const markup=panel.logoAddressField("command_address","","Command","",false,"numbers",profile);
console.log(JSON.stringify({{optional:builder(),required:builder(true),existing,markup}}));'''
    result = json.loads(subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    ).stdout)

    empty = {"area": "", "number": "", "numberDisabled": True,
             "bitDisabled": True, "hidden": "", "logo": "", "internal": ""}
    assert result["optional"]["initial"] == {**empty, "error": "", "valid": True}
    assert result["optional"]["selected"] == {
        "area": "AI", "number": 1, "numberDisabled": False,
        "bitDisabled": True, "hidden": "DB1,INT1032", "logo": "AI1",
        "internal": "DB1,INT1032", "error": "", "valid": True,
    }
    assert result["optional"]["cleared"] == {**empty, "error": "", "valid": True}
    assert result["required"]["initial"] == {
        **empty, "error": "incomplete", "valid": False,
    }
    assert result["existing"]["area"] == "VW"
    assert result["existing"]["number"] == 2
    assert result["existing"]["logo"] == "VW2"
    assert result["existing"]["hidden"] == "DB1,WORD2"
    assert '<option value="" selected>address_builder.not_configured</option>' in result["markup"]
    assert "address_builder.command_address_fallback" not in result["markup"]
    assert "command-address-fallback" not in result["markup"]


def test_logo_yaml_save_does_not_invent_optional_command_address() -> None:
    saved = _configuration_from_yaml(
        "numbers:\n  - address: DB1,WORD2\n    min_value: 0\n    max_value: 7000\n",
        {},
        plc_family="logo_0ba8",
    )
    assert saved["numbers"][0]["address"] == "DB1,WORD2"
    assert "command_address" not in saved["numbers"][0]

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_address_modes_persist_per_plc_entity_and_field() -> None:
    """Saved UI choices are isolated and invalid/absent preferences fall back safely."""
    script = f'''
const store = new Map();
global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};
global.localStorage={{getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value)}};
{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();panel.escape=value=>String(value??"");panel.t=key=>key;
panel.entries=[{{entry_id:"plc-a",plc_family:"s7"}},{{entry_id:"plc-b",plc_family:"s7"}}];
const render=(entryId,identity,field,value)=>{{panel.entryId=entryId;panel._addressPreferenceContext={{entryId,type:"switches",identity}};return panel.addressField(field,value,field,"",false,"switches");}};
const mode=html=>html.includes('data-address-mode="guided" class="active"')?"guided":"manual";
const state={{automatic:mode(render("plc-a","entity-a","state_address","DB1,X0.0")),unparseable:mode(render("plc-a","entity-a","state_address","not-an-address"))}};
panel._addressPreferenceContext={{entryId:"plc-a",type:"switches",identity:"entity-a"}};
panel.writeAddressMode(panel.addressPreferenceKey("state_address"),"manual");
panel.writeAddressMode(panel.addressPreferenceKey("command_address"),"guided");
state.savedManual=mode(render("plc-a","entity-a","state_address","DB1,X0.0"));
state.otherField=mode(render("plc-a","entity-a","command_address","DB1,X0.1"));
state.otherEntity=mode(render("plc-a","entity-b","state_address","DB1,X0.0"));
state.otherPlc=mode(render("plc-b","entity-a","state_address","DB1,X0.0"));
store.set(ADDRESS_MODE_STORAGE_KEY,'{{"bad":"sideways"');
state.invalidStorage=mode(render("plc-a","entity-a","state_address","DB1,X0.0"));
store.set(ADDRESS_MODE_STORAGE_KEY,JSON.stringify({{[panel.addressPreferenceKey("state_address")]:"guided"}}));
state.invalidNeverGuided=mode(render("plc-a","entity-a","state_address","not-an-address"));
console.log(JSON.stringify(state));'''
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout) == {
        "automatic": "guided",
        "unparseable": "manual",
        "savedManual": "manual",
        "otherField": "guided",
        "otherEntity": "guided",
        "otherPlc": "guided",
        "invalidStorage": "guided",
        "invalidNeverGuided": "manual",
    }


def test_address_mode_toggle_preserves_address_value() -> None:
    """Mode event handlers only copy the current value; they never clear or convert it."""
    source = PANEL_JAVASCRIPT.read_text(encoding="utf-8")

    assert "manual.value=hidden.value;setMode('manual');this.writeAddressMode" in source
    assert "hidden.value=manual.value;writeParts(parsed);setMode('guided')" in source
    assert "this.writeAddressMode(field.dataset.addressPreferenceKey,'manual')" in source
    assert "this.writeAddressMode(field.dataset.addressPreferenceKey,'guided')" in source

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_duplicate_action_is_accessible_for_every_existing_entity_and_clicks_editor() -> (
    None
):
    """Both layouts use the same cards, whose duplicate action opens create mode."""
    script = f"""global.HTMLElement=class {{}};global.customElements={{get(){{}},define(){{}}}};{PANEL_LOADER}
const panel=new S7PlcConfigurationPanel();
panel.t=key=>({{"actions.duplicate":"Duplicate entity","common.entity":"Entity"}}[key]||key);
panel.bt=key=>key;panel.escape=value=>String(value??"");panel.icon=()=>"help";panel.stateText=()=>"";panel.selectedIndices=new Set();panel._viewMode="tabs";
panel.entries=[{{entry_id:"entry",entities:Object.fromEntries(TYPES.map(type=>[type,[{{uid:`uid-${{type}}`,name:type,address:"DB1,X0.0"}}]]))}}];panel.entryId="entry";
const markup=Object.fromEntries(TYPES.map(type=>[type,panel.entityCards(panel.entries[0],type)]));
let call=null;panel.openEditor=(...args)=>call=args;
let stopped=false;const button={{dataset:{{duplicate:"0",entityType:"lights"}}}};
button.onclick=event=>{{event.stopPropagation();panel.duplicateEntity(Number(button.dataset.duplicate),button.dataset.entityType);}};
button.onclick({{stopPropagation:()=>stopped=true}});
console.log(JSON.stringify({{markup,call,stopped,empty:panel.entityCards({{entities:{{sensors:[]}}}},"sensors")}}));"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    for markup in result["markup"].values():
        assert 'type="button" data-duplicate="0"' in markup
        assert 'icon="mdi:content-copy"' in markup
        assert 'title="Duplicate entity"' in markup
        assert 'aria-label="Duplicate entity"' in markup
        assert "<ha-tooltip>Duplicate entity</ha-tooltip>" in markup
        assert (
            markup.index("data-edit=")
            < markup.index("data-duplicate=")
            < markup.index("data-delete=")
        )
    assert "data-duplicate" not in result["empty"]
    assert result["stopped"] is True
    assert result["call"][:2] == [None, "lights"]
    assert result["call"][2]["uid"] == "uid-lights"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_duplicate_editor_deep_clones_sanitizes_and_infers_virtual_modes() -> None:
    """A duplicate is an independent create draft with clean YAML and inferred UI state."""
    script = r"""
const vm=require("vm");let Panel;let dialog;let captured;
const form={dataset:{},elements:{},querySelector:()=>null,querySelectorAll:()=>[]};
const context={structuredClone,HTMLElement:class{},customElements:{get(){},define:(_,cls)=>Panel=cls},document:{createElement:()=>dialog={style:{setProperty(){}},setAttribute(){},querySelector:s=>s==='form'?form:{},querySelectorAll:()=>[],addEventListener(){},remove(){}},body:{appendChild(){}}}};
vm.createContext(context);vm.runInContext(require('fs').readFileSync(process.argv[1],'utf8'),context);
const panel=new Panel();panel.entryId='entry';panel.entries=[{entry_id:'entry',entities:{selects:[]}}];panel.t=k=>k;panel.escape=v=>String(v??'');panel.icon=()=>"help";panel.initAddressBuilders=()=>{};panel.editorSections=(type,item)=>(captured={type,item},'');
const source={uid:'original-uid',name:'Copy me',address:'DB1,BYTE0',command_address:'DB1,BYTE2',options_map:{nested:[{value:1,label:'One'}]},area:'kitchen',availability_mode:'bit',availability_address:'DB1,X4.0'};
panel.openEditor(null,'selects',source);
captured.item.options_map.nested[0].label='Changed only in draft';
const light=panel.inferred({state_address:'DB1,X0.0',brightness_state_address:'DB1,BYTE2'},'lights');
const cover=panel.inferred({position_state_address:'DB1,BYTE4',stop_command_address:'DB1,X8.0'},'covers');
const climate=panel.inferred({current_temperature_address:'DB1,REAL0',target_temperature_address:'DB1,REAL4',preset_mode_address:'DB1,BYTE8',on_off_address:'DB1,X9.0',hvac_status_address:'DB1,BYTE10'},'climates');
console.log(JSON.stringify({draft:captured.item,source,header:dialog.headerTitle,html:dialog.innerHTML,light,cover,climate}));
"""
    result = json.loads(
        subprocess.run(
            ["node", "-e", script, str(PANEL_JAVASCRIPT)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    assert "uid" not in result["draft"]
    assert "original-uid" not in result["html"]
    assert result["header"] == "editor.duplicate_entity"
    assert result["source"]["options_map"]["nested"][0]["label"] == "One"
    assert (
        result["draft"]["options_map"]["nested"][0]["label"] == "Changed only in draft"
    )
    assert result["draft"]["area"] == "kitchen"
    assert result["draft"]["availability_address"] == "DB1,X4.0"
    assert result["light"]["light_mode"] == "dimmable"
    assert result["cover"]["cover_control_mode"] == "position"
    assert result["cover"]["cover_stop_enabled"] == "enabled"
    assert result["climate"]["climate_mode_control"] == "coded_on_off"
    assert result["climate"]["climate_action_feedback"] == "plc"


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
