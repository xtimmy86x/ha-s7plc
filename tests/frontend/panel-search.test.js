// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createPanel, getPanelTestHelpers, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
  localStorage.clear();
});

describe("panel entity search", () => {
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

  test("refreshes active search results from live states without losing focus", () => {
    const panel = createPanel();
    panel.searchQuery = "42.5";
    panel.render();
    const input = panel.querySelector("#entity-search-input");
    input.focus();
    input.setSelectionRange(2, 4);
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
});
