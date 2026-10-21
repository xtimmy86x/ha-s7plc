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
const merker = { ...original, start_address: 'M0.0', end_address: 'M1.7', alarms: [{ address: 'M0.0', description: 'Motor', enabled: false }] };
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
  expect(form.querySelector('[data-alarm-disclosure]').open).toBe(false);
  const saved = panel.formEntity(form, original, 'alarm_groups');
  expect(saved).toMatchObject(original);
  expect(form.querySelector('[data-alarm-disclosure]').open).toBe(false);
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
  expect(form.querySelector('[data-alarm-disclosure]').open).toBe(false);
  expect(panel.formEntity(form, original, 'alarm_groups').alarms).toEqual(original.alarms);
});

test.each([
  'address;description;enabled\n m0.0 ;Updated;0\nMX00.01;Pump;1',
  'M0.0\tUpdated\tfalse\nM0.1\tPump\ttrue',
  'address,description,enabled\nM0.0,Updated,0\nM0.1,Pump,1',
])('imports M bits and merges address aliases without losing other rows (%s)', csv => {
  const item = { ...merker, alarms: [
    { ...merker.alarms[0], address: 'MX00.00' },
    { address: 'M1.0', description: 'Keep', enabled: false },
  ] };
  const { panel, form } = open(item);
  panel._hass.callWS = vi.fn();
  form.querySelector('[data-alarm-paste]').value = csv;
  form.querySelector('[data-alarm-import]').click();
  expect(form.querySelector('[data-alarm-error]').textContent).toBe('');
  expect(form.querySelector('[data-alarm-status]').textContent).toContain('2 rows: 1 added, 1 updated');
  expect(panel.formEntity(form, item, 'alarm_groups')).toMatchObject({
    start_address: 'M0.0', end_address: 'M1.7', active_value: 0,
    alarms: [
      { address: 'M0.0', description: 'Updated', enabled: false },
      { address: 'M1.0', description: 'Keep', enabled: false },
      { address: 'M0.1', description: 'Pump', enabled: true },
    ],
  });
  expect(panel._hass.callWS).not.toHaveBeenCalled();
  expect(item.alarms[0].description).toBe('Motor');
});

test.each(['M0.8', 'MB0', 'I0.0', 'Q0.0', 'MX00.00'])(
  'invalid or duplicate imported bit %s preserves the entire M alarm list', address => {
    const { panel, form } = open(merker);
    form.querySelector('[data-alarm-paste]').value = `M0.0;Updated;1\n${address};Invalid;0`;
    form.querySelector('[data-alarm-import]').click();
    expect(form.querySelector('[data-alarm-error]').textContent).toContain('Invalid import');
    expect(panel.formEntity(form, merker, 'alarm_groups').alarms).toEqual(merker.alarms);
  },
);

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
  expect(PARSE_ALARM_CSV('DB01,X000.0;Motor')[0].address).toBe('DB1,X0.0');
  expect(() => PARSE_ALARM_CSV('DB1,X0.0;A\nDB1,0.0;B')).toThrow();
  expect(() => PARSE_ALARM_CSV('DB1,X0.0;A\nDB01,X000.0;B')).toThrow();
  expect(() => PARSE_ALARM_CSV('"DB1,X0.0","bad')).toThrow();
  expect(() => PARSE_ALARM_CSV('DB1,X0.9;A')).toThrow();
});

test.each([original, merker])('file selection imports directly with result and totals, without saving ($start_address)', async item => {
  const { panel, form } = open(item);
  panel._hass.callWS = vi.fn();
  const input = form.querySelector('[data-alarm-file]');
  const first = item.start_address, second = first.slice(0, -1) + '1';
  await input.onchange({ target: { files: [{ name: 'alarms.csv', size: 100, text: async () => `${first};Updated;0\n${second};Pump;1` }] } });
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(2);
  expect(form.querySelector('[data-alarm-disclosure]').open).toBe(true);
  expect(form.querySelector('[data-alarm-status]').textContent).toContain('2 rows: 1 added, 1 updated');
  expect(form.querySelector('[data-alarm-status]').hidden).toBe(false);
  expect(form.querySelector('[data-alarm-summary]').textContent).toContain('2 configured rows');
  expect(form.querySelector('[data-alarm-summary]').textContent).toContain('1 Excluded');
  expect(panel._hass.callWS).not.toHaveBeenCalled();
  expect(item.alarms[0].description).toBe('Motor');
});

test('large imports keep off-page rows and edits across search, filter and pages', () => {
  const { panel, form } = open({ ...original, alarms: [] });
  const csv = Array.from({ length: 970 }, (_, i) => `DB1,X${Math.floor(i / 8)}.${i % 8};Alarm ${i};${i % 2}`).join('\n');
  form.querySelector('[data-alarm-paste]').value = csv;
  form.querySelector('[data-alarm-import]').click();
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(50);
  expect(form.querySelector('[data-alarm-page-info]').textContent).toBe('1–50 of 970 rows');
  form.querySelector('[data-alarm-next]').click();
  const row = form.querySelector('[data-alarm-rows]').firstElementChild;
  row.querySelector('[data-description]').value = 'Edited motor';
  row.dispatchEvent(new Event('input', { bubbles: true }));
  const search = form.querySelector('[data-alarm-search]');
  search.value = 'edited MOTOR'; search.dispatchEvent(new Event('input'));
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(1);
  const filter = form.querySelector('[data-alarm-filter]');
  filter.value = 'included'; filter.dispatchEvent(new Event('change'));
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(0);
  expect(form.querySelector('[data-alarm-empty]').textContent).toContain('No rows match');
  filter.value = 'excluded'; filter.dispatchEvent(new Event('change'));
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(1);
  const disclosure = form.querySelector('[data-alarm-disclosure]');
  disclosure.open = false;
  const saved = panel.formEntity(form, original, 'alarm_groups');
  expect(saved.alarms).toHaveLength(970);
  expect(saved.alarms[50].description).toBe('Edited motor');
  expect(disclosure.open).toBe(false);
  disclosure.open = true;
  expect(search.value).toBe('edited MOTOR');
  expect(filter.value).toBe('excluded');
  form.querySelector('[data-remove]').click();
  expect(panel.formEntity(form, original, 'alarm_groups').alarms).toHaveLength(969);
});

test('paste area opens accessibly and imports without exposing markup', () => {
  const { form } = open();
  const toggle = form.querySelector('[data-alarm-paste-toggle]');
  expect(form.querySelector('[data-alarm-paste-box]').hidden).toBe(true);
  toggle.click();
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(document.activeElement).toBe(form.querySelector('[data-alarm-paste]'));
  form.querySelector('[data-alarm-paste]').value = 'DB1,X0.0;<img src=x onerror=alert(1)>;1';
  form.querySelector('[data-alarm-import]').click();
  expect(form.querySelector('[data-description]').value).toBe('<img src=x onerror=alert(1)>');
  expect(form.querySelector('[data-alarm-rows] img')).toBeNull();
});

test.each(['invalid', 'oversized', 'too long', 'read error'])('failed file import preserves list and reports %s', async reason => {
  const { panel, form } = open();
  const file = { name: 'bad.csv', size: reason === 'oversized' ? 3 * 1024 * 1024 : 100, text: async () => {
    if (reason === 'read error') throw Error('read');
    return reason === 'too long' ? `DB1,X0.1;${'x'.repeat(256)};1` : 'not csv';
  } };
  await form.querySelector('[data-alarm-file]').onchange({ target: { files: [file] } });
  expect(form.querySelector('[data-alarm-error]').hidden).toBe(false);
  expect(form.querySelector('[data-alarm-status]').hidden).toBe(true);
  expect(panel.formEntity(form, original, 'alarm_groups').alarms).toEqual(original.alarms);
});

test('latest file selection wins and save is blocked during reading', async () => {
  const { panel, form } = open();
  let resolve;
  const input = form.querySelector('[data-alarm-file]');
  const first = input.onchange({ target: { files: [{ size: 10, text: () => new Promise(done => { resolve = done; }) }] } });
  expect(() => panel.formEntity(form, original, 'alarm_groups')).toThrow('Reading file');
  await input.onchange({ target: { files: [{ size: 10, text: async () => 'DB1,X0.0;Second file;1' }] } });
  resolve('DB1,X0.0;Stale file;1'); await first;
  expect(panel.formEntity(form, original, 'alarm_groups').alarms[0].description).toBe('Second file');
});

test('saving reveals an incomplete row hidden by a search', () => {
  const { panel, form } = open();
  form.querySelector('[data-alarm-add]').click();
  const search = form.querySelector('[data-alarm-search]');
  search.value = 'Motor'; search.dispatchEvent(new Event('input'));
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(1);
  form.querySelector('[data-alarm-disclosure]').open = false;
  expect(() => panel.formEntity(form, original, 'alarm_groups')).toThrow();
  expect(form.querySelector('[data-alarm-disclosure]').open).toBe(true);
  expect(search.value).toBe('');
  expect(form.querySelector('[data-alarm-rows]').children).toHaveLength(2);
});
