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

const defaults = {
  scan_interval: 0.5,
  real_precision: 1,
  pulse_duration: 0.5,
  pulse_duration_range: [0.1, 60],
  operate_time: 60,
  min_temp: 7,
  max_temp: 35,
  temp_step: 0.5,
  number_limits: { INT: [-32768, 32767], BYTE: [0, 255], TIME: [-2147483.648, 2147483.647] },
  logo_time_limits: [0, 2359],
  number_step: 1,
  time_step: 0.001,
  units: { sensors: { temperature: "°C", power: "W" }, numbers: { temperature: "°C" } },
  state_classes: { temperature: "measurement", energy: "total_increasing" },
};
const flush = () => new Promise((resolve) => setTimeout(resolve));
const field = (form, key) => form.querySelector(`[data-default-field="${key}"]`);
const help = (form, key) => field(form, key).querySelector("[data-default-help]");
const badge = (form, key) => field(form, key).querySelector("[data-default-state]");
const reset = (form, key) => field(form, key).querySelector("[data-default-reset]");
const edit = (type, item, entryDefaults = defaults) => {
  const entry = createEntry(entryDefaults ? { defaults: entryDefaults } : {});
  entry.selector_options = {
    device_classes: { sensors: ["energy", "power", "temperature"], numbers: ["temperature"] },
    state_classes: ["measurement", "total", "total_increasing"],
  };
  entry.entities[type] = [item];
  const panel = createPanel(entry);
  panel.openEditor(0, type);
  return document.body.querySelector("ha-dialog form");
};
const setValue = async (form, name, value) => {
  form.elements[name].value = value;
  form.elements[name].dispatchEvent(new Event("change", { bubbles: true }));
  await flush();
};

describe("field defaults", () => {
  test("shows datatype limits for empty Number fields and marks custom values", async () => {
    const form = edit("numbers", { address: "DB1,INT20", max_value: 90 });

    expect(form.elements.min_value.placeholder).toBe("-32768");
    expect(help(form, "min_value").textContent).toBe("Empty: -32768, INT limit.");
    expect(badge(form, "min_value").textContent).toBe("Default");
    expect(reset(form, "min_value").hidden).toBe(true);

    expect(form.elements.max_value.value).toBe("90");
    expect(help(form, "max_value").textContent).toBe("Leave empty to restore the default: 32767, INT limit.");
    expect(badge(form, "max_value").textContent).toBe("Custom");
    expect(reset(form, "max_value").hidden).toBe(false);
    expect(form.elements.step.placeholder).toBe("1");
    expect(form.elements.scan_interval.placeholder).toBe("0.5");
    expect(help(form, "scan_interval").textContent).toBe("Empty: the PLC scan interval (0.5 s).");

    reset(form, "max_value").click();
    await flush();
    expect(form.elements.max_value.value).toBe("");
    expect(badge(form, "max_value").textContent).toBe("Default");
    expect(reset(form, "max_value").hidden).toBe(true);
  });

  test("recalculates defaults when the address or device class changes", async () => {
    const form = edit("numbers", { address: "DB1,INT20" });
    await setValue(form, "address", "DB1,B4");
    expect(form.elements.max_value.placeholder).toBe("255");

    await setValue(form, "address", "DB1,REAL4");
    expect(form.elements.min_value.required).toBe(true);
    expect(form.elements.min_value.placeholder).toBe("");
    expect(help(form, "min_value").textContent).toBe("Required for REAL/LREAL addresses.");
    expect(badge(form, "min_value").hidden).toBe(true);

    await setValue(form, "address", "DB1,INT20");
    expect(form.elements.min_value.required).toBe(false);
    expect(help(form, "unit_of_measurement").textContent).toBe("Empty: no unit.");
    await setValue(form, "device_class", "temperature");
    expect(form.elements.unit_of_measurement.placeholder).toBe("°C");
    expect(help(form, "unit_of_measurement").textContent).toContain("°C, default unit for");
  });

  test("names the automatic state class of the chosen device class", async () => {
    const form = edit("sensors", { address: "DB1,REAL0" });
    const automatic = form.elements.state_class.options[0];
    expect(automatic.textContent).toBe("Automatic");
    await setValue(form, "device_class", "energy");
    expect(automatic.textContent).toBe("Automatic (Total Increasing)");
    expect(form.elements.real_precision.placeholder).toBe("1");
    expect(help(form, "real_precision").textContent).toBe("Empty: decimal places: 1.");
  });

  test("shows fixed defaults with units and native bounds for pulses", () => {
    const cover = edit("covers", { open_command_address: "DB1,X0.0", close_command_address: "DB1,X0.1" });
    expect(cover.elements.operate_time.placeholder).toBe("60");
    expect(help(cover, "operate_time").textContent).toBe("Empty: 60 s.");
    expect(field(cover, "operate_time").querySelector(".input-suffix").textContent).toBe("s");
    expect(cover.elements.operate_time.min).toBe("0");

    document.body.replaceChildren();
    const button = edit("buttons", { address: "DB1,X0.0", button_pulse: 100 });
    expect(button.elements.button_pulse.min).toBe("0.1");
    expect(button.elements.button_pulse.max).toBe("60");
    expect(button.elements.button_pulse.checkValidity()).toBe(false);

    document.body.replaceChildren();
    const climate = edit("climates", {
      control_mode: "setpoint",
      current_temperature_address: "DB1,REAL0",
      target_temperature_address: "DB1,REAL4",
    });
    expect(climate.elements.min_temp.placeholder).toBe("7");
    expect(help(climate, "temp_step").textContent).toBe("Empty: 0.5 °C.");
  });

  test("stays silent when the backend does not provide defaults", () => {
    const form = edit("numbers", { address: "DB1,INT20" }, null);
    expect(form.elements.min_value.placeholder).toBe("");
    expect(help(form, "min_value").hidden).toBe(true);
    expect(badge(form, "min_value").hidden).toBe(true);
  });
});
