// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createPanel, installPanel } from "./panel-fixture.js";

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

describe("panel category navigation", () => {
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

  test("selects single-row, wrapped, and compact modes from measured rows", () => {
    const panel = createPanel();
    const layout = panel.querySelector(".category-layout");
    const nav = panel.querySelector(".category-tabs");
    const buttons = [...nav.querySelectorAll("button[data-type]")];
    let scrollWidth = 500;
    let clientWidth = 500;
    let rowTops = buttons.map(() => 0);

    Object.defineProperties(nav, {
      scrollWidth: { configurable: true, get: () => scrollWidth },
      clientWidth: { configurable: true, get: () => clientWidth },
    });
    buttons.forEach((button, index) => Object.defineProperty(button, "offsetTop", {
      configurable: true,
      get: () => rowTops[index],
    }));

    panel.updateCategoryMode();
    expect(layout.classList.contains("single-row-category-mode")).toBe(true);

    scrollWidth = 800;
    rowTops = buttons.map((_, index) => index < 6 ? 0 : 40);
    panel.updateCategoryMode();
    expect(layout.classList.contains("wrapped-category-mode")).toBe(true);

    rowTops = buttons.map((_, index) => Math.floor(index / 4) * 40);
    panel.updateCategoryMode();
    expect(layout.classList.contains("compact-category-mode")).toBe(true);

    clientWidth = 800;
    panel.updateCategoryMode();
    expect(layout.classList.contains("single-row-category-mode")).toBe(true);
  });

  test("keeps touch navigation scrollable and reveals the active category", () => {
    const panel = createPanel();
    const nav = panel.querySelector(".category-tabs");
    const active = nav.querySelector(".active");
    Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 1 });
    Object.defineProperties(nav, {
      clientWidth: { configurable: true, value: 200 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
    });
    Object.defineProperties(active, {
      offsetLeft: { configurable: true, value: 260 },
      offsetWidth: { configurable: true, value: 80 },
    });

    panel.updateCategoryMode();

    expect(panel.querySelector(".category-layout").classList.contains("single-row-category-mode")).toBe(true);
    expect(nav.scrollLeft).toBe(148);
    Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 0 });
  });

  test("positions the compact menu inside the viewport and supports keyboard navigation", () => {
    const panel = createPanel();
    const toggle = panel.querySelector("[data-category-menu-toggle]");
    const menu = panel.querySelector("[data-category-menu]");
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 800 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 600 });
    toggle.getBoundingClientRect = () => ({ left: 760, top: 500, bottom: 540 });
    menu.getBoundingClientRect = () => ({ width: 280, height: 250 });
    menu.hidden = false;

    panel.positionCategoryMenu();

    expect(menu.style.left).toBe("508px");
    expect(menu.style.top).toBe("244px");
    expect(menu.classList.contains("opens-up")).toBe(true);

    const items = [...menu.querySelectorAll('[role="menuitem"]')];
    items[0].focus();
    items[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement).toBe(items[1]);
  });
});
