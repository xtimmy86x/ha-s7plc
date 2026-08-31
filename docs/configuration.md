# Configuration Guide

This guide covers the complete configuration process for the S7 PLC integration.

## Connection Configuration

Configuration is handled entirely through the Home Assistant UI. After installing the component, add the integration and enter the PLC connection details.

### Basic Setup Steps

1. In Home Assistant, go to **Settings → Devices & Services** and click **+ Add Integration**.
2. Search for **"S7 PLC"** and select it.
3. Choose your connection type: **Rack/Slot** or **TSAP** (see below for details).
4. Pick one of the auto-discovered PLC hosts or type the PLC `host` manually.
5. Fill in connection parameters when prompted.
6. Let the initial Config Flow verify the connection and create the PLC entry.
7. Open **S7 PLC** from the sidebar to manage entities.

After the first S7 PLC entry is loaded, administrators also get an **S7 PLC** item
in the Home Assistant sidebar. This is the recommended workspace for day-to-day
entity management. It provides a visual editor, an advanced YAML editor, current
entity states, and a PLC connection indicator. See the dedicated
[Side Panel Guide](sidepanel.md).

## Connection Types

The integration supports two connection methods:

### Rack/Slot Connection (Default)

The standard connection method using rack and slot numbers.

**Common settings:**
- S7-1200/1500: `rack: 0`, `slot: 1`
- S7-300/400: often `rack: 0`, `slot: 2` (verify in hardware config)
- Logo! 8 (0BA8 and newer): `rack: 0`, `slot: 2`
- Logo! 0BA7 and older: Use TSAP connection (see below)

**Configuration parameters:**
- **Host**: IP address or hostname of the PLC
- **Port**: Communication port (default: `102`)
- **Rack**: Rack number (typically `0`)
- **Slot**: Slot number (varies by CPU model)

### TSAP Connection

TSAP (Transport Service Access Point) is an alternative addressing mode that may be required for specific PLC configurations, older S7 models, or when connecting through gateways and communication processors.

**When to use TSAP:**
- **Logo! 0BA7 and older versions** (0BA6, 0BA5, etc.) - Required instead of Rack/Slot
- Some S7-300/400 CPUs with specific firmware versions
- Connecting through CP (Communication Processor) modules
- Network configurations that require explicit TSAP addressing
- Legacy systems where rack/slot addressing is not available

**Configuration parameters:**
- **Host**: IP address or hostname of the PLC
- **Port**: Communication port (default: `102`)
- **Local TSAP**: The TSAP identifier of the client (Home Assistant). Format: `XX.YY` (e.g., `01.00`)
- **Remote TSAP**: The TSAP identifier of the PLC. Format: `XX.YY` (e.g., `01.01`)

**Common TSAP values:**
- **Logo! 0BA7**: `Local: 10.00`, `Remote: 10.01`
- For S7-300/400 CPUs: often `Local: 01.00`, `Remote: 01.02` or `Remote: 01.01`
- Check your PLC hardware configuration or consult your system documentation for the correct TSAP values

**Note:** The connection type is fixed after setup. The Options Flow lets you edit the parameters for the configured Rack/Slot or TSAP mode, but it cannot switch between the two modes.

## Timeout & Retry Settings

During the initial setup you can tune the PLC communication resilience directly from the UI:

| Field | Description | Default |
|-------|-------------|---------|
| **Operation timeout (s)** | Maximum time allowed for a single read/write cycle before a retry is attempted. | 5.0 |
| **Retry attempts** | Number of retry attempts before the operation is considered failed. | 3 |
| **Retry backoff start (s)** | Delay before the first retry after an error. | 0.5 |
| **Retry backoff max (s)** | Maximum delay used between subsequent retries. | 2.0 |
| **Optimize batch reads** | Enable optimized batch read operations for potentially better performance. | `true` |
| **Enable performance metrics** | Enable diagnostic sensors that report connection health and communication statistics from pyS7. See [Performance Metrics](advanced-features.md#performance-metrics). | `false` |

### About Optimized Batch Reads

When enabled, the integration uses pyS7's optimized read mode which attempts to consolidate multiple read requests into fewer, more efficient operations. This can significantly improve performance when reading many tags. However, some older PLCs or specific network configurations may not support this optimization properly, leading to communication errors. If you experience intermittent read failures or incorrect values, try disabling this option.

### Network Profile Guidelines

Use the following guidelines based on the typical round-trip latency between Home Assistant and the PLC:

| Network profile | Typical latency | Suggested timeout | Suggested retries | Suggested backoff (start → max) |
|-----------------|-----------------|-------------------|-------------------|-------------------------------|
| **Local/LAN** | < 20 ms | 3–5 s | 2–3 | 0.3 s → 2 s |
| **VPN / Remote site** | 20–100 ms | 6–8 s | 3–4 | 0.5 s → 4 s |
| **High-latency / Cellular** | > 100 ms | 8–12 s | 4–5 | 1.0 s → 6 s |

Values outside these ranges are supported, but increasing them further may delay error reporting and entity updates. Lower values improve responsiveness but can cause frequent reconnects on congested networks.

## Entity Configuration

> [!IMPORTANT]
> Entity management through the legacy Entity Options Flow was removed in
> version **7.0.0**. The **S7 PLC Side Panel** is the only supported interface
> for adding, editing, deleting, importing, and exporting entities.

Open **S7 PLC** in the Home Assistant sidebar. The Side Panel is available to
administrators and supports visual forms and **Advanced YAML**. **Configure**
opens the connection Options Flow and does not manage entities. Do not edit Home
Assistant's internal config-entry storage manually.

### Adding Entities

1. Open the Side Panel and select the PLC and entity-type tab.
2. Select **Add** and complete the visual editor, or use its YAML mode.
3. Review the fields described below and select **Save changes**.

### Entity Type Details

**Note**: The **Name** field is optional for all entity types. If omitted, the integration automatically generates a name based on the PLC address (e.g., "DB1 X0 0" for address `DB1,X0.0`). This auto-generated name is then combined with the PLC device name by Home Assistant.

#### Switch and Light (On/Off)

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **State Address**: PLC address to read the actual state
- **Command Address**: PLC address to write commands (defaults to state address if omitted)
- **Sync State**: Enable to automatically synchronize external PLC state changes back to the command address (see [Advanced Features](advanced-features.md#state-synchronization))
- **Pulse Command Mode**: When enabled, sends a pulse (ON then OFF) instead of a continuous state. Useful for bistable relays, flip-flop circuits, or momentary button control
- **Pulse Duration**: Duration of the pulse in seconds (0.1-60s, default: 0.5s). Only used when Pulse Command Mode is enabled

#### Dimmer Light

A brightness-controlled light entity using `ColorMode.BRIGHTNESS`. A dimmer light combines a boolean on/off address with a separate brightness address.

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **State Address**: PLC address to read the boolean on/off state (required)
- **Command Address**: PLC address to write the boolean on/off command (defaults to state address if omitted)
- **Brightness State Address**: PLC address to read the current brightness level (numeric, 0 to scale). **Required to enable dimmer mode**
- **Brightness Command Address**: PLC address to write the brightness level (defaults to brightness state address if omitted)
- **Brightness Scale**: Maximum value representing full brightness on the PLC side (default: `255`). Set to `100` if your PLC uses 0–100% range, or any other scale your dimmer hardware expects. The integration automatically maps between this scale and Home Assistant's 0–255 range. **Required to enable dimmer mode**
- **Sync State**: Enable to automatically synchronize external PLC state changes back to the command address (see [Advanced Features](advanced-features.md#state-synchronization)). Applies to the boolean on/off state
- **Pulse Command Mode**: When enabled, sends a pulse (ON then OFF) instead of a continuous state. Useful for bistable relays or flip-flop circuits. Applies to the boolean on/off state
- **Pulse Duration**: Duration of the pulse in seconds (0.1-60s, default: 0.5s). Only used when Pulse Command Mode is enabled

#### Cover (Traditional Open/Close)

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Open Command Address**: Address to command cover open
- **Close Command Address**: Address to command cover close
- **Position Feedback**: Choose timed estimation, only the fully-open limit
  switch, only the fully-closed limit switch, both limit switches, or a mapped
  PLC status word. The selected limit-switch fields are required for the
  corresponding single/both mode.
- **Movement Feedback**: Optionally report opening, closing, and stopped state
  from individual BIT addresses or from the same mapped PLC status word.
- **Status Word Values**: Map distinct integer values to open, closed, opening,
  closing, and stopped states when status-word feedback is selected.
- **Operate Time**: Time in seconds to automatically reset command outputs (default: 60s)

#### Cover (Position-Based)

Position-based covers use a 0–100% numeric range instead of separate open/close commands.

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Position State Address**: PLC address to read the current position (0–100)
- **Position Command Address**: PLC address to write the target position (defaults to state address if omitted)
- **Invert Position**: When enabled, inverts the position scale (PLC 0 = HA 100 and vice versa)
- **Position Feedback**: Choose the reported position value (the default -
  "closed" is the position reading 0, no separate source needed), only the
  fully-open limit switch, only the fully-closed limit switch, both limit
  switches, or a mapped PLC status word. The selected limit-switch fields are
  required for the corresponding single/both mode.
- **Movement Feedback**: Optionally report opening, closing, and stopped state
  from individual BIT addresses or from the same mapped PLC status word,
  independent of the Position Feedback choice.
- **Status Word Values**: Map distinct integer values to open, closed, opening,
  closing, and stopped states when status-word feedback is selected.
- **Device Class**: Optional cover device class (e.g., `shutter`, `blind`, `garage`)

**Stop command**: For position-based covers, the **Stop** action writes the current actual position to the target position register, effectively halting the movement at the current point

#### Button

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to pulse
- **Pulse Time**: Duration of the pulse in seconds (supports decimal values, e.g., `0.1` for 100ms, `1` default, up to 60s)

#### Sensor

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to read
- **Device Class**: Optional sensor device class for proper display
  - To remove a previously set device class, select **"No device class"** from the dropdown
- **Value Multiplier**: Scale factor to apply to raw PLC values (e.g., `0.1` to convert tenths to units)
- **REAL Precision**: Number of decimal places for REAL values

#### Number

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to read
- **Command Address**: PLC address to write (optional, defaults to read address)
- **Device Class**: Optional number device class
  - To remove a previously set device class, select **"No device class"** from the dropdown
- **Min/Max/Step**: Value constraints for Home Assistant (automatically clamped to PLC data type limits)
- **REAL Precision**: Number of decimal places for REAL values
- **Value Multiplier**: Scale factor applied to the raw PLC value before displaying it in Home Assistant (e.g., `0.1` to convert tenths to units, `0.001` for millivolts to volts). When set, the multiplier is automatically applied in reverse when writing: the Home Assistant value is divided by the multiplier before being sent to the PLC. Min/Max/Step are also scaled accordingly so the UI always works in display units

#### Select

Maps numeric PLC values to named options, so operating modes, fan speeds,
duty/standby pump selection and similar single-choice values can be picked
from a dropdown instead of a raw number.

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to read the current value (must be a discrete numeric type: BYTE, WORD, DWORD, SINT, USINT, INT, DINT, or TIME)
- **Command Address**: PLC address to write (optional, defaults to read address)
- **Options Map**: `value:label` pairs separated by `;`, for example:

  ```
  0:Off;1:Pump A;2:Pump B
  ```

  Each PLC value maps to the option shown in Home Assistant. Values must be
  unique integers within the range of both the state and command PLC data types, and labels must be
  unique and cannot contain `;` or newlines. TIME option values are expressed in
  seconds, consistently with the sensor and number entities. If the PLC reports a value that is not in the map, the entity state
  becomes unknown until a mapped value is read again.

#### Text

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to read (must be STRING or WSTRING type)
- **Command Address**: PLC address to write (optional, defaults to read address)
- **Pattern**: Optional regex pattern for input validation (e.g., `^[A-Z0-9]{1,10}$` for uppercase alphanumeric)
- **Min/Max Length**: Automatically determined from PLC string length declaration

#### Binary Sensor

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Address**: PLC address to read
- **Device Class**: Optional binary sensor device class
  - To remove a previously set device class, select **"No device class"** from the dropdown
- **Invert State**: Inverts the sensor state (PLC True → Off, PLC False → On). Useful for NC (Normally Closed) contacts or when PLC logic is inverted

#### Climate (Direct Control)

Direct control mode: Home Assistant manages heating/cooling outputs while reading the current temperature from the PLC.

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Current Temperature Address**: PLC address to read the current temperature (REAL)
- **Heating Output Address**: PLC boolean address for the heating relay (optional if cooling is set)
- **Cooling Output Address**: PLC boolean address for the cooling relay (optional if heating is set)
- **Heating Action Address** (optional): PLC address to read actual heating status feedback
- **Cooling Action Address** (optional): PLC address to read actual cooling status feedback
- **Min Temperature**: Minimum allowed target temperature (default: 7.0°C)
- **Max Temperature**: Maximum allowed target temperature (default: 35.0°C)
- **Temperature Step**: Step increment for temperature adjustments (default: 0.5°C)

The entity exposes a `climate_type` attribute set to **"Direct Control"**.

#### Climate (Setpoint Control)

Setpoint control mode: the PLC manages heating/cooling autonomously; Home Assistant only reads temperatures and writes the target setpoint.

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Current Temperature Address**: PLC address to read the current temperature (REAL)
- **Target Temperature Address**: PLC address to read/write the target setpoint (REAL)
- **Preset Mode Address** (optional): PLC address to write HVAC mode commands.
- **On/Off Address** (optional): Separate boolean enable address. The integration
  writes `false` for OFF and `true` for every enabled HVAC mode. This is useful
  when the PLC's mode register has no native OFF value.
- **Bidirectional Preset Mode**: Read the preset mode address back from the PLC,
  so changes made by an HMI or PLC program are reflected in Home Assistant. It
  is disabled by default to preserve write-only command-register behavior.
- **Preset mode values**: Map Home Assistant's OFF, HEAT, COOL, HEAT_COOL, AUTO,
  DRY, and FAN_ONLY modes to the integer codes expected by the PLC. The defaults
  are `0`, `1`, `2`, and `3` for the first four modes; AUTO, DRY, and FAN_ONLY
  are disabled by default. Leave any mapping empty to hide/disable that mode.
- **HVAC Status Address** (optional): PLC address used to report the current HVAC
  action independently from the commanded mode.
- **HVAC status values**: Map one or more comma-separated PLC integers to OFF,
  HEATING, COOLING, IDLE, DRYING, FAN, PREHEATING, or DEFROSTING. Defaults are
  `0`, `1`, and `2` for OFF, HEATING, and COOLING. Unmapped values fall back to
  IDLE. If no status address is provided, the action is estimated by comparing
  current and target temperatures.
- **Min Temperature**: Minimum allowed target temperature (default: 7.0°C)
- **Max Temperature**: Maximum allowed target temperature (default: 35.0°C)
- **Temperature Step**: Step increment for temperature adjustments (default: 0.5°C)

The entity exposes a `climate_type` attribute set to **"Setpoint Control"**.

Preset-mode values must be unique only when a **Preset Mode Address** is configured
and **Bidirectional Preset Mode** is enabled. In write-only configurations, the
same PLC value may be assigned to multiple modes. A status code cannot be assigned
to two different HVAC statuses. The Side Panel rejects ambiguous mappings before
saving.

#### Entity Sync

- **Address**: PLC address where values will be written
- **Source Entity**: Home Assistant entity to monitor
- See [Advanced Features](advanced-features.md#entity-sync) for detailed documentation

### Per-Entity Scan Interval

Every entity lets you override the **scan interval** just for that tag. Leave the field empty to inherit the PLC default defined during setup. This allows you to poll critical values more frequently while keeping less important tags at a slower rate.

### Editing Entities

Open the Side Panel, select the PLC and entity-type tab, and use the edit button
on the entity card. Modify the pre-filled values and select **Save changes**.

### Removing Entities

In the Side Panel, use an entity card's delete button, or select multiple cards
and use the batch delete action. Confirm the deletion; the integration reloads
automatically.

## Export and Import

### Exporting an Entity Backup

Need to move your configuration to another Home Assistant instance or keep a backup?

1. Open **Advanced YAML** in the Side Panel.
2. Select **Export YAML** to download the entity backup.

The exported file contains every configured entity grouped by type (`sensors`,
`binary_sensors`, `switches`, `covers`, `buttons`, `lights`, `numbers`,
`selects`, `texts`, `climates`, and `entity_sync`) together with addresses, limits, scan intervals,
and other entity metadata.

### Importing an Entity Backup

To restore a backup:

1. Open **Advanced YAML** for the target PLC and select **Import YAML**.
2. Choose the `.yaml` or `.yml` backup. This only loads it into the editor.
3. Review it, then select **Save changes** to apply it.

**Important Notes:**
- Saving the complete configuration replaces every entity list atomically. If
  any entity is invalid, nothing is saved.
- Options unrelated to entity lists, including connection settings, are preserved.
- A backup contains entities only; it does not include or restore connection settings.
- Valid UIDs are retained when a backup is restored to the same Config Entry.
  When importing into another Config Entry, or when UIDs are missing or
  duplicated, safe UIDs are generated.

## Connection Management

You can edit the connection settings at any time:

1. Open the integration from **Settings → Devices & Services**.
2. Click **Configure** to open the connection Options Flow.
3. Modify the name, host and port, the Rack/Slot or TSAP parameters for the
   connection method selected during setup, pyS7 connection type, global scan
   interval, timeout, retry/backoff, optimized reads, write batching, or metrics
   as needed. The Rack/Slot ↔ TSAP method itself cannot be changed here.
4. The integration will test the new connection before saving.

## Upgrading from 6.5.x

Existing configurations are retained and require no manual migration. Entity
data and UIDs remain unchanged, and the entity format stored in
`ConfigEntry.options` has not changed. After upgrading, manage entities in the
Side Panel; **Configure** continues to edit connection settings. Before major
changes, use **Export YAML** in the Side Panel to create an entity backup.

## Next Steps

- Learn about [S7 Addressing](addressing.md)
- Explore [Advanced Features](advanced-features.md) like State Synchronization, Entity Sync, and Performance Metrics
- Check [Examples](examples.md) for common use cases

## Per-entity availability

User-configured entities may select one of three availability policies. Omitting
`availability_mode` uses the backwards-compatible `connection` policy, which
requires both a PLC connection and valid entity data. `always` keeps the entity
available with its last known (and potentially stale) state even while the PLC is
disconnected. Commands are still rejected while disconnected. `bit` additionally
requires a BIT value read from `availability_address` to be exactly true; a cached
true bit can never make an entity available without a PLC connection.

```yaml
name: Motor ready
address: DB1,X0.0
availability_mode: bit
availability_address: DB1,X10.0
```

Availability addresses use the normal read optimizer and may deliberately be
shared by multiple entities. They may also equal another address on the same
entity: each internal topic retains its own meaning while the coordinator can
coalesce the physical read.

### Siemens `TIME` durations

The Siemens `TIME` datatype is supported for **sensor**, **number**, and **select** entities.
It is a signed 32-bit duration stored by the PLC in milliseconds, while Home
Assistant always displays and configures it in seconds. It must not be confused
with Home Assistant's time-of-day entity.

* Reads divide the PLC value by 1000: `TIME#1500ms` is `1.5 s`, `TIME#1s` is
  `1.0 s`, and `TIME#-250ms` is `-0.25 s`.
* Select mappings also use integer seconds and require an exact match; an
  unmapped fractional duration has no current option.
* Number writes multiply seconds by 1000 and round to the nearest millisecond:
  `2.345 s` is written as `2345 ms`.
* Negative durations are supported. The complete range is
  `-2147483.648 s` through `2147483.647 s`, with native `0.001 s` resolution.
* `min_value`, `max_value`, and `step` on a `TIME` number are expressed in
  seconds. When omitted, the signed TIME range and a `0.001 s` step are used.
* A `value_conversions.value` conversion is applied after conversion to seconds
  on reads and reversed before conversion to milliseconds on writes.

Use an address such as `DB1,TIME0`. `TIME` is not accepted for entity
platforms other than sensor, number, and select. Other Siemens temporal datatypes, including `LTIME` and time-of-day
variants, are not supported.

## Value conversion

Numeric PLC addresses can use centralized, per-channel conversions without
changing address syntax. See [PLC value conversions](value-conversions.md) for
the channel matrix, YAML schema, converter semantics and legacy compatibility.

### Brightness value conversions

The logical brightness exposed by every light is always 0–255. A linear
brightness conversion lets you edit only the PLC minimum and maximum (for
example 0–1000); its Home Assistant minimum 0, maximum 255, and clamping are
fixed. Multiplier and custom-expression results are likewise clamped before
being exposed to Home Assistant, while writes are clamped before conversion.
Existing legacy brightness settings are automatically migrated to the same
bidirectional linear conversion without applying it twice.
