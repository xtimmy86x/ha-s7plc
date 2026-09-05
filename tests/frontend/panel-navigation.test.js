// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createPanel, entityTypes, installPanel } from "./panel-fixture.js";

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
  test("keeps the layout toggle above category-specific navigation", () => {
    const panel = createPanel();
    const layout = panel.querySelector(".category-layout");

    expect([...layout.children].map((node) => node.className)).toEqual([
      "toolbar",
      "category-navigation",
      "",
    ]);
    expect(layout.children[2].tagName).toBe("MAIN");
    expect(layout.querySelector(".toolbar .category-tabs")).toBeNull();
    expect(layout.querySelector(".toolbar [data-category-menu-toggle]")).toBeNull();
    expect(layout.querySelector(".category-navigation .category-tabs")).not.toBeNull();
    expect(layout.querySelector(".category-navigation [data-category-menu-toggle]")).not.toBeNull();
    expect(layout.querySelector(".toolbar-actions").firstElementChild)
      .toBe(layout.querySelector("[data-layout-toggle]"));

    layout.querySelector("[data-layout-toggle]").click();
    const sectionsToolbar = panel.querySelector(".sections-toolbar");
    expect(sectionsToolbar.firstElementChild.className).not.toBe("category-navigation");
    expect(sectionsToolbar.querySelector(".toolbar-actions").firstElementChild)
      .toBe(sectionsToolbar.querySelector("[data-layout-toggle]"));
  });

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

describe("panel global add action", () => {
  test("keeps Add last in both toolbars and preserves the other action order", () => {
    const panel = createPanel();
    let actions = panel.querySelector(".toolbar .toolbar-actions");

    expect([...actions.children].map((node) => node.matches(
      "[data-layout-toggle], [data-batch-delete], [data-add]",
    ))).toEqual([true, true, true]);
    expect(actions.lastElementChild.matches('[data-add="sensors"]')).toBe(true);

    panel.querySelector("[data-layout-toggle]").click();
    actions = panel.querySelector(".sections-toolbar .toolbar-actions");
    expect([...actions.children].map((node) => node.matches(
      "[data-layout-toggle], [data-batch-delete-global], [data-global-add], [data-add-type-menu]",
    ))).toEqual([true, true, true, true]);
    expect(actions.querySelector("[data-global-add]").nextElementSibling)
      .toBe(actions.querySelector("[data-add-type-menu]"));
  });

  test("opens the selected category editor directly in Categories view", () => {
    const panel = createPanel();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});
    panel.querySelector('[data-type="switches"]').click();

    panel.querySelector('.toolbar [data-add="switches"]').click();

    expect(openEditor).toHaveBeenCalledOnce();
    expect(openEditor).toHaveBeenCalledWith(null, "switches");
    expect(panel.querySelector("[data-add-type-menu]")).toBeNull();
  });

  test("opens an accessible entity-type menu with every supported type once", () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const add = panel.querySelector("[data-global-add]");
    const menu = panel.querySelector("[data-add-type-menu]");

    expect(add.getAttribute("aria-haspopup")).toBe("menu");
    expect(add.getAttribute("aria-expanded")).toBe("false");
    add.click();

    const items = [...menu.querySelectorAll('[role="menuitem"]')];
    expect(menu.hidden).toBe(false);
    expect(add.getAttribute("aria-expanded")).toBe("true");
    expect(items.map((item) => item.dataset.addType)).toEqual(entityTypes);
    expect(new Set(items.map((item) => item.dataset.addType)).size).toBe(entityTypes.length);
    expect(items.every((item) => item.querySelector("ha-icon") && item.querySelector("span")?.textContent)).toBe(true);
    expect(document.activeElement).toBe(items[0]);
    items[0].dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
    expect(document.activeElement).toBe(items.at(-1));
  });

  test("selects a type without changing view or category and closes the menu", () => {
    const panel = createPanel();
    panel.type = "switches";
    panel.querySelector("[data-layout-toggle]").click();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});
    const add = panel.querySelector("[data-global-add]");
    add.click();

    panel.querySelector('[data-add-type="climates"]').click();

    expect(openEditor).toHaveBeenCalledWith(null, "climates");
    expect(panel._viewMode).toBe("sections");
    expect(panel.type).toBe("switches");
    expect(panel.querySelector("[data-add-type-menu]").hidden).toBe(true);
    expect(add.getAttribute("aria-expanded")).toBe("false");
  });

  test("keeps section Add buttons as direct shortcuts", () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const openEditor = vi.spyOn(panel, "openEditor").mockImplementation(() => {});

    panel.querySelector('[data-section-type="numbers"] [data-add="numbers"]').click();

    expect(openEditor).toHaveBeenCalledWith(null, "numbers");
    expect(panel.querySelector("[data-add-type-menu]").hidden).toBe(true);
  });

  test("closes on Escape or outside click and restores focus only for Escape", () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const add = panel.querySelector("[data-global-add]");
    const menu = panel.querySelector("[data-add-type-menu]");
    add.click();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(menu.hidden).toBe(true);
    expect(document.activeElement).toBe(add);

    add.click();
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(menu.hidden).toBe(true);
    expect(add.getAttribute("aria-expanded")).toBe("false");
  });

  test("supports repeated opening without duplicate items or active listeners", () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const add = panel.querySelector("[data-global-add]");
    const addListener = vi.spyOn(document, "addEventListener");
    const removeListener = vi.spyOn(document, "removeEventListener");

    for (let index = 0; index < 3; index += 1) {
      add.click();
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    }

    expect(panel.querySelectorAll("[data-add-type]")).toHaveLength(entityTypes.length);
    expect(addListener.mock.calls.filter(([type]) => type === "click")).toHaveLength(3);
    expect(addListener.mock.calls.filter(([type]) => type === "keydown")).toHaveLength(3);
    expect(removeListener.mock.calls.filter(([type]) => type === "click")).toHaveLength(3);
    expect(removeListener.mock.calls.filter(([type]) => type === "keydown")).toHaveLength(3);
  });

  test("positions the menu within desktop and mobile viewports", () => {
    const panel = createPanel();
    panel.querySelector("[data-layout-toggle]").click();
    const add = panel.querySelector("[data-global-add]");
    const menu = panel.querySelector("[data-add-type-menu]");
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1200 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 900 });
    add.getBoundingClientRect = () => ({ left: 1060, right: 1188, top: 120, bottom: 160 });
    menu.getBoundingClientRect = () => ({ width: 280, height: 400 });
    menu.hidden = false;

    panel.positionAddMenu();

    expect(menu.style.right).toBe("12px");
    expect(menu.style.top).toBe("166px");
    expect(menu.classList.contains("opens-up")).toBe(false);

    Object.defineProperty(window, "innerWidth", { configurable: true, value: 360 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 640 });
    add.getBoundingClientRect = () => ({ left: 280, right: 352, top: 570, bottom: 610 });
    menu.getBoundingClientRect = () => ({ width: 336, height: 400 });
    menu.hidden = false;

    panel.positionAddMenu();

    expect(menu.style.right).toBe("12px");
    expect(menu.style.top).toBe("164px");
    expect(menu.style.maxHeight).toBe("616px");
    expect(menu.classList.contains("opens-up")).toBe(true);
  });
});
