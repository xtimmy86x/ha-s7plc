// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createPanel, getPanelTestHelpers, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.replaceChildren();
  localStorage.clear();
});

describe("panel entity search", () => {
  test.each(["tabs", "sections"])("keeps the input, focus and selection during filtering in %s view", async (view) => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.setViewMode(view);
    const input = panel.querySelector("#entity-search-input");
    input.focus();
    const focus = vi.spyOn(input, "focus");
    const render = vi.spyOn(panel, "render");

    for (const query of ["pre", "pressure", "no-match", ""]) {
      input.value = query;
      input.setSelectionRange(0, Math.min(2, query.length));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await vi.advanceTimersByTimeAsync(150);

      expect(panel.querySelector("#entity-search-input")).toBe(input);
      expect(input.isConnected).toBe(true);
      expect(document.activeElement).toBe(input);
      expect(input.selectionStart).toBe(0);
      expect(input.selectionEnd).toBe(Math.min(2, query.length));
    }
    expect(render).not.toHaveBeenCalled();
    expect(focus).not.toHaveBeenCalled();
    expect(panel.querySelectorAll(".cards article")).toHaveLength(view === "tabs" ? 2 : 3);
  });

  test("filters cards after the debounce and clears the search interactively", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    const input = panel.querySelector("#entity-search-input");

    input.value = "  PRESSURE  ";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(150);

    expect([...panel.querySelectorAll(".cards article .details > b")].map((node) => node.textContent)).toEqual([
      "Tank pressure",
    ]);
    expect(panel.querySelector("#entity-search-results").textContent).toBe("1 result");
    expect(panel.querySelector('[data-entity-action="edit"]').dataset.entityIndex).toBe("1");

    panel.querySelector("[data-clear-search]").click();

    expect(panel.querySelectorAll(".cards article")).toHaveLength(2);
    expect(panel.querySelector("#entity-search-input").value).toBe("");
  });

  test("indexes addresses, metadata, mappings, numeric values, and runtime state", () => {
    const { ENTITY_SEARCH_TEXT, FILTER_ENTITY_ITEMS } = getPanelTestHelpers();
    const entity = {
      name: "Supply pressure",
      address: "DB1,R4",
      command_address: "DB2,W8",
      extra_addresses: ["I0.1", "Q0.2"],
      area: "Plant room",
      device_class: "pressure",
      state_class: "measurement",
      unit_of_measurement: "bar",
      scale: 12.5,
      value_conversions: {
        value: {
          type: "enum_map",
          mappings: [{ value: 0, label: "Stopped" }, { value: 1, label: "Running" }],
        },
      },
      _cache: "secret",
      uid: "technical-only",
    };
    const text = ENTITY_SEARCH_TEXT(entity, 42);

    for (const value of ["supply pressure", "db1,r4", "db2,w8", "i0.1", "q0.2", "plant room", "measurement", "12.5", "stopped", "running", "42"]) {
      expect(text).toContain(value);
    }
    expect(text).not.toContain("secret");
    expect(text).not.toContain("technical-only");
    expect([...FILTER_ENTITY_ITEMS([entity, undefined], " PRESSURE ")].map((item) => item.index)).toEqual([0]);
  });

  test.each(["tabs", "sections"])("refreshes live search results without replacing the input in %s view", (view) => {
    const panel = createPanel();
    panel.setViewMode(view);
    panel.searchQuery = "42.5";
    panel.render();
    const input = panel.querySelector("#entity-search-input");
    input.focus();
    input.setSelectionRange(2, 4);
    const focus = vi.spyOn(input, "focus");
    expect(panel.querySelectorAll(".cards article")).toHaveLength(1);

    panel.hass = {
      ...panel._hass,
      states: {
        ...panel._hass.states,
        "sensor.boiler_temperature": {
          state: "19.0",
          attributes: { unit_of_measurement: "°C" },
        },
      },
    };

    expect(panel.querySelectorAll(".cards article")).toHaveLength(0);
    expect(panel.querySelector(".search-empty")).not.toBeNull();
    expect(panel.querySelector("#entity-search-input")).toBe(input);
    expect(focus).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(panel.querySelector("#entity-search-input"));
    expect(panel.querySelector("#entity-search-input").selectionStart).toBe(2);
    expect(panel.querySelector("#entity-search-input").selectionEnd).toBe(4);
  });

  test("searches globally in sections view and renders only matching sections", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const input = panel.querySelector("#entity-search-input");

    input.value = "pump";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(150);

    expect(panel.querySelector('[data-section-type="sensors"]')).toBeNull();
    expect(panel.querySelector('[data-section-type="switches"]')).not.toBeNull();
    expect(panel.querySelector('[data-section-type="switches"] .details > b').textContent).toBe("Circulation pump");
    expect(panel.querySelector("#entity-search-results").textContent).toBe("1 result");
  });

  test.each(["tabs", "sections"])("preserves pending text when live results change in %s view", async (view) => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.setViewMode(view);
    panel.searchQuery = "42.5";
    panel.render();
    const input = panel.querySelector("#entity-search-input");
    input.focus();
    input.value = "  pressure ";
    input.setSelectionRange(3, 5);
    input.dispatchEvent(new Event("input", { bubbles: true }));

    panel.hass = {
      ...panel._hass,
      states: { ...panel._hass.states, "sensor.boiler_temperature": { state: "19", attributes: {} } },
    };

    expect(panel.querySelector("#entity-search-input")).toBe(input);
    expect(input.value).toBe("  pressure ");
    expect(input.selectionStart).toBe(3);
    expect(input.selectionEnd).toBe(5);
    await vi.advanceTimersByTimeAsync(150);
    expect(panel.searchQuery).toBe("pressure");
    expect(input.value).toBe("  pressure ");
    expect(document.activeElement).toBe(input);
    expect(panel.querySelector(".cards article .details > b").textContent).toBe("Tank pressure");
    expect(panel.querySelector("#entity-search-results").textContent).toBe("1 result");
  });

  test.each(["tabs", "sections"])("clears results without replacing the input in %s view", async (view) => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.setViewMode(view);
    const input = panel.querySelector("#entity-search-input");
    input.focus();

    for (const action of ["button", "escape", "empty"]) {
      input.value = "no-match";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await vi.advanceTimersByTimeAsync(150);
      expect(panel.querySelector("#entity-search-results").textContent).toBe("0 results");
      expect(panel.querySelector(".entity-search [data-clear-search]").hidden).toBe(false);

      if (action === "escape") input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      else panel.querySelector(action === "empty" ? ".search-empty [data-clear-search]" : ".entity-search [data-clear-search]").click();

      expect(panel.querySelector("#entity-search-input")).toBe(input);
      expect(input.value).toBe("");
      expect(panel.querySelectorAll(".cards article")).toHaveLength(view === "tabs" ? 2 : 3);
      expect(panel.querySelector("#entity-search-results").textContent).toBe("");
      expect(panel.querySelector(".entity-search [data-clear-search]").hidden).toBe(true);
      if (action !== "empty") expect(document.activeElement).toBe(input);
    }
  });

  test.each(["tabs", "sections"])("keeps card actions and bulk selection working after filtering in %s view", async (view) => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.setViewMode(view);
    const editor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});
    const bulkEdit = vi.spyOn(panel, "editSelection").mockImplementation(() => {});
    const input = panel.querySelector("#entity-search-input");

    for (const query of ["pre", "pressure"]) {
      input.value = query;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await vi.advanceTimersByTimeAsync(150);
    }
    panel.querySelector(".cards article").click();
    expect(editor).toHaveBeenCalledExactlyOnceWith(1, "sensors");
    panel.querySelector("[data-overflow-toggle]").click();
    expect(panel.querySelector(".entity-overflow-menu").hidden).toBe(false);
    panel.querySelector('[data-entity-action="duplicate"]').click();
    expect(editor).toHaveBeenLastCalledWith(null, "sensors", expect.objectContaining({ name: "Tank pressure" }));

    const checkbox = panel.querySelector("[data-select]");
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    panel.clearSearch();
    expect(panel.querySelector('[data-select="1"][data-entity-type="sensors"]').checked).toBe(true);
    panel.querySelector("[data-batch-edit]").click();
    expect(bulkEdit).toHaveBeenCalledOnce();
    expect(panel.selectedIndicesFor("sensors")).toEqual([1]);
  });

  test("does not steal focus when a pending search completes", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    const input = panel.querySelector("#entity-search-input");
    input.focus();
    input.value = "pressure";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const other = document.createElement("input");
    document.body.appendChild(other);
    other.focus();

    await vi.advanceTimersByTimeAsync(150);

    expect(document.activeElement).toBe(other);
    expect(panel.querySelector(".details > b").textContent).toBe("Tank pressure");
  });

  test("cancels a pending search when changing PLC context", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.entries.push({ ...panel.entries[0], entry_id: "second", title: "Second PLC" });
    panel.render();
    const input = panel.querySelector("#entity-search-input");
    input.value = "pressure";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const selector = panel.querySelector("[data-entry-selector]");
    selector.value = "second";
    selector.dispatchEvent(new Event("change", { bubbles: true }));

    await vi.advanceTimersByTimeAsync(150);

    expect(panel.entryId).toBe("second");
    expect(panel.searchQuery).toBe("");
    expect(panel.querySelector("#entity-search-input").value).toBe("");
    expect(panel.querySelectorAll(".cards article")).toHaveLength(2);
  });

  test("restores collapsed sections and their handlers after clearing search", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    panel.setViewMode("sections");
    panel.querySelector('[data-section-toggle="sensors"]').click();
    const input = panel.querySelector("#entity-search-input");
    input.value = "pressure";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(150);
    expect(panel.querySelector('[data-section-type="sensors"] .cards')).not.toBeNull();

    panel.clearSearch();
    expect(panel.querySelector('[data-section-type="sensors"] .cards')).toBeNull();
    panel.querySelector('[data-section-toggle="sensors"]').click();
    expect(panel.querySelectorAll('[data-section-type="sensors"] .cards article')).toHaveLength(2);
    const editor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});
    panel.querySelector('[data-section-type="sensors"] [data-add]').click();
    expect(editor).toHaveBeenCalledExactlyOnceWith(null, "sensors");
  });
});
