<div align="center">

# ha-s7plc

**Home Assistant integration for Siemens S7 PLCs and Logo! controllers**  
Direct + lightweight custom component using `pys7`.  
**No MQTT • No REST • No middleware**

<br/>

![ha-s7plc banner](https://raw.githubusercontent.com/xtimmy86x/ha-s7plc/main/docs/banner.png)

<br/>

[![Release](https://img.shields.io/github/v/release/xtimmy86x/ha-s7plc)](https://github.com/xtimmy86x/ha-s7plc/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-41BDF5)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB)](https://www.python.org/)
[![pyS7](https://img.shields.io/badge/Library-pys7-informational)](https://github.com/xtimmy86x/pyS7)

<br/>

<a href="https://www.buymeacoffee.com/xtimmy86x" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="175" />
</a>

<br/>

**Quick Links**
[✨ Features](#features) •
[🚀 Quick Start](#quick-start) •
[📚 Documentation](#documentation) •
[🧩 Entities](#supported-entities) •
[🛠️ Troubleshooting](#troubleshooting) •
[📊 PLC Survey](https://docs.google.com/forms/d/e/1FAIpQLSd7Yi2uho8emdZ--l2RfUXGMusEcxQVUDAXA9IMkIBbcbjIiQ/viewform?usp=publish-editor)

<br/>

### 📊 Help improve PLC compatibility

**Which Siemens PLC are you using with ha-s7plc?**

Take our short voluntary survey and help us understand which PLC models and firmware versions are actually used by the community.

[**👉 Take the PLC Compatibility Survey**](https://docs.google.com/forms/d/e/1FAIpQLSd7Yi2uho8emdZ--l2RfUXGMusEcxQVUDAXA9IMkIBbcbjIiQ/viewform?usp=publish-editor)

<sub>No information is collected automatically from Home Assistant or your PLC.</sub>

</div>

---

## Features

- ⚡ **Direct PLC communication** over S7 protocol via `pys7`
- 🧩 **Multiple entity types**: `light`, `dimmer light`, `switch`, `cover`, `button`, `binary_sensor`, `sensor`, `number`, `select`, `text`, `climate`, and Entity Sync
- 🔌 **Dual connection modes**: Rack/Slot or TSAP addressing
- 🧮 **Value multipliers**: Scale raw PLC values before Home Assistant sees them
- 🪶 **Lightweight**: Minimal overhead, no broker/services required
- 🛠️ **Full UI configuration**: Set up and manage entirely from Home Assistant's UI
- 🖥️ **Native side panel**: Manage every PLC entity from the Home Assistant sidebar with visual and YAML editors, live states, and validation
- 🔍 **Optional auto-discovery**: Pre-populates PLCs found on your local network
- 📄 **S7 STRING support** for text sensors
- 🔄 **State synchronization**: Bidirectional sync for switches and lights with physical controls
- 📤 **Entity Sync**: Push any Home Assistant entity state to PLC addresses in real-time
- 🌡️ **Climate control**: Direct control and setpoint modes for HVAC systems
- 📊 **Import/Export**: Backup and restore your entity configurations
- 📈 **Performance metrics**: Optional diagnostic sensors for connection health and PLC communication stats

---

## Quick Start

### Requirements

- **Home Assistant** installation
- **Siemens S7 PLC** (S7-1200/1500/300/400) or **Logo! controller** (Logo! 8 / 0BA8 and newer; Logo! 0BA7 and older via TSAP) reachable over ISO-on-TCP (port 102)
- Network connectivity between Home Assistant and PLC

> ℹ️ For S7-1200/1500: Ensure data blocks have **Optimized block access disabled** if using absolute addressing.
> ℹ️ For Logo! 8 (0BA8+): use Rack/Slot connection (`rack: 0`, `slot: 2`). For Logo! 0BA7 and older: use TSAP connection (see [addressing docs](docs/addressing.md#logo-0ba7-and-older-legacy)).

### Installation

**Via HACS (Recommended)**

1. Ensure [HACS](https://hacs.xyz) is installed
2. Open **HACS → Integrations**
3. Search for **"Siemens S7 PLC"** and install
4. Restart Home Assistant

**Manual Installation**

1. Copy `custom_components/s7plc` to your HA config directory
2. Restart Home Assistant

### Basic Setup

> [!IMPORTANT]
> Entity management through the legacy Entity Options Flow was removed in
> version **7.0.0**. The initial Config Flow and the connection Options Flow
> remain available; entities are managed only through the **S7 PLC Side Panel**.

1. Install the integration and restart Home Assistant.
2. Go to **Settings → Devices & Services** → **Add Integration**.
3. Search for and add **S7 PLC**.
4. Choose connection type:
   - **Rack/Slot** (default): Standard connection for most PLCs and Logo! 8
   - **TSAP**: For specific configurations, Logo! 0BA7 and older, or legacy systems
5. Enter the PLC connection details and let the Config Flow verify the connection:
   - Host, Port
   - Rack/Slot (typically `0/1` for S7-1200/1500, `0/2` for S7-300/400 and Logo! 8)
   - or Local/Remote TSAP for TSAP mode (e.g. `10.00` / `10.01` for Logo! 0BA7)
6. Configure timeout and retry settings for your network.
7. Open **S7 PLC** from the Home Assistant sidebar, then add and manage entities
   in the Side Panel.

### Changing the Connection

**Settings → Devices & Services → S7 PLC → Configure** opens the Options
Flow exclusively for connection settings: name, host and port, Rack/Slot or
TSAP parameters for the connection method selected during setup, pyS7 connection
type, global scan interval, timeout, retry and backoff,
optimized reads, write batching, and metrics. It does not manage entities.
The Rack/Slot ↔ TSAP connection method itself cannot be changed later; create a
new integration entry to use the other method.

---

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[Configuration Guide](docs/configuration.md)** - Complete setup instructions, connection types, entity management
- **[Side Panel Guide](docs/sidepanel.md)** - Visual and YAML entity editing from the Home Assistant sidebar
- **[S7 Addressing](docs/addressing.md)** - Address formats, data types, PLC-specific notes
- **[Value Conversions](docs/value-conversions.md)** - Numeric scaling and safe custom expressions
- **[Advanced Features](docs/advanced-features.md)** - State Synchronization, Entity Sync, and Performance Metrics
- **[Examples](docs/examples.md)** - Practical use cases and configuration examples
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

### Quick Links

| Topic | Description |
|-------|-------------|
| [Connection Types](docs/configuration.md#connection-types) | Rack/Slot vs TSAP addressing |
| [Entity Types](docs/configuration.md#entity-type-details) | Switch, Light, Dimmer Light, Cover, Sensor, Number, Climate, Entity Sync |
| [S7 PLC Side Panel](docs/sidepanel.md) | Visual/YAML editing, validation, live status, and multi-PLC selection |
| [Value Conversions](docs/value-conversions.md) | Read/write scaling, clamping, and custom expressions |
| [State Sync](docs/advanced-features.md#state-synchronization) | Bidirectional synchronization for physical controls |
| [Entity Sync](docs/advanced-features.md#entity-sync) | Push HA entities to PLC addresses |
| [Performance Metrics](docs/advanced-features.md#performance-metrics) | Diagnostic sensors for connection and communication stats |
| [Logo! Support](docs/addressing.md#logo-8-addressing) | Specific notes for Logo! controllers |
| [Export/Import](docs/configuration.md#export-and-import) | Backup and restore configurations |

---

## Supported Entities

| Entity Type | Read | Write | Features |
|-------------|------|-------|----------|
| **Binary Sensor** | ✅ | ❌ | Device classes, bit addressing, state inversion |
| **Sensor** | ✅ | ❌ | Numeric types, strings, multipliers, precision |
| **Switch** | ✅ | ✅ | State sync, pulse command mode, separate state/command addresses |
| **Light (On/Off)** | ✅ | ✅ | State sync, pulse command mode, separate state/command addresses |
| **Dimmer Light** | ✅ | ✅ | Brightness control, configurable scale, optional actuator relay |
| **Cover** | ✅ | ✅ | Open/close commands, position control (0–100%), stop, timing |
| **Button** | ❌ | ✅ | Pulse output with configurable duration (0.1-60s, supports decimals) |
| **Number** | ✅ | ✅ | Min/max/step, separate read/write addresses |
| **Select** | ✅ | ✅ | Map numeric PLC values to named options (modes, fan speeds, etc.) |
| **Text** | ✅ | ✅ | STRING/WSTRING support, pattern validation, auto-sized limits |
| **Climate** | ✅ | ✅ | Direct control or setpoint mode, HVAC status feedback |
| **Entity Sync** | ❌ | ✅ | Monitor any HA entity, write to PLC on change |

---

## Supported Data Types

| S7 Type | Example | Description |
|---------|---------|-------------|
| Bit | `DB1,X0.0` | Boolean values |
| Byte | `DB1,B0` | Unsigned 8-bit (0-255) |
| USInt | `DB1,USINT0` | Unsigned 8-bit (0-255, explicit USINT) |
| SInt | `DB1,SINT0` | Signed 8-bit (-128 to 127) |
| Char | `DB1,C0` | Single ASCII character |
| Word | `DB1,W2` | Unsigned 16-bit (0-65535) |
| Int | `DB1,I2` | Signed 16-bit (-32768 to 32767) |
| DWord | `DB1,DW4` | Unsigned 32-bit (0-4294967295) |
| DInt | `DB1,DI4` | Signed 32-bit (-2147483648 to 2147483647) |
| Real | `DB1,R4` | IEEE 754 32-bit float |
| LReal | `DB1,LR8` | IEEE 754 64-bit double precision float |
| String | `DB1,S0.20` | S7 STRING type (ASCII) |
| WString | `DB1,WS0.20` | S7 WSTRING type (Unicode UTF-16) |

**Note**: Use `I`/`DI` for signed integers, `W`/`DW` for unsigned integers. Use `SINT` for signed 8-bit values.

See [S7 Addressing](docs/addressing.md) for complete details.

---

## Example Use Cases

- **HVAC Control**: Read temperatures, control setpoints, climate entities with direct or setpoint modes
- **Lighting Systems**: Multi-point control with physical switches, dimmer lights with brightness control
- **Conveyor Belts**: Monitor status, control motors
- **Door Access**: Lock control, contact monitoring
- **Data Logging**: Push weather, energy data to PLC
- **Process Control**: Tank levels, valve positions, pump control

See [Examples](docs/examples.md) for detailed configurations.

---

## FAQ

**Q: Is MQTT required?**  
A: No. Direct S7 protocol communication to PLC.

**Q: Which PLCs are supported?**  
A: Any Siemens device with ISO-on-TCP (port 102) support: S7-1200, S7-1500, S7-300, S7-400, Logo! 8 (0BA8+) via Rack/Slot, and Logo! 0BA7/0BA6/0BA5 via TSAP.

**Q: Can I write values to the PLC?**  
A: Yes. `switch`, `light`, `dimmer light`, `cover`, `button`, `number`, `select`, `text`, `climate`, and Entity Sync all support writes.

**Q: Do I need to know PLC programming?**  
A: Basic knowledge helps. You need to know your data block structure and addresses.

**Q: Can I use symbolic names?**  
A: No, only absolute addressing (DB + offset) is supported.

---

## Troubleshooting

Common issues:

- **Connection fails**: Check network, firewall, rack/slot values
- **Wrong values**: Verify address, data type, alignment
- **Slow updates**: Adjust scan interval, check network latency
- **Intermittent disconnects**: Review timeout settings, network stability

See [Troubleshooting Guide](docs/troubleshooting.md) for complete solutions.

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Add documentation for new features
5. Open a Pull Request

### Development

Local development requires Python and Node.js. Install both dependency sets and run the backend and panel DOM test suites:

```bash
python -m pip install -r requirements_dev.txt
npm ci

python -m pytest tests -v
npm run test:panel
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete environment setup, focused test commands, frontend test structure, coverage checks, and pull request guidelines.

This project also uses [pre-commit](https://pre-commit.com/):

```bash
pre-commit run --files <file1> [<file2> ...]
```

---

## Roadmap

- [x] Multiple entity types
- [x] UI-only configuration
- [x] State synchronization
- [x] Entity sync (write HA entities to PLC)
- [x] TSAP connection support
- [x] Import/Export configuration
- [x] Climate entities (direct and setpoint control)
- [x] Dimmer light with brightness control
- [x] Position-based cover with stop
- [x] Performance metrics (diagnostic sensors)
- [ ] Performance optimizations

> Have ideas? Open an **issue** or **PR**!

---

## Releases

### 7.0.0

Version 7.0.0 makes the native **S7 PLC Side Panel** the primary workspace for
managing connections and entities. It provides selectable tabbed and expandable
all-entity layouts, guided simplified modes for switches, on/off and dimmable
lights, traditional and position covers, and direct or setpoint climates, plus
Advanced YAML import/export. The previous entity Options Flow has been removed;
the remaining Options Flow edits connection parameters only. Its Rack/Slot or
TSAP method remains fixed after initial setup.

Traditional covers can now derive position from a single open or closed limit
switch, both limit switches, timed estimation, or mapped status-word values.
Movement feedback can likewise use individual bits or a status word. Entities
also gain configurable availability policies: follow the PLC connection and
required data, remain available with the last known state, or require a PLC BIT.
The panel's connection detail view now provides clearer diagnostics, including
the active pyS7 version and communication settings.

Existing 6.5.x config entries, entity definitions, and UIDs remain compatible;
there is no destructive data migration and no need to recreate entities. After
upgrading and restarting Home Assistant, use the Side Panel instead of the old
entity Options Flow. As always, exporting an entity backup before a major
upgrade is recommended. The integration now requires **`pys7==3.1.1`**.

**Breaking change / user action:** entity editing in the legacy Options Flow is
no longer available. No configuration conversion is required, but entity
changes must now be made in the Side Panel. To change between Rack/Slot and TSAP,
create a new integration entry.

See [Releases](https://github.com/xtimmy86x/ha-s7plc/releases) for downloads and
earlier release notes.

---

## Security & Safety

- Use on **trusted networks** only
- Apply standard Home Assistant secrets handling
- Consider read-only DBs for monitoring to prevent accidental writes
- Test thoroughly in non-production environments first

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgements

- Built on [`pyS7`](https://github.com/xtimmy86x/pyS7) library
- Inspired by the Home Assistant community
- Not affiliated with Siemens AG or Home Assistant

---

## Support

- 📖 Read the [documentation](docs/)
- 🐛 Report bugs via [GitHub Issues](https://github.com/xtimmy86x/ha-s7plc/issues)
- 💬 Discuss in [Home Assistant Community](https://community.home-assistant.io/)
- ☕ [Buy me a coffee](https://www.buymeacoffee.com/xtimmy86x) if this helps you!
