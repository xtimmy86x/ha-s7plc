// @vitest-environment jsdom
import fs from "node:fs";
import {afterEach, beforeAll, expect, test, vi} from "vitest";

beforeAll(() => window.eval(fs.readFileSync("custom_components/s7plc/www/s7plc-schedule-card.js", "utf8")));
afterEach(() => {document.body.replaceChildren(); vi.restoreAllMocks(); vi.useRealTimers();});

function setup(count = 12) {
  const card = document.createElement("s7plc-schedule-card"), states = {}, rows = [];
  for (let i = 0; i < count; i++) {
    rows.push({name: `Fascia ${i + 1}`, on_entity: `number.on_${i}`, off_entity: `number.off_${i}`,
      ...(i % 2 === 0 ? {days_entity: `number.days_${i}`} : {})});
    states[`number.on_${i}`] = {state: "1024", attributes: {s7_raw_word: true}};
    states[`number.off_${i}`] = {state: "530", attributes: {s7_time_format: "hhmm"}};
    states[`number.days_${i}`] = {state: "190", attributes: {s7_raw_byte: true}};
  }
  const hass = {language: "it", states};
  const update = (id, value) => {
    hass.states = {...hass.states, [id]: {...hass.states[id], state: String(value)}};
    card.hass = {...hass};
  };
  hass.callService = vi.fn(async (_domain, _service, data) => update(data.entity_id, data.value));
  card.setConfig({rows, confirmation_timeout: 1, show_timeline: true}); card.hass = hass; document.body.append(card);
  return {card, hass, update};
}
const query = (card, selector) => card.shadowRoot.querySelector(selector);
const toggle = (card, index = 0) => card.shadowRoot.querySelectorAll(".slot-toggle")[index];
const summary = (card, index = 0) => card.shadowRoot.querySelectorAll(".slot-summary")[index];
const fields = (card, index = 0) => query(card, `#slot-times-${index}`);
const edit = (card, value, index = 0) => {
  const input = fields(card, index).querySelector("input"); input.focus(); input.value = value;
  input.dispatchEvent(new Event("input", {bubbles: true})); return input;
};
const click = (card, selector) => {const node = query(card, selector); node.focus(); node.click();};
const save = async card => {click(card, ".save"); await vi.waitFor(() => expect(card._saving).toBe(false));};

test("twelve slots start compact with mixed decoded times, optional weekdays and accessible disclosure controls", () => {
  const {card, hass} = setup();
  expect(card.shadowRoot.querySelectorAll(".slot-summary")).toHaveLength(12);
  for (let i = 0; i < 12; i++) {
    expect(toggle(card, i).tagName).toBe("BUTTON");
    expect(toggle(card, i).getAttribute("aria-expanded")).toBe("false");
    expect(fields(card, i).hidden).toBe(true);
    expect(summary(card, i).textContent).toContain(`Fascia ${i + 1}`);
    expect(summary(card, i).textContent).toContain("04:00");
    expect(summary(card, i).textContent).toContain("05:30");
    for (const id of toggle(card, i).getAttribute("aria-controls").split(" ")) expect(query(card, `#${id}`).hidden).toBe(true);
  }
  expect(summary(card).textContent).toContain("Lun, Mar, Mer, Gio, Ven");
  expect(summary(card, 1).textContent).toContain("nessuna entità giorni");
  const size = card.getCardSize(); toggle(card).click();
  expect(fields(card).hidden).toBe(false); expect(query(card, "#slot-days-0").hidden).toBe(false);
  expect(toggle(card).getAttribute("aria-expanded")).toBe("true");
  expect(fields(card, 1).hidden).toBe(true); expect(card.getCardSize()).toBeGreaterThan(size);
  toggle(card).click(); expect(card.getCardSize()).toBe(size);
  expect(hass.callService).not.toHaveBeenCalled();
});

test("closing an active edit finishes its field, keeps its draft and shows it until Cancel", async () => {
  const {card, hass} = setup(); toggle(card).click(); edit(card, "7");
  toggle(card).click(); await Promise.resolve();
  expect(card.shadowRoot.activeElement).toBe(toggle(card)); expect(fields(card).hidden).toBe(true);
  expect(summary(card).textContent).toContain("07:00"); expect(summary(card).textContent).toContain("Accensione: Modificato");
  expect(summary(card).hasAttribute("data-dirty")).toBe(true);
  toggle(card).click(); expect(fields(card).querySelector("input").value).toBe("07");
  toggle(card).click(); click(card, ".reset");
  expect(summary(card).textContent).toContain("04:00"); expect(summary(card).hasAttribute("data-dirty")).toBe(false);
  expect(fields(card).hidden).toBe(true); expect(hass.callService).not.toHaveBeenCalled();
});

test("bulk collapse retains edits in the last slot and Save includes closed slots", async () => {
  const {card, hass} = setup(); click(card, ".slots-expand");
  for (let i = 0; i < 12; i++) expect(fields(card, i).hidden).toBe(false);
  edit(card, "9", 11); click(card, ".slots-collapse"); await Promise.resolve();
  for (let i = 0; i < 12; i++) expect(fields(card, i).hidden).toBe(true);
  expect(card.shadowRoot.activeElement).toBe(query(card, ".slots-collapse"));
  expect(summary(card, 11).textContent).toContain("09:00");
  await save(card);
  expect(hass.callService).toHaveBeenCalledExactlyOnceWith("number", "set_value", {entity_id: "number.on_11", value: 0x0900});
  expect(summary(card, 11).hasAttribute("data-dirty")).toBe(false);
  expect(fields(card, 11).hidden).toBe(true);
});

test("HA updates preserve open slots, field nodes and focus while refreshing closed summaries", () => {
  const {card, update} = setup(); toggle(card).click(); const input = edit(card, "08"); input.setSelectionRange(1, 2);
  update("number.on_1", 0x0615); update("number.days_2", 0);
  expect(summary(card, 1).textContent).toContain("06:15"); expect(summary(card, 2).textContent).toContain("Nessun giorno");
  expect(fields(card).hidden).toBe(false); expect(fields(card, 1).hidden).toBe(true);
  expect(card.shadowRoot.activeElement).toBe(input); expect(input.selectionStart).toBe(1); expect(input.selectionEnd).toBe(2);
});

test("closed summaries expose invalid edits, external conflicts and unavailable times and days", () => {
  const {card, update} = setup(); toggle(card).click(); edit(card, "99"); toggle(card).click();
  expect(summary(card).textContent).toContain("Inserisci ore"); expect(summary(card).textContent).not.toContain("99:00");
  expect(summary(card).hasAttribute("data-error")).toBe(true); expect(query(card, ".save").disabled).toBe(true);
  click(card, ".reset"); toggle(card).click(); edit(card, "08"); toggle(card).click(); update("number.on_0", 0x0900);
  expect(summary(card).textContent).toContain("Valore cambiato in HA");
  update("number.off_1", "unavailable"); update("number.days_2", "unavailable");
  expect(summary(card, 1).textContent).toContain("Spegnimento: Non disponibile");
  expect(summary(card, 2).textContent).toContain("Giorni: Non disponibile");
  expect(summary(card, 1).querySelectorAll(".slot-clock")[1].textContent).toBe("—");
});

test("closed summaries expose sending, pending and timeout feedback without opening or losing drafts", async () => {
  const {card, hass} = setup(1); toggle(card).click(); edit(card, "08"); toggle(card).click();
  let finish; hass.callService.mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  click(card, ".save"); expect(summary(card).textContent).toContain("Accensione: Invio");
  finish(); await vi.waitFor(() => expect(card._saving).toBe(false));
  expect(summary(card).textContent).toContain("In attesa di HA");
  vi.useFakeTimers(); vi.setSystemTime(Date.now() + 2000); card.hass = {...hass};
  expect(summary(card).textContent).toContain("non confermato"); expect(summary(card).hasAttribute("data-error")).toBe(true);
  expect(fields(card).hidden).toBe(true); expect(summary(card).textContent).toContain("08:00");
});

test("failed writes remain visible in closed slots and collapsing never retries them", async () => {
  const {card, hass} = setup(1); toggle(card).click(); edit(card, "08"); toggle(card).click();
  hass.callService.mockRejectedValue(new Error("PLC offline")); await save(card);
  expect(summary(card).textContent).toContain("Scrittura fallita: PLC offline");
  expect(summary(card).hasAttribute("data-error")).toBe(true);
  toggle(card).click(); toggle(card).click();
  expect(hass.callService).toHaveBeenCalledTimes(1); expect(summary(card).textContent).toContain("08:00");
});

test("copy and weekday presets update closed summaries and explicit Save preserves bit 7", async () => {
  const {card, hass} = setup(3); toggle(card).click();
  query(card, ".day-presets [data-mask='65']").click(); toggle(card).click();
  expect(summary(card).textContent).toContain("Sab, Dom");
  const details = query(card, ".copy"); details.open = true; details.dispatchEvent(new Event("toggle"));
  const mode = query(card, ".copy-mode"); mode.value = "days"; mode.dispatchEvent(new Event("change"));
  query(card, ".copy input[data-index='2']").click(); click(card, ".copy-apply");
  expect(summary(card, 2).textContent).toContain("Sab, Dom"); expect(summary(card, 2).textContent).toContain("Giorni: Modificato");
  expect(fields(card, 2).hidden).toBe(true); expect(hass.callService).not.toHaveBeenCalled();
  await save(card);
  expect(hass.callService.mock.calls.map(call => call[2])).toEqual([
    {entity_id: "number.days_0", value: 193}, {entity_id: "number.days_2", value: 193},
  ]);
  expect(summary(card, 2).hasAttribute("data-dirty")).toBe(false);
});

test("single and empty cards omit bulk controls; idle localization preserves expansion and setConfig resets it", () => {
  const {card, hass} = setup(1); expect(query(card, ".slot-actions")).toBeNull(); toggle(card).click(); toggle(card).blur();
  card.hass = {...hass, language: "en"}; expect(toggle(card).getAttribute("aria-expanded")).toBe("true");
  expect(summary(card).textContent).toContain("Days: Mon");
  card.setConfig({rows: [{on_entity: "number.on_0", off_entity: "number.off_0"}]});
  expect(toggle(card).getAttribute("aria-expanded")).toBe("false");
  card.setConfig({rows: []}); expect(query(card, ".slot-summary")).toBeNull(); expect(query(card, ".slot-actions")).toBeNull();
});
