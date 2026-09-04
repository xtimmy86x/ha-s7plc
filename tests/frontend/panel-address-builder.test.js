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

const dialogForm = () => document.body.querySelector("ha-dialog form");
const setPart = (builder, name, value) => {
  const input = builder.querySelector(`[data-address-part="${name}"]`);
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
};

describe("S7 address builder", () => {
  test("builds a canonical address and updates dependent controls", () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');

    setPart(builder, "area", "DB");
    setPart(builder, "dbNumber", "5");
    setPart(builder, "dataType", "REAL");
    setPart(builder, "offset", "12");

    expect(form.elements.address.value).toBe("DB5,R12");
    expect(builder.querySelector(".address-preview code").textContent).toBe("DB5,R12");
    expect(builder.querySelector("[data-db-number]").hidden).toBe(false);
    expect(builder.querySelector("[data-bit]").hidden).toBe(true);
    expect(builder.querySelector("[data-length]").hidden).toBe(true);
    expect(builder.dataset.addressError).toBe("");
  });

  test("preserves values across modes and reports invalid manual input", () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const manualButton = builder.querySelector('[data-address-mode="manual"]');
    const guidedButton = builder.querySelector('[data-address-mode="guided"]');
    const manual = builder.querySelector("[data-address-manual]");

    manualButton.click();
    expect(manual.value).toBe("DB1,R0");
    expect(form.elements.address.value).toBe("DB1,R0");

    manual.value = "DB1,X0.8";
    manual.dispatchEvent(new Event("input", { bubbles: true }));
    expect(builder.dataset.addressError).toBe("invalid");
    expect(builder.querySelector(".address-error").hidden).toBe(false);
    guidedButton.click();
    expect(manualButton.classList.contains("active")).toBe(true);

    manual.value = "DB2,REAL4";
    manual.dispatchEvent(new Event("input", { bubbles: true }));
    guidedButton.click();
    expect(guidedButton.classList.contains("active")).toBe(true);
    expect(form.elements.address.value).toBe("DB2,REAL4");
    expect(builder.querySelector('[data-address-part="dbNumber"]').value).toBe("2");
  });

  test("applies a mode to every address without changing stored values", () => {
    const panel = createPanel();
    panel.openEditor(0, "switches");
    const form = dialogForm();
    const builders = [...form.querySelectorAll("[data-address-builder]")];
    const before = builders.map((builder) => builder.querySelector('input[type="hidden"]').value);

    document.body.querySelector('[data-apply-address-mode="manual"]').click();

    expect(builders.every((builder) => builder.querySelector('[data-address-mode="manual"]').classList.contains("active"))).toBe(true);
    expect(builders.map((builder) => builder.querySelector('input[type="hidden"]').value)).toEqual(before);
    expect(document.body.querySelector("[data-address-bulk-status]").textContent).toContain("Manual");
  });

  test("blocks an incomplete required address and focuses its builder", () => {
    const panel = createPanel();
    panel.openEditor(null, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const focus = vi.spyOn(builder, "focus");

    expect(panel.validateAddressBuilders(form)).toBe(false);
    expect(builder.dataset.addressError).toBe("incomplete");
    expect(focus).toHaveBeenCalledOnce();
  });

  test("offers binary and numeric addresses to entity sync and serializes both", () => {
    const entry = createEntry();
    entry.entities.entity_sync = [{
      name: "Demand sync",
      source_entity: "input_boolean.demand",
      address: "DB1,X0.0",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "entity_sync");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const types = [...builder.querySelectorAll('[data-address-part="dataType"] option')]
      .map((option) => option.value)
      .filter(Boolean);

    expect(types).toEqual([
      "BIT", "BYTE", "USINT", "SINT", "WORD", "INT", "DWORD", "DINT",
      "REAL", "LREAL",
    ]);
    expect(types).not.toContain("TIME");
    expect(types).not.toContain("STRING");
    expect(panel.formEntity(form, entry.entities.entity_sync[0], "entity_sync").address)
      .toBe("DB1,X0.0");

    setPart(builder, "area", "DB");
    setPart(builder, "dbNumber", "2");
    setPart(builder, "dataType", "REAL");
    setPart(builder, "offset", "4");
    expect(panel.formEntity(form, entry.entities.entity_sync[0], "entity_sync").address)
      .toBe("DB2,R4");
  });
});

describe("LOGO address builder", () => {
  test("converts a native LOGO input into its canonical S7 address", () => {
    const entry = createEntry({
      plc_family: "logo_0ba8",
      data: { plc_family: "logo_0ba8" },
      logo_profile: {
        family: "logo_0ba8",
        areas: [{ name: "I", first: 1, last: 24, vm_offset: 1024, data_type: "X" }],
        vm_areas: [{ name: "V", first: 0, last: 850, data_type: "X", width: 1, bit_min: 0, bit_max: 7 }],
      },
    });
    entry.entities.binary_sensors = [{ name: "Input", address: "DB1,X1024.0" }];
    const panel = createPanel(entry);
    panel.openEditor(0, "binary_sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const area = builder.querySelector("[data-logo-area]");
    const number = builder.querySelector("[data-logo-number]");

    expect(builder.hasAttribute("data-logo-builder")).toBe(true);
    expect(builder.querySelector("[data-logo-preview]").textContent).toBe("I1");
    area.value = "I";
    area.dispatchEvent(new Event("change", { bubbles: true }));
    number.value = "2";
    number.dispatchEvent(new Event("input", { bubbles: true }));

    expect(builder.querySelector("[data-logo-preview]").textContent).toBe("I2");
    expect(builder.querySelector("[data-internal-preview]").textContent).toBe("DB1,X1024.1");
    expect(form.elements.address.value).toBe("DB1,X1024.1");
    expect(builder.dataset.addressError).toBe("");
  });

  test("preserves manual input while typing and recovers from LOGO errors", () => {
    const entry = createEntry({
      plc_family: "logo_0ba8",
      data: { plc_family: "logo_0ba8" },
      logo_profile: {
        family: "logo_0ba8",
        areas: [],
        vm_areas: [{ name: "VW", first: 0, last: 849, data_type: "WORD", width: 2 }],
      },
    });
    entry.entities.sensors = [{ name: "VM word", address: "DB1,WORD2" }];
    const panel = createPanel(entry);
    panel.openEditor(0, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const manualButton = builder.querySelector('[data-address-mode="manual"]');
    const guidedButton = builder.querySelector('[data-address-mode="guided"]');
    const manual = builder.querySelector("[data-address-manual]");
    const type = (value) => {
      manual.value = value;
      manual.dispatchEvent(new Event("input", { bubbles: true }));
    };

    manualButton.click();
    type("VW");
    expect(manual.value).toBe("VW");
    expect(form.elements.address.value).toBe("");
    expect(builder.dataset.addressError).not.toBe("");

    type("VW9999");
    expect(manual.value).toBe("VW9999");
    expect(builder.dataset.addressError).toBe("address_out_of_range");

    type("VW2");
    expect(form.elements.address.value).toBe("DB1,WORD2");
    expect(builder.querySelector("[data-logo-preview]").textContent).toBe("VW2");
    expect(builder.dataset.addressError).toBe("");

    type("DB1,REAL0");
    guidedButton.click();
    expect(manualButton.classList.contains("active")).toBe(true);
    expect(manual.value).toBe("DB1,REAL0");
    expect(form.elements.address.value).toBe("DB1,REAL0");
    expect(builder.dataset.addressError).toBe("");
  });
});
