const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const panelPath = path.join(__dirname, "..", "custom_components", "s7plc", "www", "s7plc-panel.js");
const source = fs.readFileSync(panelPath, "utf8");
const context = {
  console,
  HTMLElement: class {},
  customElements: { get: () => undefined, define: () => undefined },
  document: { activeElement: null, createElement: () => ({ set textContent(value) { this.innerHTML = String(value ?? ""); } }) },
};
vm.createContext(context);
vm.runInContext(`${source}\nglobalThis.__search = { ENTITY_SEARCH_TEXT, FILTER_ENTITY_ITEMS, Panel: S7PlcConfigurationPanel };`, context);
const { ENTITY_SEARCH_TEXT, FILTER_ENTITY_ITEMS, Panel } = context.__search;

test("normalizes case and surrounding whitespace and safely handles null values", () => {
  const entities = [{ name: "Boiler Temperature", area: null }, undefined];
  assert.deepEqual([...FILTER_ENTITY_ITEMS(entities, "  TEMPERATURE  ")].map(item => item.index), [0]);
  assert.doesNotThrow(() => ENTITY_SEARCH_TEXT(undefined, undefined));
});

test("indexes names, all addresses, area, classes, units, numeric values, and readable mappings", () => {
  const entity = {
    name: "Supply pressure", address: "DB1.DBD4", command_address: "DB2.DBW8",
    extra_addresses: ["I0.1", "Q0.2"], area: "Plant room", device_class: "pressure",
    state_class: "measurement", unit_of_measurement: "bar", scale: 12.5,
    value_conversions: {
      value: {
        type: "expression", factor: 2.5, read_expression: "x * 2",
        mappings: [{ value: 0, label: "Stopped" }, { value: 1, label: "Running" }],
      },
    },
    _cache: "secret", uid: "technical-only",
  };
  const text = ENTITY_SEARCH_TEXT(entity, 42);
  for (const value of ["supply pressure", "db1.dbd4", "db2.dbw8", "i0.1", "q0.2", "plant room", "pressure", "measurement", "bar", "12.5", "expression", "2.5", "x * 2", "stopped", "running", "42"])
    assert.ok(text.includes(value), value);
  assert.ok(!text.includes("secret"));
  assert.ok(!text.includes("technical-only"));
});

const entityTypes = ["sensors","binary_sensors","switches","covers","lights","buttons","numbers","selects","texts","climates","entity_sync"];
const searchPanel = ({ query = "active", viewMode = "tabs" } = {}) => {
  const panel = new Panel();
  const entities = Object.fromEntries(entityTypes.map(type => [type, []]));
  const entity_ids = Object.fromEntries(entityTypes.map(type => [type, []]));
  entities.sensors = [{ name: "Pump" }, { name: "Valve" }];
  entity_ids.sensors = ["sensor.pump", "sensor.valve"];
  panel.entries = [
    { entry_id: "selected", entities, entity_ids },
    { entry_id: "other", entities: { ...entities, sensors: [{ name: "Other" }] }, entity_ids: { ...entity_ids, sensors: ["sensor.other"] } },
  ];
  Object.assign(panel, {
    entryId: "selected", type: "sensors", _viewMode: viewMode, searchQuery: query, _loaded: true,
    _hass: { locale: { language: "en" }, states: { "sensor.pump": { state: "active" }, "sensor.valve": { state: "idle" }, "sensor.other": { state: "idle" } } },
    renderCalls: 0, stateUpdates: 0, dialogUpdates: 0,
    render() { this.renderCalls++; }, updateStates() { this.stateUpdates++; }, updateConnectionDialog() { this.dialogUpdates++; }, syncMenuButtons() {},
  });
  panel.querySelector = () => null;
  return panel;
};

test("state updates use the lightweight path when search results stay the same", () => {
  const panel = searchPanel();
  panel.hass = { locale: { language: "en" }, states: { ...panel._hass.states, "sensor.pump": { state: "active now" } } };
  assert.equal(panel.renderCalls, 0);
  assert.equal(panel.stateUpdates, 1);
  assert.equal(panel.dialogUpdates, 1);
});

test("state updates render when an entity enters or leaves active search results", () => {
  const entering = searchPanel();
  entering._hass.states["sensor.pump"] = { state: "idle" };
  entering.hass = { locale: { language: "en" }, states: { ...entering._hass.states, "sensor.valve": { state: "active" } } };
  assert.equal(entering.renderCalls, 1);

  const leaving = searchPanel();
  leaving.hass = { locale: { language: "en" }, states: { ...leaving._hass.states, "sensor.pump": { state: "idle" } } };
  assert.equal(leaving.renderCalls, 1);
});

test("inactive search skips result comparison and unrelated entries do not render", () => {
  const inactive = searchPanel({ query: "" });
  inactive.searchResultsFingerprint = () => { throw Error("must not compare"); };
  inactive.hass = { locale: { language: "en" }, states: {} };
  assert.equal(inactive.renderCalls, 0);
  assert.equal(inactive.stateUpdates, 1);

  const unrelated = searchPanel();
  unrelated.hass = { locale: { language: "en" }, states: { ...unrelated._hass.states, "sensor.other": { state: "active" } } };
  assert.equal(unrelated.renderCalls, 0);
  assert.equal(unrelated.stateUpdates, 1);
});

test("sections fingerprints retain type and original index across categories", () => {
  const panel = searchPanel({ viewMode: "sections" });
  panel.entries[0].entities.switches = [{ name: "First" }, { name: "Second" }];
  panel.entries[0].entity_ids.switches = ["switch.first", "switch.second"];
  panel._hass.states["switch.second"] = { state: "active" };
  assert.equal(panel.searchResultsFingerprint(), '[["sensors",0],["switches",1]]');
});

test("search-triggered render restores focus and selection", () => {
  const panel = searchPanel();
  const oldInput = { selectionStart: 1, selectionEnd: 4 };
  const newInput = { focused: false, selection: null, focus() { this.focused = true; }, setSelectionRange(start, end) { this.selection = [start, end]; } };
  context.document.activeElement = oldInput;
  panel.querySelector = () => panel.renderCalls ? newInput : oldInput;
  panel.hass = { locale: { language: "en" }, states: { ...panel._hass.states, "sensor.pump": { state: "idle" } } };
  assert.equal(panel.renderCalls, 1);
  assert.equal(newInput.focused, true);
  assert.deepEqual(newInput.selection, [1, 4]);
  assert.equal(panel.searchQuery, "active");
  context.document.activeElement = null;
});

test("filtered results retain original indices for edit, duplicate, and delete actions", () => {
  const matches = FILTER_ENTITY_ITEMS([{ name: "first" }, { name: "target" }, { name: "third" }], "target");
  assert.equal(matches[0].index, 1);
  const panel = new Panel();
  Object.assign(panel, { searchQuery: "target", selectedIndices: new Set(), _viewMode: "tabs", t: key => key, bt: key => key,
    escape: value => String(value ?? ""), icon: () => "gauge", stateText: () => "", chips: () => "" });
  const entry = { entities: { sensors: [{ name: "first" }, { name: "target" }, { name: "third" }] }, entity_ids: {} };
  const html = panel.entityCards(entry, "sensors", matches);
  for (const action of ["edit", "duplicate", "delete"])
    assert.match(html, new RegExp(`data-entity-action="${action}" data-entity-index="1"`));
});

test("category filtering is local and sections filtering is global and hides empty sections", () => {
  const panel = new Panel();
  const entities = Object.fromEntries(context.TYPES?.map(type => [type, []]) ?? []);
  // TYPES is lexical in the panel script, so build every known section explicitly.
  for (const type of ["sensors","binary_sensors","switches","covers","lights","buttons","numbers","selects","texts","climates","entity_sync"]) entities[type] = [];
  entities.sensors = [{ name: "Kitchen temperature" }];
  entities.switches = [{ name: "Garage target" }];
  const entry = { entities, entity_ids: {} };
  Object.assign(panel, { searchQuery: "target", expandedSections: new Set(), selectedIndices: new Set(), _viewMode: "sections",
    t: key => key, bt: key => key, escape: value => String(value ?? ""), icon: () => "gauge", stateText: () => "", chips: () => "" });
  assert.equal(panel.matchingItems(entry, "sensors").length, 0);
  assert.equal(panel.matchingItems(entry, "switches")[0].index, 0);
  const html = panel._renderSectionsView(entry);
  assert.ok(!html.includes('data-section-type="sensors"'));
  assert.ok(html.includes('data-section-type="switches"'));
  assert.equal(panel.searchResultCount, 1);
  assert.equal(panel.expandedSections.size, 0, "temporary search expansion must not mutate stored state");
});

test("all translations and mobile overflow safeguards are present", () => {
  for (const language of ["en", "it", "de", "pl", "cs"]) {
    const translations = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "custom_components", "s7plc", "translations", `${language}.json`)));
    for (const key of ["label", "placeholder", "one_result", "many_results", "no_results", "clear"])
      assert.equal(typeof translations.config_panel.search[key], "string", `${language}.${key}`);
  }
  assert.match(source, /@media\(max-width:650px\).*?\.entity-search\{order:3;flex:1 0 100%;width:100%;max-width:none;min-width:0\}/s);
  assert.match(source, /@media\(max-width:650px\).*?\.page\{overflow-x:hidden/s);
  assert.match(source, /SEARCH_DEBOUNCE_MS = 150/);
});
