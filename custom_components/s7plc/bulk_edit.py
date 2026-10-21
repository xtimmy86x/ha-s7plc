"""Prepare an atomic area/polling patch and bind its preview to the config."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .config_validation import EntityConfigBuilder
from .const import CONF_UID, DEFAULT_SCAN_INTERVAL, OPTION_KEYS

BULK_EDIT_FIELDS = frozenset({"area", "scan_interval"})
# Match the panel: these platforms are driven by commands or HA events.
SCAN_ENTITY_TYPES = frozenset(OPTION_KEYS) - {"buttons", "entity_sync"}


def prepare_bulk_edit(entry, targets: list[dict], changes: dict) -> tuple[dict, dict]:
    """Return a new options mapping and preview without touching the entry.

    Patch only the requested fields. Rebuilding an entire item would normalize
    unrelated legacy settings and could introduce changes absent from the preview.
    """
    if not changes or not changes.keys() <= BULK_EDIT_FIELDS:
        raise ValueError("invalid_bulk_changes")
    changes = dict(changes)
    area = changes.get("area")
    if area is not None and (not isinstance(area, str) or not area.strip()):
        raise ValueError("invalid_bulk_area")
    interval = changes.get("scan_interval")
    if interval is not None:
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not math.isfinite(interval)
            or not EntityConfigBuilder._MIN_ITEM_SCAN_INTERVAL
            <= interval
            <= EntityConfigBuilder._MAX_ITEM_SCAN_INTERVAL
        ):
            raise ValueError("invalid_bulk_scan_interval")
        changes["scan_interval"] = float(interval)
    if not targets:
        raise ValueError("invalid_selection")

    options = dict(entry.options)
    selected = set()
    lookups = {}
    rows: list[dict[str, Any]] = []
    for target in targets:
        entity_type, uid = target["entity_type"], target["uid"]
        identity = (entity_type, uid)
        if entity_type not in OPTION_KEYS or not uid or identity in selected:
            raise ValueError("invalid_selection")
        selected.add(identity)
        if entity_type not in lookups:
            options[entity_type] = list(options.get(entity_type, []))
            lookup = lookups[entity_type] = {}
            for index, item in enumerate(options[entity_type]):
                key = item.get(CONF_UID)
                lookup[key] = None if key in lookup else index
        items = options[entity_type]
        index = lookups[entity_type].get(uid)
        if index is None:
            raise ValueError("invalid_selection")
        old = items[index]
        new = dict(old)
        scan_supported = entity_type in SCAN_ENTITY_TYPES
        for field, value in changes.items():
            if field == "scan_interval" and not scan_supported:
                continue
            if value is None:
                new.pop(field, None)
            else:
                new[field] = value
        rows.append(
            {
                **target,
                "name": old.get("name"),
                "address": next(
                    (
                        old[key]
                        for key in (
                            "address",
                            "state_address",
                            "position_state_address",
                            "open_command_address",
                            "current_temperature_address",
                            "start_address",
                        )
                        if old.get(key)
                    ),
                    None,
                ),
                "before": {field: old.get(field) for field in changes},
                "after": {field: new.get(field) for field in changes},
                "scan_supported": scan_supported,
                "changed": old != new,
            }
        )
        items[index] = new

    # Bind the token to this entry, the complete config and the exact operation.
    # Any concurrent edit requires a fresh preview; no server token store needed.
    snapshot = {
        "entry_id": entry.entry_id,
        "data": dict(entry.data),
        "options": dict(entry.options),
        "targets": targets,
        "changes": changes,
    }
    token = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return options, {
        "preview_token": token,
        "rows": rows,
        "changed_count": sum(row["changed"] for row in rows),
        "default_scan_interval": entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
    }
