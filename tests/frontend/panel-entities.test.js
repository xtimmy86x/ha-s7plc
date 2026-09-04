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
