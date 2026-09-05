// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { createPanel, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
  vi.restoreAllMocks();
});

const currentDialog = () => document.body.querySelector("ha-dialog");

describe("complete configuration YAML editor", () => {
  test("loads canonical YAML and saves it once while a request is pending", async () => {
    const panel = createPanel();
    let resolveSave;
    const savePending = new Promise((resolve) => { resolveSave = resolve; });
    panel._hass.callWS = vi.fn(async (message) => {
      if (message.type === "s7plc/config/get_configuration") {
        return { configuration_yaml: "sensors:\n  - address: DB1,REAL0\n" };
      }
      if (message.type === "s7plc/config/save_configuration") return savePending;
      throw new Error(`Unexpected call: ${message.type}`);
    });
    panel.load = vi.fn(async () => {});

    await panel.openConfigurationEditor();
    const dialog = currentDialog();
    const textarea = dialog.querySelector("textarea");
    const save = dialog.querySelector('[slot="primaryAction"]');
    expect(textarea.value).toBe("sensors:\n  - address: DB1,REAL0\n");

    textarea.value = "sensors:\n  - address: DB1,REAL4\n";
    const first = save.onclick();
    const second = save.onclick();

    expect(save.disabled).toBe(true);
    expect(panel._hass.callWS.mock.calls.filter(([message]) => message.type === "s7plc/config/save_configuration")).toHaveLength(1);
    resolveSave({});
    await Promise.all([first, second]);

    expect(panel._hass.callWS).toHaveBeenLastCalledWith({
      type: "s7plc/config/save_configuration",
      entry_id: "plc-entry",
      configuration_yaml: "sensors:\n  - address: DB1,REAL4\n",
    });
    expect(dialog.open).toBe(false);
    expect(panel.selectedIndices.size).toBe(0);
    expect(panel.load).toHaveBeenCalledOnce();
  });

  test("imports a local YAML file into the textarea", async () => {
    const panel = createPanel();
    panel._hass.callWS = vi.fn(async () => ({ configuration_yaml: "sensors: []\n" }));
    await panel.openConfigurationEditor();
    const dialog = currentDialog();
    const file = dialog.querySelector("#yaml-file");
    Object.defineProperty(file, "files", {
      configurable: true,
      value: [{ text: async () => "switches:\n  - state_address: DB1,X0.0\n" }],
    });

    await file.onchange();

    expect(dialog.querySelector("textarea").value).toBe("switches:\n  - state_address: DB1,X0.0\n");
    expect(file.value).toBe("");
  });

  test("exports the draft and downloads a fresh backup", async () => {
    const panel = createPanel();
    let getCalls = 0;
    let resolveBackup;
    const backupPending = new Promise((resolve) => { resolveBackup = resolve; });
    panel._hass.callWS = vi.fn(async () => {
      getCalls += 1;
      if (getCalls === 1) return { configuration_yaml: "sensors: []\n" };
      return backupPending;
    });
    const downloads = [];
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:test"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      downloads.push(this.download);
    });

    await panel.openConfigurationEditor();
    const dialog = currentDialog();
    dialog.querySelector("#yaml-export").click();
    const backup = dialog.querySelector("#yaml-backup");
    const first = backup.onclick();
    const second = backup.onclick();

    expect(backup.disabled).toBe(true);
    expect(panel._hass.callWS).toHaveBeenCalledTimes(2);
    resolveBackup({ configuration_yaml: "switches: []\n" });
    await Promise.all([first, second]);

    expect(downloads).toEqual(["cpu1211-config.yaml", "cpu1211-backup.yaml"]);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
    expect(panel._hass.callWS).toHaveBeenCalledTimes(2);
    expect(backup.disabled).toBe(false);
  });

  test("disables every mutation control when initial loading fails", async () => {
    const panel = createPanel();
    panel._hass.callWS = vi.fn(async () => { throw new Error("PLC offline"); });

    await panel.openConfigurationEditor();
    const dialog = currentDialog();
    const alert = dialog.querySelector(".editor-error");

    expect(dialog.querySelector("textarea").disabled).toBe(true);
    expect(dialog.querySelector('[slot="primaryAction"]').disabled).toBe(true);
    expect(dialog.querySelector("#yaml-import").disabled).toBe(true);
    expect(dialog.querySelector("#yaml-export").disabled).toBe(true);
    expect(dialog.querySelector("#yaml-backup").disabled).toBe(true);
    expect(alert.style.display).toBe("block");
    expect(alert.textContent).toContain("PLC offline");
  });

  test("keeps the dialog open and exposes save failures", async () => {
    const panel = createPanel();
    panel._hass.callWS = vi.fn(async (message) => {
      if (message.type === "s7plc/config/get_configuration") return { configuration_yaml: "sensors: []\n" };
      throw new Error("Configuration rejected");
    });
    await panel.openConfigurationEditor();
    const dialog = currentDialog();

    await dialog.querySelector('[slot="primaryAction"]').onclick();

    expect(dialog.open).toBe(true);
    expect(dialog.querySelector('[slot="primaryAction"]').disabled).toBe(false);
    expect(dialog.querySelector(".editor-error").style.display).toBe("block");
    expect(dialog.querySelector(".editor-error").textContent).toContain("Configuration rejected");
  });
});
