// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import {
  createEntry,
  createPanel,
  getPanelTestHelpers,
  installPanel,
} from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  globalThis.matchMedia = () => ({ matches: false });
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("compact panel header", () => {
  test("renders the PLC title as the switcher only when several PLCs exist", () => {
    const entry = createEntry();
    const panel = createPanel(entry);

    expect(panel.querySelector(".summary .plc-title b").textContent).toBe("CPU1211");
    expect(panel.querySelector("[data-entry-selector]")).toBeNull();
    const header = panel.querySelector(".page > header.summary.hero-summary");
    expect(header).not.toBeNull();
    expect(header.style.getPropertyValue("--s7plc-banner")).toContain("/s7plc_static/s7plc-header.png");
    expect(panel.querySelector(".hero-banner")).toBeNull();
    expect(header.querySelector(".plc-status .connection-badge + .plc-meta")).not.toBeNull();

    panel.entries = [entry, createEntry({ entry_id: "second-plc", title: "CPU1511" })];
    panel.render();
    const selector = panel.querySelector(".plc-switcher [data-entry-selector]");
    expect(selector).not.toBeNull();
    expect(selector.getAttribute("aria-label")).toBe("Select PLC");
    expect(panel.querySelectorAll("[data-entry-selector]")).toHaveLength(1);
    const switcher = panel.querySelector(".plc-switcher.multiple");
    expect(switcher.title).toBe("Select PLC");
    expect(switcher.querySelector(".plc-count").textContent).toBe("1/2");
    expect(switcher.querySelector('ha-icon[icon="mdi:unfold-more-horizontal"]')).not.toBeNull();
  });

  test("shows the current uptime in the connection badge", () => {
    const panel = createPanel();
    const changed = new Date(Date.now() - (2 * 3600 + 5 * 60) * 1000).toISOString();
    panel._hass.states["binary_sensor.cpu1211_connection"].last_changed = changed;
    panel.render();

    expect(panel.querySelector(".connection-badge-uptime").textContent).toBe("· 2h 5m");
    panel._hass.states["binary_sensor.cpu1211_connection"].state = "off";
    panel.render();
    expect(panel.querySelector(".connection-badge-uptime")).toBeNull();
  });

  test("keeps rarely used preferences inside the settings menu", () => {
    const panel = createPanel();
    const toggle = panel.querySelector("[data-settings-toggle]");
    const menu = panel.querySelector("[data-settings-menu]");

    expect(menu.hidden).toBe(true);
    expect(menu.querySelector("[data-default-address-mode]")).not.toBeNull();
    expect(menu.querySelector(".settings-footer .project-badge")).not.toBeNull();
    expect(panel.querySelector(".page > .default-address-mode")).toBeNull();

    toggle.click();
    expect(menu.hidden).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(menu.hidden).toBe(true);
    expect(document.activeElement).toBe(toggle);

    toggle.click();
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(menu.hidden).toBe(true);
  });

  test("focuses the search field with the slash shortcut outside text inputs", () => {
    const panel = createPanel();
    const event = new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true });

    document.body.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(panel.querySelector("#entity-search-input"));
    const typed = new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true });
    document.activeElement.dispatchEvent(typed);
    expect(typed.defaultPrevented).toBe(false);
  });
});

describe("entity list presentation", () => {
  test("persists the list density", () => {
    const panel = createPanel();

    expect(panel.querySelector(".cards").classList.contains("list-density")).toBe(false);
    panel.querySelector('[data-density="list"]').click();

    expect(localStorage.getItem("s7plc-panel-density")).toBe("list");
    expect(panel.querySelector(".cards").classList.contains("list-density")).toBe(true);
    expect(panel.querySelector('[data-density="list"]').getAttribute("aria-pressed")).toBe("true");
  });

  test("opens the editor when the card body is clicked", () => {
    const panel = createPanel();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});

    panel.querySelectorAll(".cards article")[1].querySelector(".details code").click();

    expect(openEditor).toHaveBeenCalledWith(1, "sensors");
    expect(panel.querySelector(".entity-actions")).toBeNull();
  });

  test("uses an explicit selection mode with a bulk action bar", () => {
    const panel = createPanel();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});

    expect(panel.querySelector("[data-bulk-bar]").hidden).toBe(true);
    panel.querySelector("[data-selection-toggle]").click();
    expect(panel.querySelector(".cards").classList.contains("selection-mode")).toBe(true);
    const bar = panel.querySelector("[data-bulk-bar]");
    expect(bar.hidden).toBe(false);
    expect(bar.querySelector("[data-bulk-count]").textContent).toBe("0 selected");

    panel.querySelector(".cards article .details").click();
    expect(openEditor).not.toHaveBeenCalled();
    expect(panel.querySelector('[data-select="0"]').checked).toBe(true);
    expect(bar.querySelector("[data-bulk-count]").textContent).toBe("1 selected");
    expect(bar.querySelector("[data-batch-delete]").hidden).toBe(false);

    bar.querySelector("[data-selection-cancel]").click();
    expect(panel.selectedIndices.size).toBe(0);
    expect(panel.querySelector("[data-bulk-bar]").hidden).toBe(true);
  });

  test("classifies state badges by meaning", () => {
    const { STATE_TONE } = getPanelTestHelpers();

    expect(STATE_TONE("sensor.a", { state: "42" })).toBe("active");
    expect(STATE_TONE("sensor.a", { state: "unavailable" })).toBe("warning");
    expect(STATE_TONE("sensor.a", undefined)).toBe("warning");
    expect(STATE_TONE("switch.a", { state: "off" })).toBe("neutral");
    expect(STATE_TONE("binary_sensor.a", { state: "on", attributes: { device_class: "problem" } })).toBe("error");
    expect(STATE_TONE("binary_sensor.a", { state: "off", attributes: { device_class: "problem" } })).toBe("neutral");
    expect(STATE_TONE("binary_sensor.a", { state: "on", attributes: { device_class: "door" } })).toBe("active");

    const panel = createPanel();
    const badge = panel.querySelector('.state-badge[data-entity-id="sensor.tank_pressure"]');
    expect(badge.classList.contains("tone-active")).toBe(true);
    panel._hass.states["sensor.tank_pressure"] = { state: "unavailable", attributes: {} };
    panel.updateStates();
    expect(badge.classList.contains("tone-warning")).toBe(true);
    expect(badge.classList.contains("tone-active")).toBe(false);
  });

  test("shortens self-describing chips and keeps the full text as a tooltip", () => {
    const entry = createEntry();
    entry.entities.sensors[0] = { ...entry.entities.sensors[0], scan_interval: 2 };
    const panel = createPanel(entry);
    const chips = [...panel.querySelector(".cards article .details > div").children];

    expect(chips.map((chip) => chip.textContent)).toEqual(["°C", "2 s"]);
    expect(chips[0].title).toBe("Unit of measurement: °C");
  });

  test("uses a sidebar for categories on wide layouts and marks empty categories", () => {
    const panel = createPanel();
    const layout = panel.querySelector(".category-layout");
    Object.defineProperty(layout, "clientWidth", { configurable: true, value: 1100 });

    panel.updateCategoryMode();

    expect(layout.classList.contains("sidebar-category-mode")).toBe(true);
    expect(panel.querySelector('[data-type="buttons"]').classList.contains("empty-category")).toBe(true);
    expect(panel.querySelector('[data-type="sensors"]').classList.contains("empty-category")).toBe(false);
  });

  test("collapses empty sections in the all-entities view", () => {
    const panel = createPanel();
    panel.setViewMode("sections");
    const empty = panel.querySelector('[data-section-type="buttons"]');

    expect(empty.classList.contains("empty-section")).toBe(true);
    expect(empty.querySelector("[data-section-toggle]").disabled).toBe(true);
    expect(empty.querySelector(".cards")).toBeNull();
    expect(empty.querySelector('[data-add="buttons"]')).not.toBeNull();
    expect(panel.querySelector('[data-section-type="sensors"] .cards')).not.toBeNull();
  });
});

describe("entity editor header", () => {
  test("names the entity, its type and PLC and offers section shortcuts", () => {
    const panel = createPanel();
    panel.openEditor(0, "switches");
    const dialog = document.body.querySelector("ha-dialog");

    expect(dialog.querySelector(".editor-intro h3").textContent).toBe("Circulation pump");
    expect(dialog.querySelector(".editor-intro .eyebrow").textContent).toBe("Switch · CPU1211");
    expect(dialog.querySelector(".editor-intro .mode-tabs")).not.toBeNull();
    const jump = dialog.querySelector(".section-jump");
    expect(jump.hidden).toBe(false);
    expect([...jump.querySelectorAll("button")].length)
      .toBe(dialog.querySelectorAll("form .form-section").length);

    dialog.querySelector('[data-mode="yaml"]').click();
    expect(jump.classList.contains("yaml-mode")).toBe(true);
  });

  test("shows the live value next to an unchanged main address", () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const form = document.body.querySelector("ha-dialog form");
    const builder = form.querySelector('[data-field="address"]');
    const live = builder.querySelector(".address-live");

    expect(live.hidden).toBe(false);
    expect(live.textContent).toContain("42.5 °C");

    const manual = builder.querySelector("[data-address-manual]");
    builder.querySelector('[data-address-mode="manual"]').click();
    manual.value = "DB1,R8";
    manual.dispatchEvent(new Event("input", { bubbles: true }));
    return Promise.resolve().then(() => expect(live.hidden).toBe(true));
  });

  test("uses the add label for a new entity", () => {
    const panel = createPanel();
    panel.openEditor(null, "sensors");

    expect(document.body.querySelector(".editor-intro h3").textContent).toBe("Add sensor");
    expect(document.body.querySelector(".address-live")).toBeNull();
  });
});

describe("connection availability", () => {
  test("explains unknown periods with a legend and the calculation basis", () => {
    const { BUILD_CONNECTION_AVAILABILITY } = getPanelTestHelpers();
    const panel = createPanel();
    const hour = 3_600_000;
    const now = Date.now();
    const result = BUILD_CONNECTION_AVAILABILITY([
      { state: "on", last_changed: new Date(now - 2 * hour).toISOString() },
    ], now);
    const host = document.createElement("div");

    host.innerHTML = panel.availabilityMarkup(result);

    const legend = [...host.querySelectorAll(".timeline-legend li")].map((item) => item.className);
    expect(legend).toEqual(["connected", "disconnected", "unknown"]);
    expect(host.querySelector(".timeline-legend .unknown").textContent).toContain("No data");
    expect(host.querySelector(".timeline-legend .unknown b").textContent).toBe("22h");
    expect(host.querySelectorAll(".availability-stats > div")).toHaveLength(3);
    expect(host.querySelector(".availability-stats dd").textContent).toBe("100%");
    expect(host.querySelector(".availability-stats small").textContent).toBe("based on 2h of data");
  });
});
