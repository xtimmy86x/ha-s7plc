# Advanced Features

This document covers advanced functionality including State Synchronization and Entity Sync.

## State Synchronization

The **Sync State** feature is available for `switch` and `light` entities and provides intelligent bidirectional synchronization between Home Assistant and the PLC.

### How it Works

When `sync_state` is enabled:

1. **Home Assistant commands are tracked**: When you turn on/off a switch or light from Home Assistant, the integration writes to the `command_address` and marks the change as "pending".

2. **PLC feedback is monitored**: The integration continuously reads the `state_address` to detect the actual PLC state.

3. **Echo prevention**: If the PLC state matches the pending command, the integration knows the command was successful and clears the pending flag. This prevents sending duplicate commands back to the PLC.

4. **External changes are synchronized**: If the PLC state changes externally (e.g., from a physical button, PLC program logic, or another system), the integration detects the mismatch and automatically writes the new state to the `command_address`. This keeps both addresses in sync.

### When to Use Sync State

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

### When NOT to Use Sync State

Disable `sync_state` (default) when:

- **Single control point**: Only Home Assistant controls the output
- **Same address for state and command**: The PLC uses a single address for both reading and writing
- **PLC handles synchronization**: Your PLC program already manages any necessary feedback logic
- **Performance concerns**: High-frequency state monitoring or write operations might impact PLC performance

### Configuration

To enable sync state for a switch or light:

1. Open the integration from **Settings → Devices & Services**
2. Click **Configure** and choose **Add items** (for new entities) or **Edit** (for existing ones)
3. Select `switch` or `light` as the entity type
4. Enter the `state_address` (the PLC address to read the actual state)
5. Enter the `command_address` (the PLC address to write commands) - if omitted, defaults to state_address
6. **Enable the `Sync State` checkbox**
7. Save the configuration

### Technical Details

- The synchronization logic runs during the normal polling cycle based on your configured scan interval
- State changes are written asynchronously to avoid blocking the coordinator
- The integration maintains internal state tracking to distinguish between Home Assistant commands and external PLC changes
- Initial state on entity creation is read-only (no synchronization) to avoid unintended writes during startup

### Performance Considerations

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

### Common Use Cases

#### Data Integration
- Send weather data from Home Assistant weather integrations to PLC for HVAC control
- Forward energy consumption from smart meters to PLC monitoring systems
- Push setpoints from Home Assistant `input_number` helpers to PLC controllers
- Transmit calculated values from template sensors to PLC

#### Multi-System Coordination
- Synchronize data between different automation platforms through the PLC
- Feed external sensor readings into PLC-based control algorithms
- Send occupancy or presence detection to PLC for lighting/HVAC automation
- Forward alarm states or security system status to PLC logic

#### Process Control
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

### Configuration Examples

**Weather temperature to PLC**
```
Address: DB10,R0
Source Entity: sensor.openweathermap_temperature
Name: Outside Temperature Sync
```
Writes the current outside temperature to `DB10,R0` (REAL) whenever the weather sensor updates.

**Input number setpoint**
```
Address: DB20,W10
Source Entity: input_number.hvac_setpoint
Name: HVAC Setpoint Sync
```
Writes the value from an `input_number` helper to `DB20,W10` (INT/WORD) whenever you adjust the setpoint slider.

**Power consumption monitoring**
```
Address: DB5,R100
Source Entity: sensor.home_power_consumption
Name: Power Consumption Sync
```
Continuously sends your home's real-time power consumption to the PLC for monitoring or demand response logic.

**Binary sensor to PLC bit**
```
Address: DB1,X0.5
Source Entity: binary_sensor.front_door
Name: Front Door Status Writer
```
Writes the front door binary sensor state (`on`/`off`) to a PLC bit `DB1,X0.5`. When the door opens (state = `on`), the bit is set to `true`; when closed (state = `off`), it's set to `false`.

**Switch state to PLC bit**
```
Address: DB10,X5.2
Source Entity: switch.irrigation_zone_1
Name: Irrigation Zone 1 Writer
```
Mirrors a Home Assistant switch state to a PLC bit. Useful for monitoring HA automation states from the PLC or coordinating with PLC-based interlocks.

### Entity Attributes

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

### Data Type Handling

Writers automatically detect the PLC data type from the address and handle conversions:

- **BIT** (`DB#,X#.#`): Writes boolean values. Accepts states like `on`, `off`, `true`, `false`, `1`, `0`, `yes`, `no` (case-insensitive) or any numeric value (non-zero = true, zero = false)
- **REAL** (`DB#,R#`): Writes floating-point values with full precision
- **INT/WORD** (`DB#,W#`): Converts to 16-bit signed integer (-32768 to 32767)
- **DINT/DWORD** (`DB#,DW#`): Converts to 32-bit signed integer
- **BYTE** (`DB#,B#`): Converts to unsigned byte (0 to 255)

If the source entity provides a non-numeric state (e.g., "unavailable", "unknown") or an invalid boolean state for BIT addresses, the write is skipped and `error_count` increments. The writer logs a warning to help with troubleshooting.

### Behavior Notes

**Automatic type detection**
- Writers automatically detect if the PLC address is a BIT type and adapt their behavior and representation
- Binary writers (BIT addresses) display `on`/`off` states with dynamic toggle switch icons
- Numeric writers display numerical values with an upload icon

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

### When to Use Entity Sync vs. Number Entities

**Use Entity Sync when:**
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
Combine a `number` entity (for PLC → HA data flow) with an `entity_sync` (for external data → PLC flow) to create complex data exchange patterns.

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

## Next Steps

- Return to [Configuration Guide](configuration.md)
- Check [Examples](examples.md) for practical implementations
- See [Troubleshooting](troubleshooting.md) if you encounter issues
