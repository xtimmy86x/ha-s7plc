# ha-s7plc

Direct Home Assistant integration for Siemens S7 PLCs.

This project provides a custom component that creates `light`, `switch` and `sensor` entities without relying on MQTT or the Home Assistant HTTP API.

## Installation

Copy the `custom_components/s7` directory into your Home Assistant
configuration folder.

## Configuration

Add entries to `configuration.yaml` using the platforms:

```yaml
light:
  - platform: s7
    name: "Test Light"
    address: "DB1.DBX0.0"

switch:
  - platform: s7
    name: "Test Switch"
    address: "DB1.DBX0.1"

sensor:
  - platform: s7
    name: "Test Sensor"
    address: "DB1.DBR2"
    unit_of_measurement: "°C"
```

The integration communicates with the PLC via the `python-snap7` library and
updates entity state directly within Home Assistant.
