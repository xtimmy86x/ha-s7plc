// @vitest-environment jsdom
import fs from "node:fs";
import {afterEach, beforeAll, expect, test, vi} from "vitest";

beforeAll(() => window.eval(fs.readFileSync("custom_components/s7plc/www/s7plc-schedule-card.js", "utf8")));
afterEach(() => {document.body.replaceChildren(); vi.useRealTimers();});

function setup(pairs, {show = true} = {}) {
  const Card = customElements.get("s7plc-schedule-card"), card = new Card();
  const states = {}, rows = pairs.map(([on, off], i) => {
    // Each pair deliberately mixes raw BCD and already converted HHMM.
    states[`number.on_${i}`] = {state: String(Card.encodeTime(...on)), attributes: {s7_raw_word: true}};
    states[`number.off_${i}`] = {state: String(Number(off[0]) * 100 + Number(off[1])), attributes: {s7_time_format: "hhmm"}};
    return {name: `Slot ${i + 1}`, on_entity: `number.on_${i}`, off_entity: `number.off_${i}`};
  });
  const hass = {language: "en", states, callService: vi.fn(async () => {})};
  const config = {rows, confirmation_timeout: 1, ...(show ? {show_timeline: true} : {})};
  card.setConfig(config); card.hass = hass; document.body.append(card);
  const update = (id, state, attributes) => {
    states[id] = {...states[id], state: String(state), ...(attributes ? {attributes} : {})};
    card.hass = {...hass};
  };
  return {card, hass, config, update};
}
const timeline = card => card.shadowRoot.querySelector(".timeline");
const lanes = card => [...timeline(card).querySelectorAll(".timeline-row")];
const ranges = node => [...node.querySelectorAll(".timeline-bar")].map(bar => [Number(bar.dataset.start), Number(bar.dataset.end)]);
const overlapRanges = card => ranges(timeline(card).querySelector(".timeline-overlaps") ?? document.createElement("div"));
const input = (card, index, value) => {
  const field = card.shadowRoot.querySelectorAll("input")[index]; field.focus(); field.value = value;
  field.dispatchEvent(new Event("input", {bubbles: true})); return field;
};

test("timeline is opt-in; the editor toggles it without changing pairs or calling services", () => {
  const {card, hass, config} = setup([[[4, 0], [5, 0]]], {show: false});
  expect(timeline(card)).toBeNull();
  const size = card.getCardSize();
  const editor = document.createElement("s7plc-schedule-card-editor");
  editor.setConfig(config); editor.hass = hass; document.body.append(editor);
  const configs = [];
  editor.addEventListener("config-changed", event => configs.push(event.detail.config));
  const toggle = editor.shadowRoot.querySelector(".show-timeline");
  expect(toggle.checked).toBe(false); toggle.click();
  expect(configs).toHaveLength(1); expect(configs[0].rows).toEqual(config.rows);
  card.setConfig(configs[0]); expect(timeline(card)).not.toBeNull(); expect(card.getCardSize()).toBeGreaterThan(size);
  editor.setConfig(configs[0]); expect(editor.shadowRoot.querySelector(".show-timeline")).toBe(toggle);
  toggle.click(); card.setConfig(configs[1]); expect(timeline(card)).toBeNull();
  expect(hass.callService).not.toHaveBeenCalled();
  expect(() => card.setConfig({...config, show_timeline: "false"})).toThrow("boolean");
});

test("mixed formats produce exact daily and overnight ranges; touching endpoints do not overlap", () => {
  const {card, hass} = setup([[[22, 0], [2, 0]], [[1, 0], [3, 0]], [[3, 0], [4, 0]], [[23, 0], [1, 30]]]);
  expect(lanes(card).map(ranges)).toEqual([[[0, 120], [1320, 1440]], [[60, 180]], [[180, 240]], [[0, 90], [1380, 1440]]]);
  expect(overlapRanges(card)).toEqual([[0, 120], [1380, 1440]]);
  expect(lanes(card).map(node => node.hasAttribute("data-overlap"))).toEqual([true, true, false, true]);
  expect(lanes(card)[0].textContent).toContain("Crosses midnight");
  expect(timeline(card).querySelector(".timeline-overlaps").textContent).toContain("00:00–02:00, 23:00–24:00");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("midnight endpoints, one-minute intervals, identical times and empty schedules remain unambiguous", () => {
  const {card, config} = setup([[[23, 59], [0, 0]], [[0, 0], [0, 1]], [[4, 0], [4, 0]], [[0, 0], [0, 0]]]);
  expect(lanes(card).map(ranges)).toEqual([[[1439, 1440]], [[0, 1]], [], []]);
  expect(overlapRanges(card)).toEqual([]);
  expect(lanes(card)[2].textContent).toContain("Identical times");
  const bar = lanes(card)[0].querySelector(".timeline-bar");
  expect(parseFloat(bar.style.left)).toBeCloseTo(1439 / 1440 * 100);
  expect(parseFloat(bar.style.width)).toBeCloseTo(100 / 1440);
  card.setConfig({...config, rows: []}); expect(lanes(card)).toHaveLength(0);
  expect(timeline(card).textContent).not.toContain("NaN");
});

test("unavailable, missing, invalid or incompatible values omit only their own intervals and recover on update", () => {
  const {card, update} = setup(Array.from({length: 5}, () => [[4, 0], [5, 0]]));
  update("number.on_0", "unavailable"); update("number.on_1", 0x1260);
  update("number.off_2", 500, {s7_time_format: "other"});
  delete card.hass.states["number.on_3"]; card.hass = {...card.hass};
  expect(lanes(card).map(ranges)).toEqual([[], [], [], [], [[240, 300]]]);
  expect(lanes(card)[0].textContent).toContain("Interval not shown");
  expect(overlapRanges(card)).toEqual([]);
  update("number.on_0", 1024); expect(overlapRanges(card)).toEqual([[240, 300]]);
});

test("draft preview follows edits and Cancel, preserves input focus, and excludes invalid or conflicted drafts", () => {
  const {card, hass, update} = setup([[[4, 0], [5, 0]], [[6, 0], [7, 0]]]);
  const originalLane = lanes(card)[0]; card.hass = {...hass}; expect(lanes(card)[0]).toBe(originalLane);
  const field = input(card, 2, "06"); field.setSelectionRange(1, 1);
  expect(ranges(lanes(card)[0])).toEqual([[240, 360]]);
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(true);
  expect(timeline(card).querySelector(".timeline-hint").textContent).toContain("Preview");
  update("number.off_1", 730);
  expect(card.shadowRoot.activeElement).toBe(field); expect(field.selectionStart).toBe(1);
  input(card, 2, "99"); expect(ranges(lanes(card)[0])).toEqual([]);
  input(card, 2, "06"); update("number.off_0", 530); expect(ranges(lanes(card)[0])).toEqual([]);
  const cancel = card.shadowRoot.querySelector(".reset"); cancel.focus(); cancel.click();
  expect(ranges(lanes(card)[0])).toEqual([[240, 330]]);
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(false);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("overlaps are advisory; Save stays explicit and the timeline remains a preview until HA confirms", async () => {
  const {card, hass, update} = setup([[[4, 0], [5, 0]], [[6, 0], [7, 0]]]);
  input(card, 2, "07"); expect(overlapRanges(card)).toEqual([[360, 420]]);
  const save = card.shadowRoot.querySelector(".save"); expect(save.disabled).toBe(false);
  expect(hass.callService).not.toHaveBeenCalled(); save.focus(); save.click();
  await vi.waitFor(() => expect(card._saving).toBe(false));
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith("number", "set_value", {entity_id: "number.off_0", value: 700});
  expect(lanes(card)[0].textContent).toContain("Waiting for HA");
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(true);
  update("number.off_0", 700);
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(false);
  expect(ranges(lanes(card)[0])).toEqual([[240, 420]]);
});

test("failed or unconfirmed writes never become confirmed timeline intervals", async () => {
  const {card, hass} = setup([[[4, 0], [5, 0]]]);
  input(card, 2, "06"); hass.callService.mockRejectedValueOnce(new Error("PLC offline"));
  card.shadowRoot.querySelector(".save").click();
  await vi.waitFor(() => expect(card._saving).toBe(false));
  expect(ranges(lanes(card)[0])).toEqual([]);
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(true);
  input(card, 2, "07"); card.shadowRoot.querySelector(".save").click();
  await vi.waitFor(() => expect(card._saving).toBe(false));
  vi.useFakeTimers(); vi.setSystemTime(Date.now() + 2000); card.hass = {...hass};
  expect(ranges(lanes(card)[0])).toEqual([]);
  expect(lanes(card)[0].hasAttribute("data-preview")).toBe(true);
});

test("timeline labels localize, stay accessible and treat slot names as text", () => {
  const {card, hass, config} = setup([[[22, 0], [2, 0]]]);
  card.hass = {...hass, language: "it"};
  card.setConfig({...config, rows: [{...config.rows[0], name: "<img src=x>"}]});
  expect(timeline(card).getAttribute("aria-label")).toBe("Timeline giornaliera");
  const track = lanes(card)[0].querySelector('[role="img"]');
  expect(track.getAttribute("aria-label")).toContain("22:00–02:00 · Attraversa mezzanotte");
  expect(timeline(card).querySelector("img")).toBeNull();
  expect(lanes(card)[0].textContent).toContain("<img src=x>");
});
