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

A multiplier reads `HA = PLC × factor` and writes `PLC = HA ÷ factor`. A linear
scale maps the configured PLC interval to the HA interval and reverses that
formula on writes; `clamp` limits the source to its interval. Integer targets
support `half_even` (default), `half_up`, `floor`, and `ceil` rounding.

`logo_time_bcd` is write-only and requires WORD. It accepts `HH:MM` or
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

Only arithmetic (`+ - * / // %`), unary signs, `value`, and `round`, `min`,
`max`, `abs`, `int`, `float`, and `clamp` are accepted. The integration parses a
bounded AST; it never uses `eval`, templates, attributes, indexing, imports or
arbitrary calls. Non-finite results and datatype overflows abort only the
affected operation and are logged with entity/channel context.

## Legacy compatibility

Legacy values are normalized in memory and are never chained with a new value:

* `value_multiplier` → `multiplier.factor` for the `value` channel;
* `scale_raw_min`/`scale_raw_max` plus `min_value`/`max_value` → `linear_scale`,
  retaining the historical precedence over `value_multiplier`;
* `brightness_scale` → brightness scale `0…brightness_scale` ↔ `0…255`, with
  clamping and integer rounding identical to the dimmer behaviour.

YAML import continues accepting legacy fields. New and equivalent legacy fields
in the same entity are rejected as an explicit conflict rather than silently
being doubled. Editing may persist the new map and remove only the legacy fields
that it replaces; there is no destructive bulk migration.
