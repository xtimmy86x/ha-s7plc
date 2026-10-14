// @vitest-environment jsdom
import { afterEach, beforeAll, expect, test, vi } from 'vitest';
import { createEntry, createPanel, getPanelTestHelpers, installPanel } from './panel-fixture.js';

beforeAll(() => {
  globalThis.requestAnimationFrame = callback => callback();
  installPanel();
});
afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});
const original = { uid: 'alarms-1', name: 'Machine', start_address: 'DB1,X0.0', end_address: 'DB1,X100.7', active_value: 0, alarms: [{ address: 'DB1,X0.0', description: 'Motor', enabled: false }] };
const open = (item = original) => {
  const entry = createEntry();
  entry.entities.alarm_groups = [item];
  entry.entity_ids = { ...entry.entity_ids, alarm_groups: ['sensor.machine_alarms'] };
  const panel = createPanel(entry);
  panel.type = 'alarm_groups';
  panel.render();
  panel.openEditor(0, 'alarm_groups');
  return { panel, form: document.querySelector('ha-dialog form'), dialog: document.querySelector('ha-dialog') };
};

test('group editor preserves active-low, exclusions and range through save', () => {
  const { panel, form } = open();
  expect(form.elements.active_value.value).toBe('0');
  expect(form.querySelector('[data-enabled]').checked).toBe(false);
  const saved = panel.formEntity(form, original, 'alarm_groups');
  expect(saved).toMatchObject(original);
  expect(form.querySelector('[data-field="start_address"] [data-address-part="dataType"]').value).toBe('BIT');
  expect(panel.querySelector('[data-type="alarm_groups"]')).not.toBeNull();
});

test.each([
  ['address;description;enabled\nDB1,X0.0;Motor;0\nDB1,X0.1;Pump;1', 'Motor'],
  ['DB1,X0.0\tMotor\t0\nDB1,X0.1\tPump\t1', 'Motor'],
  ['"DB1,X0.0","Motor; \"\"A\"\"",false\n"DB1,X0.1",Pump,true', 'Motor; "A"'],
])('imports CSV and Excel, updating the matching row (%s)', (csv, label) => {
  const { panel, form } = open();
  form.querySelector('[data-alarm-paste]').value = csv;
  form.querySelector('[data-alarm-import]').click();
  expect(form.querySelector('[data-alarm-error]').textContent).toBe('');
  const saved = panel.formEntity(form, original, 'alarm_groups');
  expect(saved.alarms).toEqual([
    { address: 'DB1,X0.0', description: label, enabled: false },
    { address: 'DB1,X0.1', description: 'Pump', enabled: true },
  ]);
});

test('failed import leaves existing descriptions intact', () => {
  const { panel, form } = open();
  form.querySelector('[data-alarm-paste]').value = 'DB1,X0.0;Motor;perhaps';
  form.querySelector('[data-alarm-import]').click();
  expect(form.querySelector('[data-alarm-error]').textContent).toContain('Invalid import');
  expect(panel.formEntity(form, original, 'alarm_groups').alarms).toEqual(original.alarms);
});

test('add, edit and delete rows without generating per-bit entities', () => {
  const { panel, form } = open();
  form.querySelector('[data-alarm-add]').click();
  const rows = form.querySelector('[data-alarm-rows]');
  rows.lastElementChild.querySelector('[data-address]').value = 'DB1,X0.2';
  rows.lastElementChild.querySelector('[data-description]').value = 'Pressure';
  rows.lastElementChild.dispatchEvent(new Event('input', { bubbles: true }));
  rows.firstElementChild.querySelector('[data-remove]').click();
  expect(panel.formEntity(form, original, 'alarm_groups').alarms).toEqual([{ address: 'DB1,X0.2', description: 'Pressure', enabled: true }]);
});

test('YAML saves the YAML editor, not the CSV paste buffer', async () => {
  const { panel, form, dialog } = open();
  const messages = [];
  panel._hass.callWS = vi.fn(async message => { messages.push(message); return {}; });
  panel.load = vi.fn();
  form.querySelector('[data-alarm-paste]').value = 'CSV buffer';
  dialog.querySelector('.yaml-editor textarea').value = 'name: YAML group';
  dialog.querySelector('[data-mode="yaml"]').click();
  await dialog.querySelector('[slot="primaryAction"]').onclick();
  expect(messages[0].entity_yaml).toBe('name: YAML group');
});

test('live list updates, escapes labels and hides cached alarms when unavailable', () => {
  const { panel } = open();
  const list = panel.querySelector('[data-alarm-live]');
  expect(list.textContent).toBe('Data unavailable');
  panel._hass.states['sensor.machine_alarms'] = { state: '1', attributes: { active_alarms: [{ address: 'DB1,X0.0', description: '<img src=x onerror=alert(1)>' }] } };
  panel.updateStates();
  expect(list.textContent).toContain('<img src=x');
  expect(list.querySelector('img')).toBeNull();
  panel._hass.states['sensor.machine_alarms'].state = 'unavailable';
  panel.updateStates();
  expect(list.textContent).toBe('Data unavailable');
  panel._hass.states['sensor.machine_alarms'] = { state: '0', attributes: { active_alarms: [] } };
  panel.updateStates();
  expect(list.textContent).toBe('No active alarms');
});

test('CSV parser canonicalizes shorthand and rejects duplicate or unclosed rows', () => {
  const { PARSE_ALARM_CSV } = getPanelTestHelpers();
  expect(PARSE_ALARM_CSV('DB1,0.0;Motor')[0].address).toBe('DB1,X0.0');
  expect(() => PARSE_ALARM_CSV('DB1,X0.0;A\nDB1,0.0;B')).toThrow();
  expect(() => PARSE_ALARM_CSV('"DB1,X0.0","bad')).toThrow();
  expect(() => PARSE_ALARM_CSV('DB1,X0.9;A')).toThrow();
});
