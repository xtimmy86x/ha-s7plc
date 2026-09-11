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
  let selects = editor.shadowRoot.querySelectorAll("select");
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
  let select = editor.shadowRoot.querySelector("select");
  expect(select.value).toBe("number.missing");
  expect([...select.options].some(o => o.value === "number.converted")).toBe(false);
  expect(editor.shadowRoot.textContent).toContain("Aggiungi fascia");
  hass.states["number.new"] = {state: "0", attributes: {friendly_name: "New"}};
  editor.hass = {...hass, language: "it"}; select = editor.shadowRoot.querySelector("select");
  expect([...select.options].some(o => o.value === "number.new")).toBe(true);
});
