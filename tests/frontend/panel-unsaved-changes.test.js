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

const dialogs = () => [...document.body.querySelectorAll("ha-dialog")];
const close = (dialog) => {
  dialog.open = false;
  dialog.dispatchEvent(new Event("closed"));
};
// Mimics the cancelable wa-hide that ha-dialog's inner wa-dialog fires on Escape or a scrim click.
const dismiss = (dialog) => {
  const event = new Event("wa-hide", { bubbles: true, composed: true, cancelable: true });
  dialog.dispatchEvent(event);
  if (!event.defaultPrevented) close(dialog);
  return event;
};
const editSensor = (panel) => {
  const entry = createEntry();
  entry.entities.sensors = [{ address: "DB1,R0", name: "Temperature" }];
  panel ??= createPanel(entry);
  panel.openEditor(0, "sensors");
  return { panel, editor: dialogs()[0] };
};

describe("unsaved changes guard", () => {
  test("closes an untouched editor without asking", () => {
    const { editor } = editSensor();
    editor.querySelector("[slot=secondaryAction]").click();
    expect(editor.open).toBe(false);
    expect(dialogs()).toHaveLength(1);
    expect(dismiss(editor).defaultPrevented).toBe(false);
  });

  test("asks before cancel discards edits and keeps editing on request", () => {
    const { editor } = editSensor();
    editor.querySelector("form").elements.name.value = "Changed";
    editor.querySelector("[slot=secondaryAction]").click();
    expect(editor.open).toBe(true);
    const confirm = dialogs()[1];
    expect(confirm.headerTitle).toBe("Unsaved changes");
    expect(confirm.textContent).toContain("Leave without saving?");
    confirm.querySelector("[slot=secondaryAction]").click();
    confirm.dispatchEvent(new Event("closed"));
    expect(editor.open).toBe(true);
    expect(dialogs()).toEqual([editor]);
    expect(editor.querySelector("form").elements.name.value).toBe("Changed");
  });

  test("blocks Escape or scrim dismissal until the user discards", () => {
    const { editor } = editSensor();
    editor.querySelector("form").elements.name.value = "Changed";
    expect(dismiss(editor).defaultPrevented).toBe(true);
    expect(dismiss(editor).defaultPrevented).toBe(true);
    expect(dialogs()).toHaveLength(2);
    const confirm = dialogs()[1];
    confirm.querySelector("[slot=primaryAction]").click();
    confirm.dispatchEvent(new Event("closed"));
    expect(editor.open).toBe(false);
  });

  test("treats edits reverted to their original value as clean", () => {
    const { editor } = editSensor();
    const name = editor.querySelector("form").elements.name;
    name.value = "Changed";
    name.value = "Temperature";
    editor.querySelector("[slot=secondaryAction]").click();
    expect(editor.open).toBe(false);
    expect(dialogs()).toHaveLength(1);
  });

  test("detects edits made in YAML mode", () => {
    const { editor } = editSensor();
    editor.querySelector('[data-mode="yaml"]').click();
    editor.querySelector(".yaml-editor textarea").value += '\nunit_of_measurement: "°C"';
    expect(dismiss(editor).defaultPrevented).toBe(true);
  });

  test("ignores wa-hide events from nested overlays", () => {
    const { editor } = editSensor();
    editor.querySelector("form").elements.name.value = "Changed";
    const event = new Event("wa-hide", { bubbles: true, cancelable: true });
    editor.querySelector("form").dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(dialogs()).toHaveLength(1);
  });

  test("does not ask after a successful save", async () => {
    const { panel, editor } = editSensor();
    panel._hass.callWS = vi.fn(async () => ({}));
    panel.load = vi.fn();
    editor.querySelector("form").elements.name.value = "Changed";
    await editor.querySelector("[slot=primaryAction]").onclick();
    expect(editor.open).toBe(false);
    expect(dismiss(editor).defaultPrevented).toBe(false);
    expect(dialogs()).toHaveLength(0);
  });

  test("guards the advanced configuration YAML editor", async () => {
    const panel = createPanel();
    await panel.openConfigurationEditor();
    const editor = dialogs()[0];
    editor.querySelector("textarea").value += "\n# edited";
    editor.querySelector("[slot=secondaryAction]").click();
    expect(editor.open).toBe(true);
    expect(dialogs()[1].headerTitle).toBe("Unsaved changes");
  });
});
