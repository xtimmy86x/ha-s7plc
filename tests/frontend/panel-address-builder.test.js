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
  test("persists the global default and lets a field preference override it", () => {
    const entry = createEntry();
    entry.entities.sensors[0].uid = "boiler-temperature";
    const second = createEntry({ entry_id: "second-plc", title: "CPU1511" });
    const panel = createPanel(entry);
    panel.entries = [entry, second];
    panel.render();
    const manualDefault = panel.querySelector('[data-default-address-mode="manual"]');

    expect(panel.querySelector('[data-default-address-mode="guided"]').getAttribute("aria-pressed")).toBe("true");
    manualDefault.click();
    expect(localStorage.getItem("s7plc-panel-default-address-mode-v1")).toBe("manual");
    expect(manualDefault.getAttribute("aria-pressed")).toBe("true");

    panel.openEditor(0, "sensors");
    let builder = dialogForm().querySelector('[data-field="address"]');
    expect(builder.querySelector('[data-address-mode="manual"]').classList.contains("active")).toBe(true);
    builder.querySelector('[data-address-mode="guided"]').click();
    expect(builder.querySelector('[data-address-mode="guided"]').classList.contains("active")).toBe(true);

    document.body.querySelector("ha-dialog").remove();
    panel.openEditor(0, "sensors");
    builder = dialogForm().querySelector('[data-field="address"]');
    expect(builder.querySelector('[data-address-mode="guided"]').classList.contains("active")).toBe(true);

    document.body.querySelector("ha-dialog").remove();
    panel.entryId = "second-plc";
    panel.render();
    expect(panel.querySelector('[data-default-address-mode="manual"]').getAttribute("aria-pressed")).toBe("true");
  });

  test("falls back safely for invalid defaults and unavailable storage", () => {
    const panel = createPanel();
    localStorage.setItem("s7plc-panel-default-address-mode-v1", "mixed");
    expect(panel.readDefaultAddressMode()).toBe("guided");

    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(panel.readDefaultAddressMode()).toBe("guided");
    getItem.mockRestore();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(panel.writeDefaultAddressMode("manual")).toBe(false);
    expect(panel.writeDefaultAddressMode("mixed")).toBe(false);
  });

  test("isolates address preferences by PLC, entity, and field", () => {
    const first = createEntry();
    first.entities.switches[0].uid = "pump-a";
    first.entities.switches.push({
      uid: "pump-b",
      name: "Second pump",
      state_address: "DB1,X10.0",
      command_address: "DB1,X10.1",
    });
    const second = createEntry({ entry_id: "second-plc", title: "CPU1511" });
    second.entities.switches[0].uid = "pump-a";
    const panel = createPanel(first);
    panel.entries = [first, second];

    panel.openEditor(0, "switches");
    let form = dialogForm();
    form.querySelector('[data-field="state_address"] [data-address-mode="manual"]').click();
    document.body.querySelector("ha-dialog").remove();

    panel.openEditor(0, "switches");
    form = dialogForm();
    expect(form.querySelector('[data-field="state_address"] [data-address-mode="manual"]').classList.contains("active")).toBe(true);
    expect(form.querySelector('[data-field="command_address"] [data-address-mode="guided"]').classList.contains("active")).toBe(true);
    document.body.querySelector("ha-dialog").remove();

    panel.openEditor(1, "switches");
    expect(dialogForm().querySelector('[data-field="state_address"] [data-address-mode="guided"]').classList.contains("active")).toBe(true);
    document.body.querySelector("ha-dialog").remove();

    panel.entryId = "second-plc";
    panel.openEditor(0, "switches");
    expect(dialogForm().querySelector('[data-field="state_address"] [data-address-mode="guided"]').classList.contains("active")).toBe(true);
    document.body.querySelector("ha-dialog").remove();

    localStorage.setItem("s7plc-panel-address-modes-v1", "{bad json");
    panel.openEditor(0, "switches");
    expect(dialogForm().querySelector('[data-field="state_address"] [data-address-mode="guided"]').classList.contains("active")).toBe(true);
    document.body.querySelector("ha-dialog").remove();

    second.entities.switches[0].state_address = "not-an-address";
    panel.openEditor(0, "switches");
    expect(dialogForm().querySelector('[data-field="state_address"] [data-address-mode="manual"]').classList.contains("active")).toBe(true);
  });

  test("builds a canonical address and updates dependent controls", () => {
    const panel = createPanel();
    panel.openEditor(0, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');

    expect(builder.tagName).toBe("FIELDSET");
    expect(builder.querySelector(":scope > legend + .address-builder-layout")).not.toBeNull();

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
  test("selects the matching VM area and exposes bit controls only for V", () => {
    const profile = {
      family: "logo_0ba8",
      vm_last_byte: 850,
      areas: [],
      vm_areas: [
        { name: "V", first: 0, last: 850, data_type: "X", width: 1, bit_min: 0, bit_max: 7 },
        { name: "VB", first: 0, last: 850, data_type: "BYTE", width: 1 },
        { name: "VW", first: 0, last: 849, data_type: "WORD", width: 2 },
        { name: "VD", first: 0, last: 847, data_type: "DWORD", width: 4 },
      ],
    };
    const cases = [
      ["DB1,BYTE10", "VB", true],
      ["DB1,WORD20", "VW", true],
      ["DB1,DWORD30", "VD", true],
      ["DB1,X10.3", "V", false],
    ];

    for (const [address, area, bitHidden] of cases) {
      document.body.replaceChildren();
      const entry = createEntry({ plc_family: "logo_0ba8", data: { plc_family: "logo_0ba8" }, logo_profile: profile });
      entry.entities.entity_sync = [{ name: area, source_entity: "input_number.test", address }];
      const panel = createPanel(entry);
      panel.openEditor(0, "entity_sync");
      const builder = dialogForm().querySelector('[data-field="address"]');

      expect(builder.querySelector("[data-logo-area]").value).toBe(area);
      expect(builder.querySelector("[data-logo-number-text]").textContent).toBe("VM offset");
      expect(builder.querySelector("[data-logo-bit]").hidden).toBe(bitHidden);
      expect(builder.querySelector('input[type="hidden"]').value).toBe(address);
    }
  });

  test("keeps LOGO text addresses in manual mode", () => {
    const entry = createEntry({
      plc_family: "logo_0ba8",
      data: { plc_family: "logo_0ba8" },
      logo_profile: {
        family: "logo_0ba8",
        areas: [{ name: "I", first: 1, last: 24, vm_offset: 1024, data_type: "X" }],
        vm_areas: [],
      },
    });
    entry.entities.texts = [{ name: "Message", address: "DB1,S0.20" }];
    const panel = createPanel(entry);
    panel.openEditor(0, "texts");
    const builder = dialogForm().querySelector('[data-field="address"]');

    expect(builder.querySelector('[data-address-mode="guided"]').disabled).toBe(true);
    expect(builder.querySelector('[data-address-mode="manual"]').classList.contains("active")).toBe(true);
    expect(builder.querySelector(".address-guided").hidden).toBe(true);
    expect(builder.querySelector("[data-address-manual]").value).toBe("DB1,S0.20");
    expect(builder.querySelector('input[type="hidden"]').value).toBe("DB1,S0.20");
  });

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
    expect(builder.tagName).toBe("FIELDSET");
    expect(builder.querySelector(":scope > legend + .address-builder-layout")).not.toBeNull();
    expect(builder.querySelector(".address-manual").hidden).toBe(true);
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

  test("validates empty LOGO fields and generates only after selecting an area", () => {
    const entry = createEntry({
      plc_family: "logo_0ba8",
      data: { plc_family: "logo_0ba8" },
      logo_profile: {
        family: "logo_0ba8",
        areas: [{ name: "AI", first: 1, last: 8, vm_offset: 1032, data_type: "INT" }],
        vm_areas: [{ name: "VW", first: 0, last: 849, data_type: "WORD", width: 2 }],
      },
    });
    const panel = createPanel(entry);
    panel.openEditor(null, "sensors");
    const form = dialogForm();
    const builder = form.querySelector('[data-field="address"]');
    const area = builder.querySelector("[data-logo-area]");

    expect(form.elements.address.value).toBe("");
    expect(builder.dataset.addressError).toBe("incomplete");
    expect(panel.validateAddressBuilders(form)).toBe(false);

    area.value = "AI";
    area.dispatchEvent(new Event("change", { bubbles: true }));
    expect(form.elements.address.value).toBe("DB1,INT1032");
    expect(builder.querySelector("[data-logo-preview]").textContent).toBe("AI1");
    expect(builder.dataset.addressError).toBe("");
    expect(panel.validateAddressBuilders(form)).toBe(true);

    area.value = "";
    area.dispatchEvent(new Event("change", { bubbles: true }));
    expect(form.elements.address.value).toBe("");
    expect(builder.dataset.addressError).toBe("incomplete");

    document.body.replaceChildren();
    const numberPanel = createPanel(entry);
    numberPanel.openEditor(null, "numbers");
    const command = dialogForm().querySelector('[data-field="command_address"]');
    expect(command.dataset.required).toBe("false");
    expect(command.dataset.addressError).toBe("");
    expect(command.querySelector("[data-logo-area]").value).toBe("");
  });
});
