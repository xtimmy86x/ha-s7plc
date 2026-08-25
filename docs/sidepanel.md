# S7 PLC Side Panel

> [!IMPORTANT]
> Entity management through the legacy Entity Options Flow was removed in
> version **7.0.0**. The **S7 PLC Side Panel** is now the only supported
> interface for managing entities.

The integration registers a native **S7 PLC** page in the Home Assistant
sidebar. It is the current interface for adding, editing, deleting, importing,
and exporting PLC entities.

## Availability and Access

- The sidebar item appears after at least one S7 PLC config entry is loaded.
- The page is restricted to Home Assistant administrators.
- If multiple PLC entries exist, use the selector in the page header to switch
  between them. Every change applies only to the selected entry.
- The header shows whether the selected PLC coordinator is currently connected.
  Select the connection-status badge beside the PLC name to open a read-only
  view of all connection parameters (host, connection method, timing, retries,
  and performance options).

If the item does not appear after installing or upgrading the integration,
restart Home Assistant and confirm that the S7 PLC integration loaded without
errors.

## Page Overview

Entity-type tabs show the number of configured sensors, binary sensors,
switches, covers, lights, buttons, numbers, texts, climates, and Entity Sync
items. Each card includes:

- the configured name and primary PLC address;
- useful configuration flags;
- the current Home Assistant state, when the entity is available;
- buttons to edit or delete the item.

The internal entity UID is deliberately not displayed or edited in the normal
summary. It is preserved by the backend when an entity is updated, including
updates made in YAML mode, so changing an address does not create a new Home
Assistant entity identity.

## Adding and Editing an Entity

1. Open **S7 PLC** in the sidebar.
2. Select the correct PLC entry and entity-type tab.
3. Choose **Add**, or use the edit button on an existing card.
4. Keep **Visual editor** selected for a guided form, or choose **YAML** for
   advanced editing.
5. Review the values and choose **Save changes**.

The editor groups fields into PLC connection/data sources, entity-specific
behavior, and Home Assistant details. The cover editor dynamically shows only
fields compatible with the selected control type, position feedback, movement
feedback, stop command, and (for position covers) tilt. These guided choices are
derived from existing configuration keys and do not add YAML properties.

The Climate editor uses the same guided, card-based approach. It separates
direct Home Assistant regulation from PLC setpoint regulation, then guides the
choice of heating/cooling outputs, optional direct-action bits, setpoint power
and coded-mode commands, and operating-status feedback. Existing entities are
projected onto these choices from their stored addresses; the choices themselves
are never written to YAML.

**HVAC mode command/readback** and **operating status** are deliberately separate:

- Mode mappings decide which requested modes Home Assistant exposes and, when a
  coded mode address is configured, which number it writes. Optional mode
  readback reads the selected mode from that same address.
- Operating-status feedback reports what the equipment is actually doing, such
  as heating, cooling, idle, drying, or defrosting. It can be inferred from
  temperatures or read from its own coded PLC status address.

The two PLC addresses may be identical when that matches the PLC program, but
their meanings remain independent. Hidden legacy mappings are retained when
feedback is temporarily disabled, including explicit empty and disabled values.

Saving updates the selected config entry and Home Assistant reloads the
integration automatically. The page then refreshes its entity cards and live
states.

## Visual Editor

The visual editor is recommended for most changes because it supplies clear
labels, help text, choices, and historical defaults. It performs only simple
browser-side required-field checks; the shared backend validator remains
authoritative for PLC addresses and duplicate Climate preset/status mappings.

PLC address fields use the integration's S7 address rules. Examples include
`DB1,X0.0`, `DB1,REAL4`, and `DB1,S20.32`. Invalid or incompatible addresses are
rejected instead of being stored. Refer to the [S7 Addressing
Reference](addressing.md) for the complete syntax and alignment rules.

## Advanced YAML Editor

YAML mode edits one entity at a time as a mapping of configuration keys to
values. It is useful for copying a complex entity or changing fields not shown
in the guided view.

```yaml
name: "Living room temperature"
address: "DB1,REAL4"
unit_of_measurement: "°C"
scan_interval: 2
real_precision: 1
```

YAML mode is not an unrestricted bypass. Before saving, the backend:

- requires a YAML mapping (not a list or scalar);
- allows only fields supported by the selected entity type;
- validates value types and required fields;
- validates PLC address syntax and entity-specific address types;
- preserves the existing UID when editing an item and assigns one when adding;
- rejects invalid or ambiguous climate mappings.

Errors are shown in the editor dialog and the existing configuration remains
unchanged. Prefer the visual editor unless you understand the stored entity
schema; omitted optional YAML keys may remove their previous values.

### Complete configuration editor

Choose **Advanced YAML** in the page header to edit every entity belonging to
the selected PLC in one document. The top-level mapping contains one list for
each supported entity type (`sensors`, `binary_sensors`, `switches`, and so on).
Saving validates every item before replacing the entity configuration; if any
item is invalid, none of the changes are applied. Options unrelated to entity
lists are retained.

Use **Export YAML** to download the document currently shown in the editor, or
**Import YAML** to load a `.yaml`/`.yml` file into the editor. Importing a file
does not change Home Assistant until **Save changes** is selected. Because a
save replaces all entity lists, export a backup before making bulk changes.
Valid UIDs are retained when restoring to the same Config Entry. When importing
into another Config Entry, or when UIDs are missing or duplicated, safe UIDs are
generated. The YAML document backs up entities only, not connection settings.

## Deleting Entities

Choose the delete button on an entity card and confirm the dialog. Deletion is
immediate and cannot be undone. Export the current configuration first if you
might need to restore it; see [Export and Import](configuration.md#export-and-import).

## Side Panel vs. Integration Options

The initial Config Flow still adds a PLC, and **Settings → Devices & Services
→ S7 PLC → Configure** still opens the Options Flow for connection settings.
Neither is an entity editor in version 7.0.0.

| Function | Interface |
|----------|-----------|
| Add a PLC | Initial Config Flow |
| Modify the connection | Integration **Configure** / Options Flow |
| Add or modify entities | Side Panel |
| Delete entities | Side Panel |
| Back up and restore entities | Side Panel YAML |
| Connection diagnostics and status | Side Panel |

## Entity availability

Every configurable entity editor includes an availability policy. **Follow PLC
connection** is the default and preserves existing behavior. **Always available**
keeps the last state visible (which may be stale), but cannot bypass command
connection checks. **PLC availability bit** shows a required BIT address and only
makes the entity available when its normal data is valid, the PLC is connected,
and the bit is true. Switching away from the bit policy removes its address.
The same fields are supported by the visual and YAML editors.
