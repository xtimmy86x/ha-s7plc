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

function openSensorEditor(entity = {}) {
  const entry = createEntry();
  entry.entities.sensors = [{
    name: "Converted sensor",
    address: "DB1,REAL0",
    ...entity,
  }];
  const panel = createPanel(entry);
  panel.openEditor(0, "sensors");
  const dialog = document.body.querySelector("ha-dialog");
  const form = dialog.querySelector("form");
  const row = form.querySelector('[data-value-conversion="value"]');
  return { entry, panel, dialog, form, row };
}

function selectKind(form, kind) {
  const select = form.elements.vc_value_type;
  select.value = kind;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  return select;
}

describe("value conversion editor", () => {
  test("configures and serializes a multiplier through the real form", () => {
    const { entry, panel, form, row } = openSensorEditor();

    expect(row.hidden).toBe(false);
    selectKind(form, "multiplier");
    form.elements.vc_value_factor.value = "2.5";
    form.elements.vc_value_factor.dispatchEvent(new Event("input", { bubbles: true }));

    expect(row.querySelector('[data-kind="multiplier"]').hidden).toBe(false);
    expect(row.querySelector('[data-kind="linear_scale"]').hidden).toBe(true);
    expect(row.querySelector("[data-conversion-summary]").textContent).toContain("2.5");
    expect(panel.formEntity(form, entry.entities.sensors[0], "sensors").value_conversions).toEqual({
      value: { type: "multiplier", factor: 2.5 },
    });
  });

  test("updates linear-scale clamping feedback and serializes every bound", () => {
    const { entry, panel, form, row } = openSensorEditor();
    selectKind(form, "linear_scale");
    form.elements.vc_value_plc_min.value = "0";
    form.elements.vc_value_plc_max.value = "27648";
    form.elements.vc_value_ha_min.value = "-10";
    form.elements.vc_value_ha_max.value = "50";
    form.elements.vc_value_clamp.checked = true;
    form.elements.vc_value_clamp.dispatchEvent(new Event("change", { bubbles: true }));

    expect(row.querySelector('[data-kind="linear_scale"]').hidden).toBe(false);
    expect(row.querySelector(".conversion-preview").textContent.toLowerCase()).toContain("clamp");
    expect(panel.formEntity(form, entry.entities.sensors[0], "sensors").value_conversions.value).toEqual({
      type: "linear_scale",
      plc_min: 0,
      plc_max: 27648,
      ha_min: -10,
      ha_max: 50,
      clamp: true,
    });
  });

  test("keeps read and write expressions directional", () => {
    const { entry, panel, form, row } = openSensorEditor();
    selectKind(form, "expression");
    form.elements.vc_value_read_expression.value = "value / 10";
    form.elements.vc_value_write_expression.value = "value * 10";

    expect(row.querySelector('[data-kind="expression"]').hidden).toBe(false);
    expect(row.querySelector('[name="vc_value_read_expression"]').closest("label").hidden).toBe(false);
    expect(row.querySelector('[name="vc_value_write_expression"]').closest("label").hidden).toBe(true);
    expect(panel.formEntity(form, entry.entities.sensors[0], "sensors").value_conversions.value).toEqual({
      type: "expression",
      read_expression: "value / 10",
      write_expression: "value * 10",
    });
  });

  test("offers Enum mapping only for integer sensors and serializes ordered rows", () => {
    const { entry, panel, form, row } = openSensorEditor({
      address: "DB1,BYTE0",
      unit_of_measurement: "state",
      state_class: "measurement",
      real_precision: 2,
    });
    const select = form.elements.vc_value_type;

    expect(select.querySelector('option[value="enum_map"]')).not.toBeNull();
    selectKind(form, "enum_map");
    const rows = row.querySelector("[data-enum-rows]");
    rows.children[0].querySelector(".om-value").value = "0";
    rows.children[0].querySelector(".om-label").value = "Off";
    row.querySelector("[data-enum-add]").click();
    rows.children[1].querySelector(".om-value").value = "1";
    rows.children[1].querySelector(".om-label").value = "On";

    const entity = panel.formEntity(form, entry.entities.sensors[0], "sensors");
    expect(entity.device_class).toBe("enum");
    expect(entity).not.toHaveProperty("unit_of_measurement");
    expect(entity).not.toHaveProperty("state_class");
    expect(entity).not.toHaveProperty("real_precision");
    expect(entity.value_conversions.value).toEqual({
      type: "enum_map",
      mappings: [{ value: 0, label: "Off" }, { value: 1, label: "On" }],
    });
  });

  test("invalidates Enum mode after changing the sensor to a non-integer datatype", () => {
    const { panel, form, row } = openSensorEditor({ address: "DB1,INT0" });
    selectKind(form, "enum_map");
    const builder = form.querySelector('[data-field="address"]');
    const manual = builder.querySelector("[data-address-manual]");
    builder.querySelector('[data-address-mode="manual"]').click();
    manual.value = "DB1,REAL0";
    manual.dispatchEvent(new Event("input", { bubbles: true }));

    expect(form.elements.vc_value_type.value).toBe("");
    expect(form.elements.vc_value_type.querySelector('option[value="enum_map"]')).toBeNull();
    expect(row.querySelector("[data-enum-unavailable]").hidden).toBe(false);
    expect(form.elements.device_class.disabled).toBe(false);

    for (let index = 0; index < 3; index += 1) {
      form.elements.address.value = "DB1,INT0";
      panel.syncValueConversions(form);
      const values = [...form.elements.vc_value_type.options].map((option) => option.value);
      expect(values.filter((value) => value === "enum_map")).toHaveLength(1);
      expect(values.indexOf("enum_map")).toBeLessThan(values.indexOf("logo_time_bcd"));
      expect(row.querySelector("[data-enum-unavailable]").hidden).toBe(true);

      form.elements.address.value = "DB1,REAL0";
      panel.syncValueConversions(form);
      expect(form.elements.vc_value_type.querySelector('option[value="enum_map"]')).toBeNull();
    }
  });

  test("restores the previous device class after leaving Enum mode", () => {
    const run = (deviceClass) => {
      const { form } = openSensorEditor({ address: "DB1,INT0", device_class: deviceClass });
      selectKind(form, "enum_map");
      expect(form.elements.device_class.disabled).toBe(true);
      expect(form.querySelector('[data-field="unit_of_measurement"]')
        .classList.contains("hidden-field")).toBe(true);

      selectKind(form, "multiplier");
      return {
        deviceClass: form.elements.device_class.value,
        disabled: form.elements.device_class.disabled,
        unitHidden: form.querySelector('[data-field="unit_of_measurement"]')
          .classList.contains("hidden-field"),
      };
    };

    expect(run("temperature")).toEqual({
      deviceClass: "temperature",
      disabled: false,
      unitHidden: false,
    });
    document.body.replaceChildren();
    expect(run("enum")).toEqual({ deviceClass: "", disabled: false, unitHidden: false });
  });

  test("limits Enum to integer sensors and preserves existing mapping order", () => {
    const existing = openSensorEditor({
      address: "DB1,INT0",
      value_conversions: {
        value: {
          type: "enum_map",
          mappings: [{ value: 7, label: "Seven" }, { value: -1, label: "Minus one" }],
        },
      },
    });
    const rows = [...existing.row.querySelectorAll("[data-enum-row]")];
    expect(rows.map((item) => ({
      value: item.querySelector(".om-value").value,
      label: item.querySelector(".om-label").value,
    }))).toEqual([
      { value: "7", label: "Seven" },
      { value: "-1", label: "Minus one" },
    ]);

    document.body.replaceChildren();
    const real = openSensorEditor({ address: "DB1,REAL0" });
    expect(real.form.elements.vc_value_type.querySelector('option[value="enum_map"]')).toBeNull();
    expect(real.form.elements.vc_value_type.querySelector('option[value="expression"]')).not.toBeNull();

    document.body.replaceChildren();
    const entry = createEntry();
    entry.entities.numbers = [{
      name: "Integer number",
      address: "DB1,INT0",
      min_value: 0,
      max_value: 10,
      step: 1,
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "numbers");
    const numberForm = document.body.querySelector("ha-dialog form");
    expect(numberForm.elements.vc_value_type.querySelector('option[value="enum_map"]')).toBeNull();
  });

  test("reports incomplete and duplicate Enum mappings", () => {
    const { form, row, panel } = openSensorEditor({ address: "DB1,INT0" });
    selectKind(form, "enum_map");
    const rows = row.querySelector("[data-enum-rows]");
    rows.children[0].querySelector(".om-value").value = "1";

    expect(() => panel.enumMappingsFromRow(row)).toThrow("Home Assistant state is required.");

    rows.children[0].querySelector(".om-label").value = "Open";
    row.querySelector("[data-enum-add]").click();
    rows.children[1].querySelector(".om-value").value = "1";
    rows.children[1].querySelector(".om-label").value = "Closed";
    expect(() => panel.enumMappingsFromRow(row)).toThrow("PLC value is duplicated.");

    rows.children[1].querySelector(".om-value").value = "1.5";
    expect(() => panel.enumMappingsFromRow(row)).toThrow("PLC value must be an integer.");

    rows.children[0].querySelector(".om-value").value = "0";
    rows.children[1].querySelector(".om-value").value = "1.0";
    expect(panel.enumMappingsFromRow(row)).toEqual([
      { value: 0, label: "Open" },
      { value: 1, label: "Closed" },
    ]);

    rows.replaceChildren();
    expect(() => panel.enumMappingsFromRow(row)).toThrow("At least one mapping is required.");
  });

  test("keeps bidirectional expressions intact while their addresses change", () => {
    const entry = createEntry();
    entry.entities.numbers = [{
      name: "Scaled setpoint",
      address: "DB1,REAL0",
      command_address: "DB1,REAL4",
      min_value: 0,
      max_value: 100,
      step: 1,
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "numbers");
    const form = document.body.querySelector("ha-dialog form");
    const row = form.querySelector('[data-value-conversion="value"]');
    selectKind(form, "expression");
    form.elements.vc_value_read_expression.value = "value / 10";
    form.elements.vc_value_write_expression.value = "value * 10";

    expect(row.dataset.direction).toBe("bidirectional_distinct");
    expect(row.querySelector('[name="vc_value_read_expression"]').closest("label").hidden)
      .toBe(false);
    expect(row.querySelector('[name="vc_value_write_expression"]').closest("label").hidden)
      .toBe(false);

    form.elements.command_address.value = "";
    panel.syncValueConversions(form);
    expect(row.dataset.direction).toBe("bidirectional_same");
    expect(row.querySelector('[name="vc_value_write_expression"]').closest("label").hidden)
      .toBe(false);

    form.elements.command_address.value = "DB1,REAL4";
    panel.syncValueConversions(form);
    expect(form.elements.vc_value_read_expression.value).toBe("value / 10");
    expect(form.elements.vc_value_write_expression.value).toBe("value * 10");
  });

  test("keeps brightness output fixed to HA 0-255 with mandatory clamping", () => {
    const entry = createEntry();
    entry.entities.lights = [{
      name: "Dimmer",
      state_address: "DB1,X0.0",
      command_address: "DB1,X0.1",
      brightness_state_address: "DB1,WORD2",
      brightness_command_address: "DB1,WORD4",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "lights");
    const form = document.body.querySelector("ha-dialog form");
    const row = form.querySelector('[data-value-conversion="brightness"]');
    const select = form.elements.vc_brightness_type;
    select.value = "linear_scale";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    form.elements.vc_brightness_plc_min.value = "0";
    form.elements.vc_brightness_plc_max.value = "1000";

    expect(form.elements.vc_brightness_ha_min).toBeUndefined();
    expect(form.elements.vc_brightness_ha_max).toBeUndefined();
    expect(form.elements.vc_brightness_clamp).toBeUndefined();
    expect(row.textContent).toContain("0–255");
    expect(panel.formEntity(form, entry.entities.lights[0], "lights")
      .value_conversions.brightness).toEqual({
      type: "linear_scale",
      plc_min: 0,
      plc_max: 1000,
      ha_min: 0,
      ha_max: 255,
      clamp: true,
    });
  });
});
