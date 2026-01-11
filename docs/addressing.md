# S7 Addressing Reference

This guide covers all supported addressing formats for Siemens S7 PLCs.

## Standard S7 Absolute Addressing

Use standard S7 absolute addressing for all entity configurations:

| Type                  | Example       | Size     | Typical meaning           |
|-----------------------|---------------|----------|---------------------------|
| Bit (boolean)         | `DB1,X0.0`    | 1 bit    | Discrete I/O, flags       |
| Byte (unsigned)       | `DB1,B0`      | 8 bits   | Small counters/bytes      |
| Word (signed 16-bit)  | `DB1,W2`      | 16 bits  | INT                       |
| DWord (signed 32-bit) | `DB1,DW4`     | 32 bits  | DINT                      |
| REAL (IEEE 754)       | `DB1,R4`      | 32 bits  | Float (temperature etc.)  |
| String (S7)           | `DB1,S0.20`   | 2+N bytes| Text (S7 STRING)          |

## Addressing Rules

### Data Block Notation

All addresses must reference a Data Block (DB):
- Format: `DB<number>,<type><offset>[.<bit>]`
- DB number: 1-65535
- Offset: byte position in the DB
- Bit: 0-7 (only for bit addresses)

### Type Identifiers

- `X` = Bit/Boolean
- `B` = Byte (unsigned, 0-255)
- `W` = Word (signed 16-bit, -32768 to 32767)
- `DW` = Double Word (signed 32-bit)
- `R` = Real (IEEE 754 floating point)
- `S` = String (format: `S<offset>.<length>`)

### Offset Alignment

Choose the correct **offset** and **type** based on your PLC data block layout:

- **Bit addresses** can start at any byte
- **Word** addresses should be even-aligned (0, 2, 4, ...)
- **DWord** and **Real** addresses should be 4-byte aligned (0, 4, 8, ...)

For REAL values, ensure the PLC writes IEEE 754 floating point into that DBD.

## Important Notes

### S7-1200/1500 Optimized Blocks

For S7-1200/1500 PLCs:

- If you use **absolute addresses** (DB + byte/bit offsets), ensure the data blocks you read/write are **not optimized**
- Disable *Optimized block access* for those DBs in TIA Portal
- Otherwise byte/bit offsets may not match your source symbols
- Optimized blocks use symbolic access which is not compatible with absolute addressing

### Data Type Conversion

The integration automatically handles conversions:

- **Binary sensors**: Any non-zero value = `on`, zero = `off`
- **Sensors**: Numeric types are converted to float, strings are read as UTF-8
- **Numbers**: Respects min/max bounds and converts to appropriate PLC type on write
- **Switches/Lights**: Boolean values (true/false) are written as 1/0 to bit addresses

## Logo! 8 Addressing

On the Logo! (from 0BA8 version) logic modules, use the default Rack/Slot value of 0/2.

### Read-Only System Areas

The following memory areas are accessible without additional settings (read-only):

| Logo Block | VM Range | Example Address | Description | Access |
|------------|----------|-----------------|-------------|--------|
| `I` | 1024-1031 | `DB1,BYTE1024` or `DB1,X1024.5` | Input terminals 1-8 (or word 1-16) | R |
| `AI` | 1032-1063 | `DB1,WORD1032` | Analog input terminal 1 | R |
| `Q` | 1064-1071 | `DB1,BYTE1064` or `DB1,X1064.5` | Output terminals 1-8 (or word 1-16) | R |
| `AQ` | 1072-1103 | `DB1,WORD1072` | Analog output terminal 1 | R |
| `M` | 1104-1117 | `DB1,BYTE1104` or `DB1,X1104.5` | Bit flags M1-8 (or word M1-16) | R |
| `AM` | 1118-1245 | `DB1,WORD1118` | Analog flag 1 | R |
| `NI` | 1246-1261 | `DB1,BYTE1246` | Network input 1-8 (or word 1-16) | R |
| `NAI` | 1262-1389 | `DB1,WORD1262` | Analog network input 1 | R |
| `NQ` | 1390-1405 | `DB1,BYTE1390` | Network output 1-8 (or word 1-16) | R |
| `NAQ` | 1406-1469 | `DB1,WORD1406` | Analog network output 1 | R |

### Read/Write User Memory

Logo memory areas VM 0-849 are mutable from outside the controller, but they need to be mapped into the Logo program using "Network" function blocks (with *"Local variable memory (VM)"* option).

**Addressing examples:**

| Logo VM | Example Address | Description |
|---------|----------------|-------------|
| `0` | `DB1,BYTE0` | R/W access byte |
| `1` | `DB1,X1.3` | R/W access bit 3 |
| `2-3` | `DB1,WORD2` | R/W access word |
| `4-7` | `DB1,DWORD4` | R/W access dword |

## Address Validation

The integration validates addresses during configuration:

- **Format check**: Ensures proper DB notation and type identifier
- **Offset check**: Verifies alignment for multi-byte types
- **Bit range**: Ensures bit index is 0-7
- **Test read**: Attempts to read from the address during setup

If validation fails, the configuration form will show a specific error message indicating what needs to be corrected.

## Finding the Right Address

### TIA Portal (S7-1200/1500)

1. Open your project in TIA Portal
2. Navigate to the Program blocks section
3. Open the Data Block you want to read/write
4. Note the offset shown for each variable
5. Use format: `DB<number>,<type><offset>`

### Step 7 (S7-300/400)

1. Open your project in Step 7
2. Open the data block in the DB editor
3. Check the byte offset column for each variable
4. Use format: `DB<number>,<type><offset>`

### Logo! Soft Comfort

1. Open your Logo! program
2. If using VM areas, note which VM addresses are mapped to Network function blocks
3. Use the VM range table above for system areas
4. Use format: `DB1,<type><offset>` (Logo always uses DB1)

## Common Mistakes

### Wrong offset
```
❌ DB1,R1  (REAL at byte 1 - not 4-byte aligned)
✅ DB1,R0  (REAL at byte 0 - properly aligned)
```

### Missing bit index
```
❌ DB1,X0  (incomplete bit address)
✅ DB1,X0.0  (bit 0 of byte 0)
```

### Invalid type
```
❌ DB1,I0  (I is not a valid type identifier)
✅ DB1,W0  (use W for INT/Word)
```

### Optimized DB on S7-1200/1500
```
❌ Using DB1,W10 on an optimized block
✅ Disable "Optimized block access" in block properties
```

## Next Steps

- Return to [Configuration Guide](configuration.md)
- Learn about [Advanced Features](advanced-features.md)
- Check [Examples](examples.md) for real-world addressing scenarios
