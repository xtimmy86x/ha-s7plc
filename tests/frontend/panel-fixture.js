import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const panelSource = fs.readFileSync(
  path.join(root, "custom_components/s7plc/www/s7plc-panel.js"),
  "utf8",
);
const translations = JSON.parse(
  fs.readFileSync(
    path.join(root, "custom_components/s7plc/translations/en.json"),
    "utf8",
  ),
);

const entityTypes = [
  "sensors",
  "binary_sensors",
  "switches",
  "covers",
  "lights",
  "buttons",
  "numbers",
  "selects",
  "texts",
  "climates",
  "entity_sync",
];

export function installPanel() {
  if (!customElements.get("s7plc-configuration-panel")) {
    window.eval(`${panelSource}\nwindow.__s7plcPanelTestHelpers = {
      BUILD_CONNECTION_AVAILABILITY,
      APPLY_LIVE_CONNECTION_DURATION,
      LIVE_CONNECTION_STATUS,
      ENTITY_SEARCH_TEXT,
      FILTER_ENTITY_ITEMS,
    };`);
  }
  globalThis.ResizeObserver ??= class {
    observe() {}
    disconnect() {}
  };
}

export function getPanelTestHelpers() {
  installPanel();
  return window.__s7plcPanelTestHelpers;
}

export function createEntry(overrides = {}) {
  const entities = Object.fromEntries(entityTypes.map((type) => [type, []]));
  entities.sensors = [
    { name: "Boiler temperature", address: "DB1,R0", unit_of_measurement: "°C" },
    { name: "Tank pressure", address: "DB1,R4", unit_of_measurement: "bar" },
  ];
  entities.switches = [
    { name: "Circulation pump", state_address: "DB1,X8.0", command_address: "DB1,X8.1" },
  ];
  return {
    entry_id: "plc-entry",
    title: "CPU1211",
    connected: true,
    connection_entity_id: "binary_sensor.cpu1211_connection",
    data: {
      host: "192.168.100.230",
      port: 102,
      plc_family: "s7",
      connection_type: "rack_slot",
      rack: 0,
      slot: 1,
      scan_interval: 1,
      operation_timeout: 5,
      optimize_read: true,
      enable_write_batching: true,
      enable_metrics: false,
    },
    connection_runtime: {
      last_cycle_seconds: 0.04,
      read_count: 12,
      write_count: 2,
      communication_errors: 0,
    },
    entities,
    entity_ids: {
      sensors: ["sensor.boiler_temperature", "sensor.tank_pressure"],
      switches: ["switch.circulation_pump"],
    },
    selector_options: { device_classes: {}, state_classes: [] },
    ...overrides,
  };
}

export function createHass(entry) {
  return {
    language: "en",
    locale: { language: "en" },
    areas: {},
    states: {
      "binary_sensor.cpu1211_connection": {
        state: "on",
        last_changed: "2026-09-04T10:00:00Z",
        attributes: {
          connection_enabled: true,
          last_cycle_seconds: 0.04,
          read_count: 12,
          write_count: 2,
          communication_errors: 0,
        },
      },
      "sensor.boiler_temperature": { state: "42.5", attributes: { unit_of_measurement: "°C" } },
      "sensor.tank_pressure": { state: "5.4", attributes: { unit_of_measurement: "bar" } },
      "switch.circulation_pump": { state: "on", attributes: {} },
    },
    callWS: async (message) => {
      if (message.type === "s7plc/config/list") return [entry];
      throw new Error(`Unexpected WebSocket call: ${message.type}`);
    },
    callApi: async () => [[
      {
        state: "on",
        last_changed: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
      },
    ]],
  };
}

export function createPanel(entry = createEntry()) {
  installPanel();
  const Panel = customElements.get("s7plc-configuration-panel");
  const panel = new Panel();
  panel.selectedIndices = new Set();
  panel.expandedSections = new Set(entityTypes);
  panel._viewMode = "tabs";
  panel.searchQuery = "";
  panel.entries = [entry];
  panel.entryId = entry.entry_id;
  panel.panelTranslations = translations;
  panel._hass = createHass(entry);
  panel._loaded = true;
  panel.render();
  document.body.appendChild(panel);
  return panel;
}
