# Configuration Guide

This guide covers the complete configuration process for the S7 PLC integration.

## Initial Setup

Configuration is handled entirely through the Home Assistant UI. After installing the component, add the integration and enter the PLC connection details.

### Basic Setup Steps

1. In Home Assistant, go to **Settings → Devices & Services** and click **+ Add Integration**.
2. Search for **"S7 PLC"** and select it.
3. Choose your connection type: **Rack/Slot** or **TSAP** (see below for details).
4. Pick one of the auto-discovered PLC hosts or type the PLC `host` manually.
5. Fill in connection parameters when prompted.
6. Once the integration is added, open it and choose **Configure** to manage entities.

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

**Note:** You can change the connection type later by editing the integration configuration.

## Timeout & Retry Settings

During the initial setup you can tune the PLC communication resilience directly from the UI:

| Field | Description | Default |
|-------|-------------|---------|
| **Operation timeout (s)** | Maximum time allowed for a single read/write cycle before a retry is attempted. | 5.0 |
| **Retry attempts** | Number of retry attempts before the operation is considered failed. | 3 |
| **Retry backoff start (s)** | Delay before the first retry after an error. | 0.5 |
| **Retry backoff max (s)** | Maximum delay used between subsequent retries. | 2.0 |
| **Optimize batch reads** | Enable optimized batch read operations for potentially better performance. | `true` |

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

## Managing Entities

### Adding Entities

1. Open the integration and choose **Configure** → **Add items**.
2. Select the entity type (`light`, `switch`, `cover`, `button`, `binary_sensor`, `sensor`, `number`, `text`, `Entity Sync`).
3. Fill in the form fields based on entity type (see below for details).
4. Use **Add another** to chain the creation of multiple entities.
5. Click **Send** to persist the last entry.

### Entity Type Details

**Note**: The **Name** field is optional for all entity types. If omitted, the integration automatically generates a name based on the PLC address (e.g., "DB1 X0 0" for address `DB1,X0.0`). This auto-generated name is then combined with the PLC device name by Home Assistant.

#### Switch and Light

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **State Address**: PLC address to read the actual state
- **Command Address**: PLC address to write commands (defaults to state address if omitted)
- **Sync State**: Enable to automatically synchronize external PLC state changes back to the command address (see [Advanced Features](advanced-features.md#state-synchronization))
- **Pulse Command Mode**: When enabled, sends a pulse (ON then OFF) instead of a continuous state. Useful for bistable relays, flip-flop circuits, or momentary button control
- **Pulse Duration**: Duration of the pulse in seconds (0.1-60s, default: 0.5s). Only used when Pulse Command Mode is enabled

#### Cover

- **Name** (optional): Custom friendly name for the entity. If not provided, a name is generated from the address
- **Open Command Address**: Address to command cover open
- **Close Command Address**: Address to command cover close
- **Opening State Address**: Address to read opening state (optional, reuses command address if blank)
- **Closing State Address**: Address to read closing state (optional, reuses command address if blank)
- **Operate Time**: Time in seconds to automatically reset command outputs (default: 60s)

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

#### Entity Sync

- **Address**: PLC address where values will be written
- **Source Entity**: Home Assistant entity to monitor
- See [Advanced Features](advanced-features.md#entity-sync) for detailed documentation

### Per-Entity Scan Interval

Every entity lets you override the **scan interval** just for that tag. Leave the field empty to inherit the PLC default defined during setup. This allows you to poll critical values more frequently while keeping less important tags at a slower rate.

### Editing Entities

1. Open the integration and choose **Configure** → **Remove items**.
2. Select an entity from the list (entities are organized by type and sorted alphabetically).
3. The form will be pre-filled with current values.
4. Modify as needed and save.

### Removing Entities

1. Open the integration and choose **Configure** → **Remove items**.
2. Select the entities to remove and submit.
3. The integration reloads automatically to apply changes.

## Export and Import

### Exporting Configuration

Need to move your configuration to another Home Assistant instance or keep a backup?

1. Open the integration options and choose **Export items**.
2. The dialog shows the JSON payload and offers a download link (active for 5 minutes).
3. Save the file to your device.

The exported file contains every configured entity grouped by type (`sensor`, `binary_sensor`, `switch`, `cover`, `button`, `light`, `number`, `text`, `entity_sync`) together with their addresses, limits, scan intervals, and other metadata.

### Importing Configuration

To restore a backup:

1. Select **Import items** from the integration options.
2. Paste the exported JSON.
3. The integration validates the structure before applying it.
4. On success, all configured items are replaced with the contents of the file.

**Important Notes:**
- **The import replaces ALL entity categories**, not just the ones in the JSON
- Any category not included in the import JSON will be cleared (set to empty)
- To keep existing entities in a category, you must include them in the import
- Other integration options (connection settings) remain intact
- Always export your current configuration before importing to avoid data loss
- Review the payload carefully before submitting

**Example:** If you import `{"numbers": []}`, ALL categories (sensors, switches, lights, etc.) will be cleared, not just numbers.

## Connection Management

You can edit the connection settings at any time:

1. Open the integration from **Settings → Devices & Services**.
2. Click **Configure** → **Edit Connection**.
3. Modify host, port, rack/slot or TSAP values as needed.
4. The integration will test the new connection before saving.

## Next Steps

- Learn about [S7 Addressing](addressing.md)
- Explore [Advanced Features](advanced-features.md) like State Synchronization and Entity Sync
- Check [Examples](examples.md) for common use cases
