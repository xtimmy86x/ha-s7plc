# Schedule dashboard card

**S7 PLC — Schedule** edits on/off times stored in raw BCD WORD or converted
HHMM entities. Each row contains a name, an on time and an off time, with
separate hour and minute fields. The number of rows is configurable; it is not
limited to twelve.

The card changes the PLC's schedule parameters. The existing PLC program
continues to execute the schedule, including when the dashboard is closed.

## Add the card

1. Install this version of ha-s7plc and restart Home Assistant.
2. Refresh the browser or reload the Companion app frontend.
3. Edit your dashboard, choose **Add card**, and search for **S7 PLC — Schedule**.
4. Add slots and select the on/off number entity for each. Names, order, entity-value display and confirmation timeout
   are configurable.

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

## Add multiple slots with a pairing preview

Open **Add multiple slots** at the bottom of the visual editor. This prepares
new pairs without changing existing rows:

1. Search the on-entity list by name or ID and check the desired entities, or
   use **Select results** to select all matching results. Repeat for off entities.
   The editor's PLC filter and automatic S7 format detection also apply to these lists.
2. Review **Pairing preview**. Initial ordering is natural entity-ID order
   (`1, 2, …, 12`); the first on entity pairs with the first off entity, and so
   on. This is positional pairing, not automatic inference from PLC addresses
   or entity names. Use the arrows in either column to adjust the pairs.
3. Press **Add N slots** to append the previewed pairs. Existing rows, names,
   assignments and per-field formats are preserved. Review the new rows, then
   save the card configuration in Home Assistant.

For twelve pairs, select twelve on entities and twelve off entities. The two
lists must have equal non-zero counts. Entities already used in the card or
selected for the other side are excluded. Missing or newly incompatible
selections remain in the preview with a warning and block additions until
corrected. The final click revalidates the entire selection before appending
any rows.

Searches and PLC filters do not discard selections; **Clear selection** clears
one side. Changing selections sorts that side by entity ID again, so adjust
the preview order after completing selection. Mixed S7 BCD/HHMM numbers are
recognized automatically in both lists and in the preview.

The wizard's selections, searches and preview remain local to the editor.
Only **Add N slots** emits a card configuration change; this workflow never
sends PLC commands and does not copy time values between entities.

## Entity value format

Raw BCD and converted HHMM entities can share one card, including the on/off
fields of the same slot. The card, individual entity pickers and bulk wizard
all detect S7 formats automatically from entity attributes. There are no
card-wide or per-field format selectors.

| Displayed time | HA state: `bcd` | HA state: `hhmm` | PLC BCD WORD |
| --- | ---: | ---: | --- |
| 00:00 | 0 | 0 | `0x0000` |
| 04:00 | 1024 | 400 | `0x0400` |
| 04:30 | 1072 | 430 | `0x0430` |
| 12:45 | 4677 | 1245 | `0x1245` |
| 23:59 | 9049 | 2359 | `0x2359` |

The format is never guessed from a numeric value: `1024` means 04:00 in BCD
mode but 10:24 in HHMM mode.

### Automatic detection

S7 entities with `s7_time_format: hhmm` use HHMM; unconverted writable WORDs
with `s7_raw_word: true` use BCD. Both appear in the same entity picker. Other
S7 conversions remain excluded. Detection uses metadata, never the numeric
value, entity name or numeric limits.

Existing `time_format`, `on_format` and `off_format` settings no longer override
S7 metadata. They can remain in old YAML; no changes are needed for existing
S7 cards to use automatic detection.

For external numbers/helpers without S7 metadata, BCD remains the fallback.
Previously saved format settings are honored only for those external entities
to preserve their existing encoding. The editor retains these old settings when
editing the card but does not offer format controls or generate new settings.
Without metadata or an existing format setting, external HHMM cannot be inferred
reliably from the state alone.

### Raw BCD WORD (`bcd`)

Use `number` entities that expose the **raw decimal WORD**, without any value
conversion. A typical entity configuration has `min_value: 0`,
`max_value: 65535`, and `step: 1`. The card packs and unpacks the BCD digits.
The entity's maximum must be at least 9049 to represent every time of day;
2359 is insufficient for raw BCD.

### Converted HHMM (`hhmm`)

For S7 PLC numbers, enable the **LOGO! time BCD** value conversion in the S7 PLC
configuration panel (`value_conversions.value.type: logo_time_bcd`). The entity
then exposes an integer HHMM in Home Assistant. Default limits are 0–2359 with
step 1. The card displays and sends HHMM; the integration converts between HHMM
and the PLC's BCD WORD. For example, editing 04:30 sends `430` to
`number.set_value`, and the integration writes `0x0430` (decimal 1072) to the PLC.

HHMM represents a clock time, not elapsed minutes. Values such as 1260 or 2399
are invalid, even though they fall within the numeric limits.

### Compatibility and validation

Both formats support separate read and command addresses when both are scalar
WORD channels. S7 numbers expose `s7_raw_word` for unconverted writable WORDs;
LOGO clock numbers additionally expose `s7_time_format: hhmm`. The card uses
these attributes to recognize the format and reject other conversions,
incompatible datatypes, array channels and missing command addresses. This
prevents applying BCD conversion twice. Incompatible entities are excluded from
the editor's choices; existing selections remain visible with a warning.

Other `number` entities and `input_number` helpers are also supported. Their
encoding cannot be verified by ha-s7plc; the fallback and legacy compatibility
rules above apply. An `input_number` helper alone does not write to a PLC.

The card checks entity limits and step in the detected HA value format before
saving. Hours must be 00–23 and minutes 00–59. `00:00` is midnight, not a disabled
slot; `24:00` and special sentinel values such as 65535 are invalid. On/off
ordering is unrestricted to allow overnight schedules.

## Editing and confirmation

On screens up to 600 px wide or devices with a coarse pointer (touch), time
fields have 44 × 44 px touch targets and Save/Cancel buttons are at least 44 px
high. Long tables scroll vertically within the card, up to half the viewport
height (capped at 420 px). Column headings stay visible inside this scrolling
area; the status and Save/Cancel controls remain outside it, below the table.
You can reach the actions without scrolling through all the slots. The card
itself follows normal dashboard scrolling. Wider desktop screens with a mouse
retain the full-height table.

Entering an hour or minute field selects its digits, both by keyboard focus
and on the first tap/click. Type to replace the value directly. Further taps
within the focused field position the cursor normally. Incoming HA updates
preserve the current input and selection while editing.

Changes remain local until **Save changes** is pressed. Only edited times are
sent, through `number.set_value` or `input_number.set_value`. **Cancel** discards
unsaved edits and displays the latest HA states. Unsaved edits do not survive
recreating the card or reloading the page.

Incoming HA updates do not replace fields while typing. If an entity changes
externally during editing, saving its stale value is blocked. Cancel and edit
again using the latest value. This also applies if the detected format changes;
pending writes require feedback in the same format that was sent.
Offline entities are disabled. Invalid BCD/HHMM is
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
S7 formats are detected automatically; no format configuration is needed.
`show_raw` defaults to `false` and displays the HA entity value labelled WORD or
HHMM. `confirmation_timeout` defaults to 15 seconds and accepts 1–300 seconds.

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
- If converted S7 entities are absent from the picker, check the PLC filter
  and that both read/write addresses are scalar WORD channels. Converted S7
  entities require `s7_time_format: hhmm`; update the integration and restart HA
  if it is missing. The format is detected automatically.
- If saving reports a range or step error, adjust the number entity's limits
  and step in the S7 PLC configuration panel.
- If a write is not confirmed, check PLC connectivity and polling interval
  before retrying or increasing the confirmation timeout.
