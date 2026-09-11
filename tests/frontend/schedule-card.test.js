// @vitest-environment jsdom
import fs from "node:fs";
import {afterEach, beforeAll, expect, test, vi} from "vitest";

const source = fs.readFileSync("custom_components/s7plc/www/s7plc-schedule-card.js", "utf8");
let Card;
beforeAll(() => {window.eval(source); Card = customElements.get("s7plc-schedule-card");});
afterEach(() => {document.body.replaceChildren(); vi.useRealTimers(); vi.restoreAllMocks();});

function setup({count = 1, delayed = false, reject = false} = {}) {
  const card = new Card();
  const rows = Array.from({length: count}, (_, i) => ({name: `Slot ${i + 1}`, on_entity: `number.on_${i}`, off_entity: `number.off_${i}`}));
  const states = {};
  for (const row of rows) for (const id of [row.on_entity, row.off_entity]) {
    states[id] = {state: "1024", attributes: {min: 0, max: 65535, step: 1, s7_raw_word: true}};
  }
  const hass = {language: "en", states, callService: vi.fn(async (domain, service, data) => {
    if (reject && data.entity_id.includes("off")) throw new Error("PLC offline");
    if (!delayed) update(data.entity_id, data.value);
  })};
  function update(id, value) {
    hass.states = {...hass.states, [id]: {...hass.states[id], state: String(value)}};
    card.hass = {...hass};
  }
  card.setConfig({rows, confirmation_timeout: 2});
  card.hass = hass; document.body.append(card);
  return {card, hass, update};
}
const fields = card => [...card.shadowRoot.querySelectorAll("input")];
const edit = (input, value) => {input.focus(); input.value = value; input.dispatchEvent(new Event("input", {bubbles: true}));};
const clickSave = async card => {
  const button = card.shadowRoot.querySelector(".save"); button.focus(); button.click();
  await vi.waitFor(() => expect(card._saving).toBe(false));
};

test("all 65536 WORD values contain exactly 1440 valid times and round-trip", () => {
  let count = 0;
  for (let n = 0; n <= 65535; n++) {
    const time = Card.decodeWord(n);
    if (time) {count++; expect(Card.encodeTime(time.hours, time.minutes)).toBe(n);}
  }
  expect(count).toBe(1440);
  expect(Card.decodeWord("1024.0")).toEqual({hours: "04", minutes: "00"});
  expect(Card.encodeTime(23, 59)).toBe(9049);
  for (const raw of ["", " ", null, undefined, -1, 65536, "0x0400", "1024.5", "unknown", 0x0a00, 0x2400, 0x1260]) expect(Card.decodeWord(raw)).toBeNull();
  for (const [h, m] of [["", 0], [24, 0], [0, 60], [-1, 0], ["1e1", 0]]) expect(Card.encodeTime(h, m)).toBeNull();
});

test("standalone module registers card/editor once; stub works without a panel", () => {
  window.eval(source);
  expect(customElements.get("s7plc-schedule-card")).toBe(Card);
  expect(window.customCards.filter(c => c.type === "s7plc-schedule-card")).toHaveLength(1);
  expect(Card.getConfigElement().tagName.toLowerCase()).toBe("s7plc-schedule-card-editor");
  const card = new Card(); card.setConfig(Card.getStubConfig());
  expect(card.shadowRoot.textContent).toContain("Open the card editor");
});

test("12 pairs display 48 fields; localization and names are rendered safely", () => {
  const {card, hass} = setup({count: 12});
  expect(card.shadowRoot.querySelectorAll("tbody tr")).toHaveLength(12);
  expect(fields(card)).toHaveLength(48);
  expect(fields(card)[0].value).toBe("04");
  card.hass = {...hass, language: "it-IT"};
  expect(card.shadowRoot.querySelector("h2").textContent).toBe("Programmazione oraria");
  expect(card.shadowRoot.querySelector(".save").textContent).toBe("Salva modifiche");
  card.setConfig({title: "<img src=x>", rows: [{name: "<b>test</b>", on_entity: "number.on_0", off_entity: "number.off_0"}]});
  expect(card.shadowRoot.querySelector("h2").textContent).toBe("<img src=x>");
  expect(card.shadowRoot.querySelector("img")).toBeNull();
});

test("typing survives HA updates and only explicit Save writes the edited WORD", async () => {
  const {card, hass, update} = setup();
  const minute = fields(card)[1]; edit(minute, "30");
  update("number.off_0", 1280);
  expect(fields(card)[1]).toBe(minute);
  expect(card.shadowRoot.activeElement).toBe(minute);
  expect(minute.value).toBe("30");
  expect(hass.callService).not.toHaveBeenCalled();
  await clickSave(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith("number", "set_value", {entity_id: "number.on_0", value: 1072});
  expect(card._cells[0].draft).toBeNull();
});

test("first pointer entry selects both digits while later taps preserve the chosen caret", () => {
  const {card, hass} = setup();
  for (const input of fields(card).slice(0, 2)) {
    input.dispatchEvent(new Event("pointerdown")); input.focus();
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, 2]);
    // Simulate the browser placing its caret before dispatching click.
    input.setSelectionRange(2, 2); input.click();
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, 2]);
    input.dispatchEvent(new Event("pointerdown")); input.setSelectionRange(1, 1); input.click();
    expect([input.selectionStart, input.selectionEnd]).toEqual([1, 1]);
  }
  expect(hass.callService).not.toHaveBeenCalled();
});

test("keyboard focus selects digits; editing the last slot survives updates and still requires Save", async () => {
  const {card, hass, update} = setup({count: 12});
  const hours = fields(card)[44], minutes = fields(card)[45];
  const replace = (input, value) => {
    input.focus(); expect([input.selectionStart, input.selectionEnd]).toEqual([0, 2]);
    input.setRangeText(value, input.selectionStart, input.selectionEnd, "end");
    input.dispatchEvent(new Event("input", {bubbles: true}));
  };
  replace(hours, "23");
  update("number.on_0", 1280);
  expect(card.shadowRoot.activeElement).toBe(hours);
  expect([hours.selectionStart, hours.selectionEnd]).toEqual([2, 2]);
  expect(hours.value).toBe("23");
  replace(minutes, "59");
  expect(hass.callService).not.toHaveBeenCalled();
  const cancel = card.shadowRoot.querySelector(".reset"); cancel.focus(); cancel.click();
  expect([hours.value, minutes.value]).toEqual(["04", "00"]);
  replace(hours, "23"); replace(minutes, "59");
  await clickSave(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith("number", "set_value", {entity_id: "number.on_11", value: 9049});
  expect(card._cells[22].draft).toBeNull();
});

test("remote change between focusing hours and editing minutes prevents stale overwrite", async () => {
  const {card, hass, update} = setup();
  fields(card)[0].focus(); update("number.on_0", 1280); edit(fields(card)[1], "45");
  expect(card.shadowRoot.querySelector(".save").disabled).toBe(true);
  expect(card.shadowRoot.textContent).toContain("Value changed in HA");
  const cancel = card.shadowRoot.querySelector(".reset"); cancel.focus(); cancel.click();
  await Promise.resolve();
  expect(fields(card)[0].value).toBe("05");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("invalid time, numeric bounds, offline and converted S7 entities prevent writes", async () => {
  const {card, hass, update} = setup();
  edit(fields(card)[0], "24"); expect(card.shadowRoot.querySelector(".save").disabled).toBe(true);
  edit(fields(card)[0], "05"); hass.states["number.on_0"].attributes.max = 1100; card.hass = {...hass};
  expect(card.shadowRoot.textContent).toContain("exceeds maximum");
  update("number.on_0", "unavailable"); expect(fields(card)[0].disabled).toBe(true);
  hass.states["number.on_0"].attributes = {min: 0, max: 65535, step: 1, s7_raw_word: false};
  update("number.on_0", 1024); expect(fields(card)[0].disabled).toBe(true);
  await card._saveChanges(); expect(hass.callService).not.toHaveBeenCalled();
});

test("corrupt BCD can be repaired; midnight remains a valid value", async () => {
  const {card, hass, update} = setup(); update("number.on_0", 0x0a00);
  expect(card.shadowRoot.textContent).toContain("Invalid BCD");
  expect(fields(card)[0].value).toBe("");
  edit(fields(card)[0], "00"); edit(fields(card)[1], "00"); await clickSave(card);
  expect(hass.callService).toHaveBeenCalledWith("number", "set_value", {entity_id: "number.on_0", value: 0});
});

test("partial failure keeps failed draft; retries exclude confirmed writes", async () => {
  const {card, hass} = setup({reject: true}); edit(fields(card)[1], "15"); edit(fields(card)[3], "45");
  await clickSave(card); expect(card.shadowRoot.textContent).toContain("PLC offline");
  expect(card._cells[0].draft).toBeNull(); expect(fields(card)[3].value).toBe("45");
  await clickSave(card);
  expect(hass.callService.mock.calls.filter(([, , data]) => data.entity_id === "number.on_0")).toHaveLength(1);
});

test("pending write survives old states and confirms on matching HA value", async () => {
  const {card, update} = setup({delayed: true}); edit(fields(card)[1], "30"); await clickSave(card);
  update("number.on_0", 1024); expect(fields(card)[1].value).toBe("30"); expect(fields(card)[1].disabled).toBe(true);
  update("number.on_0", 1072); expect(fields(card)[1].disabled).toBe(false); expect(card._cells[0].draft).toBeNull();
});

test("confirmation timeout preserves draft and timers stop on disconnect", async () => {
  vi.useFakeTimers(); const {card} = setup({delayed: true}); edit(fields(card)[1], "30");
  fields(card)[1].blur(); await card._saveChanges();
  await vi.advanceTimersByTimeAsync(3000);
  expect(card.shadowRoot.textContent).toContain("not confirmed by HA"); expect(fields(card)[1].value).toBe("30");
  card.remove(); expect(vi.getTimerCount()).toBe(0);
});

test("service failure during language change does not orphan pending cells", async () => {
  const {card, hass} = setup(); let reject;
  hass.callService = vi.fn(() => new Promise((_, fail) => {reject = fail;})); card.hass = hass;
  edit(fields(card)[1], "30"); const save = card._saveChanges();
  card.hass = {...hass, language: "it"}; reject(new Error("Offline")); await save;
  expect(card._cells[0].pending).toBeNull(); expect(card._cells[0].draft).not.toBeNull();
  expect(card.shadowRoot.textContent).toContain("Offline");
});

test("unsupported domains and duplicate assignments are rejected", () => {
  const card = new Card();
  expect(() => card.setConfig({rows: [{on_entity: "sensor.a", off_entity: "number.b"}]})).toThrow(/number/);
  expect(() => card.setConfig({rows: [{on_entity: "number.a", off_entity: "number.a"}]})).toThrow(/Duplicate/);
  expect(() => card.setConfig({rows: [], confirmation_timeout: 0})).toThrow(/timeout/);
});

test("input_number writes retain their domain", async () => {
  const {card, hass} = setup(); hass.states["input_number.demo"] = {...hass.states["number.on_0"]};
  card.setConfig({rows: [{on_entity: "input_number.demo", off_entity: "number.off_0"}]}); card.hass = hass;
  edit(fields(card)[1], "30"); await clickSave(card);
  expect(hass.callService).toHaveBeenCalledWith("input_number", "set_value", {entity_id: "input_number.demo", value: 1072});
});

test("visual editor adds, edits, reorders and removes pairs with config-changed", () => {
  const {hass} = setup(); const editor = Card.getConfigElement();
  editor.hass = hass; editor.setConfig({type: "custom:s7plc-schedule-card", rows: [], show_raw: true}); document.body.append(editor);
  const events = [];
  editor.addEventListener("config-changed", event => {events.push(event.detail.config); editor.setConfig(event.detail.config);});
  const button = text => [...editor.shadowRoot.querySelectorAll("button")].find(b => b.textContent === text);
  button("Add slot").click();
  const name = editor.shadowRoot.querySelector("fieldset input"); edit(name, "Pump");
  expect(editor.shadowRoot.querySelector("fieldset input")).toBe(name);
  let selects = editor.shadowRoot.querySelectorAll(".entity-select");
  selects[0].value = "number.on_0"; selects[0].dispatchEvent(new Event("change"));
  selects[1].value = "number.off_0"; selects[1].dispatchEvent(new Event("change"));
  expect(events.at(-1).rows[0]).toEqual({name: "Pump", on_entity: "number.on_0", off_entity: "number.off_0"});
  button("Add slot").click(); button("Move down").click();
  expect(events.at(-1).rows[1].name).toBe("Pump");
  button("Remove slot").click(); expect(events.at(-1).rows).toHaveLength(1);
  expect(events.at(-1).show_raw).toBe(true);
});

test("editor filters incompatible S7 entities, retains missing selections and updates options", () => {
  const {hass} = setup(); hass.states["number.converted"] = {state: "4", attributes: {s7_raw_word: false}};
  const editor = Card.getConfigElement(); editor.hass = {...hass, language: "it"};
  editor.setConfig({rows: [{on_entity: "number.missing", off_entity: "number.off_0"}]}); document.body.append(editor);
  let select = editor.shadowRoot.querySelector(".entity-select");
  expect(select.value).toBe("number.missing");
  expect([...select.options].some(o => o.value === "number.converted")).toBe(false);
  expect(editor.shadowRoot.textContent).toContain("Aggiungi fascia");
  hass.states["number.new"] = {state: "0", attributes: {friendly_name: "New"}};
  editor.hass = {...hass, language: "it"}; select = editor.shadowRoot.querySelector(".entity-select");
  expect([...select.options].some(o => o.value === "number.new")).toBe(true);
});

function setupEditor(hass, rows) {
  const editor = Card.getConfigElement();
  editor.hass = hass;
  editor.setConfig({type: "custom:s7plc-schedule-card", rows, show_raw: true});
  const configs = [];
  editor.addEventListener("config-changed", event => {
    configs.push(event.detail.config);
    editor.setConfig(event.detail.config);
  });
  document.body.append(editor);
  return {editor, configs};
}
const editorButton = (editor, text) => [...editor.shadowRoot.querySelectorAll("button")].find(b => b.textContent === text);
const choose = (select, value) => {select.value = value; select.dispatchEvent(new Event("change"));};
const nativeChoice = (picker, value) => picker.dispatchEvent(new CustomEvent("value-changed", {detail: {value}, bubbles: true, composed: true}));
function mockNativePicker(ready = () => true) {
  const get = customElements.get.bind(customElements);
  vi.spyOn(customElements, "get").mockImplementation(name => name === "ha-entity-picker" ? (ready() ? HTMLElement : undefined) : get(name));
}

test("slot sections keep their state, summary and focus through edits and reordering", () => {
  const {hass} = setup({count: 12});
  const rows = Array.from({length: 12}, (_, i) => ({name: `Pump ${i}`, on_entity: `number.on_${i}`, off_entity: `number.off_${i}`}));
  const {editor, configs} = setupEditor(hass, rows);
  let sections = [...editor.shadowRoot.querySelectorAll("details.slot")];
  expect(sections.filter(d => d.open)).toHaveLength(1);
  expect(sections[0].querySelector("summary").textContent).toContain("04:00");
  editorButton(editor, "Collapse all").click();
  expect(sections.every(d => !d.open)).toBe(true);
  expect(configs).toHaveLength(0);
  sections[0].open = true;
  sections[0].dispatchEvent(new Event("toggle"));
  const name = sections[0].querySelector("input"); edit(name, "<b>Heating</b>");
  editor.hass = {...hass};
  expect(editor.shadowRoot.activeElement).toBe(name);
  expect(sections[0].querySelector("summary").textContent).toContain("<b>Heating</b>");
  expect(sections[0].querySelector("summary b")).toBeNull();
  editorButton(editor, "Move down").click();
  sections = [...editor.shadowRoot.querySelectorAll("details.slot")];
  expect(sections[1].open).toBe(true);
  expect(sections[0].open).toBe(false);
  expect(editor.shadowRoot.activeElement).toBe(sections[1].querySelector("summary"));
  expect(configs.at(-1).rows[1]).toEqual({...rows[0], name: "<b>Heating</b>"});
  expect(Object.keys(configs.at(-1)).sort()).toEqual(["rows", "show_raw", "type"]);
  editorButton(editor, "Expand all").click();
  expect(sections.every(d => d.open)).toBe(true);
  editorButton(editor, "Add slot").click();
  expect(editor.shadowRoot.querySelectorAll("details.slot")[12].open).toBe(true);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("fallback searches names and IDs without losing focus or clearing a filtered selection", () => {
  const {hass} = setup({count: 2});
  hass.states["number.on_1"].attributes.friendly_name = "Boiler morning";
  const {editor, configs} = setupEditor(hass, [{on_entity: "number.on_0", off_entity: "number.off_0"}]);
  const search = editor.shadowRoot.querySelector(".entity-search");
  const select = editor.shadowRoot.querySelector(".entity-select");
  edit(search, "BOILER");
  expect([...select.options].map(o => o.value)).toEqual(["", "number.on_0", "number.on_1"]);
  expect(select.value).toBe("number.on_0");
  expect(configs).toHaveLength(0);
  hass.states["number.extra"] = {state: "1024", attributes: {friendly_name: "Boiler evening"}};
  editor.hass = {...hass};
  expect(editor.shadowRoot.activeElement).toBe(search);
  expect(search.value).toBe("BOILER");
  expect([...select.options].some(o => o.value === "number.extra")).toBe(true);
  edit(search, "number.off_1");
  expect([...select.options].map(o => o.value)).toEqual(["", "number.on_0", "number.off_1"]);
  choose(select, "number.off_1");
  expect(configs.at(-1).rows[0].on_entity).toBe("number.off_1");
  edit(search, "no-such-entity");
  expect(select.value).toBe("number.off_1");
  expect(select.textContent).toContain("No matching entities");
  expect(configs).toHaveLength(1);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("PLC filter uses device registries and preserves selections from another PLC", () => {
  const {hass} = setup({count: 2});
  hass.entities = Object.fromEntries([0, 1].flatMap(i => ["on", "off"].map(key => [`number.${key}_${i}`, {device_id: `plc-${i}`}])));
  hass.devices = {"plc-0": {name: "PLC basement"}, "plc-1": {name: "PLC old", name_by_user: "PLC garden"}};
  const {editor, configs} = setupEditor(hass, [{on_entity: "number.on_0", off_entity: "number.off_0"}]);
  const filter = editor.shadowRoot.querySelector(".plc-filter");
  expect(filter.parentElement.hidden).toBe(false);
  expect(filter.textContent).toContain("PLC garden");
  choose(filter, "plc-1");
  const select = editor.shadowRoot.querySelector(".entity-select");
  expect(select.value).toBe("number.on_0");
  expect([...select.options].map(o => o.value).sort()).toEqual(["", "number.off_1", "number.on_0", "number.on_1"]);
  expect(configs).toHaveLength(0);
  choose(select, "number.on_1");
  expect(configs.at(-1).rows[0]).toEqual({on_entity: "number.on_1", off_entity: "number.off_0"});
  expect(configs.at(-1)).not.toHaveProperty("plc");
});

test("native picker contract rejects stale duplicate choices and retains missing selections", () => {
  mockNativePicker();
  const {hass} = setup({count: 2});
  hass.states["number.converted"] = {state: "400", attributes: {s7_raw_word: false}};
  const {editor, configs} = setupEditor(hass, [
    {on_entity: "number.on_0", off_entity: "number.off_0"},
    {on_entity: "number.missing", off_entity: "number.off_1"},
  ]);
  const pickers = editor.shadowRoot.querySelectorAll("ha-entity-picker");
  expect(pickers[0].includeDomains).toEqual(["number", "input_number"]);
  expect(pickers[0].includeEntities).toEqual(["number.on_0", "number.on_1"]);
  expect(pickers[0].allowCustomEntity).toBe(false);
  expect(pickers[0].entityFilter({entity_id: "number.off_1"})).toBe(false);
  expect(pickers[2].value).toBe("number.missing");
  expect(editor.shadowRoot.querySelectorAll(".warning")[1].textContent).toContain("Unavailable");
  nativeChoice(pickers[0], "number.on_1");
  expect(configs.at(-1).rows[0].on_entity).toBe("number.on_1");
  expect(pickers[2].includeEntities).not.toContain("number.on_1");
  // A stale popup must not bypass duplicate/domain/conversion filtering.
  nativeChoice(pickers[2], "number.on_1");
  nativeChoice(pickers[2], "sensor.invalid");
  nativeChoice(pickers[2], "number.converted");
  expect(configs).toHaveLength(1);
  nativeChoice(pickers[2], undefined);
  expect(configs.at(-1).rows[1].on_entity).toBe("");
  editor.hass = {...hass};
  expect(editor.shadowRoot.querySelector("ha-entity-picker")).toBe(pickers[0]);
  expect(pickers[0].hass).toBe(editor._hass);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("lazy native picker loading waits until a focused fallback field is left", async () => {
  let ready = false, finish;
  mockNativePicker(() => ready);
  const loaded = new Promise(resolve => {finish = () => {ready = true; resolve();};});
  const loadEditor = vi.fn(() => loaded);
  window.loadCardHelpers = vi.fn(async () => ({createCardElement: () => ({constructor: {getConfigElement: loadEditor}})}));
  try {
    const {hass} = setup();
    const {editor} = setupEditor(hass, [{on_entity: "number.on_0", off_entity: "number.off_0"}]);
    const search = editor.shadowRoot.querySelector(".entity-search"); edit(search, "pump");
    await vi.waitFor(() => expect(loadEditor).toHaveBeenCalledOnce());
    finish(); await Promise.resolve(); await Promise.resolve();
    expect(editor.shadowRoot.activeElement).toBe(search);
    expect(editor.shadowRoot.querySelector("ha-entity-picker")).toBeNull();
    search.blur();
    await vi.waitFor(() => expect(editor.shadowRoot.querySelector("ha-entity-picker")).not.toBeNull());
    expect(editor.shadowRoot.querySelector("ha-entity-picker").value).toBe("number.on_0");
  } finally {delete window.loadCardHelpers;}
});

test("picker helper failure leaves searchable HTML controls usable", async () => {
  window.loadCardHelpers = vi.fn().mockRejectedValue(new Error("Unavailable"));
  try {
    const {hass} = setup();
    const {editor, configs} = setupEditor(hass, [{on_entity: "", off_entity: "number.off_0"}]);
    await vi.waitFor(() => expect(editor._loadingPicker).toBe(false));
    const select = editor.shadowRoot.querySelector(".entity-select");
    choose(select, "number.on_0");
    expect(configs.at(-1).rows[0].on_entity).toBe("number.on_0");
    expect(editor.shadowRoot.querySelector(".entity-search")).not.toBeNull();
  } finally {delete window.loadCardHelpers;}
});

test("HHMM validates every minute and never guesses the encoding from the value", () => {
  let valid = 0;
  for (let n = 0; n <= 2359; n++) {
    const time = Card.decodeHHMM(n);
    if (time) {valid++; expect(Card.encodeTime(time.hours, time.minutes, "hhmm")).toBe(n);}
  }
  expect(valid).toBe(1440);
  expect(Card.decodeHHMM("400.0")).toEqual({hours: "04", minutes: "00"});
  expect(Card.decodeHHMM(1024)).toEqual({hours: "10", minutes: "24"});
  expect(Card.decodeWord(1024)).toEqual({hours: "04", minutes: "00"});
  for (const raw of ["", null, true, -1, 60, 1260, 2399, 2400, 65535, "400.5", "04:00", "unknown"]) expect(Card.decodeHHMM(raw)).toBeNull();
  expect(() => new Card().setConfig({rows: [], time_format: "unknown"})).toThrow(/time_format/);
});

test.each(["number", "input_number"])("HHMM %s writes HA units and waits for matching feedback", async domain => {
  const {card, hass, update} = setup({delayed: true});
  const id = `${domain}.clock`;
  hass.states[id] = {state: "400", attributes: {
    min: 0, max: 2359, step: 1,
    ...(domain === "number" ? {s7_raw_word: false, s7_time_format: "hhmm"} : {}),
  }};
  card.setConfig({...(domain === "input_number" ? {time_format: "hhmm"} : {}), show_raw: true, rows: [{on_entity: id}]});
  card.hass = hass;
  expect(fields(card)[0].value).toBe("04");
  expect(card.shadowRoot.textContent).toContain("HHMM 400");
  edit(fields(card)[0], "23"); edit(fields(card)[1], "59");
  await clickSave(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith(domain, "set_value", {entity_id: id, value: 2359});
  update(id, 400);
  expect(fields(card)[0].disabled).toBe(true);
  expect(fields(card)[0].value).toBe("23");
  update(id, 2359);
  expect(card._cells[0].draft).toBeNull();
  expect(fields(card)[0].disabled).toBe(false);
  edit(fields(card)[0], "00"); edit(fields(card)[1], "00");
  await clickSave(card);
  expect(hass.callService).toHaveBeenLastCalledWith(domain, "set_value", {entity_id: id, value: 0});
  update(id, 0); expect(card._cells[0].pending).toBeNull();
});

test("S7 metadata prevents double conversion and HHMM limits use HA values", async () => {
  const {card, hass, update} = setup();
  const rows = [{on_entity: "number.on_0"}];
  card.setConfig({time_format: "hhmm", rows}); card.hass = hass;
  expect(fields(card)[0].value).toBe("04"); // Metadata overrides the old HHMM card setting.
  expect(fields(card)[0].disabled).toBe(false);
  hass.states["number.on_0"].attributes = {min: 0, max: 2359, step: 1, s7_raw_word: false, s7_time_format: "hhmm"};
  card.setConfig({rows}); card.hass = hass;
  expect(fields(card)[0].disabled).toBe(false); // Converted S7 works without a format setting.
  card.setConfig({time_format: "hhmm", rows}); update("number.on_0", 400);
  edit(fields(card)[1], "60");
  await card._saveChanges(); expect(hass.callService).not.toHaveBeenCalled();
  edit(fields(card)[1], "30"); hass.states["number.on_0"].attributes.max = 429; card.hass = {...hass};
  expect(card.shadowRoot.textContent).toContain("Value 430 exceeds maximum 429");
  await card._saveChanges(); expect(hass.callService).not.toHaveBeenCalled();
  hass.states["number.on_0"].attributes.max = 2359;
  hass.states["number.on_0"].attributes.step = 100; card.hass = {...hass};
  expect(card.shadowRoot.textContent).toContain("Incompatible entity step");
  hass.states["number.on_0"].attributes.step = 1;
  update("number.on_0", 500);
  expect(card.shadowRoot.textContent).toContain("Value changed in HA");
  await card._saveChanges(); expect(hass.callService).not.toHaveBeenCalled();
});

test("editor automatically lists both S7 formats with no format selectors", () => {
  const {hass} = setup();
  hass.states["number.logo"] = {state: "430", attributes: {s7_raw_word: false, s7_time_format: "hhmm", friendly_name: "LOGO clock"}};
  hass.states["number.scaled"] = {state: "430", attributes: {s7_raw_word: false}};
  hass.entities = {"number.logo": {device_id: "logo"}};
  hass.devices = {logo: {name: "LOGO garden"}};
  const {editor, configs} = setupEditor(hass, [{on_entity: "number.logo", off_entity: "number.off_0"}]);
  expect(editor.shadowRoot.querySelector(".time-format")).toBeNull();
  expect(editor.shadowRoot.querySelector(".entity-format")).toBeNull();
  expect(editor.shadowRoot.querySelector(".picker-note").textContent).toBe("");
  expect(editor.shadowRoot.querySelector("summary").textContent).toContain("04:30");
  expect(editor.shadowRoot.querySelector(".plc-filter").textContent).toContain("LOGO garden");
  const on = editor.shadowRoot.querySelector(".entity-select");
  expect([...on.options].map(o => o.value).sort()).toEqual(["", "number.logo", "number.on_0"]);
  choose(on, "number.on_0");
  expect(configs.at(-1).rows[0]).toEqual({on_entity: "number.on_0", off_entity: "number.off_0"});
  expect(configs.at(-1)).not.toHaveProperty("time_format");
  expect(hass.callService).not.toHaveBeenCalled();
});

test.each([false, true])("mixed row reads/writes automatically, including obsolete format choices (%s)", async legacy => {
  const {card, hass, update} = setup({delayed: true, reject: true});
  hass.states["number.off_0"].attributes = {min: 0, max: 2359, step: 1, s7_raw_word: false, s7_time_format: "hhmm"};
  card.setConfig({...(legacy ? {time_format: "bcd"} : {}), show_raw: true, rows: [{on_entity: "number.on_0", off_entity: "number.off_0", ...(legacy ? {on_format: "hhmm", off_format: "bcd"} : {})}]});
  card.hass = hass;
  // Identical numeric states have different meanings; only metadata decides.
  expect(fields(card).map(f => f.value)).toEqual(["04", "00", "10", "24"]);
  expect(card.shadowRoot.textContent).toContain("WORD 1024");
  expect(card.shadowRoot.textContent).toContain("HHMM 1024");
  for (const offset of [0, 2]) {edit(fields(card)[offset], "23"); edit(fields(card)[offset + 1], "59");}
  await clickSave(card);
  expect(hass.callService).toHaveBeenNthCalledWith(1, "number", "set_value", {entity_id: "number.on_0", value: 9049});
  expect(hass.callService).toHaveBeenNthCalledWith(2, "number", "set_value", {entity_id: "number.off_0", value: 2359});
  expect(card._cells[0].pending).not.toBeNull();
  expect(card._cells[1].error).toContain("PLC offline");
  update("number.on_0", 9049);
  expect(card._cells[0].draft).toBeNull();
  expect(fields(card)[2].value).toBe("23");
  hass.callService.mockImplementation(async () => {});
  await clickSave(card);
  expect(hass.callService).toHaveBeenCalledTimes(3);
  expect(hass.callService).toHaveBeenLastCalledWith("number", "set_value", {entity_id: "number.off_0", value: 2359});
  update("number.off_0", 2359);
  expect(card._cells.every(c => !c.pending && !c.draft)).toBe(true);
});

test.each([false, true])("mixed editor exposes raw and converted entities (native picker: %s)", native => {
  if (native) mockNativePicker();
  const {hass} = setup();
  hass.states["number.logo"] = {state: "430", attributes: {s7_raw_word: false, s7_time_format: "hhmm"}};
  hass.states["number.scaled"] = {state: "430", attributes: {s7_raw_word: false}};
  hass.entities = Object.fromEntries(["number.on_0", "number.off_0", "number.logo"].map(id => [id, {device_id: "plc"}]));
  hass.devices = {plc: {name: "Mixed PLC"}};
  const {editor, configs} = setupEditor(hass, [{on_entity: "", off_entity: ""}]);
  choose(editor.shadowRoot.querySelector(".plc-filter"), "plc");
  const pickers = [...editor.shadowRoot.querySelectorAll(native ? "ha-entity-picker" : ".entity-select")];
  const choices = picker => native ? picker.includeEntities : [...picker.options].map(o => o.value).filter(Boolean);
  expect(choices(pickers[0]).sort()).toEqual(["number.logo", "number.off_0", "number.on_0"]);
  (native ? nativeChoice : choose)(pickers[0], "number.on_0");
  (native ? nativeChoice : choose)(pickers[1], "number.logo");
  expect(configs.at(-1).rows[0]).toEqual({on_entity: "number.on_0", off_entity: "number.logo"});
  expect(choices(pickers[1])).not.toContain("number.on_0");
  expect(editor.shadowRoot.querySelector("summary").textContent).toContain("04:00");
  expect(editor.shadowRoot.querySelector("summary").textContent).toContain("04:30");
  expect([...editor.shadowRoot.querySelectorAll(".picker-note")].every(n => !n.textContent)).toBe(true);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("legacy helper formats survive editor changes without exposing manual selectors", async () => {
  const {card, hass, update} = setup({delayed: true});
  hass.states["input_number.raw"] = {state: "1024", attributes: {min: 0, max: 65535, step: 1}};
  hass.states["input_number.clock"] = {state: "400", attributes: {min: 0, max: 2359, step: 1}};
  const {editor, configs} = setupEditor(hass, [{on_entity: "input_number.raw", off_entity: "input_number.clock", off_format: "hhmm"}]);
  expect(editor.shadowRoot.querySelector(".entity-format")).toBeNull();
  edit(editor.shadowRoot.querySelector(".slot fieldset input"), "Helpers");
  expect(configs.at(-1).rows[0].off_format).toBe("hhmm");
  expect(editor.shadowRoot.querySelector("summary").textContent.match(/04:00/g)).toHaveLength(2);
  card.setConfig(configs.at(-1)); card.hass = hass;
  edit(fields(card)[1], "30"); edit(fields(card)[3], "30");
  await clickSave(card);
  expect(hass.callService).toHaveBeenNthCalledWith(1, "input_number", "set_value", {entity_id: "input_number.raw", value: 1072});
  expect(hass.callService).toHaveBeenNthCalledWith(2, "input_number", "set_value", {entity_id: "input_number.clock", value: 430});
  update("input_number.raw", 1072); update("input_number.clock", 430);
  expect(card._cells.every(c => !c.pending && !c.draft)).toBe(true);
  expect(() => card.setConfig({rows: [{on_format: "invalid"}]})).toThrow(/on_format/);
});

test("automatic format changes cannot reinterpret a draft or acknowledge another encoding", async () => {
  const {card, hass, update} = setup({delayed: true});
  card.setConfig({confirmation_timeout: 1, rows: [{on_entity: "number.on_0"}]});
  card.hass = hass;
  fields(card)[0].focus();
  hass.states["number.on_0"].attributes = {s7_raw_word: false, s7_time_format: "hhmm"};
  update("number.on_0", 1024);
  edit(fields(card)[1], "30");
  await card._saveChanges();
  expect(hass.callService).not.toHaveBeenCalled();
  expect(card.shadowRoot.textContent).toContain("Value changed in HA");
  const cancel = card.shadowRoot.querySelector(".reset"); cancel.focus(); cancel.click();
  edit(fields(card)[0], "00"); edit(fields(card)[1], "00");
  await clickSave(card);
  expect(hass.callService).toHaveBeenLastCalledWith("number", "set_value", {entity_id: "number.on_0", value: 0});
  hass.states["number.on_0"].attributes = {s7_raw_word: true};
  update("number.on_0", 0); // Midnight has the same number in either encoding.
  expect(card._cells[0].pending).not.toBeNull();
  vi.useFakeTimers(); vi.setSystemTime(Date.now() + 2000); card.hass = {...hass};
  expect(card._cells[0].pending).toBeNull();
  expect(card._cells[0].draft).not.toBeNull();
  await card._saveChanges();
  expect(hass.callService).toHaveBeenCalledTimes(1);
});

function bulkSelect(editor, key, query) {
  editor.shadowRoot.querySelector("details.bulk").open = true;
  edit(editor.shadowRoot.querySelector(`.bulk-search-${key}`), query);
  editor.shadowRoot.querySelector(`.bulk-all-${key}`).click();
}

test("bulk wizard previews 12 naturally ordered mixed pairs and appends them only on Apply", () => {
  const {hass} = setup({count: 13});
  for (let i = 1; i <= 12; i += 2) {
    hass.states[`number.off_${i}`] = {state: "430", attributes: {s7_raw_word: false, s7_time_format: "hhmm"}};
  }
  const existing = {name: "Keep me", on_entity: "number.on_0", off_entity: "number.off_0", on_format: "bcd"};
  const {editor, configs} = setupEditor(hass, [existing]);
  bulkSelect(editor, "on", "number.on_");
  expect(editor.shadowRoot.querySelector(".bulk-apply").disabled).toBe(true);
  bulkSelect(editor, "off", "number.off_");
  const preview = [...editor.shadowRoot.querySelectorAll(".bulk-preview tbody tr")];
  expect(preview).toHaveLength(12);
  expect(preview[1].textContent).toContain("number.on_2");
  expect(preview[9].textContent).toContain("number.on_10");
  expect(preview[0].textContent).toContain("04:30");
  expect(editor.shadowRoot.querySelector('.bulk [role="status"]').textContent).toBe("12 on entities · 12 off entities");
  expect(configs).toHaveLength(0);
  editor.shadowRoot.querySelector(".bulk-apply").click();
  expect(configs).toHaveLength(1);
  expect(configs[0].rows).toHaveLength(13);
  expect(configs[0].rows[0]).toEqual(existing);
  expect(configs[0].rows.slice(1)).toEqual(Array.from({length: 12}, (_, i) => ({name: "", on_entity: `number.on_${i + 1}`, off_entity: `number.off_${i + 1}`})));
  expect(Object.keys(configs[0]).sort()).toEqual(["rows", "show_raw", "type"]);
  expect(editor.shadowRoot.querySelector("details.bulk").open).toBe(false);
  expect(editor.shadowRoot.activeElement).toBe(editor.shadowRoot.querySelectorAll("details.slot")[1].querySelector("summary"));
  editor.shadowRoot.querySelector(".bulk-apply").click(); expect(configs).toHaveLength(1);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("bulk preview can reorder either column and highlights incomplete pairing", () => {
  const {hass} = setup({count: 2}), {editor, configs} = setupEditor(hass, []);
  bulkSelect(editor, "on", "number.on_"); bulkSelect(editor, "off", "number.off_");
  editor.shadowRoot.querySelector('.bulk-move[data-key="off"][data-index="0"][data-delta="1"]').click();
  expect(editor.shadowRoot.querySelector(".bulk-preview tbody tr").textContent).toContain("number.off_1");
  expect(configs).toHaveLength(0);
  editor.shadowRoot.querySelector(".bulk-apply").click();
  expect(configs[0].rows).toEqual([
    {name: "", on_entity: "number.on_0", off_entity: "number.off_1"},
    {name: "", on_entity: "number.on_1", off_entity: "number.off_0"},
  ]);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("bulk selections survive search and PLC filters; checkbox focus survives HA refresh", () => {
  const {hass} = setup({count: 2});
  hass.entities = Object.fromEntries([0, 1].flatMap(i => ["on", "off"].map(key => [`number.${key}_${i}`, {device_id: `plc-${i}`}])));
  hass.devices = {"plc-0": {name: "Basement"}, "plc-1": {name: "Garden"}};
  const {editor, configs} = setupEditor(hass, []);
  choose(editor.shadowRoot.querySelector(".plc-filter"), "plc-1");
  bulkSelect(editor, "on", "on_");
  expect(editor.shadowRoot.querySelectorAll(".bulk-list-on input")).toHaveLength(1);
  const checkbox = editor.shadowRoot.querySelector(".bulk-list-on input"); checkbox.focus();
  editor.hass = {...hass};
  expect(editor.shadowRoot.activeElement).toBe(checkbox);
  expect(editor.shadowRoot.querySelector(".bulk-preview").textContent).toContain("number.on_1");
  edit(editor.shadowRoot.querySelector(".bulk-search-on"), "no results");
  choose(editor.shadowRoot.querySelector(".plc-filter"), "plc-0");
  expect(editor.shadowRoot.querySelector(".bulk-preview").textContent).toContain("number.on_1");
  bulkSelect(editor, "off", "off_");
  expect(editor.shadowRoot.querySelector(".bulk-preview").textContent).toContain("number.off_0");
  editor.shadowRoot.querySelector(".bulk-clear-on").click();
  expect(editor.shadowRoot.querySelector(".bulk-apply").disabled).toBe(true);
  expect(editor.shadowRoot.querySelector(".bulk-preview").textContent).not.toContain("number.on_1");
  expect(configs).toHaveLength(0);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("bulk Apply rechecks missing, incompatible and newly assigned entities without partial additions", () => {
  const {hass} = setup({count: 2}), {editor, configs} = setupEditor(hass, []);
  bulkSelect(editor, "on", "on_"); bulkSelect(editor, "off", "off_");
  const saved = hass.states["number.off_1"];
  delete hass.states["number.off_1"];
  editor._bulkAdd(); expect(configs).toHaveLength(0);
  expect(editor.shadowRoot.querySelector(".bulk-preview .warning")).not.toBeNull();
  hass.states["number.off_1"] = {...saved, attributes: {s7_raw_word: false}};
  editor._bulkAdd(); expect(configs).toHaveLength(0);
  hass.states["number.off_1"] = saved;
  editor.setConfig({type: "custom:s7plc-schedule-card", rows: [{on_entity: "number.on_1"}]});
  editor._bulkAdd(); expect(configs).toHaveLength(0);
  expect(editor.shadowRoot.querySelector(".bulk-apply").disabled).toBe(true);
  expect(editor._config.rows).toEqual([{on_entity: "number.on_1"}]);
  expect(hass.callService).not.toHaveBeenCalled();
});
