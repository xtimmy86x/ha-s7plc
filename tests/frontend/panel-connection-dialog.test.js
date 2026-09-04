// @vitest-environment jsdom

import { afterEach, beforeAll, describe, expect, test } from "vitest";

import { createEntry, createPanel, getPanelTestHelpers, installPanel } from "./panel-fixture.js";

beforeAll(() => {
  globalThis.requestAnimationFrame = (callback) => callback();
  installPanel();
});

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
});

describe("connection details dialog", () => {
  test("opens from the status badge as an accessible read-only dialog", () => {
    const panel = createPanel();
    const badge = panel.querySelector(".connection-badge");

    expect(badge.getAttribute("aria-label")).toBe("Connected · Show connection details");
    badge.click();
    const dialog = document.body.querySelector("ha-dialog");

    expect(dialog.open).toBe(true);
    expect(dialog.headerTitle).toBe("Connection details");
    expect(dialog.getAttribute("aria-label")).toBe("Connection details");
    expect(dialog.querySelector('.connection-status[role="status"]')).not.toBeNull();
    expect(dialog.querySelector("input, select, textarea")).toBeNull();
    expect(dialog.querySelector(".availability-container")).not.toBeNull();
  });

  test("shows performance metrics only when they are enabled", () => {
    const entry = createEntry();
    const panel = createPanel(entry);

    panel.querySelector(".connection-badge").click();
    let dialog = document.body.querySelector("ha-dialog");
    expect(dialog.querySelector(".section-connection")).not.toBeNull();
    expect(dialog.querySelector(".section-configuration")).not.toBeNull();
    expect(dialog.querySelector(".section-metrics")).toBeNull();
    dialog.remove();
    panel._connectionDialog = null;

    entry.data.enable_metrics = true;
    panel.render();
    panel.querySelector(".connection-badge").click();
    dialog = document.body.querySelector("ha-dialog");

    expect(dialog.querySelector(".section-metrics")).not.toBeNull();
    expect(dialog.querySelector(".section-metrics").textContent).toContain("Last cycle duration");
    expect(dialog.querySelector(".section-metrics").textContent).toContain("0.04 s");
  });

  test("refreshes the badge and an open dialog from the live connection sensor", async () => {
    const entry = createEntry();
    const panel = createPanel(entry);
    panel.querySelector(".connection-badge").click();
    panel._hass.states[entry.connection_entity_id].state = "off";

    await panel.refreshConnectionStatus();

    const badge = panel.querySelector(".connection-badge");
    const dialogStatus = document.body.querySelector("ha-dialog .connection-status");
    expect(badge.classList.contains("connected")).toBe(false);
    expect(badge.getAttribute("aria-label")).toContain("Disconnected");
    expect(dialogStatus.classList.contains("disconnected")).toBe(true);
    expect(dialogStatus.textContent).toBe("Disconnected");
  });

  test("renders rack/slot and TSAP inventories without dropping false or zero values", () => {
    const rackEntry = createEntry({
      pys7_version: "3.1.1",
      data: {
        ...createEntry().data,
        scan_interval: 0,
        optimize_read: false,
        enable_write_batching: false,
        max_retries: 3,
        retry_backoff_initial: 0,
        retry_backoff_max: 2,
        future_option: 42,
      },
    });
    const panel = createPanel(rackEntry);
    panel.querySelector(".connection-badge").click();
    let dialog = document.body.querySelector("ha-dialog");

    expect(dialog.querySelector(".section-connection").textContent).toContain("3.1.1");
    expect(dialog.querySelector(".section-configuration").textContent).toContain("No");
    expect(dialog.querySelector(".section-retry").textContent).toContain("0");
    expect(dialog.querySelector(".section-other").textContent).toContain("42");
    dialog.remove();
    panel._connectionDialog = null;

    rackEntry.data = {
      ...rackEntry.data,
      connection_type: "tsap",
      local_tsap: "01.00",
      remote_tsap: "03.02",
    };
    panel.render();
    panel.querySelector(".connection-badge").click();
    dialog = document.body.querySelector("ha-dialog");

    expect(dialog.querySelector(".section-connection").textContent).toContain("01.00");
    expect(dialog.querySelector(".section-connection").textContent).toContain("03.02");
    expect(dialog.querySelector(".section-connection").textContent).not.toContain("Rack");
  });

  test("calculates availability without inventing missing recorder history", () => {
    const { BUILD_CONNECTION_AVAILABILITY } = getPanelTestHelpers();
    const hour = 3_600_000;
    const now = Date.parse("2026-08-21T12:00:00Z");
    const history = [
      { state: "on", last_changed: "2026-08-20T14:00:00Z" },
      { state: "off", last_changed: "2026-08-20T18:00:00Z" },
      { state: "unavailable", last_changed: "2026-08-20T20:00:00Z" },
      { state: "on", last_changed: "2026-08-20T21:00:00Z" },
      { state: "off", last_changed: "2026-08-21T02:00:00Z" },
      { state: "on", last_changed: "2026-08-21T03:00:00Z" },
    ];
    const result = BUILD_CONNECTION_AVAILABILITY(history, now, 24 * hour);

    expect(result.durations).toEqual({ connected: 18 * hour, disconnected: 3 * hour, unknown: 3 * hour });
    expect(result.availability).toBeCloseTo(18 / 21 * 100);
    expect(result.disconnects).toBe(2);
    expect(result.currentUptime).toBe(9 * hour);

    const incomplete = BUILD_CONNECTION_AVAILABILITY(
      [{ state: "on", last_changed: "2026-08-21T10:00:00Z" }],
      now,
      24 * hour,
    );
    expect(incomplete.durations.unknown).toBe(22 * hour);
    expect(incomplete.durations.connected).toBe(2 * hour);
  });

  test("prefers live state for status and current connection duration", () => {
    const { APPLY_LIVE_CONNECTION_DURATION, LIVE_CONNECTION_STATUS } = getPanelTestHelpers();
    const hour = 3_600_000;
    const now = Date.parse("2026-08-21T12:00:00Z");
    const historical = { currentUptime: 2 * hour };

    expect(APPLY_LIVE_CONNECTION_DURATION(historical, { state: "on", last_changed: "2026-08-19T06:00:00Z" }, now).currentUptime).toBe(54 * hour);
    expect(APPLY_LIVE_CONNECTION_DURATION(historical, { state: "off", last_changed: "2026-08-21T07:00:00Z" }, now).currentDowntime).toBe(5 * hour);
    expect(APPLY_LIVE_CONNECTION_DURATION(historical, undefined, now).currentUptime).toBe(2 * hour);
    expect(LIVE_CONNECTION_STATUS({ state: "on" }, false)).toBe("connected");
    expect(LIVE_CONNECTION_STATUS({ state: "off" }, true)).toBe("disconnected");
    expect(LIVE_CONNECTION_STATUS({ state: "unavailable" }, true)).toBe("unknown");
    expect(LIVE_CONNECTION_STATUS(undefined, true)).toBe("connected");
  });
});
