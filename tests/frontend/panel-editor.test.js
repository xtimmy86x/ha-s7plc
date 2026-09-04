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

const currentDialog = () => document.body.querySelector("ha-dialog");

describe("entity editor", () => {
  test("opens an existing entity and switches between visual and YAML modes", () => {
    const panel = createPanel();

    panel.querySelector('[data-entity-action="edit"]').click();
    const dialog = currentDialog();
    const visual = dialog.querySelector('.visual-form');
    const yaml = dialog.querySelector('.yaml-editor');
    const tabs = dialog.querySelectorAll('[data-mode]');

    expect(dialog.open).toBe(true);
    expect(dialog.headerTitle).toBe("Edit entity");
    expect(dialog.getAttribute("width")).toBe("large");
    expect(dialog.style.getPropertyValue("--ha-dialog-width-lg")).toBe("960px");
    expect(dialog.style.getPropertyValue("--ha-dialog-max-width")).toBe("min(960px,96vw)");
    expect(dialog.style.getPropertyValue("--mdc-dialog-max-width")).toBe("min(960px,96vw)");
    expect(visual.elements.name.value).toBe("Boiler temperature");
    expect(visual.style.display).toBe("");
    expect(yaml.style.display).toBe("none");

    tabs[1].click();

    expect(tabs[0].classList.contains("active")).toBe(false);
    expect(tabs[1].classList.contains("active")).toBe(true);
    expect(visual.style.display).toBe("none");
    expect(yaml.style.display).toBe("block");
    expect(yaml.querySelector("textarea").value).toContain('name: "Boiler temperature"');
  });

  test("shows and requires the availability address only in bit mode", () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const form = currentDialog().querySelector("form");
    const field = form.querySelector('[data-field="availability_address"]');
    const address = form.elements.availability_address;

    expect(field.hidden).toBe(true);
    expect(field.classList.contains("hidden-field")).toBe(true);
    expect(address.required).toBe(false);

    const bit = form.querySelector('input[name="availability_mode"][value="bit"]');
    bit.checked = true;
    bit.dispatchEvent(new Event("change", { bubbles: true }));

    expect(field.hidden).toBe(false);
    expect(field.classList.contains("hidden-field")).toBe(false);
    expect(address.required).toBe(true);

    const always = form.querySelector('input[name="availability_mode"][value="always"]');
    always.checked = true;
    always.dispatchEvent(new Event("change", { bubbles: true }));
    expect(field.hidden).toBe(true);
    expect(address.required).toBe(false);
  });

  test("saves edited visual-form values through the panel WebSocket contract", async () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const dialog = currentDialog();
    const form = dialog.querySelector("form");
    form.elements.name.value = "Updated boiler";
    const messages = [];
    panel._hass.callWS = vi.fn(async (message) => {
      messages.push(message);
      return { entities: [message.entity] };
    });
    panel.load = vi.fn(async () => {});

    await dialog.querySelector('[slot="primaryAction"]').onclick();

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      type: "s7plc/config/save_entity",
      entry_id: "plc-entry",
      entity_type: "sensors",
      index: 0,
      entity: { name: "Updated boiler", address: "DB1,R0" },
    });
    expect(messages[0]).not.toHaveProperty("entity_yaml");
    expect(dialog.open).toBe(false);
    expect(panel.load).toHaveBeenCalledOnce();
  });

  test("sends raw YAML when the advanced editor is active", async () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const dialog = currentDialog();
    dialog.querySelector('[data-mode="yaml"]').click();
    dialog.querySelector("textarea").value = 'name: "From YAML"\naddress: "DB1,REAL0"';
    panel._hass.callWS = vi.fn(async () => ({ entities: [] }));
    panel.load = vi.fn(async () => {});

    await dialog.querySelector('[slot="primaryAction"]').onclick();

    expect(panel._hass.callWS).toHaveBeenCalledWith({
      type: "s7plc/config/save_entity",
      entry_id: "plc-entry",
      entity_type: "sensors",
      index: 0,
      entity_yaml: 'name: "From YAML"\naddress: "DB1,REAL0"',
    });
    expect(dialog.open).toBe(false);
    expect(panel.load).toHaveBeenCalledOnce();
  });

  test("keeps the dialog open and displays save failures", async () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const dialog = currentDialog();
    panel._hass.callWS = vi.fn(async () => {
      throw new Error("PLC rejected the entity");
    });

    await dialog.querySelector('[slot="primaryAction"]').onclick();

    const alert = dialog.querySelector(".editor-error");
    expect(dialog.open).toBe(true);
    expect(alert.style.display).toBe("block");
    expect(alert.textContent).toContain("PLC rejected the entity");
  });

  test("duplicates into an independent sanitized create draft", () => {
    const entry = createEntry();
    entry.entities.selects = [{
      uid: "original-uid",
      name: "Copy me",
      address: "DB1,BYTE0",
      command_address: "DB1,BYTE2",
      options_map: { nested: [{ value: 1, label: "One" }] },
    }];
    const panel = createPanel(entry);

    panel.openEditor(null, "selects", entry.entities.selects[0]);
    const dialog = currentDialog();

    expect(dialog.headerTitle).toBe("Duplicate entity");
    expect(dialog.querySelector("textarea").value).not.toContain("original-uid");
    expect(dialog.querySelector("form").elements.name.value).toBe("Copy me");
    expect(entry.entities.selects[0].uid).toBe("original-uid");
    expect(entry.entities.selects[0].options_map.nested[0].label).toBe("One");
  });
});
