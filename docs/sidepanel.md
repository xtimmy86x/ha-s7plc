# S7 PLC Side Panel

> [!IMPORTANT]
> Starting with version **7.0.0**, the config flow for entity management will be
> deprecated and entities can be configured only from this side panel.

The integration registers a native **S7 PLC** page in the Home Assistant
sidebar. It is the quickest way to inspect and maintain PLC entities without
stepping through the integration options flow for each change.

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
behavior, and Home Assistant details. The cover editor dynamically shows only fields compatible with the selected control type, position feedback, movement feedback, stop command, and (for position covers) tilt. These guided choices are derived from existing configuration keys and do not add YAML properties. Fields that do not apply to the chosen climate control mode are hidden automatically. Climate preset mappings
appear only when a preset mode address is configured, while HVAC status mappings
appear only when an HVAC status address is configured.

Saving updates the selected config entry and Home Assistant reloads the
integration automatically. The page then refreshes its entity cards and live
states.

## Visual Editor

The visual editor is recommended for most changes because it supplies the same
labels, help text, choices, and defaults as the integration options flow. It
also performs browser-side checks for required fields and rejects duplicate
climate preset/status mappings.

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
Existing unique IDs in exported files are retained so restored entities keep
their Home Assistant identity; missing or duplicate IDs are safely regenerated.

## Deleting Entities

Choose the delete button on an entity card and confirm the dialog. Deletion is
immediate and cannot be undone. Export the current configuration first if you
might need to restore it; see [Export and Import](configuration.md#export-and-import).

## Side Panel vs. Integration Options

The side panel is the recommended interface for routine entity creation and
maintenance, and becomes the only supported entity-configuration interface in
version 7.0.0. On releases before 7.0.0, you can continue to use
**Settings → Devices & Services → S7 PLC → Configure** for:

- PLC host, Rack/Slot or TSAP, timeout, retry, and performance settings;
- bulk configuration import and export;
- the classic guided entity workflows.

Both interfaces operate on the same configuration. A change made in one is
visible in the other after the integration reloads.
