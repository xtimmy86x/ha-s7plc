// @vitest-environment jsdom
import fs from "node:fs";
import {afterEach, beforeAll, expect, test, vi} from "vitest";

beforeAll(() => window.eval(fs.readFileSync("custom_components/s7plc/www/s7plc-schedule-card.js", "utf8")));
afterEach(() => {document.body.replaceChildren(); vi.restoreAllMocks();});

function setup() {
  const card = document.createElement("s7plc-schedule-card"), rows = [], states = {};
  for (let index = 0; index < 3; index++) {
    rows.push({name: `Slot ${index + 1}`, on_entity: `number.on_${index}`, off_entity: `number.off_${index}`, days_entity: `number.days_${index}`});
    const h = 4 + index * 4;
    states[`number.on_${index}`] = {state: String(index % 2 ? h * 100 : card.constructor.encodeTime(h, 0)),
      attributes: index % 2 ? {s7_time_format: "hhmm"} : {s7_raw_word: true}};
    states[`number.off_${index}`] = {state: String(index % 2 ? card.constructor.encodeTime(h + 1, 0) : (h + 1) * 100),
      attributes: index % 2 ? {s7_raw_word: true} : {s7_time_format: "hhmm"}};
    states[`number.days_${index}`] = {state: String([190, 1, 129][index]), attributes: {s7_raw_byte: true, min: 0, max: 255, step: 1}};
  }
  const hass = {language: "en", states};
  const update = (id, value, attributes) => {
    hass.states = {...hass.states, [id]: {...hass.states[id], state: String(value), ...(attributes ? {attributes} : {})}};
    card.hass = {...hass};
  };
  hass.callService = vi.fn(async (_domain, _service, data) => update(data.entity_id, data.value));
  const config = {rows, show_timeline: true}; card.setConfig(config); card.hass = hass; document.body.append(card);
  const details = card.shadowRoot.querySelector(".copy"); details.open = true; details.dispatchEvent(new Event("toggle"));
  return {card, hass, update, config};
}
const control = (card, cls) => card.shadowRoot.querySelector(`.${cls}`);
const select = (card, cls, value) => {const node = control(card, cls); node.value = value; node.dispatchEvent(new Event("change"));};
const target = (card, index) => card.shadowRoot.querySelector(`.copy input[data-index="${index}"]`);
const choose = (card, index) => target(card, index).click();
const apply = card => control(card, "copy-apply").click();
const edit = (card, index, value) => {
  const field = card.shadowRoot.querySelectorAll(".time input")[index]; field.focus(); field.value = value;
  field.dispatchEvent(new Event("input", {bubbles: true}));
};
const save = async card => {control(card, "save").focus(); control(card, "save").click(); await vi.waitFor(() => expect(card._saving).toBe(false));};
const cancel = card => {control(card, "reset").focus(); control(card, "reset").click();};
const preset = (card, row, mask) => card.shadowRoot.querySelectorAll(".day-presets")[row].querySelector(`[data-mask="${mask}"]`).click();

test("day presets replace only weekday bits, update the preview and remain local until Save", async () => {
  const {card, hass} = setup();
  for (const row of [0, 1]) for (const mask of [127, 62, 65, 0]) {
    preset(card, row, mask);
    expect(card._dayCells[row].draft?.value ?? Number(hass.states[`number.days_${row}`].state)).toBe(mask | (row === 0 ? 128 : 0));
    expect(card.shadowRoot.querySelectorAll(".day-presets")[row].querySelector(`[data-mask="${mask}"]`).getAttribute("aria-pressed")).toBe("true");
  }
  expect(hass.callService).not.toHaveBeenCalled(); cancel(card);
  expect(card._dayCells.every(cell => !cell.draft)).toBe(true);
  preset(card, 1, 62); await save(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith("number", "set_value", {entity_id: "number.days_1", value: 62});
});

test("copy both previews before/after, uses source drafts and preserves destination bit 7 across formats", async () => {
  const {card, hass} = setup(); edit(card, 1, "30"); edit(card, 5, "15");
  select(card, "copy-mode", "both"); choose(card, 1); choose(card, 2);
  expect(target(card, 1).parentElement.textContent).toContain("08:15 → 04:30");
  expect(card._dayCells[1].draft).toBeNull(); apply(card);
  expect(hass.callService).not.toHaveBeenCalled();
  expect(card._cells[2].draft.hours).toBe("04"); expect(card._cells[2].draft.minutes).toBe("30");
  expect(card._dayCells[1].draft.value).toBe(62); expect(card._dayCells[2].draft.value).toBe(190);
  expect(control(card, "copy-apply").disabled).toBe(true);
  expect(control(card, "copy-message").textContent).toContain("already match");
  await save(card);
  const values = Object.fromEntries(hass.callService.mock.calls.map(call => [call[2].entity_id, call[2].value]));
  expect(values).toMatchObject({"number.on_0": 1072, "number.on_1": 430, "number.off_1": 1280,
    "number.on_2": 1072, "number.off_2": 500, "number.days_1": 62, "number.days_2": 190});
});

test.each(["times", "days"])("copy %s leaves the other destination values and non-selected rows untouched; Cancel restores HA", mode => {
  const {card, hass} = setup(); select(card, "copy-mode", mode); choose(card, 1); apply(card);
  expect(Boolean(card._cells[2].draft)).toBe(mode === "times");
  expect(Boolean(card._dayCells[1].draft)).toBe(mode === "days");
  expect(card._cells[4].draft).toBeNull(); expect(card._dayCells[2].draft).toBeNull();
  cancel(card); expect(card._allCells().every(cell => !cell.draft)).toBe(true);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("a missing weekday or invalid destination blocks the entire selected batch without staging partial copies", () => {
  const {card, hass, config, update} = setup();
  card.setConfig({...config, rows: config.rows.map((row, i) => i === 2 ? {...row, days_entity: ""} : row)});
  control(card, "copy").open = true; control(card, "copy").dispatchEvent(new Event("toggle"));
  select(card, "copy-mode", "both"); choose(card, 1); choose(card, 2);
  expect(control(card, "copy-apply").disabled).toBe(true);
  expect(target(card, 2).parentElement.textContent).toContain("weekday entity");
  card._applyCopy(); expect(card._allCells().every(cell => !cell.draft)).toBe(true);
  select(card, "copy-mode", "times"); update("number.on_2", 0x1200, {s7_raw_word: true, min: 0x0600});
  expect(control(card, "copy-message").textContent).toContain("minimum");
  card._applyCopy(); expect(card._allCells().every(cell => !cell.draft)).toBe(true);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("invalid or conflicted sources cannot be copied; destination conflicts cannot be rebased by copying", () => {
  const {card, hass, update} = setup(); choose(card, 1);
  edit(card, 0, "99"); card._applyCopy(); expect(card._cells[2].draft).toBeNull();
  edit(card, 0, "05"); update("number.on_0", 0x0600); card._applyCopy(); expect(card._cells[2].draft).toBeNull();
  cancel(card); edit(card, 4, "09"); update("number.on_1", 1000);
  const draft = {...card._cells[2].draft}; card._applyCopy(); expect(card._cells[2].draft).toEqual(draft);
  expect(control(card, "copy-message").textContent).toContain("Value changed");
  expect(hass.callService).not.toHaveBeenCalled();
});

test("live preview preserves control focus, source changes exclude themselves, and Apply rechecks latest state", () => {
  const {card, update} = setup(); choose(card, 1); const checkbox = target(card, 1); checkbox.focus();
  update("number.on_1", 830); expect(checkbox.parentElement.textContent).toContain("08:30 → 04:00");
  expect(card.shadowRoot.activeElement).toBe(checkbox); expect(checkbox.checked).toBe(true);
  select(card, "copy-source", "1"); expect(checkbox.checked).toBe(false); expect(checkbox.parentElement.hidden).toBe(true);
  choose(card, 2);
  // Simulate a state change between the last rendered preview and the final click.
  card.hass.states["number.on_2"] = {state: "unavailable", attributes: {s7_raw_word: true}};
  card._applyCopy(); expect(card._allCells().every(cell => !cell.draft)).toBe(true);
});

test("pending saves block copy and presets; copied drafts retain normal remote conflict protection", async () => {
  const {card, hass, update} = setup(); select(card, "copy-mode", "days"); choose(card, 1); apply(card);
  update("number.days_1", 129); await save(card); expect(hass.callService).not.toHaveBeenCalled();
  cancel(card); preset(card, 1, 62); hass.callService.mockResolvedValue(); await save(card);
  expect(control(card, "copy-apply").disabled).toBe(true);
  expect(card.shadowRoot.querySelectorAll(".day-presets")[1].querySelector("button").disabled).toBe(true);
  card._applyCopy(); expect(card._dayCells[2].draft).toBeNull();
});
