"""Native Home Assistant panel for managing S7 PLC configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml

from .const import CONF_UID, DOMAIN, OPTION_KEYS

PANEL_URL = "s7plc-config"
PANEL_DATA = "_panel_registered"


def _entity_from_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Return and validate an entity supplied by the visual or YAML editor."""
    if "entity_yaml" not in msg:
        entity = msg.get("entity")
        if not isinstance(entity, dict):
            raise ValueError("Entity configuration must be an object")
        return dict(entity)

    try:
        entity = yaml.safe_load(msg["entity_yaml"])
    except yaml.YAMLError as err:
        raise ValueError(f"Invalid YAML: {err}") from err
    if not isinstance(entity, dict) or not entity:
        raise ValueError("YAML configuration must be a non-empty mapping")
    if not all(isinstance(key, str) for key in entity):
        raise ValueError("YAML configuration keys must be strings")
    return entity


# Option key → Home Assistant entity domain (entity_sync entities are sensors).
_OPTION_DOMAINS = {
    "sensors": "sensor",
    "binary_sensors": "binary_sensor",
    "switches": "switch",
    "covers": "cover",
    "lights": "light",
    "buttons": "button",
    "numbers": "number",
    "texts": "text",
    "climates": "climate",
    "entity_sync": "sensor",
}


def _entity_ids_payload(hass: Any, entry: Any) -> dict[str, list[str | None]]:
    """Map every configured item to its Home Assistant entity_id (or None).

    ``uid`` is already the complete unique_id (see helpers.CONF_UID), so no
    device_id concatenation is needed here. Items without a uid yet (not
    backfilled by ``ensure_item_uids`` because setup hasn't run) are simply
    skipped by ``_iter_entity_unique_ids`` and resolve to ``None`` below.
    """
    from homeassistant.helpers import entity_registry as er

    from .helpers import _iter_entity_unique_ids

    registry = er.async_get(hass)
    uid_by_item = {
        id(item): uid for uid, item in _iter_entity_unique_ids(entry.options)
    }
    payload: dict[str, list[str | None]] = {}
    for key in OPTION_KEYS:
        domain = _OPTION_DOMAINS.get(key, "sensor")
        ids: list[str | None] = []
        for item in entry.options.get(key, []):
            uid = uid_by_item.get(id(item))
            ids.append(
                registry.async_get_entity_id(domain, DOMAIN, uid) if uid else None
            )
        payload[key] = ids
    return payload


def _selector_options() -> dict[str, Any]:
    """Return device/state class choices used by the panel dropdowns.

    The values are shared with the options flow (see helpers) so both
    editors always offer the same choices.
    """
    from .helpers import DEVICE_CLASS_ENUMS, STATE_CLASS_VALUES, device_class_values

    return {
        "device_classes": {
            entity_type: device_class_values(entity_type)
            for entity_type in DEVICE_CLASS_ENUMS
        },
        "state_classes": list(STATE_CLASS_VALUES),
    }


def _entry_payload(entry: Any, hass: Any = None) -> dict[str, Any]:
    """Return the editable portion of a config entry."""
    runtime_data = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime_data, "coordinator", None)
    payload = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": dict(entry.data),
        "connected": bool(coordinator and coordinator.is_connected()),
        "entities": {key: list(entry.options.get(key, [])) for key in OPTION_KEYS},
        "selector_options": _selector_options(),
    }
    if hass is not None:
        payload["entity_ids"] = _entity_ids_payload(hass, entry)
    return payload


async def async_setup_panel(hass: Any) -> None:
    """Register the panel, its static asset, and administration commands once."""
    if hass.data.setdefault(DOMAIN, {}).get(PANEL_DATA):
        return

    from homeassistant.components import panel_custom, websocket_api
    from homeassistant.components.http import StaticPathConfig

    asset_url = "/s7plc_static/s7plc-panel.js"
    asset_path = Path(__file__).parent / "www" / "s7plc-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(asset_url, str(asset_path), cache_headers=False)]
    )

    @websocket_api.websocket_command({vol.Required("type"): "s7plc/config/list"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_list(hass, connection, msg):
        connection.send_result(
            msg["id"],
            [
                _entry_payload(entry, hass)
                for entry in hass.config_entries.async_entries(DOMAIN)
            ],
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "s7plc/config/save_entity",
            vol.Required("entry_id"): str,
            vol.Required("entity_type"): vol.In(OPTION_KEYS),
            vol.Optional("index"): vol.Any(None, int),
            vol.Optional("entity"): dict,
            vol.Optional("entity_yaml"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_entity(hass, connection, msg):
        from .helpers import generate_uid

        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(
                msg["id"], "entry_not_found", "S7 PLC entry not found"
            )
            return
        options = dict(entry.options)
        items = list(options.get(msg["entity_type"], []))
        index = msg.get("index")
        try:
            entity = _entity_from_message(msg)
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_entity", str(err))
            return
        if index is None:
            # New entity: assign a permanent uid now rather than relying on
            # ensure_item_uids to backfill one at the next reload.
            entity[CONF_UID] = generate_uid()
            items.append(entity)
        elif index < 0 or index >= len(items):
            connection.send_error(msg["id"], "invalid_index", "Entity no longer exists")
            return
        else:
            # Preserve the existing item's uid as a backend guarantee, not
            # an accident of the frontend echoing it back unchanged (the
            # YAML editor lets a user delete that line from the payload).
            entity[CONF_UID] = items[index].get(CONF_UID) or generate_uid()
            items[index] = entity
        options[msg["entity_type"]] = items
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"entities": items})

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "s7plc/config/delete_entity",
            vol.Required("entry_id"): str,
            vol.Required("entity_type"): vol.In(OPTION_KEYS),
            vol.Required("index"): int,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_entity(hass, connection, msg):
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(
                msg["id"], "entry_not_found", "S7 PLC entry not found"
            )
            return
        options = dict(entry.options)
        items = list(options.get(msg["entity_type"], []))
        index = msg["index"]
        if index < 0 or index >= len(items):
            connection.send_error(msg["id"], "invalid_index", "Entity no longer exists")
            return
        items.pop(index)
        options[msg["entity_type"]] = items
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"entities": items})

    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_save_entity)
    websocket_api.async_register_command(hass, ws_delete_entity)

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="s7plc-configuration-panel",
        frontend_url_path=PANEL_URL,
        module_url=asset_url,
        sidebar_title="S7 PLC",
        sidebar_icon="mdi:memory",
        require_admin=True,
        config={"domain": DOMAIN},
    )
    hass.data[DOMAIN][PANEL_DATA] = True
