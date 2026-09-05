// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test } from "vitest";

import { createEntry, createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
});

const currentForm = () => document.body.querySelector("ha-dialog form");
const choose = (form, name, value) => {
  const input = form.querySelector(`input[name="${name}"][value="${value}"]`);
  input.checked = true;
  input.dispatchEvent(new Event("change", { bubbles: true }));
};
const setAddress = (form, name, value) => {
  const field = form.querySelector(`[data-field="${name}"]`);
  const input = field.querySelector("[data-address-manual]");
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
};
const isHidden = (form, key) => form
  .querySelector(`[data-field="${key}"], [data-section="${key}"]`)
  .classList.contains("hidden-field");
const openCover = (original) => {
  const entry = createEntry();
  entry.entities.covers = [{ name: "Legacy cover", ...original }];
  const panel = createPanel(entry);
  panel.openEditor(0, "covers");
  return { panel, form: currentForm(), original: entry.entities.covers[0] };
};
const openClimate = (original = {}) => {
  const entry = createEntry();
  entry.entities.climates = [{
    name: "Legacy climate",
    control_mode: "setpoint",
    current_temperature_address: "DB1,REAL0",
    target_temperature_address: "DB1,REAL4",
    ...original,
  }];
  const panel = createPanel(entry);
  panel.openEditor(0, "climates");
  return { panel, form: currentForm(), original: entry.entities.climates[0] };
};

describe("advanced Cover and Climate editors", () => {
  test("validates and serializes Cover status-word position feedback", () => {
    const entry = createEntry();
    entry.entities.covers = [{
      name: "Warehouse shutter",
      open_command_address: "DB1,X0.0",
      close_command_address: "DB1,X0.1",
      operate_time: 20,
      cover_position_feedback: "timed",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "covers");
    const form = currentForm();

    choose(form, "cover_position_feedback", "status");
    expect(isHidden(form, "cover_status_address")).toBe(false);
    expect(isHidden(form, "opening_state_address")).toBe(true);
    setAddress(form, "cover_status_address", "DB1,BYTE10");

    expect(() => panel.formEntity(form, entry.entities.covers[0], "covers"))
      .toThrow("Status-word feedback requires at least one state mapping.");

    form.elements.cover_status_open_values.value = "1";
    form.elements.cover_status_closed_values.value = "0";
    const entity = panel.formEntity(form, entry.entities.covers[0], "covers");

    expect(entity).toMatchObject({
      cover_position_feedback: "status",
      cover_status_address: "DB1,BYTE10",
      cover_status_open_values: "1",
      cover_status_closed_values: "0",
    });
    expect(entity).not.toHaveProperty("use_state_topics");
    expect(entity).not.toHaveProperty("opening_state_address");
    expect(entity).not.toHaveProperty("closing_state_address");
  });

  test("reveals and serializes position Cover stop and tilt controls", () => {
    const entry = createEntry();
    entry.entities.covers = [{
      name: "Position blind",
      position_state_address: "DB1,BYTE20",
      position_command_address: "DB1,BYTE22",
      cover_position_feedback: "position",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "covers");
    const form = currentForm();

    expect(isHidden(form, "cover-position-feedback")).toBe(false);
    expect(form.querySelector('input[name="cover_movement_feedback"][value="bits"]')
      .closest(".control-card").classList.contains("hidden-field")).toBe(false);
    choose(form, "cover_position_feedback", "both");
    choose(form, "cover_movement_feedback", "bits");
    choose(form, "cover_stop_enabled", "enabled");
    choose(form, "cover_tilt_enabled", "enabled");
    expect(isHidden(form, "stop_command_address")).toBe(false);
    expect(isHidden(form, "tilt_state_address")).toBe(false);

    setAddress(form, "stop_command_address", "DB1,X24.0");
    setAddress(form, "tilt_state_address", "DB1,BYTE26");
    setAddress(form, "tilt_command_address", "DB1,BYTE28");
    setAddress(form, "opening_state_address", "DB1,X30.0");
    expect(() => panel.formEntity(form, entry.entities.covers[0], "covers"))
      .toThrow("Closed-end-stop feedback requires the fully-closed address.");
    setAddress(form, "closing_state_address", "DB1,X30.1");
    setAddress(form, "cover_opening_address", "DB1,X32.0");
    setAddress(form, "cover_closing_address", "DB1,X32.1");
    form.elements.stop_pulse_duration.value = "0.5";
    form.elements.invert_tilt.checked = true;
    const entity = panel.formEntity(form, entry.entities.covers[0], "covers");

    expect(entity).toMatchObject({
      position_state_address: "DB1,BYTE20",
      position_command_address: "DB1,BYTE22",
      stop_command_address: "DB1,X24.0",
      stop_pulse_duration: 0.5,
      tilt_state_address: "DB1,BYTE26",
      tilt_command_address: "DB1,BYTE28",
      invert_tilt: true,
      opening_state_address: "DB1,X30.0",
      closing_state_address: "DB1,X30.1",
      cover_opening_address: "DB1,X32.0",
      cover_closing_address: "DB1,X32.1",
    });
    expect(entity).not.toHaveProperty("open_command_address");
    expect(entity).not.toHaveProperty("close_command_address");
  });

  test("round-trips legacy Cover end stops without rendering a derived input", () => {
    const { panel, form, original } = openCover({
      uid: "cover-1",
      area: "living",
      device_class: "blind",
      scan_interval: 2,
      open_command_address: "DB1,X0.0",
      close_command_address: "DB1,X0.1",
      opening_state_address: "DB1,X0.2",
      closing_state_address: "DB1,X0.3",
      use_state_topics: true,
    });

    expect(form.elements.use_state_topics).toBeUndefined();
    expect(form.querySelector('[name="use_state_topics"]')).toBeNull();
    expect(form.elements.cover_position_feedback.value).toBe("both");
    const entity = panel.formEntity(form, original, "covers");
    expect(entity).toMatchObject({
      uid: "cover-1",
      area: "living",
      device_class: "blind",
      scan_interval: 2,
      opening_state_address: "DB1,X0.2",
      closing_state_address: "DB1,X0.3",
      use_state_topics: true,
    });
    for (const key of [
      "cover_control_mode", "cover_movement_feedback", "cover_stop_enabled",
      "cover_tilt_enabled", "cover_mode", "feedback_mode",
    ]) expect(entity).not.toHaveProperty(key);
  });

  test("validates an explicitly selected pair of Cover end stops", () => {
    const { panel, form, original } = openCover({
      open_command_address: "DB1,X0.0",
      close_command_address: "DB1,X0.1",
      cover_position_feedback: "timed",
    });

    choose(form, "cover_position_feedback", "both");
    setAddress(form, "opening_state_address", "DB1,X0.2");
    expect(() => panel.formEntity(form, original, "covers"))
      .toThrow("Closed-end-stop feedback requires the fully-closed address.");
    setAddress(form, "closing_state_address", "DB1,X0.3");
    const entity = panel.formEntity(form, original, "covers");
    expect(entity).toMatchObject({
      opening_state_address: "DB1,X0.2",
      closing_state_address: "DB1,X0.3",
      use_state_topics: true,
    });

    choose(form, "cover_position_feedback", "timed");
    const timed = panel.formEntity(form, original, "covers");
    expect(timed.use_state_topics).toBe(false);
    expect(timed).not.toHaveProperty("opening_state_address");
    expect(timed).not.toHaveProperty("closing_state_address");
  });

  test("normalizes position feedback and preserves independently usable status mappings", () => {
    const movement = openCover({
      position_state_address: "DB1,B0",
      cover_position_feedback: "timed",
      cover_status_address: "DB1,B10",
      cover_status_opening_values: "1",
      cover_status_closing_values: "2",
      cover_status_stopped_values: "3",
    });
    expect(movement.form.elements.cover_position_feedback.value).toBe("position");
    expect(movement.form.elements.cover_movement_feedback.value).toBe("status");
    expect(movement.form.querySelector(
      'input[name="cover_position_feedback"][value="timed"]',
    ).closest(".control-card").classList.contains("hidden-field")).toBe(true);
    expect(movement.form.querySelector(
      'input[name="cover_position_feedback"][value="position"]',
    ).closest(".control-card").classList.contains("hidden-field")).toBe(false);
    const movementEntity = movement.panel.formEntity(
      movement.form, movement.original, "covers",
    );
    expect(movementEntity).toMatchObject({
      cover_position_feedback: "position",
      cover_status_address: "DB1,B10",
      cover_status_opening_values: "1",
    });

    document.body.replaceChildren();
    const position = openCover({
      position_state_address: "DB1,B0",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "1",
      cover_status_closed_values: "2",
    });
    expect(position.form.elements.cover_position_feedback.value).toBe("status");
    expect(position.form.elements.cover_movement_feedback.value).toBe("none");
    const positionEntity = position.panel.formEntity(
      position.form, position.original, "covers",
    );
    expect(positionEntity).toMatchObject({
      cover_position_feedback: "status",
      cover_status_address: "DB1,B10",
      cover_status_open_values: "1",
    });
  });

  test("preserves single legacy end stops and removes disabled position accessories", () => {
    const opening = openCover({
      open_command_address: "DB1,X0.0",
      close_command_address: "DB1,X0.1",
      opening_state_address: "DB1,X0.2",
    });
    expect(opening.form.elements.cover_position_feedback.value).toBe("opening");
    const opened = opening.panel.formEntity(opening.form, opening.original, "covers");
    expect(opened.opening_state_address).toBe("DB1,X0.2");
    expect(opened).not.toHaveProperty("closing_state_address");
    expect(opened).not.toHaveProperty("use_state_topics");

    document.body.replaceChildren();
    const accessories = openCover({
      position_state_address: "DB1,BYTE0",
      stop_command_address: "DB1,X10.0",
      stop_pulse_duration: 0.5,
      tilt_state_address: "DB1,BYTE2",
      tilt_command_address: "DB1,BYTE4",
      invert_tilt: true,
    });
    choose(accessories.form, "cover_stop_enabled", "disabled");
    choose(accessories.form, "cover_tilt_enabled", "disabled");
    const cleaned = accessories.panel.formEntity(
      accessories.form, accessories.original, "covers",
    );
    for (const key of [
      "stop_command_address", "stop_pulse_duration", "tilt_state_address",
      "tilt_command_address", "invert_tilt",
    ]) expect(cleaned).not.toHaveProperty(key);
  });

  test("configures coded setpoint modes with PLC action feedback", () => {
    const entry = createEntry();
    entry.entities.climates = [{
      name: "Office climate",
      control_mode: "setpoint",
      current_temperature_address: "DB1,REAL30",
      target_temperature_address: "DB1,REAL34",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "climates");
    const form = currentForm();

    choose(form, "climate_mode_control", "coded");
    expect(isHidden(form, "climate-mode-feedback")).toBe(false);
    expect(isHidden(form, "preset_mode_address")).toBe(false);
    const history = form.querySelector(
      'input[name="preset_mode_bidirectional"][value="false"]',
    ).closest(".control-card");
    expect(history.querySelector("ha-icon").getAttribute("icon")).toBe("mdi:history");
    choose(form, "preset_mode_bidirectional", "true");
    setAddress(form, "preset_mode_address", "DB1,BYTE38");
    choose(form, "climate_action_feedback", "plc");
    expect(isHidden(form, "hvac_status_address")).toBe(false);
    expect(() => panel.formEntity(form, entry.entities.climates[0], "climates"))
      .toThrow("Enter the PLC operating-status address.");
    setAddress(form, "hvac_status_address", "DB1,BYTE40");
    form.elements.preset_mode_heat_value.value = "11";
    form.elements.preset_mode_cool_value.value = "12";
    form.elements.hvac_status_heating_values.value = "1,5";
    form.elements.hvac_status_cooling_values.value = "2,6";

    const entity = panel.formEntity(form, entry.entities.climates[0], "climates");
    expect(entity).toMatchObject({
      control_mode: "setpoint",
      preset_mode_address: "DB1,BYTE38",
      preset_mode_bidirectional: true,
      hvac_status_address: "DB1,BYTE40",
      preset_mode_heat_value: 11,
      preset_mode_cool_value: 12,
      hvac_status_heating_values: "1,5",
      hvac_status_cooling_values: "2,6",
    });
  });

  test("configures direct heat/cool outputs with independent PLC feedback", () => {
    const entry = createEntry();
    entry.entities.climates = [{
      name: "Plant climate",
      control_mode: "direct",
      current_temperature_address: "DB1,REAL50",
      heating_output_address: "DB1,X54.0",
    }];
    const panel = createPanel(entry);
    panel.openEditor(0, "climates");
    const form = currentForm();

    choose(form, "climate_direct_function", "heat_cool");
    choose(form, "climate_direct_feedback", "plc");
    expect(isHidden(form, "cooling_output_address")).toBe(false);
    expect(isHidden(form, "heating_action_address")).toBe(false);
    expect(isHidden(form, "cooling_action_address")).toBe(false);
    setAddress(form, "cooling_output_address", "DB1,X54.1");
    setAddress(form, "heating_action_address", "DB1,X56.0");
    setAddress(form, "cooling_action_address", "DB1,X56.1");

    const entity = panel.formEntity(form, entry.entities.climates[0], "climates");
    expect(entity).toMatchObject({
      control_mode: "direct",
      heating_output_address: "DB1,X54.0",
      cooling_output_address: "DB1,X54.1",
      heating_action_address: "DB1,X56.0",
      cooling_action_address: "DB1,X56.1",
    });
    expect(entity).not.toHaveProperty("target_temperature_address");
    expect(entity).not.toHaveProperty("preset_mode_address");
    expect(entity).not.toHaveProperty("hvac_status_address");
  });

  test("renders legacy Climate core defaults without persisting untouched values", () => {
    const { panel, form, original } = openClimate();
    expect([
      form.elements.preset_mode_off_value.value,
      form.elements.preset_mode_heat_value.value,
      form.elements.preset_mode_cool_value.value,
      form.elements.preset_mode_heat_cool_value.value,
    ]).toEqual(["0", "1", "2", "3"]);
    expect(form.elements.preset_mode_auto_value.value).toBe("");
    expect([
      form.elements.hvac_status_off_values.value,
      form.elements.hvac_status_heating_values.value,
      form.elements.hvac_status_cooling_values.value,
    ]).toEqual(["0", "1", "2"]);
    expect(form.elements.hvac_status_idle_values.value).toBe("");

    const entity = panel.formEntity(form, original, "climates");
    for (const key of [
      "preset_mode_off_value", "preset_mode_heat_value",
      "preset_mode_cool_value", "preset_mode_heat_cool_value",
      "hvac_status_off_values", "hvac_status_heating_values",
      "hvac_status_cooling_values",
    ]) expect(entity).not.toHaveProperty(key);
  });

  test("keeps explicitly cleared Climate core mappings disabled", () => {
    const { panel, form, original } = openClimate({
      preset_mode_off_value: null,
      preset_mode_heat_cool_value: null,
      hvac_status_off_values: "",
      hvac_status_cooling_values: "",
    });
    expect(form.elements.preset_mode_off_value.value).toBe("");
    expect(form.elements.preset_mode_heat_cool_value.value).toBe("");
    expect(form.elements.hvac_status_off_values.value).toBe("");
    expect(form.elements.hvac_status_cooling_values.value).toBe("");

    const entity = panel.formEntity(form, original, "climates");
    expect(entity.preset_mode_off_value).toBeNull();
    expect(entity.preset_mode_heat_cool_value).toBeNull();
    expect(entity.hvac_status_off_values).toBe("");
    expect(entity.hvac_status_cooling_values).toBe("");
  });
});
