// @vitest-environment jsdom

import { beforeAll, describe, expect, test } from "vitest";

import { getPanelTestHelpers, getTranslations, installPanel } from "./panel-fixture.js";

beforeAll(() => installPanel());

describe("entity configuration helpers", () => {
  test("maps graphical command behavior to legacy backend booleans", () => {
    const { APPLY_CONTROL_MODE, CONTROL_MODE_FROM_ENTITY } = getPanelTestHelpers();
    expect([
      {}, { sync_state: true }, { pulse_command: true },
      { sync_state: true, pulse_command: true },
    ].map(CONTROL_MODE_FROM_ENTITY)).toEqual(["direct", "sync", "pulse", "pulse"]);
    expect(["direct", "sync", "pulse"].map((mode) => (
      APPLY_CONTROL_MODE({ name: "unchanged", unrelated: 42 }, mode)
    ))).toEqual([
      { name: "unchanged", unrelated: 42, sync_state: false, pulse_command: false },
      { name: "unchanged", unrelated: 42, sync_state: true, pulse_command: false },
      { name: "unchanged", unrelated: 42, sync_state: false, pulse_command: true },
    ]);
  });

  test("infers dimmable mode only from a brightness state address", () => {
    const { LIGHT_MODE_FROM_ENTITY } = getPanelTestHelpers();
    expect([
      {},
      { brightness_scale: 10 },
      { brightness_command_address: "DB1,W2" },
      { brightness_state_address: "DB1,W0" },
    ].map(LIGHT_MODE_FROM_ENTITY)).toEqual(["on_off", "on_off", "on_off", "dimmable"]);
  });

  test("keeps field definitions technical and backed by panel copy", () => {
    const { FIELDS } = getPanelTestHelpers();
    const english = getTranslations("en").config_panel;
    const kinds = new Set([
      "text", "number", "checkbox", "select", "control", "light",
      "cover-selector", "climate-selector", "options-map",
    ]);

    for (const [entityType, definitions] of Object.entries(FIELDS)) {
      for (const definition of definitions) {
        expect(definition.length, `${entityType}.${definition[0]}`).toBeLessThanOrEqual(4);
        if (definition.length > 1) expect(kinds.has(definition[1]), `${entityType}.${definition[0]}`).toBe(true);
        const key = definition[0];
        const copy = english.entity_types[entityType].fields[key]
          ?? english.common.fields[key]
          ?? (key === "control_behavior" ? english.control_behavior : null);
        expect(copy?.label, `${entityType}.${key}`).toBeTruthy();
        if (key !== "control_behavior") expect(copy?.description, `${entityType}.${key}`).toBeTruthy();
      }
    }
  });
});
