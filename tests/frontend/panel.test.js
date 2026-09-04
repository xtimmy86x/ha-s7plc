// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
  localStorage.clear();
});

describe("S7 PLC configuration panel", () => {
  test("renders entity cards and changes category through the real DOM", () => {
    const panel = createPanel();

    expect(panel.querySelector(".category-heading h2").textContent).toBe("Sensors");
    expect([...panel.querySelectorAll(".cards article .details > b")].map((node) => node.textContent)).toEqual([
      "Boiler temperature",
      "Tank pressure",
    ]);

    panel.querySelector('[data-type="switches"]').click();

    expect(panel.querySelector(".category-heading h2").textContent).toBe("Switches");
    expect(panel.querySelector(".cards article .details > b").textContent).toBe("Circulation pump");
    expect(panel.querySelector('[data-type="switches"]').classList.contains("active")).toBe(true);
  });

  test("filters cards after the debounce and clears the search interactively", async () => {
    vi.useFakeTimers();
    const panel = createPanel();
    const input = panel.querySelector("#entity-search-input");

    input.value = "pressure";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(150);

    expect([...panel.querySelectorAll(".cards article .details > b")].map((node) => node.textContent)).toEqual([
      "Tank pressure",
    ]);
    expect(panel.querySelector("#entity-search-results").textContent).toBe("1 result");

    panel.querySelector("[data-clear-search]").click();

    expect(panel.querySelectorAll(".cards article")).toHaveLength(2);
    expect(panel.querySelector("#entity-search-input").value).toBe("");
  });

  test("shows performance metrics only when they are enabled", () => {
    const entry = createEntry();
    const panel = createPanel(entry);

    panel.querySelector(".connection-badge").click();
    let dialog = document.body.querySelector("ha-dialog");

    expect(dialog.open).toBe(true);
    expect(dialog.querySelector(".section-connection")).not.toBeNull();
    expect(dialog.querySelector(".section-configuration")).not.toBeNull();
    expect(dialog.querySelector(".section-metrics")).toBeNull();
    dialog.remove();
    panel._connectionDialog = null;

    entry.data.enable_metrics = true;
    panel.render();
    panel.querySelector(".connection-badge").click();
    dialog = document.body.querySelector("ha-dialog");

    expect(dialog.querySelector(".section-metrics")).not.toBeNull();
    expect(dialog.querySelector(".section-metrics").textContent).toContain("Last cycle duration");
    expect(dialog.querySelector(".section-metrics").textContent).toContain("0.04 s");
  });
});
