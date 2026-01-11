# Troubleshooting Guide

Common issues and solutions for the S7 PLC integration.

## Connection Issues

### Cannot Connect to PLC

**Symptoms**: Integration setup fails with connection error, or entities show "Unavailable".

**Troubleshooting steps**:

1. **Check network connectivity**:
   ```bash
   ping <PLC_IP>
   ```
   If ping fails, check network cables, switches, and router configuration.

2. **Verify port 102 is accessible**:
   ```bash
   telnet <PLC_IP> 102
   # or
   nc -zv <PLC_IP> 102
   ```
   If connection fails:
   - Check firewall rules on Home Assistant host
   - Check firewall rules on PLC
   - Verify PLC allows connections on port 102

3. **Verify rack/slot or TSAP settings**:
   - S7-1200/1500: typically `rack: 0`, `slot: 1`
   - S7-300/400: often `rack: 0`, `slot: 2` (verify in hardware config)
   - Logo! 8: `rack: 0`, `slot: 2`
   - For TSAP connections: verify Local and Remote TSAP values match PLC configuration

4. **Check PLC configuration**:
   - Ensure ISO-on-TCP communication is enabled
   - Verify PUT/GET access is allowed
   - Check connection resources are available (not all consumed)

5. **Test with minimal configuration**:
   - Try connecting without entities first
   - Add a simple binary sensor after connection succeeds

### Intermittent Disconnections

**Symptoms**: Connection drops randomly, entities become unavailable then recover.

**Possible causes and solutions**:

1. **Network instability**:
   - Check network quality with prolonged ping test: `ping -c 1000 <PLC_IP>`
   - Look for packet loss or high latency spikes
   - Consider using wired connection instead of WiFi

2. **PLC resource exhaustion**:
   - Check PLC connection table (other systems may be consuming connections)
   - Reduce scan interval to decrease connection load
   - Verify PLC CPU load is acceptable

3. **Timeout settings too aggressive**:
   - Increase operation timeout in integration settings
   - Increase retry backoff times for slower networks
   - See [Configuration Guide](configuration.md#network-profile-guidelines) for recommended values

4. **Optimize batch reads issues**:
   - Try disabling "Optimize batch reads" in integration settings
   - Some older PLCs don't support optimized reads properly

### Connection Succeeds But No Data

**Symptoms**: Integration shows connected but entity values are stuck or show unknown.

**Troubleshooting steps**:

1. **Verify addresses are correct**:
   - Double-check DB numbers and offsets
   - Ensure bit indexes are 0-7 for bit addresses
   - Verify data type matches PLC configuration

2. **Check PLC program is running**:
   - Ensure PLC is in RUN mode, not STOP
   - Verify the data you're trying to read is actually being written by the PLC program

3. **Test with a known good address**:
   - Try reading a simple input or output that you can physically toggle
   - This verifies the communication path works

4. **Review Home Assistant logs**:
   ```
   Settings → System → Logs
   ```
   Look for S7 PLC integration errors with specific details about what failed.

## Data Issues

### Values Look Wrong or Show Zeros

**Symptoms**: Entity values are incorrect, always zero, or nonsensical.

**Common causes**:

1. **Wrong address**:
   - Verify the DB number is correct
   - Check byte offset matches your PLC program
   - Ensure bit index is correct for boolean values

2. **Wrong data type**:
   - Reading a REAL as INT will show wrong values
   - Reading multi-byte values at wrong offset gives garbage
   - Ensure type identifier matches: X=bit, B=byte, W=word, DW=dword, R=real

3. **Optimized Data Blocks (S7-1200/1500)**:
   - On S7-1200/1500, ensure target DBs have **"Optimized block access" disabled**
   - Optimized blocks don't support absolute addressing
   - Byte offsets won't match if optimization is enabled

4. **Alignment issues**:
   - WORD should be at even offsets (0, 2, 4, ...)
   - DWORD and REAL should be at 4-byte aligned offsets (0, 4, 8, ...)
   - Misaligned reads can capture parts of multiple variables

5. **Value multiplier misconfigured**:
   - Check if a value multiplier is applied
   - Try setting multiplier to 1.0 to see raw value
   - Recalculate multiplier if scaling is incorrect

### Binary Sensor Shows Inverted State

**Symptoms**: Binary sensor shows "on" when it should be "off" and vice versa.

**Solutions**:

1. **PLC side**: Invert the logic in your PLC program (use NOT instruction)

2. **Home Assistant side**: Create a template binary sensor:
   ```yaml
   template:
     - binary_sensor:
         - name: "Inverted Door Sensor"
           state: "{{ is_state('binary_sensor.door_sensor', 'off') }}"
   ```

3. **Check wiring**: Verify if hardware uses normally-open or normally-closed contacts

### String Sensors Show Garbage

**Symptoms**: String sensor displays unreadable characters or wrong text.

**Troubleshooting**:

1. **Verify S7 STRING format**:
   - Address should be `DB#,S<offset>.<length>`
   - First 2 bytes are max length and current length
   - Actual string data starts at offset+2

2. **Check string encoding**:
   - Ensure PLC writes valid ASCII/UTF-8 characters
   - Control characters may display incorrectly

3. **Verify length parameter**:
   - Length in address should match STRING definition in PLC
   - Too short: truncates text
   - Too long: may read into other variables

## Performance Issues

### Slow Updates

**Symptoms**: Entities update slowly, lag behind PLC changes.

**Possible causes and solutions**:

1. **Scan interval too long**:
   - Check global scan interval in integration settings
   - Override scan interval for critical entities
   - See [Examples](examples.md#polling-interval-optimization) for guidance

2. **Network latency**:
   - Measure ping time to PLC: `ping <PLC_IP>`
   - High latency networks need larger timeout values
   - Consider local execution for time-critical automations

3. **Too many entities**:
   - Large number of entities increases cycle time
   - Consider if all entities need the same scan rate
   - Use per-entity scan intervals to stagger updates

4. **PLC CPU load**:
   - Check PLC diagnostics for CPU utilization
   - High PLC load increases response times
   - Optimize PLC program if necessary

### Home Assistant Becomes Slow

**Symptoms**: Home Assistant UI is sluggish when integration is active.

**Solutions**:

1. **Reduce polling frequency**:
   - Increase scan interval to reduce CPU load
   - Use 1-2 second intervals unless faster updates are truly needed

2. **Disable optimize batch reads**:
   - Some systems perform better with this disabled
   - Try both settings to see which works better

3. **Check system resources**:
   - Monitor Home Assistant host CPU/memory usage
   - Ensure adequate resources for other integrations too

## Entity Sync Issues

### Entity Sync Shows "Unavailable"

**Causes**:
- Source entity doesn't exist or is misspelled
- Source entity itself is unavailable
- PLC connection is lost

**Solutions**:
1. Verify source entity ID is correct (check in Developer Tools → States)
2. Ensure source entity is available
3. Check PLC connection status

### Error Count Increasing

**Symptoms**: `error_count` attribute keeps going up.

**Troubleshooting**:

1. **Check logs** for specific error messages:
   ```
   Settings → System → Logs → Search for "s7plc"
   ```

2. **Verify source entity provides valid data**:
   - Numeric addresses need numeric states
   - Bit addresses need boolean-compatible states
   - Check source entity history for "unknown" or "unavailable" states

3. **Confirm PLC address is correct**:
   - Test address with a regular sensor first
   - Ensure data block is writable
   - Verify data type matches expected values

4. **Check data type compatibility**:
   - Bit addresses: source must provide boolean or numeric values
   - REAL addresses: source should provide numeric values
   - INT/WORD: values must fit in -32768 to 32767 range

### Values Not Updating in PLC

**Symptoms**: Entity sync shows increasing `write_count` but PLC doesn't see changes.

**Troubleshooting**:

1. **Verify PLC program reads the address**:
   - Add PLC logic to display/use the value
   - Check online monitoring in TIA Portal/Step7

2. **Check data block properties**:
   - Ensure DB is not write-protected
   - Verify Standard access (not Optimized for S7-1200/1500)

3. **Confirm address offset**:
   - Double-check byte offset in PLC program
   - Verify alignment for multi-byte types

4. **Monitor write_count**:
   - If write_count increases, writes are succeeding
   - Problem is likely on PLC side (not reading the address)
   - If write_count doesn't increase, source entity isn't changing

## Configuration Issues

### Import Fails with Error

**Symptoms**: JSON import shows validation error.

**Solutions**:

1. **Check JSON syntax**:
   - Use a JSON validator (jsonlint.com)
   - Ensure all brackets and quotes are balanced
   - Check for trailing commas

2. **Verify required fields**:
   - Each entity needs `address` field
   - Entity-specific required fields must be present

3. **Check data types**:
   - Numeric fields (scan_interval, min, max) should be numbers not strings
   - Boolean fields should be true/false not "true"/"false"

4. **Start fresh**:
   - Export current configuration to see correct format
   - Modify exported JSON rather than writing from scratch

### Entities Not Appearing

**Symptoms**: Configuration is saved but entities don't show up.

**Solutions**:

1. **Check entity registry**:
   ```
   Settings → Devices & Services → Integration → # devices/entities
   ```

2. **Reload integration**:
   ```
   Settings → Devices & Services → S7 PLC → Reload
   ```

3. **Check for duplicate entity IDs**:
   - Entity IDs must be unique
   - Check logs for entity ID conflicts

4. **Restart Home Assistant**:
   - Sometimes a full restart is needed
   - Configuration → Server Controls → Restart

## Getting Help

If you're still experiencing issues after trying these troubleshooting steps:

1. **Enable debug logging**:
   ```yaml
   logger:
     default: warning
     logs:
       custom_components.s7plc: debug
   ```

2. **Collect information**:
   - Home Assistant version
   - Integration version
   - PLC model and firmware version
   - Full error messages from logs
   - Configuration (sanitize sensitive data)

3. **Open an issue**:
   - Visit the [GitHub repository](https://github.com/xtimmy86x/ha-s7plc)
   - Provide all collected information
   - Include steps to reproduce the problem

## Preventive Measures

### Best Practices

1. **Start simple**:
   - Test connection with one binary sensor first
   - Add complexity gradually

2. **Document your configuration**:
   - Keep a spreadsheet of all addresses
   - Note which PLC program sections use which addresses

3. **Use meaningful names**:
   - Makes troubleshooting easier
   - Clear error messages reference entity names

4. **Regular backups**:
   - Export configuration periodically
   - Store in version control or backup location

5. **Test in development**:
   - Set up a test environment if possible
   - Verify changes before deploying to production

6. **Monitor logs initially**:
   - Watch logs when adding new entities
   - Catch issues early before they become problems

7. **Use appropriate scan intervals**:
   - Don't poll faster than needed
   - Reduces PLC load and network traffic

## Next Steps

- Return to [Configuration Guide](configuration.md)
- Review [Examples](examples.md) for working configurations
- Check [S7 Addressing](addressing.md) for address format details
