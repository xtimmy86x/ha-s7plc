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
    form.elements.address.value = "DB1,REAL0";

    panel.syncValueConversions(form);

    expect(form.elements.vc_value_type.value).toBe("");
    expect(form.elements.vc_value_type.querySelector('option[value="enum_map"]')).toBeNull();
    expect(row.querySelector("[data-enum-unavailable]").hidden).toBe(false);
    expect(form.elements.device_class.disabled).toBe(false);
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
});
