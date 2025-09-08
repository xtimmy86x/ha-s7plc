from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_BINARY_SENSORS,
    CONF_HOST,
    CONF_LIGHTS,
    CONF_NAME,
    CONF_PORT,
    CONF_RACK,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_SWITCHES,
    DEFAULT_PORT,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)


class S7PLCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for S7 PLC."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            rack = user_input.get(CONF_RACK, DEFAULT_RACK)
            slot = user_input.get(CONF_SLOT, DEFAULT_SLOT)
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            scan_s = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            name = user_input.get(CONF_NAME, "S7 PLC")

            coordinator = S7Coordinator(
                self.hass,
                host=host,
                rack=rack,
                slot=slot,
                port=port,
                scan_interval=scan_s,
            )
            try:
                await self.hass.async_add_executor_job(coordinator.connect)
                await self.hass.async_add_executor_job(coordinator.disconnect)
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "cannot_connect"
            else:
                unique_id = f"{host}-{rack}-{slot}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_RACK, default=DEFAULT_RACK): int,
                vol.Optional(CONF_SLOT, default=DEFAULT_SLOT): int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return S7PLCOptionsFlow(config_entry)


def _dump_list(value: list[dict[str, Any]]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_list(value: str) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning("Invalid JSON list provided: %s", value)
    return []


class S7PLCOptionsFlow(config_entries.OptionsFlow):
    """Handle options for S7 PLC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            options = {
                CONF_SENSORS: _parse_list(user_input.get(CONF_SENSORS, "")),
                CONF_BINARY_SENSORS: _parse_list(
                    user_input.get(CONF_BINARY_SENSORS, "")
                ),
                CONF_SWITCHES: _parse_list(user_input.get(CONF_SWITCHES, "")),
                CONF_LIGHTS: _parse_list(user_input.get(CONF_LIGHTS, "")),
            }
            return self.async_create_entry(title="", data=options)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SENSORS,
                    default=_dump_list(
                        self._config_entry.options.get(CONF_SENSORS, [])
                    ),
                ): str,
                vol.Optional(
                    CONF_BINARY_SENSORS,
                    default=_dump_list(
                        self._config_entry.options.get(CONF_BINARY_SENSORS, [])
                    ),
                ): str,
                vol.Optional(
                    CONF_SWITCHES,
                    default=_dump_list(
                        self._config_entry.options.get(CONF_SWITCHES, [])
                    ),
                ): str,
                vol.Optional(
                    CONF_LIGHTS,
                    default=_dump_list(self._config_entry.options.get(CONF_LIGHTS, [])),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
