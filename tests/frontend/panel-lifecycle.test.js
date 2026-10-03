// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import {
  createEntry,
  createHass,
  createPanel,
  evaluatePanelSource,
  getTranslations,
  installPanel,
} from "./panel-fixture.js";

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
  test("reuses one custom-element registration across repeated installs", () => {
    const registered = customElements.get("s7plc-configuration-panel");

    evaluatePanelSource();
    evaluatePanelSource();

    expect(customElements.get("s7plc-configuration-panel")).toBe(registered);
  });

  test.each([
    {
      locale: "it-IT",
      responses: { it: getTranslations("it") },
      urls: ["/s7plc_translations/it.json"],
      title: "Configurazione S7 PLC",
      field: "Nome",
    },
    {
      locale: "fr-FR",
      responses: { en: getTranslations("en") },
      urls: ["/s7plc_translations/en.json"],
      title: "S7 PLC configuration",
      field: "Name",
    },
    {
      locale: "de-DE",
      responses: { en: getTranslations("en") },
      urls: ["/s7plc_translations/de.json", "/s7plc_translations/en.json"],
      title: "S7 PLC configuration",
      field: "Name",
    },
  ])("loads translations and safely falls back for $locale", async ({
    locale, responses, urls, title, field,
  }) => {
    const panel = freshPanel();
    panel._hass = { locale: { language: locale } };
    const requested = [];
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async (url) => {
      requested.push(url);
      const language = url.match(/\/([^/]+)\.json$/)[1];
      return language in responses
        ? { ok: true, json: async () => responses[language] }
        : { ok: false, status: 503 };
    }));

    await panel.loadPanelTranslations();

    expect(requested).toEqual(urls);
    for (const url of urls) expect(fetch).toHaveBeenCalledWith(url, { cache: "no-cache" });
    expect(panel.t("common.title")).toBe(title);
    expect(panel.fieldText("sensors", "name", "label")).toBe(field);
    expect(warning).toHaveBeenCalledTimes(urls.length - 1);
  });

  test("revalidates translations using both the integration version and frontend build", async () => {
    const panel = freshPanel();
    panel._hass = { language: "it" };
    panel.panel = { config: { version: "7.5.1", frontend_build: "20261003.2" } };
    const current = getTranslations("it");
    const stale = structuredClone(current);
    delete stale.config_panel.control_behavior.options.single_fire;
    vi.stubGlobal("fetch", vi.fn(async (url, options) => ({
      ok: true,
      json: async () => options?.cache === "no-cache" && url.endsWith("?v=7.5.1&build=20261003.2") ? current : stale,
    })));

    await panel.loadPanelTranslations();

    expect(fetch).toHaveBeenCalledWith(
      "/s7plc_translations/it.json?v=7.5.1&build=20261003.2", { cache: "no-cache" },
    );
    expect(panel.t("control_behavior.options.single_fire.title")).toBe("Comando singolo");
  });

  test("uses the same cache version when falling back to English", async () => {
    const panel = freshPanel();
    panel._hass = { language: "de" };
    panel.panel = { config: { version: "7.5.1", frontend_build: "20261003.2" } };
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async url => url.includes("/de.json")
      ? { ok: false, status: 503 }
      : { ok: true, json: async () => getTranslations("en") }));

    await panel.loadPanelTranslations();

    expect(fetch.mock.calls).toEqual([
      ["/s7plc_translations/de.json?v=7.5.1&build=20261003.2", { cache: "no-cache" }],
      ["/s7plc_translations/en.json?v=7.5.1&build=20261003.2", { cache: "no-cache" }],
    ]);
    expect(panel.t("control_behavior.options.single_fire.title")).toBe("Single-fire control");
  });

  test("refreshes loaded translations when panel metadata arrives or its build changes", async () => {
    const panel = createPanel();
    vi.stubGlobal("fetch", vi.fn(async url => {
      const translations = getTranslations("en");
      translations.config_panel.common.title = url.includes("build=second") ? "Updated panel" : "Initial panel";
      return { ok: true, json: async () => translations };
    }));
    panel.panel = { config: { version: "7.5.1", frontend_build: "first" } };
    await vi.waitFor(() => expect(panel.t("common.title")).toBe("Initial panel"));
    panel.panel = { config: { version: "7.5.1", frontend_build: "second" } };
    await vi.waitFor(() => expect(panel.t("common.title")).toBe("Updated panel"));
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "/s7plc_translations/en.json?v=7.5.1&build=first",
      "/s7plc_translations/en.json?v=7.5.1&build=second",
    ]);
    panel.panel = { config: { version: "7.5.1", frontend_build: "second" } };
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  test("a slow old request cannot replace translations for a newer build", async () => {
    const panel = createPanel();
    let finishOld;
    vi.stubGlobal("fetch", vi.fn(url => {
      const translations = getTranslations("en");
      translations.config_panel.common.title = url.includes("build=new") ? "New panel" : "Old panel";
      const response = { ok: true, json: async () => translations };
      return url.includes("build=new") ? Promise.resolve(response)
        : new Promise(resolve => { finishOld = () => resolve(response); });
    }));
    const oldRequest = panel.loadPanelTranslations();
    panel.panel = { config: { version: "7.5.1", frontend_build: "new" } };
    await vi.waitFor(() => expect(panel.t("common.title")).toBe("New panel"));
    finishOld();
    await oldRequest;
    expect(panel.t("common.title")).toBe("New panel");
  });

  test("renders the repository badge with an optional integration version", () => {
    const panel = createPanel();
    vi.spyOn(panel, "loadPanelTranslations").mockResolvedValue();

    panel.panel = { config: { version: "7.3.0" } };
    let badge = panel.querySelector(".project-badge");
    expect(badge.href).toBe("https://github.com/xtimmy86x/ha-s7plc");
    expect(badge.target).toBe("_blank");
    expect(badge.rel).toBe("noopener noreferrer");
    expect(badge.getAttribute("aria-label")).toBe("Open ha-s7plc on GitHub");
    expect(badge.querySelector('ha-icon[icon="mdi:github"]')
      .getAttribute("aria-hidden")).toBe("true");
    expect(badge.textContent).toContain("@xtimmy86x");
    expect(badge.textContent).toContain("v7.3.0");

    panel.panel = { config: {} };
    badge = panel.querySelector(".project-badge");
    expect(badge.textContent).toContain("@xtimmy86x");
    expect(badge.textContent).not.toMatch(/v(?:undefined|null)/);
  });

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
    expect(fetch).toHaveBeenCalledWith("/s7plc_translations/en.json", { cache: "no-cache" });
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
