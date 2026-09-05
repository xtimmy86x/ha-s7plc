# PLC value conversions

An **address** selects PLC memory and its datatype. A **value conversion** is a
separate, optional transformation between that raw value and Home Assistant.
Conversions are stored per logical channel, so a cover's position and tilt or a
climate entity's current and target temperatures cannot accidentally share a
transform.

## Supported channels

| Entity | Channel | Read address | Write address | Effective direction |
| --- | --- | --- | --- | --- |
| Sensor | value | `address` | — | read |
| Number | value | `address` | `command_address` (or `address`) | read/write |
| Select | value | `address` | `command_address` (or `address`) | read/write |
| Entity sync | value | — | `address` | write |
| Light | brightness | `brightness_state_address` | `brightness_command_address` | according to configured addresses |
| Cover | position | `position_state_address` | `position_command_address` | according to configured addresses |
| Cover | tilt | `tilt_state_address` | `tilt_command_address` | according to configured addresses |
| Cover | status | `cover_status_address` | — | read |
| Climate | current temperature | `current_temperature_address` | — | read |
| Climate | target temperature | `target_temperature_address` | same address | read/write |
| Climate | preset mode | `preset_mode_address` when bidirectional | same address | write or read/write |
| Climate | HVAC status | `hvac_status_address` | — | read |

Boolean commands, end stops, movement bits, availability addresses and climate
on/off/direct outputs are deliberately excluded because their schema requires
`BIT`. Text entities are excluded because their addresses require `STRING` or
`WSTRING`; `CHAR` is also not a numeric conversion datatype.

Discrete mappings are applied in this order: PLC value, numeric conversion,
semantic mapping, Home Assistant state. Writes use the exact inverse order:
Home Assistant option/mode, semantic numeric mapping, conversion to the PLC
domain, PLC write. This applies to select option maps, cover status words,
climate preset modes and HVAC status words.


## YAML schema

Omit `value_conversions` for identity behaviour. Each channel contains exactly
one converter:

```yaml
sensors:
  - address: DB1,INT0
    value_conversions:
      value:
        type: multiplier
        factor: 0.1

numbers:
  - address: DB1,INT2
    command_address: DB1,INT4
    min_value: 0
    max_value: 100
    value_conversions:
      value:
        type: linear_scale
        plc_min: 0
        plc_max: 27648
        ha_min: 0
        ha_max: 100
        clamp: true
        rounding: half_even

lights:
  - state_address: DB1,X0.0
    brightness_state_address: DB1,WORD10
    brightness_command_address: DB1,WORD12
    value_conversions:
      brightness:
        type: linear_scale
        plc_min: 0
        plc_max: 27648
        ha_min: 0
        ha_max: 255
        clamp: true

entity_sync:
  - source_entity: input_datetime.shift_start
    address: DB1,WORD20
    value_conversions:
      value:
        type: logo_time_bcd
```

For `number` entities, `min_value` and `max_value` are only the limits exposed
by Home Assistant for selecting a value. They do not describe the PLC range and
do not take part in the conversion. A `sensor` has no selectable value, so these
fields are not offered for sensors. Configure every numeric mapping explicitly
with the four `linear_scale` endpoints shown above.

A multiplier reads `HA = PLC × factor` and writes `PLC = HA ÷ factor`. A linear
scale maps the configured PLC interval to the HA interval and reverses that
formula on writes. The `clamp` option limits the **result** to the configured
range in both directions: it prevents Home Assistant values below or above the
HA limits and PLC writes below or above the PLC limits. Values already within
the interval are unchanged. This is especially useful for percentages, analog
signals, and measurements that can drift slightly outside their expected scale.

For a `0–1000 ↔ 0–100` scale with `clamp: true`, PLC values `1200` and `-100`
read as `100` and `0`; Home Assistant values `120` and `-10` write as `1000`
and `0`. The editor preview is local only and never writes to the PLC.

Integer targets support `half_even` (default), `half_up`, `floor`, and `ceil`
rounding.

`logo_time_bcd` is write-only and requires WORD. The visual editor offers this shortcut only for LOGO! connections (`plc_family` beginning with `logo_`) that have an available WORD write channel; runtime and YAML validation remain based on direction and datatype. It accepts `HH:MM` or
`HH:MM:SS`, validates seconds but packs only hours/minutes (`08:30` becomes
`0x0830`, decimal 2096). It uses the normal pyS7 WORD write without an extra
byte swap.

Expressions require explicit directions:

```yaml
value_conversions:
  value:
    type: expression
    read_expression: "value / 10"
    write_expression: "value * 10"
```

The two directions are independent. `read_expression` converts **PLC → Home
Assistant**, while `write_expression` converts **Home Assistant → PLC**. Define
only the directions the channel actually supports. In particular, the
integration does not derive or automatically invert a write expression from a
read expression (or vice versa).

Common expression examples are:

| Purpose | Expression |
| --- | --- |
| Read conversion | `value / 10` |
| Inverse write conversion | `value * 10` |
| Limit the result | `clamp(value, 0, 100)` |
| Round to one decimal place | `round(value, 1)` |

Only arithmetic (`+ - * / // %`), unary signs, `value`, and `round`, `min`,
`max`, `abs`, `int`, `float`, and `clamp` are accepted. The integration parses a
bounded AST; it never uses `eval`, templates, attributes, indexing, imports or
arbitrary calls. Non-finite results and datatype overflows abort only the
affected operation and are logged with entity/channel context.

The `clamp` function signature is `clamp(value, minimum, maximum)`: results
below `minimum` become `minimum`, and results above `maximum` become `maximum`.

## Automatic migration of legacy conversions

Existing config entries are persistently and automatically migrated before any
entity platform is set up. Entities do not need to be recreated: their UID,
Home Assistant registry records, addresses, ordering, and unrelated properties
are preserved. The panel displays and exports only `value_conversions`:

* `value_multiplier` → `multiplier.factor` for the `value` channel;
* `scale_raw_min`/`scale_raw_max` plus `min_value`/`max_value` → `linear_scale`,
  retaining the historical precedence over `value_multiplier`;
* `brightness_scale` → brightness scale `0…brightness_scale` ↔ `0…255`, with
  clamping and integer rounding identical to the dimmer behaviour.

During the 7.x series YAML/import still accepts these legacy fields, emits a
deprecation warning, and converts them before persistence. A valid new channel
is authoritative in mixed input; an equivalent legacy value is removed, while
a different value is removed with a warning and is never chained. Invalid new
configuration or incomplete/corrupt legacy scaling aborts the entire atomic
migration. Starting with 8.0.0, new legacy YAML input will no longer be accepted;
versioned config-entry migration remains available for direct upgrades from old
versions.

Migration validation is intentionally limited to conversion channels and the
addresses/datatypes needed to establish their read/write direction. Persisted
7.x entities are not re-submitted to the current panel validator, so unrelated
historical settings (including unknown compatible fields) cannot block an
upgrade. All entities are prepared first and the config entry is updated only
after every conversion succeeds; an error therefore leaves the original entry
untouched.

The same atomic config-entry migration also normalizes old switch and light
configurations that have `sync_state` enabled with no command address, or with a
command address equivalent to the state address. They are changed to direct
mode, where the state address continues to be used for both reading state and
sending commands. Entities do not need to be recreated.

## Light brightness invariant

Home Assistant light brightness always uses the logical range **0–255**. For a
`brightness` linear scale only the PLC interval is configurable; `ha_min: 0`,
`ha_max: 255`, and `clamp: true` are fixed and are enforced by the editor,
configuration validation, and the light runtime. For example, a PLC range of
0–1000 is configured as:

```yaml
value_conversions:
  brightness:
    type: linear_scale
    plc_min: 0
    plc_max: 1000
    ha_min: 0
    ha_max: 255
    clamp: true
```

This maps PLC 500 to approximately HA 128 and HA 128 to approximately PLC 502.
The invariant does not restrict the PLC range. Multiplier and expression read
results are also rounded and clamped at the Home Assistant boundary; before a
write, the Home Assistant input is clamped to 0–255 and only then passed to the
configured converter. The converter's PLC result is checked against the PLC
datatype, not against 0–255.

An existing legacy brightness setting is persistently migrated to exactly the
linear scale above, so the runtime never applies a second conversion.

## Sensor enum mapping

`enum_map` is a read-only conversion available **only** for the Sensor `value`
channel and the integer PLC datatypes `BYTE`, `USINT`, `SINT`, `WORD`, `INT`,
`DWORD`, and `DINT`. It is an alternative to multiplier, linear scale, custom
expression, and LOGO! time BCD conversions; converters cannot be chained.
Selecting it automatically sets `device_class: enum` and removes
`unit_of_measurement`, `state_class`, and `real_precision` from the persisted
configuration.

```yaml
sensors:
  - address: DB1,INT0
    name: Door state
    device_class: enum
    value_conversions:
      value:
        type: enum_map
        mappings:
          - value: 0
            label: Closed
          - value: 1
            label: Opening
          - value: 2
            label: Open
          - value: 3
            label: Fault
```

Mappings are an ordered list and that order becomes the Home Assistant enum
options order. PLC values are canonical integers and must be unique and within
the address datatype limits. Labels are trimmed and must be non-empty and
unique using case-sensitive comparison. An unmapped PLC value produces an
unknown state (`None`), and the raw number is never exposed. A warning is logged
once for each consecutive occurrence of an unmapped value. After a mapped value
is received, warning deduplication is reset, and normal state is restored. YAML
import applies the same device-class and incompatible-field normalization as the
visual editor.
