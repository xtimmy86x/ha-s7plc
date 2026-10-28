// @vitest-environment jsdom
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => { globalThis.requestAnimationFrame = cb => cb(); installPanel(); });
afterEach(() => { document.body.replaceChildren(); localStorage.clear(); vi.restoreAllMocks(); });
const dialog = () => document.body.querySelector("ha-dialog");
const choose = (form, mode) => {
  const input = form.querySelector(`input[name="control_behavior"][value="${mode}"]`);
  input.checked = true;
  input.dispatchEvent(new Event("change", { bubbles: true }));
};
const address = (form, key, value) => {
  const field = form.querySelector(`[data-field="${key}"]`);
  field.querySelector('[data-address-mode="manual"]').click();
  const input = field.querySelector('[data-address-manual]');
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
};

test.each(["switches", "lights"])("creates, saves and reopens separate pulse commands for %s", async type => {
  const entry = createEntry();
  const original = { uid: "dual", name: "Light relay", state_address: "I1.3", command_address: "Q1.0" };
  entry.entities[type] = [original];
  const panel = createPanel(entry);
  panel.openEditor(0, type);
  let form = dialog().querySelector("form");
  expect(form.querySelector('[data-field="off_command_address"]').classList.contains('hidden-field')).toBe(true);
  choose(form, "dual_pulse");
  expect(form.querySelector('[data-field="off_command_address"]').classList.contains('hidden-field')).toBe(false);
  expect(form.querySelector('[data-field="pulse_duration"]').classList.contains('hidden-field')).toBe(false);
  expect(form.querySelector('[data-field="state_address"]').dataset.required).toBe("false");
  expect(form.querySelector('[data-field="command_address"]').dataset.required).toBe("true");
  expect(() => panel.formEntity(form, original, type)).toThrow();
  address(form, "off_command_address", "Q1.1");
  form.elements.pulse_duration.value = "0.7";
  panel._hass.callWS = vi.fn(async message => { entry.entities[type][0] = message.entity; return { entities: entry.entities[type] }; });
  panel.load = vi.fn(async () => {});
  await dialog().querySelector('[slot="primaryAction"]').onclick();
  expect(panel._hass.callWS).toHaveBeenCalledWith(expect.objectContaining({
    type: 's7plc/config/save_entity', entity_type: type,
    entity: expect.objectContaining({ uid: "dual", off_command_address: "Q1.1", pulse_duration: 0.7, sync_state: false, pulse_command: false }),
  }));
  expect(original).not.toHaveProperty("off_command_address");
  panel.openEditor(0, type);
  form = dialog().querySelector("form");
  expect(form.elements.control_behavior.value).toBe("dual_pulse");
  expect(form.elements.off_command_address.value).toBe("Q1.1");
  const order = [...form.querySelectorAll('[data-section]')].map(e => e.dataset.section);
  expect(order.indexOf('command')).toBeLessThan(order.indexOf('addresses'));
  choose(form, "direct");
  expect(panel.formEntity(form, entry.entities[type][0], type)).not.toHaveProperty("off_command_address");
  expect(form.querySelector('[data-field="state_address"]').dataset.required).toBe("true");
});

test.each(["switches", "lights"])("allows optional feedback only in separate pulse mode for %s", type => {
  const entry = createEntry();
  const original = { uid: 'dual', command_address: 'Q1.0', off_command_address: 'Q1.1' };
  entry.entities[type] = [original];
  const panel = createPanel(entry);
  panel.openEditor(0, type);
  const form = dialog().querySelector('form');
  expect(panel.formEntity(form, original, type)).not.toHaveProperty('state_address');
  choose(form, 'direct');
  expect(() => panel.formEntity(form, original, type)).toThrow();
  address(form, 'state_address', '');
  choose(form, 'dual_pulse');
  expect(panel.formEntity(form, original, type)).not.toHaveProperty('state_address');
  address(form, 'command_address', '');
  expect(() => panel.formEntity(form, original, type)).toThrow();
});

test.each(["switches", "lights"])("keeps OFF output in the YAML editor for %s", type => {
  const entry = createEntry();
  entry.entities[type] = [{uid: 'dual', command_address: 'Q1.0', off_command_address: 'Q1.1'}];
  const panel = createPanel(entry);
  panel.openEditor(0, type);
  dialog().querySelector('[data-mode="yaml"]').click();
  expect(dialog().querySelector('.yaml-editor textarea').value).toContain('off_command_address: "Q1.1"');
  expect(dialog().querySelector('.yaml-editor textarea').value).not.toContain('control_behavior:');
});
