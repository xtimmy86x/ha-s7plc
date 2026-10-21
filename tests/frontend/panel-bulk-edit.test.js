// @vitest-environment jsdom

import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";

import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});
beforeEach(() => {
  // HA's scoped-custom-element-registry polyfill supports indexed/named
  // form.elements access, but its Symbol.iterator throws this exact error.
  // Exercise every bulk-edit flow with that same browser restriction.
  vi.spyOn(HTMLFormControlsCollection.prototype, Symbol.iterator).mockImplementation(() => {
    throw new Error("Method not implemented.");
  });
});
afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});

const token = "a".repeat(64);
const preview = (overrides = {}) => ({
  preview_token: token, changed_count: 1, default_scan_interval: 1,
  rows: [{
    entity_type: "sensors", uid: "temperature", name: "Boiler temperature", address: "DB1,REAL0",
    before: { area: "old", scan_interval: 5 }, after: { area: "room", scan_interval: 0.5 },
    scan_supported: true, changed: true,
  }],
  ...overrides,
});
const primary = (dialog) => dialog.querySelector('[slot="primaryAction"]');
const cancel = (dialog) => dialog.querySelector('[slot="secondaryAction"]');
const change = (form, name, value) => {
  form.elements[name].value = value;
  form.elements[name].dispatchEvent(new Event("change", { bubbles: true }));
};
const select = (panel, type, index) => {
  const input = panel.querySelector(`[data-entity-type="${type}"][data-select="${index}"]`);
  input.checked = true;
  input.dispatchEvent(new Event("change", { bubbles: true }));
};
function open({ sections = false, entry = createEntry(), secondType = "switches" } = {}) {
  const panel = createPanel(entry);
  panel._hass.areas = { old: { area_id: "old", name: "Old room" }, room: { area_id: "room", name: "Machine room" } };
  if (sections) panel.querySelector("[data-layout-toggle]").click();
  select(panel, "sensors", 0);
  if (sections) select(panel, secondType, 0);
  panel.querySelector("[data-batch-edit]").click();
  const dialog = document.body.querySelector("ha-dialog");
  return { panel, dialog, form: dialog.querySelector("form") };
}

test("starts unchanged and cancel saves nothing", () => {
  const { panel, dialog, form } = open();
  const call = vi.spyOn(panel._hass, "callWS");
  expect(dialog.headerTitle).toBe("Bulk edit");
  expect(form.elements.area_action.value).toBe("keep");
  expect(form.elements.scan_action.value).toBe("keep");
  expect(primary(dialog).disabled).toBe(true);
  expect(form.querySelector("[data-area-value]").hidden).toBe(true);
  expect(form.querySelector("[data-scan-value]").hidden).toBe(true);
  change(form, "area_action", "clear");
  cancel(dialog).onclick();
  expect(dialog.open).toBe(false);
  expect(panel.selectedIndices.size).toBe(1);
  expect(call).not.toHaveBeenCalled();
});

test("only shows and enables a value field when its action is set", () => {
  const { dialog, form } = open();
  const area = form.querySelector("[data-area-value]");
  const scan = form.querySelector("[data-scan-value]");
  expect(getComputedStyle(area).display).toBe("none");
  expect(getComputedStyle(scan).display).toBe("none");
  expect(form.elements.area.disabled).toBe(true);
  expect(form.elements.scan_interval.disabled).toBe(true);

  change(form, "area_action", "set");
  expect(getComputedStyle(area).display).not.toBe("none");
  expect(getComputedStyle(scan).display).toBe("none");
  expect(form.elements.area.disabled).toBe(false);
  expect(form.elements.area.required).toBe(true);
  expect(primary(dialog).disabled).toBe(false);

  change(form, "scan_action", "set");
  expect(getComputedStyle(scan).display).not.toBe("none");
  expect(form.elements.scan_interval.disabled).toBe(false);
  expect(form.elements.scan_interval.required).toBe(true);

  change(form, "area_action", "clear");
  change(form, "scan_action", "clear");
  expect(getComputedStyle(area).display).toBe("none");
  expect(getComputedStyle(scan).display).toBe("none");
  expect(form.elements.area.disabled).toBe(true);
  expect(form.elements.scan_interval.disabled).toBe(true);
  expect(form.elements.area.required).toBe(false);
  expect(form.elements.scan_interval.required).toBe(false);
  expect(primary(dialog).disabled).toBe(false);

  change(form, "area_action", "keep");
  change(form, "scan_action", "keep");
  expect(primary(dialog).disabled).toBe(true);
});

test("previews mixed selections and applies their captured identities once", async () => {
  const { panel, dialog, form } = open({ sections: true });
  const result = preview({ changed_count: 2 });
  result.rows.push({ ...result.rows[0], entity_type: "switches", uid: "pump", name: "Pump" });
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  panel._hass.callWS = vi.fn(async (message) => {
    if (message.type.endsWith("preview_update_entities")) return result;
    await pending;
    return { updated: 2 };
  });
  panel.load = vi.fn(async () => {});
  change(form, "area_action", "set");
  change(form, "area", "room");
  change(form, "scan_action", "set");
  change(form, "scan_interval", "0.5");
  await primary(dialog).onclick();
  expect(panel._hass.callWS).toHaveBeenCalledTimes(1);
  expect(dialog.querySelector("[data-bulk-preview]").textContent).toContain("2 of 2");
  expect(dialog.textContent).toContain("Old room");
  expect(dialog.textContent).toContain("Machine room");
  expect(dialog.querySelectorAll(".bulk-preview-table tbody tr")).toHaveLength(2);
  expect(primary(dialog).textContent).toBe("Apply changes");
  expect(panel.selectedIndices.size).toBe(2);

  // A panel refresh/reorder cannot redirect the operation to a different UID.
  panel.entries[0].entities.sensors.reverse();
  panel.entryId = "another-plc";
  const applying = primary(dialog).onclick();
  await Promise.resolve();
  await primary(dialog).onclick();
  expect(primary(dialog).disabled).toBe(true);
  expect(cancel(dialog).disabled).toBe(true);
  cancel(dialog).onclick();
  expect(dialog.open).toBe(true);
  const hide = new Event("wa-hide", { cancelable: true });
  dialog.dispatchEvent(hide);
  expect(hide.defaultPrevented).toBe(true);
  expect(panel._hass.callWS).toHaveBeenCalledTimes(2);
  const expected = {
    entry_id: "plc-entry",
    entities: [{ entity_type: "sensors", uid: "temperature" }, { entity_type: "switches", uid: "pump" }],
    changes: { area: "room", scan_interval: 0.5 },
  };
  expect(panel._hass.callWS.mock.calls[0][0]).toEqual({ type: "s7plc/config/preview_update_entities", ...expected });
  expect(panel._hass.callWS.mock.calls[1][0]).toEqual({ type: "s7plc/config/update_entities", ...expected, preview_token: token });
  release();
  await applying;
  expect(panel.load).toHaveBeenCalledOnce();
  expect(panel.selectedIndices.size).toBe(0);
  expect(dialog.open).toBe(false);
});

test("clearing overrides sends null and editing after preview requires a new preview", async () => {
  const { panel, dialog, form } = open();
  const result = preview();
  result.rows[0].after = { area: null, scan_interval: null };
  panel._hass.callWS = vi.fn(async () => result);
  change(form, "area_action", "clear");
  change(form, "scan_action", "clear");
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[0][0].changes).toEqual({ area: null, scan_interval: null });
  expect(dialog.querySelector("[data-bulk-preview]").textContent).toContain("PLC default (1 s)");
  change(form, "area_action", "keep");
  expect(dialog.querySelector("[data-bulk-preview]").hidden).toBe(true);
  expect(primary(dialog).textContent).toBe("Preview changes");
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[1][0].type).toBe("s7plc/config/preview_update_entities");
  expect(panel._hass.callWS.mock.calls[1][0].changes).toEqual({ scan_interval: null });
});

test.each(["", "0", "0.01", "3601"])("invalid scan input %s never requests preview", async (value) => {
  const { panel, dialog, form } = open();
  panel._hass.callWS = vi.fn();
  change(form, "scan_action", "set");
  change(form, "scan_interval", value);
  await primary(dialog).onclick();
  expect(panel._hass.callWS).not.toHaveBeenCalled();
});

test("no-op/unsupported rows remain visible but cannot be applied, and text is escaped", async () => {
  const { panel, dialog, form } = open();
  const result = preview({ changed_count: 0 });
  result.rows[0] = {
    ...result.rows[0], entity_type: "buttons", name: "<img src=x onerror=alert(1)>",
    scan_supported: false, changed: false,
  };
  panel._hass.callWS = vi.fn(async () => result);
  change(form, "scan_action", "clear");
  await primary(dialog).onclick();
  const table = dialog.querySelector(".bulk-preview-table");
  expect(table.textContent).toContain("Not applicable");
  expect(table.textContent).toContain("Unchanged");
  expect(table.textContent).toContain("<img src=x onerror=alert(1)>");
  expect(table.querySelector("img")).toBeNull();
  expect(primary(dialog).disabled).toBe(true);
  await primary(dialog).onclick();
  expect(panel._hass.callWS).toHaveBeenCalledOnce();
});

test("stale preview is discarded and the selection is retained", async () => {
  const { panel, dialog, form } = open();
  panel._hass.callWS = vi.fn(async (message) => {
    if (message.type.endsWith("preview_update_entities")) return preview();
    throw { code: "bulk_edit_conflict", message: "bulk_edit_conflict" };
  });
  change(form, "area_action", "clear");
  await primary(dialog).onclick();
  await primary(dialog).onclick();
  expect(panel.selectedIndices.size).toBe(1);
  expect(dialog.open).toBe(true);
  expect(dialog.querySelector("ha-alert").textContent).toContain("Generate a new preview");
  expect(dialog.querySelector("[data-bulk-preview]").hidden).toBe(true);
  expect(primary(dialog).textContent).toBe("Preview changes");
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[2][0].type).toBe("s7plc/config/preview_update_entities");
});

test("transient apply failure can be retried without losing the preview", async () => {
  const { panel, dialog, form } = open();
  panel._hass.callWS = vi.fn().mockResolvedValueOnce(preview()).mockRejectedValueOnce(new Error("Disconnected")).mockResolvedValueOnce({ updated: 1 });
  panel.load = vi.fn(async () => {});
  change(form, "area_action", "clear");
  await primary(dialog).onclick();
  await primary(dialog).onclick();
  expect(primary(dialog).textContent).toBe("Apply changes");
  expect(primary(dialog).disabled).toBe(false);
  expect(dialog.querySelector("ha-alert").textContent).toContain("Disconnected");
  expect(panel.selectedIndices.size).toBe(1);
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[2][0]).toEqual(panel._hass.callWS.mock.calls[1][0]);
  expect(dialog.open).toBe(false);
});

test("a refresh failure after saving cannot resubmit the operation", async () => {
  const { panel, dialog, form } = open();
  panel._hass.callWS = vi.fn().mockResolvedValueOnce(preview()).mockResolvedValueOnce({ updated: 1 });
  panel.load = vi.fn(async () => { throw new Error("Refresh failed"); });
  change(form, "area_action", "clear");
  await primary(dialog).onclick();
  await primary(dialog).onclick();
  expect(dialog.querySelector("ha-alert").textContent).toContain("Changes saved");
  expect(primary(dialog).disabled).toBe(true);
  expect(cancel(dialog).textContent).toBe("Close");
  await primary(dialog).onclick();
  expect(panel._hass.callWS).toHaveBeenCalledTimes(2);
  cancel(dialog).onclick();
  expect(dialog.open).toBe(false);
});

test("numeric and metadata fields preview typed values before one apply", async () => {
  const entry = createEntry();
  entry.entities.numbers = [{ uid: "setpoint", address: "DB1,REAL8", min_value: 0, max_value: 100 }];
  entry.selector_options = { device_classes: { sensors: ["temperature", "energy"], numbers: ["temperature"] }, state_classes: ["measurement", "total", "total_increasing"], units: ["°C", "kWh"] };
  const { panel, dialog, form } = open({ entry, sections: true, secondType: "numbers" });
  const details = form.querySelector("details");
  expect(details.open).toBe(false);
  details.open = true;
  const values = { value_multiplier: "0.25", real_precision: "2", device_class: "temperature", unit_of_measurement: "°C", state_class: "none" };
  for (const [key, value] of Object.entries(values)) {
    change(form, `${key}_action`, "set");
    change(form, key, value);
  }
  expect(form.querySelector("#s7plc-bulk-units option").value).toBe("°C");
  const result = preview({ error_count: 0, default_real_precision: 1 });
  Object.assign(result.rows[0], {
    before: { value_multiplier: { type: "linear_scale", plc_min: 0, plc_max: 100, ha_min: 0, ha_max: 10 }, real_precision: null, device_class: null, unit_of_measurement: null, state_class: null },
    after: { value_multiplier: { type: "multiplier", factor: 0.25 }, real_precision: 2, device_class: "temperature", unit_of_measurement: "°C", state_class: "none" },
    supported_fields: Object.keys(values), conversion_replaced: true,
  });
  result.rows.push({ ...result.rows[0], entity_type: "numbers", uid: "setpoint", supported_fields: Object.keys(values).filter(key => key !== "state_class"), conversion_replaced: false });
  panel._hass.callWS = vi.fn().mockResolvedValueOnce(result).mockResolvedValueOnce({ updated: 2 });
  panel.load = vi.fn(async () => {});
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[0][0].changes).toEqual({ ...values, value_multiplier: 0.25, real_precision: 2 });
  const table = dialog.querySelector(".bulk-preview-table");
  expect(table.textContent).toContain("0–100 → 0–10");
  expect(table.textContent).toContain("× 0.25");
  expect(table.textContent).toContain("None (disable statistics)");
  expect(table.textContent).toContain("Not applicable");
  expect(table.textContent).toContain("existing conversion will be replaced");
  expect(panel._hass.callWS).toHaveBeenCalledOnce();
  await primary(dialog).onclick();
  expect(panel._hass.callWS).toHaveBeenCalledTimes(2);
  expect(panel._hass.callWS.mock.calls[1][0].preview_token).toBe(token);
  expect(dialog.open).toBe(false);
});

test("incompatible metadata blocks applying every entity while retaining edits", async () => {
  const { panel, dialog, form } = open();
  change(form, "unit_of_measurement_action", "set");
  change(form, "unit_of_measurement", "bar");
  const result = preview({ error_count: 1 });
  Object.assign(result.rows[0], { before: { unit_of_measurement: "°C" }, after: { unit_of_measurement: "bar" }, supported_fields: ["unit_of_measurement"], errors: ["invalid_unit_of_measurement"] });
  panel._hass.callWS = vi.fn(async () => result);
  await primary(dialog).onclick();
  expect(dialog.querySelector("[data-bulk-preview]").textContent).toContain("Resolve the errors");
  expect(dialog.querySelector(".bulk-preview-error").textContent).toContain("unit compatible");
  expect(primary(dialog).disabled).toBe(true);
  await primary(dialog).onclick();
  expect(panel._hass.callWS).toHaveBeenCalledOnce();
  expect(panel.selectedIndices.size).toBe(1);
  change(form, "unit_of_measurement", "°C");
  expect(dialog.querySelector("[data-bulk-preview]").hidden).toBe(true);
  expect(primary(dialog).disabled).toBe(false);
  expect(primary(dialog).textContent).toBe("Preview changes");
});

test.each([
  { address: "DB1,S0.20" },
  { address: "DB1,W0", value_conversions: { value: { type: "enum_map", mappings: [{ value: 0, label: "Off" }] } } },
])("does not offer numeric or metadata edits for text/enum selections: %j", item => {
  const entry = createEntry();
  entry.entities.sensors[0] = { ...entry.entities.sensors[0], ...item };
  const { form } = open({ entry });
  expect(form.querySelector("details")).toBeNull();
  expect(form.elements.value_multiplier).toBeUndefined();
  expect(form.elements.device_class).toBeUndefined();
  expect(form.elements.area_action).toBeTruthy();
  expect(form.elements.scan_action).toBeTruthy();
});

test.each(["", "-1", "1.5", "7"])("invalid precision %s reopens its section without requesting a preview", async value => {
  const { panel, dialog, form } = open();
  panel._hass.callWS = vi.fn();
  const details = form.querySelector("details");
  details.open = true;
  change(form, "real_precision_action", "set");
  change(form, "real_precision", value);
  details.open = false;
  await primary(dialog).onclick();
  expect(details.open).toBe(true);
  expect(panel._hass.callWS).not.toHaveBeenCalled();
});

test("removing numeric overrides sends null and displays effective automatic metadata", async () => {
  const { panel, dialog, form } = open();
  const changes = { value_multiplier: null, real_precision: null, unit_of_measurement: null, state_class: null };
  for (const key of Object.keys(changes)) change(form, `${key}_action`, "clear");
  const result = preview({ default_real_precision: 1 });
  Object.assign(result.rows[0], {
    before: { value_multiplier: { type: "expression", read_expression: "x <img src=x>" }, real_precision: 5, unit_of_measurement: "Wh", state_class: "none" },
    after: changes, effective_after: { unit_of_measurement: "kWh", state_class: "total_increasing" }, supported_fields: Object.keys(changes), conversion_replaced: true,
  });
  panel._hass.callWS = vi.fn(async () => result);
  await primary(dialog).onclick();
  expect(panel._hass.callWS.mock.calls[0][0].changes).toEqual(changes);
  const table = dialog.querySelector(".bulk-preview-table");
  expect(table.textContent).toContain("Automatic (kWh)");
  expect(table.textContent).toContain("Automatic (Total Increasing)");
  expect(table.textContent).toContain("Default (decimal places: 1)");
  expect(table.textContent).toContain("x <img src=x>");
  expect(table.querySelector("img")).toBeNull();
});
