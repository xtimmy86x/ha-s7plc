// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createEntry, createHass, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function freshPanel() {
  const Panel = customElements.get("s7plc-configuration-panel");
  const panel = new Panel();
  document.body.appendChild(panel);
  return panel;
}

describe("panel lifecycle", () => {
  test("loads entries and translations before rendering the selected PLC", async () => {
    const entry = createEntry();
    const translations = createPanel(entry).panelTranslations;
    document.body.replaceChildren();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => translations })));
    const panel = freshPanel();
    panel._narrow = true;
    panel._hass = createHass(entry);

    await panel.load();

    expect(panel._hass.callWS).toBeDefined();
    expect(fetch).toHaveBeenCalledWith("/s7plc_translations/en.json");
    expect(panel.entryId).toBe("plc-entry");
    expect(panel.querySelector(".plc-title b").textContent).toBe("CPU1211");
    expect(panel.querySelectorAll(".cards article")).toHaveLength(2);
    for (const menu of panel.querySelectorAll("ha-menu-button")) {
      expect(menu.hass).toBe(panel._hass);
      expect(menu.narrow).toBe(true);
    }
  });

  test("renders a Home Assistant alert when entry loading fails", async () => {
    const panel = freshPanel();
    panel._hass = { callWS: vi.fn(async () => { throw new Error("Unable to list PLCs"); }) };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));

    await panel.load();

    const alert = panel.querySelector('ha-alert[alert-type="error"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain("Unable to list PLCs");
    expect(panel.querySelector("ha-menu-button").hass).toBe(panel._hass);
  });

  test("switches PLC context and clears transient search and selection", () => {
    const first = createEntry();
    const second = createEntry({ entry_id: "second-plc", title: "CPU1511" });
    second.entities.sensors = [{ name: "Second temperature", address: "DB2,REAL0" }];
    second.entity_ids.sensors = ["sensor.second_temperature"];
    const panel = createPanel(first);
    panel.entries = [first, second];
    panel.searchQuery = "boiler";
    panel.selectedIndices.add(0);
    panel.render();
    const selector = panel.querySelector('[data-entry-selector]');

    selector.value = "second-plc";
    selector.dispatchEvent(new Event("change", { bubbles: true }));

    expect(panel.entryId).toBe("second-plc");
    expect(panel.searchQuery).toBe("");
    expect(panel.selectedIndices.size).toBe(0);
    expect(panel.querySelector(".plc-title b").textContent).toBe("CPU1511");
    expect(panel.querySelector(".details b").textContent).toBe("Second temperature");
  });

  test("updates entity state badges without rebuilding the panel", () => {
    const entry = createEntry();
    const panel = createPanel(entry);
    const article = panel.querySelector(".cards article");
    expect(article.querySelector(".state-badge").textContent).toContain("42.5");
    const nextHass = createHass(entry);
    nextHass.states["sensor.boiler_temperature"] = {
      state: "47.2",
      attributes: { unit_of_measurement: "°C" },
    };

    panel.hass = nextHass;

    expect(panel.querySelector(".cards article")).toBe(article);
    expect(article.querySelector(".state-badge").textContent).toContain("47.2");
  });

  test("cleans timers, search state, and open menus when disconnected", () => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.searchQuery = "pressure";
    panel._searchTimer = setTimeout(() => {}, 1000);
    panel._statusTimer = setInterval(() => {}, 1000);
    panel.querySelector("[data-overflow-toggle]").click();

    panel.disconnectedCallback();

    expect(panel.searchQuery).toBe("");
    expect(panel._searchTimer).toBeNull();
    expect(panel._statusTimer).toBeNull();
    expect(panel.querySelector(".entity-overflow-menu").hidden).toBe(true);
    vi.useRealTimers();
  });
});
