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
const choose = (form, name, value) => {
  const input = form.querySelector(`input[name="${name}"][value="${value}"]`);
  input.checked = true;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return input;
};
const isHidden = (form, field) => form
  .querySelector(`[data-field="${field}"]`)
  .classList.contains("hidden-field");

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

  test("updates switch command behavior and serializes the selected mode", () => {
    const panel = createPanel();
    panel.openEditor(0, "switches");
    const form = currentDialog().querySelector("form");

    expect(form.elements.control_behavior.value).toBe("direct");
    expect(isHidden(form, "pulse_duration")).toBe(true);
    expect(form.querySelector('input[name="control_behavior"][value="sync"]').disabled).toBe(false);

    choose(form, "control_behavior", "pulse");
    form.elements.pulse_duration.value = "0.75";
    const entity = panel.formEntity(form, panel.entries[0].entities.switches[0], "switches");

    expect(isHidden(form, "pulse_duration")).toBe(false);
    expect(entity).toMatchObject({
      state_address: "DB1,X8.0",
      command_address: "DB1,X8.1",
      pulse_command: true,
      sync_state: false,
      pulse_duration: 0.75,
    });
  });

  test("reveals brightness addresses only for a dimmable light", () => {
    const entry = createEntry();
    entry.entities.lights = [{
      name: "Workshop light",
      state_address: "DB1,X10.0",
      command_address: "DB1,X10.1",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "lights");
    const form = currentDialog().querySelector("form");

    expect(form.elements.light_mode.value).toBe("on_off");
    expect(isHidden(form, "brightness_state_address")).toBe(true);
    expect(isHidden(form, "brightness_command_address")).toBe(true);

    choose(form, "light_mode", "dimmable");

    expect(isHidden(form, "brightness_state_address")).toBe(false);
    expect(isHidden(form, "brightness_command_address")).toBe(false);
    form.elements.brightness_state_address.value = "DB1,BYTE12";
    form.elements.brightness_command_address.value = "DB1,BYTE14";
    expect(panel.formEntity(form, entry.entities.lights[0], "lights")).toMatchObject({
      brightness_state_address: "DB1,BYTE12",
      brightness_command_address: "DB1,BYTE14",
    });

    choose(form, "light_mode", "on_off");
    const onOff = panel.formEntity(form, entry.entities.lights[0], "lights");
    expect(onOff).not.toHaveProperty("brightness_state_address");
    expect(onOff).not.toHaveProperty("brightness_command_address");
    expect(onOff).not.toHaveProperty("light_mode");
  });

  test("updates cover controls and serialization when selecting toggle mode", () => {
    const entry = createEntry();
    entry.entities.covers = [{
      name: "Gate",
      open_command_address: "DB1,X12.0",
      close_command_address: "DB1,X12.1",
      operate_time: 20,
      cover_position_feedback: "timed",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "covers");
    const form = currentDialog().querySelector("form");

    expect(form.elements.cover_control_mode.value).toBe("traditional");
    expect(isHidden(form, "close_command_address")).toBe(false);
    expect(isHidden(form, "operate_time")).toBe(false);

    choose(form, "cover_control_mode", "toggle");

    expect(isHidden(form, "open_command_address")).toBe(false);
    expect(isHidden(form, "close_command_address")).toBe(true);
    expect(isHidden(form, "operate_time")).toBe(true);
    expect(isHidden(form, "toggle_pulse_duration")).toBe(false);
    expect(form.querySelector('[data-section="cover-options"]').classList.contains("hidden-field")).toBe(false);
    expect(form.elements.open_command_address.required).toBe(true);
    expect(form.elements.close_command_address.required).toBe(false);
    form.elements.opening_state_address.value = "DB1,X13.0";
    form.elements.closing_state_address.value = "DB1,X13.1";
    form.elements.cover_opening_address.value = "DB1,X14.0";
    form.elements.cover_closing_address.value = "DB1,X14.1";
    const entity = panel.formEntity(form, entry.entities.covers[0], "covers");
    expect(entity.toggle_mode).toBe(true);
    expect(entity).not.toHaveProperty("close_command_address");
  });

  test("rebuilds climate sections when switching from setpoint to direct control", () => {
    const entry = createEntry();
    entry.entities.climates = [{
      name: "Office climate",
      control_mode: "setpoint",
      current_temperature_address: "DB1,REAL20",
      target_temperature_address: "DB1,REAL24",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "climates");
    const form = currentDialog().querySelector("form");

    expect(isHidden(form, "target_temperature_address")).toBe(false);
    expect(form.querySelector('[data-section="climate-mode-control"]').classList.contains("hidden-field")).toBe(false);
    expect(form.querySelector('[data-section="climate-direct-function"]').classList.contains("hidden-field")).toBe(true);

    choose(form, "control_mode", "direct");

    expect(isHidden(form, "target_temperature_address")).toBe(true);
    expect(isHidden(form, "heating_output_address")).toBe(false);
    expect(isHidden(form, "cooling_output_address")).toBe(true);
    expect(form.querySelector('[data-section="climate-mode-control"]').classList.contains("hidden-field")).toBe(true);
    expect(form.querySelector('[data-section="climate-direct-function"]').classList.contains("hidden-field")).toBe(false);
    form.elements.heating_output_address.value = "DB1,X28.0";
    const entity = panel.formEntity(form, entry.entities.climates[0], "climates");
    expect(entity.control_mode).toBe("direct");
    expect(entity.heating_output_address).toBe("DB1,X28.0");
    expect(entity).not.toHaveProperty("target_temperature_address");
  });
});
