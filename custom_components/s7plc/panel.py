"""Native Home Assistant panel for managing S7 PLC configuration."""

from __future__ import annotations

import json
from collections.abc import Hashable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import voluptuous as vol
import yaml

from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_BINARY_SENSORS,
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_SCALE,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_COOLING_ACTION_ADDRESS,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVER_STATUS_CLOSED_VALUES,
    CONF_COVER_STATUS_CLOSING_VALUES,
    CONF_COVER_STATUS_OPEN_VALUES,
    CONF_COVER_STATUS_OPENING_VALUES,
    CONF_COVER_STATUS_STOPPED_VALUES,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_SYNC,
    CONF_HEATING_ACTION_ADDRESS,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_HVAC_STATUS_ADDRESS,
    CONF_HVAC_STATUS_COOLING_VALUES,
    CONF_HVAC_STATUS_DEFROSTING_VALUES,
    CONF_HVAC_STATUS_DRYING_VALUES,
    CONF_HVAC_STATUS_FAN_VALUES,
    CONF_HVAC_STATUS_HEATING_VALUES,
    CONF_HVAC_STATUS_IDLE_VALUES,
    CONF_HVAC_STATUS_OFF_VALUES,
    CONF_HVAC_STATUS_PREHEATING_VALUES,
    CONF_INVERT_POSITION,
    CONF_INVERT_STATE,
    CONF_INVERT_TILT,
    CONF_LIGHTS,
    CONF_MAX_TEMP,
    CONF_MAX_VALUE,
    CONF_MIN_TEMP,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_ON_OFF_ADDRESS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_PATTERN,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_PRESET_MODE_ADDRESS,
    CONF_PRESET_MODE_AUTO_VALUE,
    CONF_PRESET_MODE_BIDIRECTIONAL,
    CONF_PRESET_MODE_COOL_VALUE,
    CONF_PRESET_MODE_DRY_VALUE,
    CONF_PRESET_MODE_FAN_ONLY_VALUE,
    CONF_PRESET_MODE_HEAT_COOL_VALUE,
    CONF_PRESET_MODE_HEAT_VALUE,
    CONF_PRESET_MODE_OFF_VALUE,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_REAL_PRECISION,
    CONF_SCALE_RAW_MAX,
    CONF_SCALE_RAW_MIN,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SOURCE_ENTITY,
    CONF_STATE_ADDRESS,
    CONF_STATE_CLASS,
    CONF_STEP,
    CONF_STOP_COMMAND_ADDRESS,
    CONF_STOP_PULSE_DURATION,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONF_TEXTS,
    CONF_TILT_COMMAND_ADDRESS,
    CONF_TILT_STATE_ADDRESS,
    CONF_TOGGLE_MODE,
    CONF_UID,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USE_STATE_TOPICS,
    CONF_VALUE_MULTIPLIER,
    DOMAIN,
    OPTION_KEYS,
)
from .helpers import generate_uid

PANEL_URL = "s7plc-config"
PANEL_DATA = "_panel_registered"


def _integration_version() -> str:
    """Return the integration version declared in the manifest."""
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest["version"]


def _versioned_asset_url(asset_url: str) -> str:
    """Append the integration version to an asset URL for cache busting."""
    return f"{asset_url}?{urlencode({'v': _integration_version()})}"


# Fields every entity type accepts ("name" comes from homeassistant.const,
# imported lazily elsewhere in this module, so the literal is used here).
_COMMON_FIELDS = frozenset({"name", CONF_AREA, CONF_SCAN_INTERVAL, CONF_UID})

_NUMERIC_SCALE_FIELDS = frozenset(
    {
        CONF_VALUE_MULTIPLIER,
        CONF_MIN_VALUE,
        CONF_MAX_VALUE,
        CONF_SCALE_RAW_MIN,
        CONF_SCALE_RAW_MAX,
        CONF_REAL_PRECISION,
    }
)

# Option key → fields the YAML editor may set. Mirrors the per-type FIELDS
# catalog in www/s7plc-panel.js (minus UI-only keys such as cover_mode).
_ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    CONF_SENSORS: _COMMON_FIELDS
    | _NUMERIC_SCALE_FIELDS
    | {
        CONF_ADDRESS,
        CONF_DEVICE_CLASS,
        CONF_UNIT_OF_MEASUREMENT,
        CONF_STATE_CLASS,
    },
    CONF_BINARY_SENSORS: _COMMON_FIELDS
    | {CONF_ADDRESS, CONF_DEVICE_CLASS, CONF_INVERT_STATE},
    # CONF_ADDRESS kept for switches/lights: accepted as a legacy alias of
    # state_address (see config_flow import validation).
    CONF_SWITCHES: _COMMON_FIELDS
    | {
        CONF_ADDRESS,
        CONF_STATE_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_SYNC_STATE,
        CONF_PULSE_COMMAND,
        CONF_PULSE_DURATION,
    },
    CONF_COVERS: _COMMON_FIELDS
    | {
        CONF_OPEN_COMMAND_ADDRESS,
        CONF_CLOSE_COMMAND_ADDRESS,
        CONF_OPENING_STATE_ADDRESS,
        CONF_CLOSING_STATE_ADDRESS,
        CONF_COVER_OPENING_ADDRESS,
        CONF_COVER_CLOSING_ADDRESS,
        CONF_COVER_STOPPED_ADDRESS,
        CONF_COVER_STATUS_ADDRESS,
        CONF_COVER_STATUS_OPEN_VALUES,
        CONF_COVER_STATUS_CLOSED_VALUES,
        CONF_COVER_STATUS_OPENING_VALUES,
        CONF_COVER_STATUS_CLOSING_VALUES,
        CONF_COVER_STATUS_STOPPED_VALUES,
        CONF_POSITION_STATE_ADDRESS,
        CONF_POSITION_COMMAND_ADDRESS,
        CONF_STOP_COMMAND_ADDRESS,
        CONF_STOP_PULSE_DURATION,
        CONF_TILT_STATE_ADDRESS,
        CONF_TILT_COMMAND_ADDRESS,
        CONF_INVERT_TILT,
        CONF_OPERATE_TIME,
        CONF_USE_STATE_TOPICS,
        CONF_TOGGLE_MODE,
        CONF_INVERT_POSITION,
        CONF_DEVICE_CLASS,
    },
    CONF_LIGHTS: _COMMON_FIELDS
    | {
        CONF_ADDRESS,
        CONF_STATE_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_SYNC_STATE,
        CONF_PULSE_COMMAND,
        CONF_PULSE_DURATION,
        CONF_BRIGHTNESS_STATE_ADDRESS,
        CONF_BRIGHTNESS_COMMAND_ADDRESS,
        CONF_BRIGHTNESS_SCALE,
    },
    CONF_BUTTONS: _COMMON_FIELDS | {CONF_ADDRESS, CONF_BUTTON_PULSE},
    CONF_NUMBERS: _COMMON_FIELDS
    | _NUMERIC_SCALE_FIELDS
    | {
        CONF_ADDRESS,
        CONF_COMMAND_ADDRESS,
        CONF_DEVICE_CLASS,
        CONF_UNIT_OF_MEASUREMENT,
        CONF_STEP,
    },
    CONF_TEXTS: _COMMON_FIELDS | {CONF_ADDRESS, CONF_COMMAND_ADDRESS, CONF_PATTERN},
    CONF_CLIMATES: _COMMON_FIELDS
    | {
        CONF_CLIMATE_CONTROL_MODE,
        CONF_CURRENT_TEMPERATURE_ADDRESS,
        CONF_TARGET_TEMPERATURE_ADDRESS,
        CONF_HEATING_OUTPUT_ADDRESS,
        CONF_COOLING_OUTPUT_ADDRESS,
        CONF_HEATING_ACTION_ADDRESS,
        CONF_COOLING_ACTION_ADDRESS,
        CONF_PRESET_MODE_ADDRESS,
        CONF_PRESET_MODE_BIDIRECTIONAL,
        CONF_ON_OFF_ADDRESS,
        CONF_PRESET_MODE_OFF_VALUE,
        CONF_PRESET_MODE_HEAT_VALUE,
        CONF_PRESET_MODE_COOL_VALUE,
        CONF_PRESET_MODE_HEAT_COOL_VALUE,
        CONF_PRESET_MODE_AUTO_VALUE,
        CONF_PRESET_MODE_DRY_VALUE,
        CONF_PRESET_MODE_FAN_ONLY_VALUE,
        CONF_HVAC_STATUS_ADDRESS,
        CONF_HVAC_STATUS_OFF_VALUES,
        CONF_HVAC_STATUS_HEATING_VALUES,
        CONF_HVAC_STATUS_COOLING_VALUES,
        CONF_HVAC_STATUS_IDLE_VALUES,
        CONF_HVAC_STATUS_DRYING_VALUES,
        CONF_HVAC_STATUS_FAN_VALUES,
        CONF_HVAC_STATUS_PREHEATING_VALUES,
        CONF_HVAC_STATUS_DEFROSTING_VALUES,
        CONF_MIN_TEMP,
        CONF_MAX_TEMP,
        CONF_TEMP_STEP,
    },
    CONF_ENTITY_SYNC: _COMMON_FIELDS | {CONF_SOURCE_ENTITY, CONF_ADDRESS},
}


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


def _validate_entity_fields(entity_type: str | None, entity: dict[str, Any]) -> None:
    """Reject unknown fields and missing required fields for *entity_type*."""
    allowed = _ALLOWED_FIELDS.get(entity_type)  # type: ignore[arg-type]
    if allowed is None:
        return
    unknown = sorted(set(entity) - allowed)
    if unknown:
        raise ValueError(f"Unknown field(s) for {entity_type}: {', '.join(unknown)}")
    from .helpers import _item_has_required_fields

    if not _item_has_required_fields(entity_type, entity):
        raise ValueError(f"Missing required field(s) for {entity_type}")
    _validate_address_fields(entity)


def _validate_address_fields(entity: dict[str, Any]) -> None:
    """Ensure every address field contains a parseable S7 address."""
    from .address import parse_tag

    for key in sorted(entity):
        if key != CONF_ADDRESS and not key.endswith("_address"):
            continue
        value = entity[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid address for {key}: {value!r}")
        try:
            parse_tag(value.strip())
        except (RuntimeError, ValueError) as err:
            raise ValueError(f"Invalid address for {key}: {value!r}") from err


def _entity_from_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Return and validate an entity supplied by the visual or YAML editor."""
    if "entity_yaml" not in msg:
        entity = msg.get("entity")
        if not isinstance(entity, dict):
            raise ValueError("Entity configuration must be an object")
        _validate_address_fields(entity)
        return dict(entity)

    try:
        entity = yaml.load(msg["entity_yaml"], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as err:
        raise ValueError(f"Invalid YAML: {err}") from err
    if not isinstance(entity, dict) or not entity:
        raise ValueError("YAML configuration must be a non-empty mapping")
    if not all(isinstance(key, str) for key in entity):
        raise ValueError("YAML configuration keys must be strings")
    _validate_entity_fields(msg.get("entity_type"), entity)
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
    translations_url = "/s7plc_translations"
    translations_path = Path(__file__).parent / "translations"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(asset_url, str(asset_path), cache_headers=False),
            StaticPathConfig(
                translations_url, str(translations_path), cache_headers=False
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
        module_url=_versioned_asset_url(asset_url),
        sidebar_title="S7 PLC",
        sidebar_icon="mdi:memory",
        require_admin=True,
        config={"domain": DOMAIN, "version": _integration_version()},
    )
    hass.data[DOMAIN][PANEL_DATA] = True
