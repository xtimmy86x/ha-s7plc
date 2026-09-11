// @vitest-environment jsdom
import fs from "node:fs";
import {afterEach, beforeAll, expect, test, vi} from "vitest";

beforeAll(() => window.eval(fs.readFileSync("custom_components/s7plc/www/s7plc-schedule-card.js", "utf8")));
afterEach(() => {document.body.replaceChildren(); vi.useRealTimers(); vi.restoreAllMocks();});

function setup(mask = 62, {delayed = false, domain = "number"} = {}) {
  const card = document.createElement("s7plc-schedule-card"), id = `${domain}.days`;
  const rows = [{name: "Pump", on_entity: "number.on", off_entity: "number.off", days_entity: id}];
  const hass = {language: "en", states: {
    "number.on": {state: "1024", attributes: {s7_raw_word: true}},
    "number.off": {state: "500", attributes: {s7_time_format: "hhmm", s7_raw_word: false}},
    [id]: {state: String(mask), attributes: {min: 0, max: 255, step: 1,
      ...(domain === "number" ? {s7_raw_word: false, s7_raw_byte: true} : {})}},
  }};
  const update = (entity, value, attributes) => {
    hass.states = {...hass.states, [entity]: {...hass.states[entity], state: String(value), ...(attributes ? {attributes} : {})}};
    card.hass = {...hass};
  };
  hass.callService = vi.fn(async (_domain, _service, data) => {if (!delayed) update(data.entity_id, data.value);});
  const config = {rows, show_timeline: true, show_raw: true, confirmation_timeout: 1};
  card.setConfig(config); card.hass = hass; document.body.append(card);
  return {card, hass, update, config, id};
}
const days = card => [...card.shadowRoot.querySelectorAll(".days button")];
const toggle = (card, bit) => card.shadowRoot.querySelector(`.days button[data-bit="${bit}"]`).click();
const save = async card => {
  const button = card.shadowRoot.querySelector(".save"); button.focus(); button.click();
  await vi.waitFor(() => expect(card._saving).toBe(false));
};
const cancel = card => {const button = card.shadowRoot.querySelector(".reset"); button.focus(); button.click();};
const edit = (card, index, value) => {
  const field = card.shadowRoot.querySelectorAll("input")[index]; field.focus(); field.value = value;
  field.dispatchEvent(new Event("input", {bubbles: true}));
};
const dayView = (card, bit) => {
  const select = card.shadowRoot.querySelector(".timeline-day select"); select.focus(); select.value = bit;
  select.dispatchEvent(new Event("change")); return select;
};
const ranges = card => [...card.shadowRoot.querySelectorAll(".timeline-row .timeline-bar")]
  .map(bar => [Number(bar.dataset.start), Number(bar.dataset.end)]);

test("all BYTE masks decode Sunday bit 0 through Saturday bit 6 in Monday-first UI order", () => {
  const {card, update, hass, id} = setup();
  expect(days(card).map(button => Number(button.dataset.bit))).toEqual([1, 2, 3, 4, 5, 6, 0]);
  for (let mask = 0; mask <= 255; mask++) {
    update(id, mask);
    expect(days(card).map(button => button.getAttribute("aria-pressed") === "true"))
      .toEqual([1, 2, 3, 4, 5, 6, 0].map(bit => Boolean(mask & (1 << bit))));
  }
  expect(hass.callService).not.toHaveBeenCalled();
  update(id, 128); expect(card.shadowRoot.querySelector(".days-summary").textContent).toBe("No days selected");
});

test.each(["number", "input_number"])("%s weekday edits preserve bit 7, Cancel and only explicit Save writes", async domain => {
  const {card, hass, id} = setup(128, {domain});
  for (const bit of [1, 2, 3, 4, 5]) toggle(card, bit);
  expect(hass.callService).not.toHaveBeenCalled();
  expect(card._dayCells[0].draft.value).toBe(190);
  cancel(card); expect(card._dayCells[0].draft).toBeNull();
  toggle(card, 0); await save(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith(domain, "set_value", {entity_id: id, value: 129});
  expect(card._dayCells[0].draft).toBeNull();
  expect(card.shadowRoot.querySelector(".days-row .raw").textContent).toBe("BYTE 129");
});

test("days and mixed-format times save together, but pending day writes wait for exact feedback", async () => {
  const {card, hass, update, id} = setup(2, {delayed: true});
  edit(card, 1, "30"); edit(card, 3, "30"); toggle(card, 2);
  await save(card);
  expect(hass.callService.mock.calls.map(call => call[2])).toEqual([
    {entity_id: "number.on", value: 1072}, {entity_id: "number.off", value: 530}, {entity_id: id, value: 6},
  ]);
  expect(days(card).every(button => button.disabled)).toBe(true);
  update("number.on", 1072); update("number.off", 530); update(id, 2);
  expect(card._dayCells[0].pending).not.toBeNull();
  expect(card.shadowRoot.querySelector(".timeline-row").hasAttribute("data-preview")).toBe(true);
  update(id, 6); expect(card._dayCells[0].pending).toBeNull();
  expect(card.shadowRoot.querySelector(".timeline-row").hasAttribute("data-preview")).toBe(false);
});

test("external changes including bit 7 block stale day writes; limits and step are enforced", async () => {
  const {card, hass, update, id} = setup(2);
  toggle(card, 2); update(id, 130); await save(card);
  expect(hass.callService).not.toHaveBeenCalled();
  expect(card.shadowRoot.querySelector(".days-row .note").textContent).toContain("Value changed");
  cancel(card); toggle(card, 2); expect(card._dayCells[0].draft.value).toBe(134);
  update(id, 130, {s7_raw_byte: true, min: 0, max: 131, step: 1}); await save(card);
  expect(card.shadowRoot.querySelector(".days-row .note").textContent).toContain("maximum");
  update(id, 130, {s7_raw_byte: true, min: 0, max: 255, step: 5}); await save(card);
  expect(card.shadowRoot.querySelector(".days-row .note").textContent).toContain("step");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("invalid or incompatible BYTEs disable day editing and omit that timeline interval", () => {
  const {card, hass, update, id} = setup();
  for (const value of ["unavailable", "unknown", "", -1, 256, 1.5, "0x02"]) {
    update(id, value); toggle(card, 0);
    expect(days(card).every(button => button.disabled)).toBe(true); expect(ranges(card)).toEqual([]);
  }
  update(id, 2, {s7_raw_byte: false}); expect(days(card).every(button => button.disabled)).toBe(true);
  update(id, 2, {s7_raw_byte: true}); expect(ranges(card)).toEqual([[240, 300]]);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("failed and timed-out weekday writes keep drafts; retry never resends confirmed time values", async () => {
  const {card, hass, update, id} = setup(2);
  hass.callService.mockImplementation(async (_d, _s, data) => {
    if (data.entity_id === id) throw new Error("PLC offline"); update(data.entity_id, data.value);
  });
  edit(card, 1, "30"); toggle(card, 2); await save(card);
  expect(card._cells[0].draft).toBeNull(); expect(card._dayCells[0].draft.value).toBe(6);
  expect(ranges(card)).toEqual([]);
  hass.callService.mockResolvedValue(); await save(card);
  expect(hass.callService.mock.calls.map(call => call[2].entity_id)).toEqual(["number.on", id, id]);
  vi.useFakeTimers(); vi.setSystemTime(Date.now() + 2000); card.hass = {...hass};
  expect(card._dayCells[0].pending).toBeNull(); expect(card._dayCells[0].draft.value).toBe(6);
  expect(card.shadowRoot.querySelector(".days-row .note").textContent).toContain("not confirmed");
});

test("daily timeline carries overnight intervals from the previous selected start day, including Sunday", () => {
  const {card, hass, update, id} = setup(64);
  update("number.on", 0x2200); update("number.off", 200);
  dayView(card, 6); expect(ranges(card)).toEqual([[1320, 1440]]);
  const select = dayView(card, 0); expect(ranges(card)).toEqual([[0, 120]]);
  card.hass = {...hass}; expect(card.shadowRoot.activeElement).toBe(select);
  expect(card.shadowRoot.querySelector(".timeline-day select")).toBe(select);
  dayView(card, 1); expect(ranges(card)).toEqual([]);
  toggle(card, 0); expect(ranges(card)).toEqual([[0, 120]]);
  cancel(card); expect(ranges(card)).toEqual([]);
  update(id, 0); dayView(card, 6); expect(ranges(card)).toEqual([]);
});

test("day filtering determines overlaps; rows without days remain daily and duplicate IDs are rejected", () => {
  const {card, hass, config} = setup(2);
  hass.states["number.on2"] = hass.states["number.on"]; hass.states["number.off2"] = hass.states["number.off"];
  card.setConfig({...config, rows: [...config.rows, {on_entity: "number.on2", off_entity: "number.off2"}]});
  card.hass = {...hass};
  expect(card.shadowRoot.querySelector(".timeline-overlaps")).not.toBeNull();
  dayView(card, 2); expect(card.shadowRoot.querySelector(".timeline-overlaps")).toBeNull();
  expect(ranges(card)).toEqual([[240, 300]]);
  expect(card.shadowRoot.querySelectorAll(".timeline-row")[1].textContent).toContain("Every day");
  expect(() => card.setConfig({rows: [{...config.rows[0], days_entity: "number.on"}]})).toThrow("Duplicate");
  expect(() => card.setConfig({rows: [{...config.rows[0], days_entity: "sensor.days"}]})).toThrow("number");
});

test.each([false, true])("days picker supports search/PLC/duplicates and clearing without changing times (native %s)", native => {
  if (native) {
    const get = customElements.get.bind(customElements);
    vi.spyOn(customElements, "get").mockImplementation(name => name === "ha-entity-picker" ? HTMLElement : get(name));
  }
  const {hass, config, id} = setup();
  hass.states["number.days2"] = hass.states[id]; hass.states["number.scaled"] = {state: "2", attributes: {s7_raw_byte: false, s7_raw_word: false}};
  hass.entities = {[id]: {device_id: "plc"}, "number.days2": {device_id: "other"}};
  hass.devices = {plc: {name: "LOGO"}, other: {name: "Other PLC"}};
  const editor = document.createElement("s7plc-schedule-card-editor"); editor.setConfig(config); editor.hass = hass; document.body.append(editor);
  const events = []; editor.addEventListener("config-changed", e => events.push(e.detail.config));
  const picker = editor.shadowRoot.querySelector('[data-field="days_entity"]');
  const choose = value => {
    if (native) picker.dispatchEvent(new CustomEvent("value-changed", {detail: {value}}));
    else {picker.value = value; picker.dispatchEvent(new Event("change"));}
  };
  const choices = () => native ? picker.includeEntities : [...picker.options].map(o => o.value).filter(Boolean);
  expect(choices()).toEqual([id, "number.days2"]);
  const filter = editor.shadowRoot.querySelector(".plc-filter"); filter.value = "plc"; filter.dispatchEvent(new Event("change"));
  expect(choices()).toEqual([id]);
  choose(""); expect(events.at(-1).rows[0]).toEqual({...config.rows[0], days_entity: ""});
  expect(hass.callService).not.toHaveBeenCalled();
});
