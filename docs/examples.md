# Examples

Practical examples and use cases for the S7 PLC integration.

## Basic Entity Configuration

**Note**: All examples include a **Name** field for clarity, but this field is optional. If you omit the name, the integration automatically generates one based on the address (e.g., `DB1,X0.0` becomes "DB1 X0 0").

### Adding a Light Entity

1. After the integration is installed, open it from **Settings → Devices & Services**.
2. Click **Configure** and choose **Add items**.
3. Select **Light**, then enter:
   - **State Address**: `DB1,X0.0` (reads actual lamp status)
   - **Command Address**: `DB1,X0.1` (sends on/off commands)
   - **Name**: "Workshop Main Light"
   - **Sync State**: Enable if physical switches exist
4. Save to create the entity or enable **Add another** to keep adding more.

### Adding a Number Entity

1. Open the integration and choose **Add items**.
2. Select **Number** and configure:
   - **Address**: `DB10,I0` (signed INT for temperature setpoint, -32768 to 32767)
   - **Command Address**: Leave blank (uses same address for read/write)
   - **Min**: 15.0
   - **Max**: 30.0
   - **Step**: 0.5
   - **Name**: "HVAC Temperature Setpoint"
3. Submit to create the entity.

Note: Use `DB10,I0` for signed INT or `DB10,W0` for unsigned WORD. Any limits that fall outside the PLC data type range are automatically clamped to the closest valid value.

### Adding a Binary Sensor

1. Open the integration and choose **Add items**.
2. Select **Binary Sensor** and configure:
   - **Address**: `DB5,X2.3` (door contact)
   - **Device Class**: door
   - **Name**: "Main Entrance Door"
3. Save the configuration.

### Adding a Sensor

1. Open the integration and choose **Add items**.
2. Select **Sensor** and configure:
   - **Address**: `DB20,R100` (REAL for temperature)
   - **Device Class**: temperature
   - **Value Multiplier**: 1.0 (no scaling needed)
   - **REAL Precision**: 1 (one decimal place)
   - **Name**: "Tank Temperature"
3. Save the configuration.

### Adding a Button Entity

1. Open the integration and choose **Add items**.
2. Select **Button** and configure:
   - **Address**: `DB3,X10.5` (pulse output for reset)
   - **Pulse Time**: 1.0 (1 second pulse)
   - **Name**: "System Reset"
3. Save the configuration.

When pressed in Home Assistant, the button sends a 1-second pulse to the PLC address.

### Adding a Text Entity

1. Open the integration and choose **Add items**.
2. Select **Text** and configure:
   - **Address**: `DB15,S0.20` (STRING with max 20 characters, ASCII)
   - **Command Address**: Leave blank (uses same address)
   - **Pattern**: `^[A-Z0-9 ]{1,20}$` (optional regex for uppercase alphanumeric with spaces)
   - **Name**: "Operator Name"
3. Save the configuration.

The text entity allows reading and writing STRING/WSTRING values from the PLC. Min/max length is automatically determined from the PLC tag declaration.

### Adding a WString Text Entity (Unicode)

1. Open the integration and choose **Add items**.
2. Select **Text** and configure:
   - **Address**: `DB20,WS0.30` (WSTRING with max 30 characters, Unicode UTF-16)
   - **Command Address**: Leave blank (uses same address)
   - **Name**: "Product Description (Multilingual)"
3. Save the configuration.

**Note**: Use WString (`WS`) for text that contains non-ASCII characters (e.g., Chinese, Arabic, emoji, accented characters). WString uses UTF-16 encoding (2 bytes per character) while String uses ASCII (1 byte per character).

### Removing an Entity

1. Open the integration from **Settings → Devices & Services** and click **Configure**.
2. Choose **Remove items**.
3. Select the entities to remove from the dropdown list.
4. Submit; the integration reloads to apply the changes.

## Practical Use Cases

### Conveyor Belt Control

**Scenario**: A conveyor with physical start/stop buttons and Home Assistant control.

**Configuration**:
- **State Address**: `DB1,X0.0` (actual motor status from contactor feedback)
- **Command Address**: `DB1,X0.1` (motor start command)
- **Sync State**: Enabled
- **Entity Type**: Switch
- **Name**: "Conveyor Belt Motor"

**Result**: Physical button presses are automatically synchronized to the command address, keeping Home Assistant and PLC in sync.

### Temperature Control System

**Scenario**: HVAC system with temperature setpoint control.

**Configuration**:
- **Address**: `DB10,R50` (REAL for current temperature reading)
- **Device Class**: temperature
- **Value Multiplier**: 1.0
- **REAL Precision**: 1
- **Entity Type**: Sensor
- **Name**: "Room Temperature"

**Setpoint configuration**:
- **Address**: `DB10,R54` (REAL for setpoint)
- **Min**: 15.0
- **Max**: 30.0
- **Step**: 0.5
- **REAL Precision**: 1
- **Entity Type**: Number
- **Name**: "HVAC Setpoint"

### High-Precision Scientific Data

**Scenario**: Laboratory environment requiring high-precision measurements (double precision).

**Configuration**:
- **Address**: `DB50,LR0` (LREAL for high-precision sensor, 64-bit)
- **Device Class**: temperature
- **Value Multiplier**: 1.0
- **REAL Precision**: 4 (four decimal places)
- **Entity Type**: Sensor
- **Name**: "Lab Temperature (High Precision)"

**Note**: LReal (64-bit double precision) provides significantly higher precision than Real (32-bit float). Use LReal when your PLC stores values that require precision beyond ~7 significant digits. Common use cases: scientific measurements, GPS coordinates, precise flow rates.

### Multi-Point Lighting Control

**Scenario**: 8 lights in a warehouse controlled from multiple locations.

**Configuration for each light**:
```
Light 1: State=DB2,X0.0, Command=DB2,X1.0, Sync=Yes
Light 2: State=DB2,X0.1, Command=DB2,X1.1, Sync=Yes
Light 3: State=DB2,X0.2, Command=DB2,X1.2, Sync=Yes
...
```

Use **Add another** button to quickly configure all 8 lights in one session.

### Weather Data to PLC

**Scenario**: Send outdoor temperature to PLC for automated ventilation control.

**Configuration**:
- **Entity Type**: Entity Sync
- **Address**: `DB30,R10` (REAL for temperature)
- **Source Entity**: `sensor.openweathermap_temperature`
- **Name**: "Outdoor Temp to PLC"

The PLC receives real-time weather updates and can adjust ventilation based on outdoor conditions.

### Energy Monitoring

**Scenario**: Log power consumption data in PLC for production tracking.

**Configuration**:
- **Entity Type**: Entity Sync
- **Address**: `DB40,R0` (REAL for power in kW)
- **Source Entity**: `sensor.production_line_power`
- **Name**: "Production Power Usage"

Production power data is automatically sent to the PLC for energy monitoring and cost calculation.

### Tank Level with Scaled Values

**Scenario**: Tank level sensor outputs 0-27648 for 0-100% level.

**Configuration**:
- **Address**: `DB15,W50` (INT/Word from level sensor)
- **Value Multiplier**: 0.00362 (27648 / 100 = 276.48, so 1/276.48 ≈ 0.00362)
- **Device Class**: None
- **Unit**: %
- **Name**: "Storage Tank Level"

Home Assistant displays the level as 0-100% directly.

### Door Access Control

**Scenario**: Monitor door contacts and control electromagnetic locks.

**Door sensor**:
- **Entity Type**: Binary Sensor
- **Address**: `DB5,X10.0`
- **Device Class**: door
- **Name**: "Server Room Door"

**Lock control**:
- **Entity Type**: Switch
- **State Address**: `DB5,X11.0` (lock feedback)
- **Command Address**: `DB5,X12.0` (lock command)
- **Sync State**: Enabled
- **Name**: "Server Room Lock"

### Production Counter

**Scenario**: Track production units manufactured.

**Configuration**:
- **Address**: `DB50,DW100` (DINT for counter)
- **Device Class**: None
- **Name**: "Production Units Today"

Display the counter on a dashboard and use it in automations.

### Emergency Stop Status

**Scenario**: Monitor emergency stop circuit status.

**Configuration**:
- **Entity Type**: Binary Sensor
- **Address**: `DB1,X5.7`
- **Device Class**: safety
- **Name**: "Emergency Stop Circuit"

Create automations to notify when emergency stop is activated.

### Roller Shutter/Cover

**Scenario**: Automated roller shutter with open/close/stop commands.

**Configuration**:
- **Entity Type**: Cover
- **Open Command Address**: `DB20,X0.0`
- **Close Command Address**: `DB20,X0.1`
- **Opening State Address**: `DB20,X1.0` (optional feedback)
- **Closing State Address**: `DB20,X1.1` (optional feedback)
- **Operate Time**: 30 (30 seconds to fully open/close)
- **Name**: "Loading Bay Door"

The integration automatically manages the timing and state transitions.

## Polling Interval Optimization

### Fast Critical Alarms

For safety-critical inputs that need rapid detection:

```
Binary Sensor: Emergency Stop
Address: DB1,X0.0
Scan Interval: 0.1 (100ms)
```

### Normal Process Values

For standard process monitoring:

```
Sensor: Tank Temperature
Address: DB10,R50
Scan Interval: 1.0 (1 second)
```

### Slow Changing Values

For values that change rarely:

```
Sensor: Total Production Count
Address: DB50,DW0
Scan Interval: 10.0 (10 seconds)
```

**Tip**: Leave scan interval empty to inherit the global PLC scan interval set during initial configuration.

## Export/Import Example

### Exporting Your Configuration

1. Configure several entities through the UI
2. Open integration options and select **Export items**
3. Download the JSON file
4. Store it in version control or backup location

### Importing to a New Instance

1. Install the integration on the new Home Assistant instance
2. Complete the initial PLC connection setup
3. Select **Import items** from integration options
4. Paste the exported JSON
5. All entities are created automatically

This is perfect for:
- Moving between development and production environments
- Deploying identical configurations to multiple sites
- Recovering after system failures

## Advanced Patterns

### Bidirectional Temperature Display

Combine entities for complete control:

**Read PLC value** (Number entity):
```
Address: DB10,R50
Name: PLC Temperature Reading
```

**Send external temperature to PLC** (Entity Sync):
```
Address: DB10,R60
Source Entity: sensor.weather_temperature
Name: External Temp to PLC
```

### Cascaded Control

**Level sensor from PLC**:
```
Sensor: DB30,R0 → sensor.tank_level
```

**Control valve based on level** (automation in HA):
```yaml
automation:
  - trigger:
      - platform: numeric_state
        entity_id: sensor.tank_level
        above: 80
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.fill_valve
```

**Send HA decision back to PLC** (Entity Sync):
```
Address: DB30,X10.0
Source Entity: switch.fill_valve
Name: Fill Valve Command Writer
```

## Tips and Best Practices

1. **Use meaningful names**: Include location and function (e.g., "Workshop North Door" not "Door 1")

2. **Group related entities**: Use consistent naming prefixes for entities that belong together

3. **Document addresses**: Keep a spreadsheet mapping entity names to PLC addresses

4. **Test connection first**: Use binary sensors (simpler) to verify PLC communication before adding complex entities

5. **Start with slower scan intervals**: Begin with 1-2 second intervals and optimize only if needed

6. **Use entity sync for external data**: Don't poll external APIs just to write to PLC - use entity sync

7. **Enable sync state selectively**: Only enable for entities with physical controls or multiple command sources

8. **Export regularly**: Keep backups of your configuration in case you need to rebuild

## Next Steps

- Learn about [Advanced Features](advanced-features.md) like State Synchronization
- Review [Troubleshooting](troubleshooting.md) for common issues
- Check [S7 Addressing](addressing.md) for detailed address formats
