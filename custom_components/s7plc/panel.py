"""Native Home Assistant panel for managing S7 PLC configuration."""

from __future__ import annotations

import json
from collections.abc import Hashable
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml

from .address import parse_tag
from .config_validation import build_entity_item
from .const import (
    CONF_PLC_FAMILY,
    CONF_UID,
    DOMAIN,
    FRONTEND_MODULE,
    OPTION_KEYS,
    PLC_FAMILY_S7,
    VERSION,
)
from .helpers import generate_uid
from .logo_address import (
    is_logo_address_candidate,
    logo_profile_payload,
    logo_to_s7_address,
)

PANEL_URL = "s7plc-config"
PANEL_DATA = "_panel_registered"
BACKUP_METADATA_KEY = "s7plc"
BACKUP_FORMAT_VERSION = 1
PYS7_VERSION_DATA = "_pys7_version"


class ConfigurationValidationError(ValueError):
    """An entity validation error with a machine-readable location."""

    def __init__(self, entity_type: str, index: int, error_key: str) -> None:
        super().__init__(f"{entity_type}[{index}]: {error_key}")
        self.entity_type = entity_type
        self.index = index
        self.error_key = error_key


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently
    keeping only the last occurrence (yaml.safe_load's default behavior)."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, Hashable):
                continue  # SafeLoader raises its own error for unhashable keys
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _entity_from_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Parse an entity supplied by the visual or YAML editor."""
    if "entity_yaml" not in msg:
        entity = msg.get("entity")
        if not isinstance(entity, dict):
            raise ValueError("Entity configuration must be an object")
        return dict(entity)

    try:
        entity = yaml.load(msg["entity_yaml"], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as err:
        raise ValueError(f"Invalid YAML: {err}") from err
    if not isinstance(entity, dict) or not entity:
        raise ValueError("YAML configuration must be a non-empty mapping")
    if not all(isinstance(key, str) for key in entity):
        raise ValueError("YAML configuration keys must be strings")
    return entity


def _configuration_from_yaml(
    configuration_yaml: str,
    current_options: dict[str, Any],
    target_entry_id: str | None = None,
    plc_family: str = PLC_FAMILY_S7,
) -> dict[str, Any]:
    """Parse and validate a complete entity configuration from YAML."""
    try:
        payload = yaml.load(configuration_yaml, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as err:
        raise ValueError(f"Invalid YAML: {err}") from err
    if not isinstance(payload, dict):
        raise ValueError("YAML configuration must be a mapping")
    if not all(isinstance(key, str) for key in payload):
        raise ValueError("YAML configuration keys must be strings")
    unknown = set(payload) - set(OPTION_KEYS) - {BACKUP_METADATA_KEY}
    if unknown:
        raise ValueError(f"Unknown configuration key: {sorted(unknown)[0]}")

    metadata_present = BACKUP_METADATA_KEY in payload
    metadata = payload.get(BACKUP_METADATA_KEY)
    if metadata_present and not isinstance(metadata, dict):
        raise ValueError(f"{BACKUP_METADATA_KEY} must be a mapping")
    if isinstance(metadata, dict) and "format_version" in metadata:
        format_version = metadata["format_version"]
        if type(format_version) is not int or format_version != BACKUP_FORMAT_VERSION:
            raise ValueError(
                "Unsupported S7 PLC backup format version: "
                f"{format_version!r} (supported: {BACKUP_FORMAT_VERSION})"
            )
    preserve_uids = bool(
        target_entry_id
        and isinstance(metadata, dict)
        and metadata.get("source_entry_id") == target_entry_id
    )

    result = {
        key: value for key, value in current_options.items() if key not in OPTION_KEYS
    }
    used_uids: set[str] = set()
    for entity_type in OPTION_KEYS:
        raw_items = payload.get(entity_type, [])
        if raw_items is None:
            raw_items = []
        if not isinstance(raw_items, list):
            raise ValueError(f"{entity_type} must be a list")
        result[entity_type] = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"{entity_type}[{index}] must be a mapping")
            normalized_item = _canonicalize_logo_addresses(raw_item, plc_family)
            item, errors = build_entity_item(
                entity_type, normalized_item, options=result
            )
            if item is None:
                raise ConfigurationValidationError(
                    entity_type, index, errors.get("base", "invalid_configuration")
                )
            uid = raw_item.get(CONF_UID) if preserve_uids else None
            if not isinstance(uid, str) or not uid or uid in used_uids:
                uid = generate_uid()
                while uid in used_uids:
                    uid = generate_uid()
            item[CONF_UID] = uid
            used_uids.add(uid)
            result[entity_type].append(item)
    return result


def _configuration_yaml(
    options: dict[str, Any], entry_id: str | None = None, title: str | None = None
) -> str:
    """Serialize all editable entity options as readable YAML."""
    payload: dict[str, Any] = {}
    if entry_id is not None:
        payload[BACKUP_METADATA_KEY] = {
            "format_version": BACKUP_FORMAT_VERSION,
            "source_entry_id": entry_id,
            "source_title": title or "",
        }
    payload.update({key: list(options.get(key, [])) for key in OPTION_KEYS})
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


# Option key → Home Assistant entity domain (entity_sync entities are sensors).
_OPTION_DOMAINS = {
    "sensors": "sensor",
    "binary_sensors": "binary_sensor",
    "switches": "switch",
    "covers": "cover",
    "lights": "light",
    "buttons": "button",
    "numbers": "number",
    "selects": "select",
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


def _connection_entity_id(hass: Any, entry: Any) -> str | None:
    """Return the diagnostic connection binary sensor for an entry."""
    from homeassistant.helpers import entity_registry as er

    runtime_data = getattr(entry, "runtime_data", None)
    device_id = getattr(runtime_data, "device_id", None)
    if not device_id:
        return None
    return er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{device_id}:connection"
    )


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
    family = entry.data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7)
    payload = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": dict(entry.data),
        "pys7_version": (
            hass.data.get(DOMAIN, {}).get(PYS7_VERSION_DATA)
            if hass is not None
            else None
        ),
        "connected": bool(coordinator and coordinator.is_connected()),
        "entities": {key: list(entry.options.get(key, [])) for key in OPTION_KEYS},
        "selector_options": _selector_options(),
        "plc_family": family,
        "logo_profile": (
            logo_profile_payload(family) if family != PLC_FAMILY_S7 else None
        ),
    }
    if hass is not None:
        payload["entity_ids"] = _entity_ids_payload(hass, entry)
        payload["connection_entity_id"] = _connection_entity_id(hass, entry)
    return payload


def _canonicalize_logo_addresses(entity: dict[str, Any], family: str) -> dict[str, Any]:
    """Convert symbolic LOGO! values before normal entity validation."""
    if family == PLC_FAMILY_S7:
        return entity
    result = dict(entity)
    for key, value in result.items():
        if not (key == "address" or key.endswith("_address")):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        if is_logo_address_candidate(value, family):
            result[key] = logo_to_s7_address(value, family)
        else:
            # Only unambiguously pyS7 input remains valid advanced/manual input.
            parse_tag(value.strip())
    return result


async def async_setup_panel(hass: Any) -> None:
    """Register the panel, its static asset, and administration commands once."""
    if hass.data.setdefault(DOMAIN, {}).get(PANEL_DATA):
        return

    from homeassistant.components import panel_custom, websocket_api
    from homeassistant.components.http import StaticPathConfig

    hass.data[DOMAIN][PYS7_VERSION_DATA] = await hass.async_add_executor_job(
        package_version, "pys7"
    )

    asset_url = "/s7plc_static/s7plc-panel.js"
    asset_path = Path(__file__).parent / "www" / "s7plc-panel.js"

    banner_url = "/s7plc_static/s7plc-header.png"
    banner_path = Path(__file__).parent / "www" / "s7plc-header.png"

    translations_url = "/s7plc_translations"
    translations_path = Path(__file__).parent / "translations"

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(asset_url, str(asset_path), cache_headers=False),
            StaticPathConfig(banner_url, str(banner_path), cache_headers=False),
            StaticPathConfig(
                translations_url,
                str(translations_path),
                cache_headers=False,
            ),
        ]
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
            vol.Required("type"): "s7plc/config/get_configuration",
            vol.Required("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_get_configuration(hass, connection, msg):
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(
                msg["id"], "entry_not_found", "S7 PLC entry not found"
            )
            return
        connection.send_result(
            msg["id"],
            {
                "configuration_yaml": _configuration_yaml(
                    dict(entry.options), entry.entry_id, entry.title
                )
            },
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
        if index is not None and (index < 0 or index >= len(items)):
            connection.send_error(msg["id"], "invalid_index", "Entity no longer exists")
            return
        try:
            raw_entity = _canonicalize_logo_addresses(
                _entity_from_message(msg),
                entry.data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7),
            )
            item, errors = build_entity_item(
                msg["entity_type"],
                raw_entity,
                options=options,
                skip_idx=index,
            )
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_entity", str(err))
            return
        if item is None:
            message = errors.get("base", str(errors))
            connection.send_error(msg["id"], "invalid_entity", message)
            return
        if index is None:
            # New entity: assign a permanent uid now rather than relying on
            # ensure_item_uids to backfill one at the next reload.
            item[CONF_UID] = generate_uid()
            items.append(item)
        else:
            # Preserve the existing item's uid as a backend guarantee, not
            # an accident of the frontend echoing it back unchanged (the
            # YAML editor lets a user delete that line from the payload).
            item[CONF_UID] = items[index].get(CONF_UID) or generate_uid()
            items[index] = item
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

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "s7plc/config/save_configuration",
            vol.Required("entry_id"): str,
            vol.Required("configuration_yaml"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_configuration(hass, connection, msg):
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(
                msg["id"], "entry_not_found", "S7 PLC entry not found"
            )
            return
        try:
            options = _configuration_from_yaml(
                msg["configuration_yaml"],
                dict(entry.options),
                entry.entry_id,
                entry.data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7),
            )
        except ConfigurationValidationError as err:
            connection.send_error(
                msg["id"],
                "invalid_configuration_entity",
                json.dumps(
                    {
                        "entity_type": err.entity_type,
                        "index": err.index,
                        "error_key": err.error_key,
                    }
                ),
            )
            return
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_configuration", str(err))
            return
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(
            msg["id"],
            {
                "configuration_yaml": _configuration_yaml(
                    options, entry.entry_id, entry.title
                )
            },
        )

    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_save_entity)
    websocket_api.async_register_command(hass, ws_delete_entity)
    websocket_api.async_register_command(hass, ws_save_configuration)
    websocket_api.async_register_command(hass, ws_get_configuration)

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="s7plc-configuration-panel",
        frontend_url_path=PANEL_URL,
        module_url=FRONTEND_MODULE,
        sidebar_title="S7 PLC",
        sidebar_icon="mdi:memory",
        require_admin=True,
        config={
            "domain": DOMAIN,
            "version": VERSION,
        },
    )
    hass.data[DOMAIN][PANEL_DATA] = True
