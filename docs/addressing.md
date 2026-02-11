# S7 Addressing Reference

This guide covers all supported addressing formats for Siemens S7 PLCs.

## Standard S7 Absolute Addressing

Use standard S7 absolute addressing for all entity configurations:

| Type                     | Example       | Size       | Range / Description                      |
|--------------------------|---------------|------------|------------------------------------------|
| Bit (boolean)            | `DB1,X0.0`    | 1 bit      | Boolean (0/1, false/true)                |
| Byte (unsigned)          | `DB1,B0`      | 8 bits     | 0 to 255                                 |
| Char                     | `DB1,C0`      | 8 bits     | Single ASCII character                   |
| Word (unsigned)          | `DB1,W2`      | 16 bits    | 0 to 65535 (WORD)                        |
| Int (signed)             | Not directly supported via `I` prefix | 16 bits | -32768 to 32767 (INT) - use Word address |
| DWord (unsigned)         | `DB1,DW4`     | 32 bits    | 0 to 4294967295 (DWORD)                  |
| DInt (signed)            | Not directly supported via `DI` prefix | 32 bits | -2147483648 to 2147483647 (DINT) - use DWord address |
| Real (IEEE 754)          | `DB1,R4`      | 32 bits    | 32-bit floating point                    |
| LReal (IEEE 754)         | `DB1,LR8`     | 64 bits    | 64-bit floating point (double precision) |
| String (S7)              | `DB1,S0.20`   | 2+N bytes  | Text (S7 STRING, ASCII)                  |
| WString (S7 Wide String) | `DB1,WS0.20`  | 4+2N bytes | Text (S7 WSTRING, Unicode UTF-16)        |

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
- `C` = Char (single ASCII character)
- `W` = Word (unsigned 16-bit, 0-65535)
- `DW` = Double Word (unsigned 32-bit, 0-4294967295)
- `R` = Real (IEEE 754 32-bit floating point)
- `LR` = LReal (IEEE 754 64-bit floating point, double precision)
- `S` = String (format: `S<offset>.<length>`, ASCII text)
- `WS` = WString (format: `WS<offset>.<length>`, Unicode UTF-16 text)

**Note**: While the S7 PLC internally distinguishes between signed (INT/DINT) and unsigned (WORD/DWORD) integers, the integration uses `W` for 16-bit and `DW` for 32-bit addresses. The actual interpretation (signed vs unsigned) depends on how the PLC stores the value. For signed values, use the same address format and the integration will handle the conversion correctly.

### Offset Alignment

Choose the correct **offset** and **type** based on your PLC data block layout:

- **Bit addresses** (`X`) can start at any byte
- **Byte** (`B`) and **Char** (`C`) can start at any byte
- **Word** (`W`) addresses should be even-aligned (0, 2, 4, 6, ...)
- **DWord** (`DW`), **Real** (`R`) addresses should be 4-byte aligned (0, 4, 8, 12, ...)
- **LReal** (`LR`) addresses should be 8-byte aligned (0, 8, 16, 24, ...)
- **String** (`S`) and **WString** (`WS`) can start at any byte but must have space for header + content

For REAL and LREAL values, ensure the PLC writes IEEE 754 floating point into that address.

### Signed vs Unsigned Integer Types

The S7 PLC supports both signed and unsigned integer types:

**16-bit integers:**
- **INT** (signed): -32768 to 32767
- **WORD** (unsigned): 0 to 65535

**32-bit integers:**
- **DINT** (signed): -2147483648 to 2147483647
- **DWORD** (unsigned): 0 to 4294967295

**Important**: When using addresses like `DB1,W0` or `DB1,DW0`, the integration will correctly handle both signed and unsigned values based on how the PLC stores them. The raw bytes are read and interpreted according to the PLC's data type. You don't need different address formats for INT vs WORD or DINT vs DWORD - use `W` for all 16-bit integers and `DW` for all 32-bit integers.

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

### Wrong alignment for LReal
```
❌ DB1,LR4  (LREAL at byte 4 - not 8-byte aligned)
✅ DB1,LR0  (LREAL at byte 0 - properly aligned)
✅ DB1,LR8  (LREAL at byte 8 - properly aligned)
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

### String vs WString confusion
```
❌ DB1,S0.20  (for Unicode text stored as WSTRING in PLC)
✅ DB1,WS0.20  (use WS for WSTRING, Unicode UTF-16)
```
Note: STRING uses ASCII encoding (1 byte per char), WSTRING uses UTF-16 (2 bytes per char)

### Optimized DB on S7-1200/1500
```
❌ Using DB1,W10 on an optimized block
✅ Disable "Optimized block access" in block properties
```

## Next Steps

- Return to [Configuration Guide](configuration.md)
- Learn about [Advanced Features](advanced-features.md)
- Check [Examples](examples.md) for real-world addressing scenarios
