# ha-s7plc

[![Release](https://img.shields.io/github/v/release/xtimmy86x/ha-s7plc)](https://github.com/xtimmy86x/ha-s7plc/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-41BDF5)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB)](https://www.python.org/)
[![pyS7](https://img.shields.io/badge/Library-pys7-informational)](https://github.com/xtimmy86x/pyS7)

**Home Assistant integration for Siemens S7 PLCs** — a direct, lightweight custom component that uses `pys7` to read and write PLC data and expose it as `light`, `switch`, `binary_sensor`, and `sensor` entities.
**No MQTT, no REST API, no middle layer.**

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Setup via UI](#setup-via-ui)
  - [Addressing reference (S7)](#addressing-reference-s7)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Development](#development)
- [Releases](#releases)
- [Security & Safety](#security--safety)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Features

- ⚡ **Direct PLC communication** over S7 protocol via `pys7`.
- 🧩 **Multiple entity types**: `light`, `switch`, `binary_sensor`, `sensor`.
- 🪶 **Lightweight**: minimal overhead, no broker/services required.
- 🛠️ **Full UI configuration**: set up and manage the integration entirely from Home Assistant's UI.
- 📄 **S7 `STRING` support** for text sensors.

---

## Requirements

- A working **Home Assistant** installation.
- A reachable **Siemens S7 PLC** (e.g., S7-1200/S7-1500/S7-300/S7-400) over ISO-on-TCP (**port 102**).
- Network connectivity between Home Assistant host and the PLC (no firewalls blocking 102/TCP).
- Python dependencies installed automatically from `requirements.txt` (notably **`pys7`**).

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

Configuration is now handled entirely through the Home Assistant UI. After installing the component, add the integration and enter the PLC connection details. Entities are created and managed from the integration's options—no YAML required.

### Setup via UI

1. In Home Assistant, go to **Settings → Devices & Services** and click **+ Add Integration**.
2. Search for **"S7 PLC"** and select it.
3. Enter the PLC `host`, `rack`, `slot`, and `port` values when prompted.
4. Once the integration is added, open it and choose **Configure** to manage entities.
5. Pick **Add items** to create a new entity or **Remove items** to delete existing ones.
   - When adding, select the entity type (`light`, `switch`, `binary_sensor`, `sensor`) and fill in the form fields.
     `switch`/`light` entries may use separate `state_address` and `command_address`.
     If `command_address` is omitted it defaults to the state address.
     Enable `sync_state` to mirror PLC state changes to the command address.

**Notes**
- `rack/slot` values depend on the CPU family. Common settings:
  - S7-1200/1500: `rack: 0`, `slot: 1`
  - S7-300/400: often `rack: 0`, `slot: 2` (verify in hardware config)
- Keep `port: 102` unless you know you changed it in the PLC/CP.

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
| String (S7)           | `DB1.DBS0`    | 2+N bytes| Text (S7 STRING)          |

> Choose the correct **offset** and **type** based on your PLC data block layout.  
> For REAL values, ensure the PLC writes IEEE 754 floating point into that DBD.

---

## Examples

Example: adding a light entity via the UI:

1. After the integration is installed, open it from **Settings → Devices & Services**.
2. Click **Configure** and choose **Add items**.
3. Select **Light**, then enter the `state_address`, optional `command_address`, name, and whether to `sync_state`.
4. Save to create the entity or enable **Add another** to keep adding more.

Example: removing an entity via the UI:

1. Open the integration from **Settings → Devices & Services** and click **Configure**.
2. Choose **Remove items**.
3. Select the entities to remove and submit; the integration reloads to apply the changes.

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

## Development

This project uses [pre-commit](https://pre-commit.com/) to enforce formatting and
linting with **black**, **isort**, and **flake8**. Run the hooks on modified
files before committing:

```bash
pip install pre-commit
pre-commit run --files <file1> [<file2> ...]
```

The hooks will automatically format the files and ensure they end with a
newline.

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

- Built on top of the excellent [`pyS7`](https://github.com/xtimmy86x/pyS7) library.
- Not affiliated with Siemens or Home Assistant.
