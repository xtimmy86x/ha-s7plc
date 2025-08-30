# ha-s7plc

[![Release](https://img.shields.io/github/v/release/xtimmy86x/ha-s7plc)](https://github.com/xtimmy86x/ha-s7plc/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-41BDF5)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB)](https://www.python.org/)
[![Snap7](https://img.shields.io/badge/Library-python--snap7-informational)](https://github.com/gijzelaerr/python-snap7)

**Home Assistant integration for Siemens S7 PLCs** — a direct, lightweight custom component that uses `python-snap7` to read and write PLC data and expose it as `light`, `switch`, `binary_sensor`, and `sensor` entities.  
**No MQTT, no REST API, no middle layer.**

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Global connection](#global-connection)
  - [Entities](#entities)
  - [Addressing reference (S7)](#addressing-reference-s7)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Releases](#releases)
- [Security & Safety](#security--safety)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Features

- ⚡ **Direct PLC communication** over S7 protocol via `python-snap7`.
- 🧩 **Multiple entity types**: `light`, `switch`, `binary_sensor`, `sensor`.
- 🪶 **Lightweight**: minimal overhead, no broker/services required.
- 🛠️ **Plain YAML setup**: drop-in custom component + a few lines in `configuration.yaml`.

---

## Requirements

- A working **Home Assistant** installation.
- A reachable **Siemens S7 PLC** (e.g., S7-1200/S7-1500/S7-300/S7-400) over ISO-on-TCP (**port 102**).
- Network connectivity between Home Assistant host and the PLC (no firewalls blocking 102/TCP).
- Python dependencies installed automatically from `requirements.txt` (notably **`python-snap7`**).

> ℹ️ For S7-1200/1500, if you use **absolute addresses** (DB + byte/bit offsets), ensure the data blocks you read/write are **not optimized** (i.e., *Optimized block access* disabled for those DBs), otherwise byte/bit offsets may not match your source symbols.

---

## Installation

**Manual (Custom Component)**

1. Copy the folder **`custom_components/s7plc`** into your Home Assistant config directory  
   (e.g., `/config/custom_components/s7plc/`).
2. Restart Home Assistant.

> Tip: keep this repository as a submodule or sync it periodically to receive updates.

---

## Configuration

All entities share a **single PLC connection** configured under the `s7plc:` key. Then you can add platforms (`light`, `switch`, `binary_sensor`, `sensor`) that reference **addresses** in the PLC.

### Global connection

```yaml
# configuration.yaml
s7plc:
  host: 192.168.100.89   # PLC IP Address
  rack: 0                # Typical: 0
  slot: 1                # Typical: 1 on S7-1200/1500 (CPU slot)
  port: 102              # S7 ISO-on-TCP
```

**Notes**
- `rack/slot` may vary by CPU family and project. Common values:
  - S7-1200/1500: `rack: 0`, `slot: 1`
  - S7-300/400: often `rack: 0`, `slot: 2` (verify in hardware config)
- Keep `port: 102` unless you know you changed it in the PLC/CP.

### Entities

#### `light`

Digital (bool) output you want to treat as a light in Home Assistant.

```yaml
light:
  - platform: s7plc
    name: "Office Lamp"
    address: "DB1.DBX0.0"     # Bit (boolean)
```

#### `switch`

Generic on/off mapped to a PLC bit.

```yaml
switch:
  - platform: s7plc
    name: "Garage Switch"
    address: "DB1.DBX0.1"     # Bit (boolean)
```

#### `binary_sensor`

Read-only boolean (e.g., limit switch, door contact).

```yaml
binary_sensor:
  - platform: s7plc
    name: "Door Sensor"
    address: "DB1.DBX0.2"     # Bit (boolean)
```

#### `sensor`

Numeric readouts (temperature, counters…). Address must point to a byte/word/dword/real.

```yaml
sensor:
  - platform: s7plc
    name: "Room Temperature"
    address: "DB1.DBD2"       # 32-bit REAL (see table below)
    unit_of_measurement: "°C"
```

> The integration reads the value and publishes it directly to Home Assistant.

---

## Addressing reference (S7)

Use standard S7 absolute addressing:

| Type                  | Example       | Size     | Typical meaning           |
|-----------------------|---------------|----------|---------------------------|
| Bit (boolean)         | `DB1.DBX0.0`  | 1 bit    | Discrete I/O, flags       |
| Byte (unsigned)       | `DB1.DBB0`    | 8 bits   | Small counters/bytes      |
| Word (signed 16-bit)  | `DB1.DBW2`    | 16 bits  | INT                       |
| DWord (signed 32-bit) | `DB1.DBD4`    | 32 bits  | DINT                      |
| REAL (IEEE 754)       | `DB1.DBD4`    | 32 bits  | Float (temperature etc.)  |

> Choose the correct **offset** and **type** based on your PLC data block layout.  
> For REAL values, ensure the PLC writes IEEE 754 floating point into that DBD.

---

## Examples

Full minimal example combining all platforms:

```yaml
s7plc:
  host: 192.168.100.89
  rack: 0
  slot: 1
  port: 102

light:
  - platform: s7plc
    name: "Office Lamp"
    address: "DB1.DBX0.0"

switch:
  - platform: s7plc
    name: "Garage Switch"
    address: "DB1.DBX0.1"

binary_sensor:
  - platform: s7plc
    name: "Door Sensor"
    address: "DB1.DBX0.2"

sensor:
  - platform: s7plc
    name: "Room Temperature"
    address: "DB1.DBD2"        # 32-bit REAL
    unit_of_measurement: "°C"
```

---

## Troubleshooting

- **Cannot connect**  
  - Ping the PLC IP from the HA host.  
  - Confirm **port 102/TCP** is open (no firewall/NAT blocking).  
  - Double-check **rack/slot** for your CPU type.

- **Values look wrong / zeros**  
  - Verify the **address** is correct (DB number, byte offset, bit index).  
  - On S7-1200/1500 ensure the target DB has **Optimized block access disabled** if you rely on absolute addresses.  
  - Confirm correct **data type** (e.g., REAL vs INT).

- **Slow updates**  
  - Network/PLC scan times and Home Assistant polling affect latency.  
  - Keep addresses local and avoid unnecessary long scan chains.

- **Binary entity inverted**  
  - If your wiring/logic uses normally-closed contacts, invert logic at the PLC or create a template entity in HA if needed.

---

## FAQ

**Q: Is MQTT required?**  
A: No. This integration talks to the PLC directly using S7 protocol.

**Q: Can I write values to the PLC?**  
A: `light` and `switch` perform writes for on/off. `binary_sensor` and `sensor` are read-only.

**Q: Which CPUs are supported?**  
A: Any Siemens S7 device that accepts ISO-on-TCP (port 102) and exposes DB areas with absolute addressing should work.

**Q: How do I find the right address?**  
A: Inspect your DB layout in TIA Portal / Step7. Use DB number + byte offset (+ bit for booleans). For REAL use 4-byte DBD aligned as in your block.

---

## Roadmap

- Covers / shutters (`cover` platform)
- Diagnostics & health entities
- More data types and scaling helpers

> Have ideas? Open an **issue** or a **PR**!

---

## Contributing

1. Fork the repository.
2. Create a feature branch (`feat/your-thing`).
3. Commit with clear messages.
4. Open a Pull Request describing the change and test steps.

Please add examples/docs where appropriate.

---

## Releases

See **[Releases](https://github.com/xtimmy86x/ha-s7plc/releases)** for changelogs and downloadable versions.

---

## Security & Safety

- This component performs network communication to your PLC. Use it on **trusted networks**.
- Apply standard **HA secrets** handling (do not commit IPs/credentials).
- Consider read-only DBs for monitoring to reduce accidental writes.

---

## Acknowledgements

- Built on top of the excellent [`python-snap7`](https://github.com/gijzelaerr/python-snap7) library.
- Not affiliated with Siemens or Home Assistant.
