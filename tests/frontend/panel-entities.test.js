// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("entity views and actions", () => {
  test("renders type-specific main addresses without duplicate chips", () => {
    const entry = createEntry();
    entry.entities.covers = [
      { name: "<Kitchen & blind>", open_command_address: "DB1,X0.0", close_command_address: "DB1,X0.1" },
      { position_state_address: "DB1,BYTE2", position_command_address: "DB1,BYTE3" },
      { close_command_address: "DB1,X0.5" },
    ];
    const panel = createPanel(entry);
    panel.type = "covers";
    panel.render();
    const cards = [...panel.querySelectorAll(".cards article")];

    expect(cards[0].querySelector(".details > b").textContent).toBe("<Kitchen & blind>");
    expect(cards[0].querySelector(".details > code").textContent).toBe("DB1,X0.0");
    expect(cards[0].querySelector(".details > div").textContent).not.toContain("DB1,X0.0");
    expect(cards[0].querySelector(".details > b").children).toHaveLength(0);
    expect(cards[1].querySelector(".details > b").textContent).toBe("DB1,BYTE2");
    expect(cards[1].querySelector(".details > code").textContent).toBe("DB1,BYTE2");
    expect(cards[1].querySelector(".details > div").textContent).not.toContain("DB1,BYTE2");
    expect(cards[2].querySelector(".details > b").textContent).toBe("Entity 3");
    expect(cards[2].querySelector(".details > code").textContent).toBe("—");
  });

  test("prioritizes conversion chips and renders bounded overflow as text", () => {
    const entry = createEntry();
    entry.entities.buttons = [{
      name: "Conversion test",
      address: "DB1,X0.0",
      property_1: "hidden-1",
      value_conversions: Object.fromEntries(
        ["a", "b", "c", "d", "e"].map((channel) => [channel, { type: "expression" }]),
      ),
    }];
    const panel = createPanel(entry);
    panel.type = "buttons";
    panel.render();
    const details = panel.querySelector(".cards article .details");
    const conversions = [...details.querySelectorAll(".conversion-chip")];
    const overflow = details.querySelector(".chip-overflow");

    expect(conversions).toHaveLength(5);
    expect(conversions.map((chip) => chip.textContent)).toEqual([
      "A · Custom expression", "B · Custom expression", "C · Custom expression",
      "D · Custom expression", "E · Custom expression",
    ]);
    expect(conversions.every((chip) => chip.tabIndex === 0)).toBe(true);
    expect(overflow.textContent).toBe("+1");
    expect(overflow.title).toBe("1 more property");
    expect(overflow.getAttribute("aria-label")).toBe("1 more property");
    expect(overflow.matches("button, [role], [tabindex]")).toBe(false);
    expect(details.textContent).not.toContain("Property 1");
  });

  test("renders known conversion summaries in channel order", () => {
    const entry = createEntry();
    entry.entities.covers = [{
      name: "Converted cover",
      position_state_address: "DB1,BYTE0",
      value_conversions: {
        tilt: { type: "multiplier", factor: 10 },
        position: { type: "linear_scale", plc_min: 0, plc_max: 27648, ha_min: 0, ha_max: 100 },
        status: { type: "linear_scale", plc_min: 0, plc_max: 10, ha_min: 0, ha_max: 1, clamp: true },
      },
    }];
    const panel = createPanel(entry);
    panel.type = "covers";
    panel.render();
    const chips = [...panel.querySelectorAll(".conversion-chip")];

    expect(chips.map((chip) => chip.textContent)).toEqual([
      "Position · Scale 0–27648 → 0–100",
      "Cover status · Scale 0–10 → 0–1 · Clamped",
      "Tilt · Multiplier × 10",
    ]);
    expect(chips.map((chip) => chip.title)).toEqual([
      "Position: Scale 0–27648 → 0–100",
      "Cover status: Scale 0–10 → 0–1 · Clamped",
      "Tilt: Multiplier × 10",
    ]);

    entry.entities.entity_sync = [{
      name: "LOGO time",
      address: "DB1,WORD0",
      value_conversions: { value: { type: "logo_time_bcd" } },
    }];
    panel.type = "entity_sync";
    panel.render();
    expect(panel.querySelector(".conversion-chip").textContent).toBe("LOGO! time (BCD)");

    entry.entities.lights = [{
      name: "Expression light",
      state_address: "DB1,X2.0",
      brightness_state_address: "DB1,BYTE2",
      value_conversions: { brightness: { type: "expression", read_expression: "<script>" } },
    }];
    panel.type = "lights";
    panel.render();
    expect(panel.querySelector(".conversion-chip").textContent).toBe("Custom expression");
  });

  test("ignores malformed and legacy card metadata while escaping summaries", () => {
    const entry = createEntry();
    entry.entities.sensors = [
      { name: "Malformed", address: "DB1,REAL0", value_conversions: null, options: { nested: true } },
      { name: "Escaped", address: "DB1,REAL4", value_conversions: { unknown: { type: "multiplier", factor: "<5>" } } },
      {
        name: "Legacy",
        address: "DB1,REAL8",
        min_value: 0,
        max_value: 100,
        scale_raw_min: 0,
        scale_raw_max: 27648,
        value_multiplier: 2,
        brightness_scale: 255,
        value_conversions: {
          value: { type: "linear_scale", plc_min: 0, plc_max: 27648, ha_min: 0, ha_max: 100 },
        },
      },
    ];
    const panel = createPanel(entry);
    const cards = [...panel.querySelectorAll(".cards article")];

    expect(cards[0].querySelector(".details > div").textContent).toBe("");
    expect(cards[0].textContent).not.toContain("[object Object]");
    const escaped = cards[1].querySelector(".conversion-chip");
    expect(escaped.textContent).toBe("Multiplier × <5>");
    expect(escaped.children).toHaveLength(0);
    expect(cards[2].querySelector(".details > div").textContent).toBe("Scale 0–27648 → 0–100");
    expect(cards[2].textContent).not.toMatch(/Min Value|Max Value|Scale Raw|Value Multiplier|Brightness Scale/);

    entry.entities.numbers = [{ name: "Limited", address: "DB1,INT0", min_value: -10, max_value: 10 }];
    panel.type = "numbers";
    panel.render();
    expect(panel.querySelector(".details > div").textContent).toContain("Minimum limit: -10");
    expect(panel.querySelector(".details > div").textContent).toContain("Maximum limit: 10");
  });

  test("switches between category and all-entities views and persists the choice", () => {
    const panel = createPanel();
    const toggle = panel.querySelector("[data-layout-toggle]");

    expect(toggle.getAttribute("aria-label")).toBe("Switch to all-entities view");
    toggle.click();

    expect(localStorage.getItem("s7plc-panel-view-mode")).toBe("sections");
    expect(panel.querySelectorAll("[data-section-type]")).toHaveLength(11);
    expect(panel.querySelector("[data-layout-toggle]").getAttribute("aria-label")).toBe("Switch to category view");
    const switchSection = panel.querySelector('[data-section-type="switches"]');
    expect(switchSection.querySelector(".cards article")).not.toBeNull();

    switchSection.querySelector("[data-section-toggle]").click();

    expect(panel.querySelector('[data-section-type="switches"] [data-section-toggle]').getAttribute("aria-expanded")).toBe("false");
    expect(panel.querySelector('[data-section-type="switches"] .cards')).toBeNull();
  });

  test("groups selected entities and completes one batch-delete lifecycle", async () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const sensor = panel.querySelector('[data-section-type="sensors"] [data-select="1"]');
    const targetSwitch = panel.querySelector('[data-section-type="switches"] [data-select="0"]');

    sensor.checked = true;
    sensor.dispatchEvent(new Event("change", { bubbles: true }));
    targetSwitch.checked = true;
    targetSwitch.dispatchEvent(new Event("change", { bubbles: true }));

    const bulk = panel.querySelector("[data-batch-delete-global]");
    expect(bulk.hidden).toBe(false);
    expect(bulk.textContent).toContain("(2)");
    expect(sensor.closest("article").classList.contains("selected")).toBe(true);

    const calls = [];
    panel._hass.callWS = async (message) => calls.push(message);
    panel.load = vi.fn(async () => {});
    bulk.click();
    const dialog = document.body.querySelector("ha-dialog");
    await dialog.querySelector('[slot="primaryAction"]').onclick();

    expect(calls).toEqual([
      { type: "s7plc/config/delete_entity", entry_id: "plc-entry", entity_type: "sensors", index: 1 },
      { type: "s7plc/config/delete_entity", entry_id: "plc-entry", entity_type: "switches", index: 0 },
    ]);
    expect(panel.selectedIndices.size).toBe(0);
    expect(panel.load).toHaveBeenCalledOnce();
    expect(dialog.open).toBe(false);
  });

  test("keeps the batch dialog open and prevents retries after a partial failure", async () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const inputs = [
      panel.querySelector('[data-section-type="sensors"] [data-select="0"]'),
      panel.querySelector('[data-section-type="sensors"] [data-select="1"]'),
      panel.querySelector('[data-section-type="switches"] [data-select="0"]'),
    ];
    for (const input of inputs) {
      input.checked = true;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    let attempts = 0;
    panel._hass.callWS = async () => {
      attempts += 1;
      if (attempts === 2) throw new Error("PLC offline");
    };
    panel.load = vi.fn(async () => {});
    panel.querySelector("[data-batch-delete-global]").click();
    const dialog = document.body.querySelector("ha-dialog");
    const primary = dialog.querySelector('[slot="primaryAction"]');

    await primary.onclick();
    await primary.onclick();

    expect(attempts).toBe(2);
    expect(panel.load).toHaveBeenCalledOnce();
    expect(dialog.open).toBe(true);
    expect(primary.disabled).toBe(true);
    expect(dialog.querySelector("ha-alert").textContent).toContain("PLC offline");
    expect(dialog.querySelector("ha-alert").style.display).toBe("block");
  });

  test("uses the original entity index for duplicate actions after filtering", () => {
    const entry = createEntry();
    entry.entities.sensors[1].uid = "pressure-uid";
    const panel = createPanel(entry);
    panel.searchQuery = "pressure";
    panel.render();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});

    panel.querySelector('.entity-actions [data-entity-action="duplicate"]').click();

    expect(openEditor).toHaveBeenCalledOnce();
    const [index, type, draft] = openEditor.mock.calls[0];
    expect(index).toBeNull();
    expect(type).toBe("sensors");
    expect(draft.name).toBe("Tank pressure");
    expect(draft.uid).toBe("pressure-uid");
  });

  test("opens the card overflow menu, handles Escape, and reuses entity actions", () => {
    const panel = createPanel();
    const toggle = panel.querySelector("[data-overflow-toggle]");
    const article = toggle.closest("article");
    const menu = article.querySelector(".entity-overflow-menu");

    toggle.click();

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(menu.hidden).toBe(false);
    expect(article.classList.contains("overflow-open")).toBe(true);
    expect(document.activeElement.getAttribute("role")).toBe("menuitem");

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(menu.hidden).toBe(true);
    expect(article.classList.contains("overflow-open")).toBe(false);
    expect(document.activeElement).toBe(toggle);

    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});
    toggle.click();
    menu.querySelector('[data-entity-action="edit"]').click();
    expect(openEditor).toHaveBeenCalledWith(0, "sensors");
    expect(menu.hidden).toBe(true);
  });
});
