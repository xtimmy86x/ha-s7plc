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

Logo! controllers use different connection methods and memory layouts depending on the version. **It's critical to use the correct addressing for your Logo! version.**

---

### Logo! 0BA8 and Newer (Recommended)

**Connection Settings:**
- **Connection Type**: Rack/Slot
- **Rack**: `0`
- **Slot**: `2`
- **Port**: `102` (default)

#### System I/O Areas (0BA8+)

The following memory areas are accessible without additional configuration (read-only):

| Logo! Block | VM Range | Example Address | Description | Access |
|-------------|----------|-----------------|-------------|--------|
| `I` | 1024-1031 | `DB1,BYTE1024` or `DB1,X1024.5` | Digital inputs I1-I8 | R |
| `AI` | 1032-1063 | `DB1,WORD1032` | Analog input AI1 (16 analog inputs total) | R |
| `Q` | 1064-1071 | `DB1,BYTE1064` or `DB1,X1064.5` | Digital outputs Q1-Q8 | R |
| `AQ` | 1072-1103 | `DB1,WORD1072` | Analog output AQ1 | R |
| `M` | 1104-1117 | `DB1,BYTE1104` or `DB1,X1104.5` | Digital flags M1-M8 | R |
| `AM` | 1118-1245 | `DB1,WORD1118` | Analog flag AM1 | R |
| `NI` | 1246-1261 | `DB1,BYTE1246` | Network input NI1-NI8 | R |
| `NAI` | 1262-1389 | `DB1,WORD1262` | Analog network input NAI1 | R |
| `NQ` | 1390-1405 | `DB1,BYTE1390` | Network output NQ1-NQ8 | R |
| `NAQ` | 1406-1469 | `DB1,WORD1406` | Analog network output NAQ1 | R |

#### User Memory (0BA8+)

VM memory areas **0-849** can be used for read/write operations. These must be mapped in your Logo! program using **"Network" function blocks** with the *"Local variable memory (VM)"* option.

**Addressing Examples (0BA8):**
- Digital input I1: `DB1,X1024.0`
- Analog input AI1: `DB1,WORD1032`
- Digital output Q1: `DB1,X1064.0`
- User VM byte 0: `DB1,BYTE0`
- User VM bit 1.3: `DB1,X1.3`
- User VM word 2-3: `DB1,WORD2`

---

### Logo! 0BA7 and Older (Legacy)

**Connection Settings:**
- **Connection Type**: TSAP ⚠️ **Required** (Rack/Slot not supported)
- **Local TSAP**: `10.00`
- **Remote TSAP**: `10.01`
- **Port**: `102` (default)

**Important Limitations:**
- VM memory layout is completely different from 0BA8+
- Network function blocks (NI, NAI, NQ, NAQ) are **not available**
- Always use `DB1` for addressing
- VM memory areas **0-849** can be used for read/write operations. 

#### I/O Mapping (0BA7)

| I/O Type | Logo! Symbol | VM Address | Example Address | Access |
|----------|--------------|------------|-----------------|--------|
| **Digital Inputs** | I1-I8 | V923.0 - V923.7 | `DB1,X923.0` (I1) | R |
| | I9-I16 | V924.0 - V924.7 | `DB1,BYTE924` (I9-I16) | R |
| | I17-I24 | V925.0 - V925.7 | `DB1,X925.0` (I17) | R |
| **Digital Outputs** | Q1-Q8 | V942.0 - V942.7 | `DB1,X942.0` (Q1) | R |
| | Q9-Q16 | V943.0 - V943.7 | `DB1,X943.0` (Q9) | R |
| **Analog Inputs** | AI1-AI8 | VW926-VW940 (even) | `DB1,WORD926` (AI1) | R |
| **Analog Outputs** | AQ1-AQ2 | VW944, VW946 | `DB1,WORD944` (AQ1) | R |
| **Digital Flags** | M1-M8 | V948.0 - V948.7 | `DB1,X948.0` (M1) | R/W |
| | M9-M16 | V949.0 - V949.7 | `DB1,X949.0` (M9) | R/W |
| | M17-M24 | V950.0 - V950.7 | `DB1,X950.0` (M17) | R/W |
| | M25-M27 | V951.0 - V951.2 | `DB1,X951.0` (M25) | R/W |
| **Analog Flags** | AM1-AM16 | VW952-VW982 (even) | `DB1,WORD952` (AM1) | R/W |

#### Special Addresses (0BA7)

| VM Address | Description | Example Address |
|------------|-------------|-----------------|
| V984 | Diagnostic bit array | `DB1,BYTE984` |
| V985-V990 | RTC: Year, Month, Day, Hour, Minute, Second | `DB1,BYTE985` (Year) |

**Complete Addressing Examples (0BA7):**
```
DB1,X923.0      → Digital input I1 (bit access)
DB1,BYTE923     → Digital inputs I1-I8 (byte access)
DB1,WORD926     → Analog input AI1
DB1,X942.0      → Digital output Q1
DB1,X948.0      → Digital flag M1 (Read/Write)
DB1,WORD952     → Analog flag AM1 (Read/Write)
DB1,BYTE984     → Diagnostic byte
DB1,BYTE985     → RTC Year
```

---

### Quick Reference Table

| Feature | 0BA7 and Older | 0BA8 and Newer |
|---------|----------------|----------------|
| **Connection** | TSAP (`10.00` / `10.01`) | Rack/Slot (`0` / `2`) |
| **DB Number** | DB1 only | DB1 only |
| **Digital I/O** | V923-V925 (I), V942-V943 (Q) | VM 1024-1031 (I), 1064-1071 (Q) |
| **Analog I/O** | VW926-VW940 (AI), VW944-VW946 (AQ) | VM 1032-1063 (AI), 1072-1103 (AQ) |
| **Flags** | V948-V951 (M), VW952-VW982 (AM) | VM 1104-1117 (M), 1118-1245 (AM) |
| **Network I/O** | ❌ Not available | ✅ VM 1246-1469 (NI, NAI, NQ, NAQ) |
| **User VM (0-849)** | ❌ Not available | ✅ Available with Network blocks |

---

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

**For Logo! 0BA8 and newer:**
1. Open your Logo! program
2. Configure "Network" function blocks to map VM areas (0-849) for read/write access
3. System I/O areas (1024+) are always accessible without configuration
4. Use format: `DB1,<type><offset>` (Logo! always uses DB1)

**For Logo! 0BA7 and older:**
1. Open your Logo! program
2. Refer to the I/O mapping table above for the correct VM addresses
3. Only I/O and flags are accessible (no user VM areas)
4. Use format: `DB1,<type><offset>` (Logo! always uses DB1)

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
