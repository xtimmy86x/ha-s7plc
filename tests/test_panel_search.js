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
  document: { createElement: () => ({ set textContent(value) { this.innerHTML = String(value ?? ""); } }) },
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
    value_conversion: { enum_map: { 0: "Stopped", 1: "Running" } },
    _cache: "secret", uid: "technical-only",
  };
  const text = ENTITY_SEARCH_TEXT(entity, 42);
  for (const value of ["supply pressure", "db1.dbd4", "db2.dbw8", "i0.1", "q0.2", "plant room", "pressure", "measurement", "bar", "12.5", "stopped", "running", "42"])
    assert.ok(text.includes(value), value);
  assert.ok(!text.includes("secret"));
  assert.ok(!text.includes("technical-only"));
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
  assert.match(source, /\.page\{overflow-x:hidden\}/);
  assert.match(source, /SEARCH_DEBOUNCE_MS = 150/);
});
