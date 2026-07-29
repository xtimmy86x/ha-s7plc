"""Native Home Assistant panel for managing S7 PLC configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml

from .const import DOMAIN, OPTION_KEYS

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


def _entry_payload(entry: Any) -> dict[str, Any]:
    """Return the editable portion of a config entry."""
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": dict(entry.data),
        "entities": {key: list(entry.options.get(key, [])) for key in OPTION_KEYS},
    }


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
                _entry_payload(entry)
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
            items.append(entity)
        elif index < 0 or index >= len(items):
            connection.send_error(msg["id"], "invalid_index", "Entity no longer exists")
            return
        else:
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
