# Schedule dashboard card

**S7 PLC — Schedule** edits on/off times stored in raw BCD WORD entities. Each
row contains a name, an on time and an off time, with separate hour and minute
fields. The number of rows is configurable; it is not limited to twelve.

The card changes the PLC's schedule parameters. The existing PLC program
continues to execute the schedule, including when the dashboard is closed.

## Add the card

1. Install this version of ha-s7plc and restart Home Assistant.
2. Refresh the browser or reload the Companion app frontend.
3. Edit your dashboard, choose **Add card**, and search for **S7 PLC — Schedule**.
4. In the visual editor, add slots and select the on/off number entity for each.
   Names, order, raw-value display and confirmation timeout are configurable.

The integration automatically serves the module and registers it in Lovelace's
resource collection. With UI-managed resources, it appears in **Settings →
Dashboards → Resources** as `/s7plc_static/s7plc-schedule-card.js` with version
and build query parameters, type **JavaScript Module**. Existing registrations
for this path are updated in place when the integration changes.

There is no file to copy to `www`, no manual resource registration, and no need
to open the S7 PLC administration panel first. The module is also advertised to
Home Assistant's frontend. This provides automatic loading when resources are
managed in YAML; in that mode the integration does not modify the resource list.
The card uses normal HA entity states and service calls, including HA's user
permissions.

English and Italian labels are included. Other frontend languages fall back to
English. Theme colors follow the Home Assistant theme.

## Configure many slots

The visual editor starts with the first slot expanded. Each slot has a
collapsible summary showing its name, selected entities and current decoded
times. Open individual slots or use **Expand all / Collapse all**. New slots
open automatically. Renaming, reordering and HA state updates preserve the
editor's open sections; these preferences are not saved in dashboard YAML.

The on/off fields use Home Assistant's searchable entity picker, displaying
entity IDs alongside names. Already assigned entities are excluded from other
fields to prevent duplicate assignments. Existing missing or incompatible
selections remain visible with a warning so they can be corrected.

When Home Assistant's entity/device registries identify S7 PLC devices, a
**Filter by PLC** field narrows the available choices. **All entities** includes
other compatible numbers and helpers. Filtering does not clear selections from
another PLC and is not saved in the card configuration.

If Home Assistant's picker cannot be loaded, the editor provides a search field
and a standard select for each time. Search matches friendly names and entity
IDs. Typing a search or expanding a slot does not change the card configuration
or send any command to the PLC.

## Entity requirements

Use `number` entities that expose the **raw decimal WORD**, without any value
conversion. A typical entity configuration has `min_value: 0`,
`max_value: 65535`, and `step: 1`. A separate command address is supported when
both the read and write addresses are scalar WORD channels.

The HA state is not decimal HHMM and is not elapsed time:

| Displayed time | Packed BCD WORD | Decimal entity state |
| --- | --- | ---: |
| 00:00 | `0x0000` | 0 |
| 04:00 | `0x0400` | 1024 |
| 04:30 | `0x0430` | 1072 |
| 12:45 | `0x1245` | 4677 |
| 23:59 | `0x2359` | 9049 |

The entity's maximum must be at least 9049 to represent every time of day;
2359 is insufficient. The card checks configured limits and step before saving.
It accepts hours 00–23 and minutes 00–59. `00:00` is midnight, not a disabled
slot; `24:00` and special sentinel values such as 65535 are not valid times.
On/off ordering is unrestricted to allow overnight schedules.

S7 number entities expose `s7_raw_word` to let the card reject incompatible
datatypes, array channels, missing command addresses and configured conversions.
Those entities are excluded from the editor's choices. An existing incompatible
selection is retained and flagged so it can be corrected.

Other `number` entities and `input_number` helpers are also supported. Their
underlying encoding cannot be verified by ha-s7plc; ensure they hold raw WORDs.
An `input_number` helper alone does not write to a PLC.

## Editing and confirmation

Changes remain local until **Save changes** is pressed. Only edited times are
sent, through `number.set_value` or `input_number.set_value`. **Cancel** discards
unsaved edits and displays the latest HA states. Unsaved edits do not survive
recreating the card or reloading the page.

Incoming HA updates do not replace fields while typing. If an entity changes
externally during editing, saving its stale value is blocked. Cancel and edit
again using the latest value. Offline entities are disabled. Invalid BCD is
reported explicitly and can be replaced with a valid time when the entity is
available and compatible.

After a successful service call, the card waits for the corresponding entity
state. Set `confirmation_timeout` above the entity's polling interval. If the
state is not confirmed, the edit is retained with a warning; no automatic retry
is performed. HA confirmation depends on the integration's state reporting and
is not an independent verification of PLC memory.

Multiple edits use sequential service calls, not an atomic PLC transaction.
Some writes can succeed while others fail. Confirmed edits are cleared; failed
edits remain visible for correction or retry. Cancel cannot undo writes already
sent to the PLC.

## YAML configuration

```yaml
type: custom:s7plc-schedule-card
title: Programmazione oraria
show_raw: false
confirmation_timeout: 15
rows:
  - name: Fascia 01
    on_entity: number.ora_accensione_01
    off_entity: number.ora_spegnimento_01
  - name: Fascia 02
    on_entity: number.ora_accensione_02
    off_entity: number.ora_spegnimento_02
```

Append more rows or use the visual editor. Entity IDs must be distinct across
the card. `title` is optional and otherwise follows the frontend language.
`show_raw` defaults to `false`; `confirmation_timeout` defaults to 15 seconds
and accepts 1–300 seconds.

## Moving from the standalone BCD card

The standalone `custom:bcd-schedule-card` and bundled
`custom:s7plc-schedule-card` have different names and can coexist.

To migrate an existing card, keep its configuration and change only `type` to
`custom:s7plc-schedule-card`. The existing `rows`, names, entity IDs, `show_raw`
and timeout remain supported. Remove the old `/local/bcd-schedule-card.js`
resource only after no dashboard uses the standalone card anymore.

## Troubleshooting

- If the card is not listed, confirm that the installed integration contains
  `frontend.py` and `www/s7plc-schedule-card.js`, then restart Home Assistant and
  refresh the frontend. Reloading just the PLC entry does not install new code.
- With UI-managed resources, check **Settings → Dashboards → Resources** for
  `/s7plc_static/s7plc-schedule-card.js` with version/build query parameters and
  type **JavaScript Module**. Enable advanced mode in your profile if the
  Resources menu is hidden. Early preview builds used only an extra frontend
  module and did not appear in this list; update to the current branch.
- Open `/s7plc_static/s7plc-schedule-card.js` on the same Home Assistant host.
  It must return JavaScript beginning with `S7 PLC Schedule Card`, not a 404 or
  the HA page. If it does not, check the installation and S7 PLC startup logs.
- For YAML-managed resources, if a cached frontend still misses the extra
  module, add the URL as a `module` under `lovelace.resources` in
  `configuration.yaml`, reload resources and refresh. Use the versioned URL
  from `SCHEDULE_CARD_MODULE` in `frontend.py` for consistent cache invalidation.
- If a selected S7 entity is incompatible, use scalar WORD read/write addresses
  and remove its value conversion. The card performs the BCD conversion itself.
- If saving reports a range or step error, adjust the number entity's limits
  and step in the S7 PLC configuration panel.
- If a write is not confirmed, check PLC connectivity and polling interval
  before retrying or increasing the confirmation timeout.
