# ha-s7plc

[![Release](https://img.shields.io/github/v/release/xtimmy86x/ha-s7plc)](https://github.com/xtimmy86x/ha-s7plc/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-41BDF5)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB)](https://www.python.org/)
[![pyS7](https://img.shields.io/badge/Library-pys7-informational)](https://github.com/xtimmy86x/pyS7)

**Home Assistant integration for Siemens S7 PLCs** — a direct, lightweight custom component that uses `pys7` to read and write PLC data and expose it as `light`, `switch`, `cover`, `button`, `binary_sensor`, and `sensor` entities, and `number` entities.
**No MQTT, no REST API, no middle layer.**

---

## Like my work? A coffee would be awesome!

<a href="https://www.buymeacoffee.com/xtimmy86x" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200" />
</a>

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
- 🧩 **Multiple entity types**: `light`, `switch`, `cover`, `button`, `binary_sensor`, `sensor`,  `number`, and `entity_sync`.
- 🧮 **Value multipliers**: scale raw PLC values before Home Assistant sees them (e.g., convert tenths or hundredths to human-friendly units).
- 🪶 **Lightweight**: minimal overhead, no broker/services required.
- 🛠️ **Full UI configuration**: set up and manage the integration entirely from Home Assistant's UI.
- 🔍 **Optional auto-discovery**: the setup wizard pre-populates PLCs found on your local network while still allowing manual IP entry.
- 📄 **S7 `STRING` support** for text sensors.
- 🔄 **Entity Sync**: automatically synchronize any Home Assistant entity state to PLC addresses in real-time.

---

## Requirements

- A working **Home Assistant** installation.
- A reachable **Siemens S7 PLC** (e.g., S7-1200/S7-1500/S7-300/S7-400) over ISO-on-TCP (**port 102**).
- Network connectivity between Home Assistant host and the PLC (no firewalls blocking 102/TCP).
- Python dependencies installed automatically from `requirements.txt` (notably **`pys7`**).

> ℹ️ For S7-1200/1500, if you use **absolute addresses** (DB + byte/bit offsets), ensure the data blocks you read/write are **not optimized** (i.e., *Optimized block access* disabled for those DBs), otherwise byte/bit offsets may not match your source symbols.

---

## Installation

**HACS (Default repository)**

1. Ensure [HACS](https://hacs.xyz) is installed.
2. In Home Assistant, open **HACS → Integrations**.
3. Search for **"Siemens S7 PLC"** in HACS and install (no custom repository needed).
4. Restart Home Assistant.

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
3. Pick one of the auto-discovered PLC hosts or type the PLC `host` manually, then fill in `rack`, `slot`, and `port` values when prompted.
4. Once the integration is added, open it and choose **Configure** to manage entities.
5. Pick **Add items** to create a new entity or **Remove items** to delete existing ones.
   - When adding, select the entity type (`light`, `switch`, `cover`, `button`, `binary_sensor`, `sensor`, `number`, `entity_sync`) and fill in the form fields.
   - `switch`/`light` entries may use separate `state_address` and `command_address`.
     If `command_address` is omitted it defaults to the state address.
     Enable `sync_state` to automatically synchronize external PLC state changes back to the command address (see [State Synchronization](#state-synchronization) below).
   - `cover` entries define separate `open`/`close` command addresses and optional
     `opening`/`closing` state addresses (leave blank to reuse the command tag).
     Set an `operate time` (default 60 s) to automatically reset the command outputs
     and clear the movement state once the run is complete.
   - `button` entries command a true value and after a configured
     `pulse time` send false.
   - `sensor` entries can apply a `value_multiplier` to rescale numeric PLC data on the fly
     (e.g., `0.1` to expose tenths as full units), and optionally set a per-entity
     `REAL precision` to round `REAL` reads to a fixed number of decimal places.
   - `number` entries expose INT/DINT/REAL values with an optional `command_address`.
     You may set `min`, `max`, and `step` for Home Assistant; limits outside the PLC data type range are automatically clamped to the closest supported value so you can express relative bounds without worrying about overflows.
     Optionally set a per-entity `REAL precision` to round `REAL` reads to a fixed
     number of decimal places.
   - `entity_sync` entries monitor any Home Assistant entity and automatically write its numeric state to a PLC address whenever it changes. Perfect for sending sensor readings, calculated values, or external system data to the PLC (see [Entity Sync](#entity-sync) below).
   - Every item lets you override the **scan interval** just for that tag. 
     Leave the field empty to inherit the PLC default defined during setup.
   - Use **Add another** to chain the creation of multiple entities; after the last 
     sensor/entity you must click **Send** to persist it, otherwise the entries will be  discarded.

#### Exporting and importing PLC items

Need to move your configuration to another Home Assistant instance or keep a backup of the PLC items you built? Open the integration options and choose **Export items**:

1. The dialog shows the JSON payload and offers a download link; the link stays active for five minutes so you can save the file directly from your browser.
2. The exported file contains every configured entity grouped by type (`sensor`, `binary_sensor`, `switch`, `cover`, `button`, `light`, `number`) together with their addresses, limits, scan intervals, and other metadata.

To restore a backup select **Import items** and paste the exported JSON. The integration validates the structure before applying it and surfaces clear errors when the JSON is malformed. A successful import replaces the entire set of configured items with the contents of the file (use an empty list in the JSON to clear a category) while keeping any other integration options intact, so review the payload before submitting it.

### Timeout & Retry settings

During the initial setup you can now tune the PLC communication resilience directly from the UI:

| Field | Description | Default |
|-------|-------------|---------|
| **Operation timeout (s)** | Maximum time allowed for a single read/write cycle before a retry is attempted. | 5.0 |
| **Retry attempts** | Number of retry attempts before the operation is considered failed. | 3 |
| **Retry backoff start (s)** | Delay before the first retry after an error. | 0.5 |
| **Retry backoff max (s)** | Maximum delay used between subsequent retries. | 2.0 |
| **Optimize batch reads** | Enable optimized batch read operations for potentially better performance. Disable if you experience read errors. | `true` |

**About optimized batch reads:**  
When enabled, the integration uses pyS7's optimized read mode which attempts to consolidate multiple read requests into fewer, more efficient operations. This can significantly improve performance when reading many tags. However, some older PLCs or specific network configurations may not support this optimization properly, leading to communication errors. If you experience intermittent read failures or incorrect values, try disabling this option. The integration defaults to enabled (`true`) for modern S7-1200/1500 PLCs where optimization typically works well.

Use the following guidelines based on the typical round-trip latency between Home Assistant and the PLC:

| Network profile | Typical latency | Suggested timeout | Suggested retries | Suggested backoff (start → max) |
|-----------------|-----------------|-------------------|-------------------|-------------------------------|
| **Local/LAN** | < 20 ms | 3–5 s | 2–3 | 0.3 s → 2 s |
| **VPN / Remote site** | 20–100 ms | 6–8 s | 3–4 | 0.5 s → 4 s |
| **High-latency / Cellular** | > 100 ms | 8–12 s | 4–5 | 1.0 s → 6 s |

Values outside these ranges are supported, but increasing them further may delay error reporting and entity updates. Lower values improve responsiveness but can cause frequent reconnects on congested networks.

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
| Bit (boolean)         | `DB1,X0.0`    | 1 bit    | Discrete I/O, flags       |
| Byte (unsigned)       | `DB1,B0`      | 8 bits   | Small counters/bytes      |
| Word (signed 16-bit)  | `DB1,W2`      | 16 bits  | INT                       |
| DWord (signed 32-bit) | `DB1,DW4`     | 32 bits  | DINT                      |
| REAL (IEEE 754)       | `DB1,R4`      | 32 bits  | Float (temperature etc.)  |
| String (S7)           | `DB1,S0.20`   | 2+N bytes| Text (S7 STRING)          ||

> Choose the correct **offset** and **type** based on your PLC data block layout.
> For REAL values, ensure the PLC writes IEEE 754 floating point into that DBD.

### Notes on Logo! 8

On the Logo! (from 0BA8 version) logic modules there is no need to set the Mode to TSAP anymore; the default Rack/Slot value of 0/2 works just fine.

The following table shows memory areas accessible without additional settings in the controller program:

*Note: These memory areas seem to be read-only from outside the controller, as they are directly used by the function blocks listed in "Logo Block" of the table.*

| Logo Block | Logo VM Range | Example address | Description | Access |
|------------|---------------|--------------------------|-------------|--------|
| `I`        | `1024 - 1031` | `DB1,BYTE1024` or `DB1,X1024.5` or `DB1,WORD1024` | Reads input terminals 1...8 or 6 or 1...16 | R |
| `AI`       | `1032 - 1063` | `DB1,WORD1032` | Reads analog input terminal 1. Always word sized. | R |
| `Q`        | `1064 - 1071` | `DB1,BYTE1064` or `DB1,X1064.5` or `DB1,WORD1064` | Reads output terminals 1...8 or 6 or 1...16 | R |
| `AQ`       | `1072 - 1103` | `DB1,WORD1072` | Reads analog output terminal 1. Always word sized. | R |
| `M`        | `1104 - 1117` | `DB1,BYTE1104` or `DB1,X1104.5` or `DB1,WORD1104` | Reads bit flags M1...M8 or M6 or M1...16 | R |
| `AM`       | `1118 - 1245` | `DB1,WORD1118` | Reads analog flag 1. Always word sized. | R |
| `NI`       | `1246 - 1261` | `DB1,BYTE1246` or `DB1,X1246.5` or `DB1,WORD1246` | Reads network input 1...8 or 6 or 1...16 | R |
| `NAI`      | `1262 - 1389` | `DB1,WORD1262` | Reads analog network input 1. Always word sized. | R |
| `NQ`       | `1390 - 1405` | `DB1,BYTE1390` or `DB1,X1390.5` or `DB1,WORD1390` | Reads network output 1...8 or 6 or 1...16 | R |
| `NAQ`      | `1406 - 1469` | `DB1,WORD1406` | Reads network output 1. Always word sized. | R |

On the other hand, Logo memory areas VM 0-849 are mutable from outside the controller, but they need to be mapped into the Logo program. Without mapping, data written into these addresses will have no effect on program execution. Used VM addresses in the range mentioned above can be read/written from/into in the Logo program using the "Network" function blocks (in the function block setup use the *"Local variable memory (VM)"* option to map VMs to the function block).

Some addressing examples:

| Logo VM | Example Node-RED address | Description |
|---------|--------------------------|-------------|
| `0`     | `DB1,BYTE0`              | R/W access |
| `1`     | `DB1,X1.3`               | R/W access (use booleans) |
| `2..3`  | `DB1,WORD2`              | R/W access |
| `4..7`  | `DB1,DWORD4`             | R/W access |

---

## State Synchronization

The **Sync State** feature is available for `switch` and `light` entities and provides intelligent bidirectional synchronization between Home Assistant and the PLC.

### How it works

When `sync_state` is enabled:

1. **Home Assistant commands are tracked**: When you turn on/off a switch or light from Home Assistant, the integration writes to the `command_address` and marks the change as "pending".

2. **PLC feedback is monitored**: The integration continuously reads the `state_address` to detect the actual PLC state.

3. **Echo prevention**: If the PLC state matches the pending command, the integration knows the command was successful and clears the pending flag. This prevents sending duplicate commands back to the PLC.

4. **External changes are synchronized**: If the PLC state changes externally (e.g., from a physical button, PLC program logic, or another system), the integration detects the mismatch and automatically writes the new state to the `command_address`. This keeps both addresses in sync.

### When to use Sync State

Enable `sync_state` when:

- **Physical controls exist**: Your system has physical buttons, switches, or HMI panels that can change the state independently of Home Assistant
- **PLC program logic**: The PLC itself can change states based on timers, sensors, or automation logic
- **Multiple control systems**: You have multiple systems (SCADA, other automation platforms) that can command the same outputs
- **Separate state/command architecture**: Your PLC uses different addresses for reading the actual state and writing commands

**Example scenario**: A conveyor belt with:
- `DB1,X0.0` (state_address) = actual motor running status from a contactor feedback
- `DB1,X0.1` (command_address) = motor start command from automation system
- Physical start/stop buttons on the control panel
- Emergency stop system that can halt the motor

With `sync_state` enabled, if someone presses the physical stop button (changing `DB1,X0.0` to `false`), Home Assistant will automatically write `false` to `DB1,X0.1` to keep the command address synchronized.

### When NOT to use Sync State

Disable `sync_state` (default) when:

- **Single control point**: Only Home Assistant controls the output
- **Same address for state and command**: The PLC uses a single address for both reading and writing
- **PLC handles synchronization**: Your PLC program already manages any necessary feedback logic
- **Performance concerns**: High-frequency state monitoring or write operations might impact PLC performance

### Configuration

To enable sync state for a switch or light:

1. Open the integration from **Settings → Devices & Services**
2. Click **Configure** and choose **Add items** (for new entities) or **Remove items** → **Edit** (for existing ones)
3. Select `switch` or `light` as the entity type
4. Enter the `state_address` (the PLC address to read the actual state)
5. Enter the `command_address` (the PLC address to write commands) - if omitted, defaults to state_address
6. **Enable the `Sync State` checkbox**
7. Save the configuration

### Technical details

- The synchronization logic runs during the normal polling cycle based on your configured scan interval
- State changes are written asynchronously to avoid blocking the coordinator
- The integration maintains internal state tracking to distinguish between Home Assistant commands and external PLC changes
- Initial state on entity creation is read-only (no synchronization) to avoid unintended writes during startup

### Performance considerations

- Each synchronized entity adds one write operation when external changes are detected
- For systems with many synchronized entities and frequent state changes, consider:
  - Increasing the scan interval for less critical entities
  - Using PLC-side logic to handle rapid state changes
  - Monitoring PLC CPU load if you notice performance issues

---

## Entity Sync

Entity Sync provides a powerful way to send data from Home Assistant to your PLC by monitoring any entity and automatically writing its state to a configured PLC address whenever it changes.

### What is Entity Sync?

An **Entity Sync** is a special sensor entity that:

1. **Monitors a source entity**: Tracks state changes of any Home Assistant entity (sensor, input_number, calculated template, etc.)
2. **Converts to appropriate value**: Extracts numeric or boolean values from the source entity
3. **Writes to PLC**: Automatically writes the value to the specified PLC address whenever the source entity changes
4. **Adapts representation**: Binary syncs (BIT addresses) display `on`/`off` states with toggle icons, while numeric syncs show numerical values with upload icons
5. **Reports statistics**: Tracks successful writes and errors as entity attributes

Entity Syncs appear as sensor entities in Home Assistant showing the last successfully written value, making it easy to verify what data was sent to the PLC.

### Common use cases

**Data integration**
- Send weather data from Home Assistant weather integrations to PLC for HVAC control
- Forward energy consumption from smart meters to PLC monitoring systems
- Push setpoints from Home Assistant `input_number` helpers to PLC controllers
- Transmit calculated values from template sensors to PLC

**Multi-system coordination**
- Synchronize data between different automation platforms through the PLC
- Feed external sensor readings into PLC-based control algorithms
- Send occupancy or presence detection to PLC for lighting/HVAC automation
- Forward alarm states or security system status to PLC logic

**Process control**
- Update PLC recipe values from Home Assistant dashboards
- Send production targets or parameters to PLC from business systems
- Forward quality control measurements to PLC data logging

### Configuration

To create an entity sync:

1. Open the integration from **Settings → Devices & Services**
2. Click **Configure** and choose **Add items**
3. Select **Entity Sync** as the entity type
4. Configure the following fields:
   - **Address**: The PLC address where values will be written (e.g., `DB1,R0` for a REAL, `DB1,W0` for an INT)
   - **Source Entity**: The Home Assistant entity to monitor (use the entity picker to select any entity)
   - **Name** (optional): A friendly name for the entity sync (defaults to "Entity Sync [address]")
5. Save the configuration

The entity sync will immediately read the current state of the source entity and write it to the PLC, then continue monitoring for any future changes.

### Example configuration

**Example 1: Weather temperature to PLC**
```
Address: DB10,R0
Source Entity: sensor.openweathermap_temperature
Name: Outside Temperature Sync
```
Writes the current outside temperature to `DB10,R0` (REAL) whenever the weather sensor updates.

**Example 2: Input number setpoint**
```
Address: DB20,W10
Source Entity: input_number.hvac_setpoint
Name: HVAC Setpoint Sync
```
Writes the value from an `input_number` helper to `DB20,W10` (INT/WORD) whenever you adjust the setpoint slider in Home Assistant.

**Example 3: Power consumption monitoring**
```
Address: DB5,R100
Source Entity: sensor.home_power_consumption
Name: Power Consumption Sync
```
Continuously sends your home's real-time power consumption to the PLC for monitoring or demand response logic.

**Example 4: Binary sensor to PLC bit**
```
Address: DB1,X0.5
Source Entity: binary_sensor.front_door
Name: Front Door Status Writer
```
Writes the front door binary sensor state (`on`/`off`) to a PLC bit `DB1,X0.5`. When the door opens (state = `on`), the bit is set to `true`; when closed (state = `off`), it's set to `false`.

**Example 5: Switch state to PLC bit**
```
Address: DB10,X5.2
Source Entity: switch.irrigation_zone_1
Name: Irrigation Zone 1 Writer
```
Mirrors a Home Assistant switch state to a PLC bit. Useful for monitoring HA automation states from the PLC or coordinating with PLC-based interlocks.

### Entity attributes

Writer entities expose useful diagnostic attributes:

| Attribute | Description |
|-----------|-------------|
| `s7_address` | The PLC address being written to |
| `source_entity` | The entity ID being monitored |
| `source_state` | Current state of the source entity |
| `source_last_updated` | Timestamp when source entity last changed |
| `write_count` | Total number of successful writes since entity creation |
| `error_count` | Total number of failed write attempts |
| `writer_type` | Type of writer: `binary` (for BIT addresses) or `numeric` (for other types) |

Access these attributes in automations, scripts, or display them on dashboards to monitor writer performance.

### Data type handling

Writers automatically detect the PLC data type from the address and handle conversions:

- **BIT** (`DB#,X#.#`): Writes boolean values. Accepts states like `on`, `off`, `true`, `false`, `1`, `0`, `yes`, `no` (case-insensitive) or any numeric value (non-zero = true, zero = false)
- **REAL** (`DB#,R#`): Writes floating-point values with full precision
- **INT/WORD** (`DB#,W#`): Converts to 16-bit signed integer (-32768 to 32767)
- **DINT/DWORD** (`DB#,DW#`): Converts to 32-bit signed integer
- **BYTE** (`DB#,B#`): Converts to unsigned byte (0 to 255)

If the source entity provides a non-numeric state (e.g., "unavailable", "unknown") or an invalid boolean state for BIT addresses, the write is skipped and `error_count` increments. The writer logs a warning to help with troubleshooting.

### Behavior notes
Automatic type detection**
- Writers automatically detect if the PLC address is a BIT type and adapt their behavior and representation
- Binary writers (BIT addresses) display `on`/`off` states with dynamic toggle switch icons
- Numeric writers display numerical values with an upload icon

**
**Initial write**
- Writers perform an immediate write when first added to Home Assistant
- If the source entity is unavailable at startup, the write is skipped until the entity becomes available

**Change detection**
- Writes occur only when the source entity state actually changes
- No unnecessary PLC traffic when values remain stable

**Error handling**
- If a write fails (PLC disconnected, invalid data), the `error_count` increments
- The writer continues monitoring and will retry on the next state change
- Check entity attributes and Home Assistant logs for diagnostic information

**Performance**
- Writers use event-driven updates (no polling overhead)
- Write operations run asynchronously to avoid blocking other entities
- Multiple writers operate independently

### When to use Writers vs. Number entities

**Use Writer when:**
- Source data comes from external integrations (weather, energy meters, etc.)
- You need one-way data flow from HA to PLC
- The value is calculated or derived from other entities
- You want to log write statistics and errors

**Use Number entity when:**
- You need bidirectional control (read and write)
- The PLC is the source of truth for the value
- You want direct user control with min/max/step validation
- The data originates from the PLC

**You can use both together:**
Combine a `number` entity (for PLC → HA data flow) with a `writer` (for external data → PLC flow) to create complex data exchange patterns.

### Troubleshooting

**Writer shows unavailable**
- Check that the source entity exists and is available
- Verify PLC connection is active

**Error count increasing**
- Check Home Assistant logs for specific error messages
- Verify the source entity provides numeric values
- Confirm the PLC address is correct and accessible
- Ensure the PLC data type matches the values being written

**Values not updating in PLC**
- Verify the source entity is actually changing (check its history)
- Ensure the PLC data block is not write-protected
- Check that `write_count` is incrementing (confirms writes are succeeding)
- Monitor PLC program to ensure it's reading the address

---

## Examples

Example: adding a light entity via the UI:

1. After the integration is installed, open it from **Settings → Devices & Services**.
2. Click **Configure** and choose **Add items**.
3. Select **Light**, then enter the `state_address`, optional `command_address`, name, and whether to `sync_state`.
4. Save to create the entity or enable **Add another** to keep adding more.

Example: adding a number entity via the UI:

1. Open the integration and choose **Add items**.
2. Select **Number** and type the PLC `address` (e.g., `DB1,W0` for an INT).
3. Optionally set a separate `command_address`, `min`, `max`, and `step`.
   Any limits that fall outside the PLC data type range are automatically tightened to the closest valid value.
4. Submit to create the entity or keep **Add another** enabled to configure more numbers in one go.

Example: removing an entity via the UI:

1. Open the integration from **Settings → Devices & Services** and click **Configure**.
2. Choose **Remove items**.
3. Select the entities to remove and submit; the integration reloads to apply the changes.

### Polling interval guidance

- Use per-tag scan interval overrides when only a subset of tags require faster updates. The coordinator automatically keeps the global polling loop aligned to the fastest tag while slower tags are polled at their own cadence.

- The **Scan interval** accepts decimal values, so entering `0.25` results in a 250 ms polling loop.
- Millisecond-level polling dramatically increases traffic to the PLC and HA host. Only use sub-second values when monitoring a very small set of critical tags.
- If you need faster reactions, prefer edge-triggered logic in the PLC itself and reserve rapid polling for diagnostics or lightweight booleans.

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
A: `light`, `switch`, `cover`, `button`, and `number` entities perform writes (`button` pulses the address). `number` can share the read address or use a dedicated command address with optional min/max limits. `binary_sensor` and `sensor` are read-only.

**Q: Which CPUs are supported?**  
A: Any Siemens S7 device that accepts ISO-on-TCP (port 102) and exposes DB areas with absolute addressing should work.

**Q: How do I find the right address?**  
A: Inspect your DB layout in TIA Portal / Step7. Use DB number + byte offset (+ bit for booleans). For REAL use 4-byte DBD aligned as in your block.

---

## Roadmap

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
