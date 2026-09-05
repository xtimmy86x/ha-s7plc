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

  test("infers Cover modes from usable legacy feedback with deterministic precedence", () => {
    const { COVER_UI_FROM_ENTITY: infer } = getPanelTestHelpers();
    const mixed = {
      position_state_address: "DB1,B0",
      open_command_address: "Q0.0",
      cover_status_address: "DB1,B10",
      cover_opening_address: "I0.0",
      tilt_command_address: "DB1,B2",
      stop_command_address: "Q0.2",
    };

    expect(infer({ open_command_address: "Q0.0" }).cover_control_mode).toBe("traditional");
    expect(infer(mixed)).toMatchObject({
      cover_control_mode: "position",
      cover_position_feedback: "position",
      cover_movement_feedback: "bits",
      cover_stop_enabled: "enabled",
      cover_tilt_enabled: "enabled",
    });
    expect(infer({})).toMatchObject({
      cover_position_feedback: "timed",
      cover_stop_enabled: "disabled",
      cover_tilt_enabled: "disabled",
    });
    expect(infer({
      opening_state_address: "I0.0",
      closing_state_address: "I0.1",
      use_state_topics: true,
    }).cover_position_feedback).toBe("both");
    expect(infer({ opening_state_address: "I0.0" }).cover_position_feedback).toBe("opening");
    expect(infer({ cover_closing_address: "I0.1" }).cover_movement_feedback).toBe("bits");
  });

  test("cleans Cover fields according to the selected UI modes", () => {
    const { CLEAN_COVER_ENTITY: clean } = getPanelTestHelpers();
    const disabled = {
      cover_stop_enabled: false,
      cover_tilt_enabled: false,
    };
    const mixed = {
      uid: "kept",
      name: "Legacy",
      position_state_address: "DB1,B0",
      open_command_address: "Q0.0",
      close_command_address: "Q0.1",
      opening_state_address: "I0.0",
      closing_state_address: "I0.1",
      operate_time: 20,
      use_state_topics: true,
      cover_opening_address: "I0.2",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "1",
      stop_command_address: "Q0.2",
      tilt_state_address: "DB1,B2",
      feedback_mode: "status",
      cover_mode: "position",
    };

    const traditional = clean(mixed, {
      ...disabled,
      cover_control_mode: "traditional",
      cover_position_feedback: "timed",
      cover_movement_feedback: "none",
    });
    expect(traditional).toMatchObject({ uid: "kept", name: "Legacy", use_state_topics: false });
    for (const key of [
      "position_state_address", "tilt_state_address", "cover_status_address",
      "stop_command_address", "cover_mode", "feedback_mode",
    ]) expect(traditional).not.toHaveProperty(key);

    const position = clean(mixed, {
      ...disabled,
      cover_control_mode: "position",
      cover_position_feedback: "timed",
      cover_movement_feedback: "status",
    });
    expect(position).toMatchObject({
      uid: "kept",
      position_state_address: "DB1,B0",
      cover_status_address: "DB1,B10",
    });
    for (const key of [
      "open_command_address", "close_command_address", "opening_state_address",
      "closing_state_address", "operate_time", "use_state_topics",
      "cover_opening_address", "stop_command_address", "tilt_state_address",
      "cover_mode", "feedback_mode",
    ]) expect(position).not.toHaveProperty(key);
  });

  test("keeps toggle position status independent from movement bits", () => {
    const { CLEAN_COVER_ENTITY: clean } = getPanelTestHelpers();
    const source = {
      open_command_address: "Q0.0",
      close_command_address: "Q0.1",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "1",
      cover_status_closed_values: "2",
      cover_opening_address: "I0.0",
      cover_closing_address: "I0.1",
    };
    const ui = {
      cover_position_feedback: "status",
      cover_movement_feedback: "bits",
      cover_stop_enabled: false,
      cover_tilt_enabled: false,
    };

    const toggle = clean(source, { ...ui, cover_control_mode: "toggle" });
    expect(toggle).toMatchObject({
      cover_status_address: "DB1,B10",
      cover_status_open_values: "1",
      cover_status_closed_values: "2",
      cover_opening_address: "I0.0",
      cover_closing_address: "I0.1",
    });

    const traditional = clean(source, { ...ui, cover_control_mode: "traditional" });
    expect(traditional).not.toHaveProperty("cover_status_address");
    expect(traditional).not.toHaveProperty("cover_status_open_values");
    expect(traditional).not.toHaveProperty("cover_opening_address");
    expect(traditional).not.toHaveProperty("cover_closing_address");
  });

  test("preserves the traditional Cover status word selected for movement", () => {
    const { CLEAN_COVER_ENTITY: clean } = getPanelTestHelpers();
    const disabled = { cover_stop_enabled: false, cover_tilt_enabled: false };
    const timed = clean({
      open_command_address: "Q0.0",
      close_command_address: "Q0.1",
      cover_status_address: "DB1,B10",
      cover_status_opening_values: "1",
      cover_status_closing_values: "2",
    }, {
      ...disabled,
      cover_control_mode: "traditional",
      cover_position_feedback: "timed",
      cover_movement_feedback: "status",
    });
    expect(timed).toMatchObject({
      cover_position_feedback: "timed",
      cover_status_address: "DB1,B10",
      cover_status_opening_values: "1",
      cover_status_closing_values: "2",
    });

    const endstop = clean({
      open_command_address: "Q0.0",
      close_command_address: "Q0.1",
      opening_state_address: "I0.0",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "3",
      cover_status_stopped_values: "4",
    }, {
      ...disabled,
      cover_control_mode: "traditional",
      cover_position_feedback: "opening",
      cover_movement_feedback: "status",
    });
    expect(endstop).toMatchObject({
      cover_position_feedback: "opening",
      opening_state_address: "I0.0",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "3",
      cover_status_stopped_values: "4",
    });
  });

  test("infers and cleans Climate modes without losing legacy mappings", () => {
    const {
      CLIMATE_UI_FROM_ENTITY: infer,
      CLEAN_CLIMATE_ENTITY: clean,
    } = getPanelTestHelpers();

    expect(infer({ heating_output_address: "Q0.0" }).climate_direct_function).toBe("heat");
    expect(infer({ cooling_output_address: "Q0.1" }).climate_direct_function).toBe("cool");
    expect(infer({
      heating_output_address: "Q0.0",
      cooling_output_address: "Q0.1",
    }).climate_direct_function).toBe("heat_cool");
    expect([
      {},
      { on_off_address: "Q0.0" },
      { preset_mode_address: "DB1,B0" },
      { preset_mode_address: "DB1,B0", on_off_address: "Q0.0" },
    ].map(infer).map((ui) => ui.climate_mode_control)).toEqual([
      "setpoint", "on_off", "coded", "coded_on_off",
    ]);

    const mappings = {
      preset_mode_off_value: null,
      hvac_status_off_values: "",
      hvac_status_heating_values: "7",
    };
    const sameAddress = clean({
      uid: "kept",
      control_mode: "setpoint",
      target_temperature_address: "DB1,R0",
      preset_mode_address: "DB1,B4",
      hvac_status_address: "DB1,B4",
      preset_mode_bidirectional: true,
      ...mappings,
    }, { ...infer({ preset_mode_address: "DB1,B4", hvac_status_address: "DB1,B4" }), control_mode: "setpoint" });
    expect(sameAddress).toMatchObject({
      uid: "kept",
      preset_mode_address: "DB1,B4",
      hvac_status_address: "DB1,B4",
      preset_mode_bidirectional: true,
    });

    const statusDisabled = clean({
      control_mode: "setpoint",
      target_temperature_address: "DB1,R0",
      hvac_status_address: "DB1,B4",
      ...mappings,
    }, { ...infer({ hvac_status_address: "DB1,B4" }), control_mode: "setpoint", climate_action_feedback: "inferred" }, ["climate_action_feedback"]);
    expect(statusDisabled).not.toHaveProperty("hvac_status_address");
    expect(statusDisabled.hvac_status_off_values).toBe("");

    const codedDisabled = clean({
      control_mode: "setpoint",
      target_temperature_address: "DB1,R0",
      preset_mode_address: "DB1,B4",
      preset_mode_bidirectional: true,
      ...mappings,
    }, { ...infer({ preset_mode_address: "DB1,B4" }), control_mode: "setpoint", climate_mode_control: "setpoint" }, ["climate_mode_control"]);
    expect(codedDisabled).not.toHaveProperty("preset_mode_address");
    expect(codedDisabled.preset_mode_off_value).toBeNull();

    const direct = clean({
      uid: "kept",
      control_mode: "setpoint",
      target_temperature_address: "DB1,R0",
      preset_mode_address: "DB1,B4",
      hvac_status_address: "DB1,B4",
      ...mappings,
    }, { ...infer({}), control_mode: "direct" }, ["control_mode"]);
    expect(direct.uid).toBe("kept");
    expect(direct).not.toHaveProperty("target_temperature_address");
    expect(direct).not.toHaveProperty("preset_mode_address");
    expect(direct).not.toHaveProperty("hvac_status_address");
    expect(direct).not.toHaveProperty("climate_mode_control");
    expect(direct).not.toHaveProperty("climate_action_feedback");
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
