// @vitest-environment jsdom
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = callback => callback();
  installPanel();
});
afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});
const open = (entity) => {
  const entry = createEntry();
  entry.entities.binary_sensors = [entity];
  const panel = createPanel(entry);
  panel.openEditor(0, "binary_sensors");
  return { panel, form: document.querySelector("ha-dialog form") };
};
const changeMode = (form, mode) => {
  const input = form.querySelector(`input[name="binary_sensor_mode"][value="${mode}"]`);
  input.click();
};

test("existing direct sensors omit comparison configuration and require no threshold", () => {
  const original = { address: "DB1,X0.0", invert_state: true };
  const { panel, form } = open(original);
  expect(form.elements.binary_sensor_mode.value).toBe("direct");
  expect([...form.querySelectorAll('.form-section')].map(section => section.dataset.section))
    .toEqual(["binary-behavior", "addresses", "behavior", "ha"]);
  const modeSection = form.querySelector('[data-section="binary-behavior"]');
  expect(modeSection.querySelector('.section-head b').textContent).toBe("Binary sensor behavior");
  expect([...modeSection.querySelectorAll('.control-card b')].map(label => label.textContent))
    .toEqual(["Boolean state", "Numeric comparison"]);
  expect(modeSection.querySelectorAll('.control-card input[type="radio"]')).toHaveLength(2);
  expect([...modeSection.querySelectorAll('.control-card small')].every(help => help.textContent.length > 40)).toBe(true);
  expect(form.elements.device_class.closest('.form-section').dataset.section).toBe("behavior");
  expect(form.elements.invert_state.closest('.form-section').dataset.section).toBe("behavior");
  expect(form.elements.comparison_value.disabled).toBe(true);
  expect(form.elements.comparison_value.required).toBe(false);
  expect(form.querySelector('[data-field="comparison_value"]').classList.contains("hidden-field")).toBe(true);
  const saved = panel.formEntity(form, original, "binary_sensors");
  expect(saved.comparison_operator).toBeUndefined();
  expect(saved.comparison_value).toBeUndefined();
  expect(saved.binary_sensor_mode).toBeUndefined();
  expect(saved.invert_state).toBe(true);
});

test.each(["eq", "ne", "gt", "ge", "lt", "le"])("edits and saves comparison %s", operator => {
  const original = { address: "DB1,I10", comparison_operator: operator, comparison_value: 15 };
  const { panel, form } = open(original);
  expect(form.elements.binary_sensor_mode.value).toBe("comparison");
  expect(form.elements.comparison_operator.value).toBe(operator);
  expect(form.elements.comparison_value.required).toBe(true);
  expect(form.querySelector('[data-address-part="dataType"]').value).toBe("INT");
  form.elements.comparison_value.value = "-2.5";
  let saved = panel.formEntity(form, original, "binary_sensors");
  expect(saved.comparison_value).toBe(-2.5);
  expect(saved.comparison_operator).toBe(operator);
  expect(saved.address).toBe("DB1,I10");
  expect(saved.binary_sensor_mode).toBeUndefined();
  changeMode(form, "direct");
  saved = panel.formEntity(form, original, "binary_sensors");
  expect(saved.comparison_operator).toBeUndefined();
  expect(saved.comparison_value).toBeUndefined();
});

test("switching to comparison requires a threshold and preserves zero", () => {
  const original = { address: "DB1,I10" };
  const { panel, form } = open(original);
  changeMode(form, "comparison");
  expect(form.elements.comparison_value.disabled).toBe(false);
  expect(() => panel.formEntity(form, original, "binary_sensors")).toThrow();
  form.elements.comparison_value.value = "0";
  const saved = panel.formEntity(form, original, "binary_sensors");
  expect(saved.comparison_value).toBe(0);
  expect(saved.comparison_operator).toBe("eq");
});
