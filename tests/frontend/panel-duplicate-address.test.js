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

const form = () => document.body.querySelector("ha-dialog form");
const note = (field) => form().querySelector(`[data-field="${field}"] .address-duplicate`);
const typeAddress = (field, value) => {
  const input = form().querySelector(`[data-field="${field}"] [data-address-manual]`);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
};
const flush = () => new Promise((resolve) => setTimeout(resolve));

describe("duplicate address warning", () => {
  test("names the other entity using the address", async () => {
    const panel = createPanel();
    panel.openEditor(null, "sensors");
    expect(note("address").hidden).toBe(true);
    typeAddress("address", "db1,8.0");
    await flush();
    expect(note("address").hidden).toBe(false);
    expect(note("address").textContent).toBe("Also used by: Circulation pump");
    typeAddress("address", "DB1,X8.2");
    await flush();
    expect(note("address").hidden).toBe(true);
  });

  test("preserves duplicate warnings when switching cover control modes", async () => {
    const entry = createEntry();
    entry.entities.covers = [{ name: "Blind", open_command_address: "DB1,X8.0", close_command_address: "DB1,X9.0", operate_time: 20 }];
    const panel = createPanel(entry);
    panel.openEditor(0, "covers");
    const field = form().querySelector('[data-field="open_command_address"]');
    expect(note("open_command_address").textContent).toBe("Also used by: Circulation pump");
    for (const mode of ["toggle", "traditional"]) {
      form().querySelector(`[name="cover_control_mode"][value="${mode}"]`).click();
      await flush();
      expect(note("open_command_address").textContent).toBe("Also used by: Circulation pump");
      expect(field.querySelector(".address-help").textContent).toBe(
        panel.fieldText("covers", "open_command_address", mode === "toggle" ? "description_toggle" : "description"),
      );
    }
    typeAddress("open_command_address", "DB1,X10.0");
    await flush();
    expect(note("open_command_address").hidden).toBe(true);
  });

  test("ignores the entity being edited", () => {
    const panel = createPanel();
    panel.openEditor(0, "switches");
    expect(note("state_address").hidden).toBe(true);
    expect(note("command_address").hidden).toBe(true);
  });

  test("warns about existing duplicates when an entity opens", () => {
    const entry = createEntry();
    entry.entities.binary_sensors = [{ address: "DB1,X8.1" }];
    entry.entities.lights = [{ name: "Hall", state_address: "DB1,X8.1", command_address: "DB1,X9.0" }];
    const panel = createPanel(entry);
    panel.openEditor(0, "switches");
    expect(note("command_address").hidden).toBe(false);
    expect(note("command_address").textContent).toBe("Also used by: Binary sensor 1, Hall");
  });

  test("warns when duplicating an entity", () => {
    const entry = createEntry();
    const panel = createPanel(entry);
    panel.openEditor(null, "switches", entry.entities.switches[0]);
    expect(note("state_address").textContent).toBe("Also used by: Circulation pump");
  });

  test("compares the internal address of LOGO! fields", () => {
    const profile = {
      family: "logo_0ba8",
      vm_last_byte: 850,
      areas: [],
      vm_areas: [{ name: "V", first: 0, last: 850, data_type: "X", width: 1, bit_min: 0, bit_max: 7 }],
    };
    const entry = createEntry({ plc_family: "logo_0ba8", data: { plc_family: "logo_0ba8" }, logo_profile: profile });
    entry.entities.entity_sync = [{ name: "Pump sync", source_entity: "input_boolean.pump", address: "DB1,X8.0" }];
    const panel = createPanel(entry);
    panel.openEditor(0, "entity_sync");
    expect(note("address").textContent).toBe("Also used by: Circulation pump");
  });

  test("does not flag shared availability addresses", () => {
    const entry = createEntry();
    entry.entities.sensors[0].availability_address = "DB1,X20.0";
    const panel = createPanel(entry);
    panel.openEditor(1, "sensors");
    expect(form().querySelector('[data-field="availability_address"] .address-duplicate')).toBeNull();
  });
});
