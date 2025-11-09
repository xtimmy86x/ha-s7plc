from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import math
from ipaddress import ip_interface, ip_network
from typing import Any, Dict, List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .address import get_numeric_limits, parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_BACKOFF_INITIAL,
    CONF_BACKOFF_MAX,
    CONF_BINARY_SENSORS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    CONF_COMMAND_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_LIGHTS,
    CONF_MAX_RETRIES,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_OP_TIMEOUT,
    CONF_RACK,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_STATE_ADDRESS,
    CONF_STEP,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    CONF_VALUE_MULTIPLIER,
    DEFAULT_BACKOFF_INITIAL,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_BUTTON_PULSE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_OP_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
    OPTION_KEYS,
)
from .coordinator import S7Coordinator
from .export import build_export_json, build_export_payload, register_export_download

_LOGGER = logging.getLogger(__name__)

bs_device_class_options = [
    selector.SelectOptionDict(value=dc.value, label=dc.value)
    for dc in BinarySensorDeviceClass
]

s_device_class_options = [
    selector.SelectOptionDict(value=dc.value, label=dc.value)
    for dc in SensorDeviceClass
]

scan_interval_selector = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0.05,
        max=3600,
        mode=selector.NumberSelectorMode.BOX,
    )
)

value_multiplier_selector = selector.NumberSelector(
    selector.NumberSelectorConfig(
        mode=selector.NumberSelectorMode.BOX,
    )
)


ADD_ENTITY_STEP_IDS: tuple[str, ...] = (
    "sensors",
    "binary_sensors",
    "switches",
    "buttons",
    "lights",
    "numbers",
)

ADD_ENTITY_LABELS: dict[str, str] = {
    "sensors": "Sensor",
    "binary_sensors": "Binary sensor",
    "switches": "Switch",
    "buttons": "Button",
    "lights": "Light",
    "numbers": "Number",
}

ADD_ENTITY_SELECT_OPTIONS = [
    selector.SelectOptionDict(value=step_id, label=ADD_ENTITY_LABELS[step_id])
    for step_id in ADD_ENTITY_STEP_IDS
]

add_item_selector = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=ADD_ENTITY_SELECT_OPTIONS,
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


class S7PLCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for S7 PLC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""

        self._discovered_hosts: list[str] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        discovered_hosts = await self._async_get_discovered_hosts()

        host_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=host, label=host)
                    for host in discovered_hosts
                ],
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): host_selector,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_RACK, default=DEFAULT_RACK): int,
                vol.Optional(CONF_SLOT, default=DEFAULT_SLOT): int,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=3600)),
                vol.Optional(CONF_OP_TIMEOUT, default=DEFAULT_OP_TIMEOUT): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=120)
                ),
                vol.Optional(CONF_MAX_RETRIES, default=DEFAULT_MAX_RETRIES): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10)
                ),
                vol.Optional(
                    CONF_BACKOFF_INITIAL, default=DEFAULT_BACKOFF_INITIAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=30)),
                vol.Optional(CONF_BACKOFF_MAX, default=DEFAULT_BACKOFF_MAX): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=120)
                ),
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=data_schema,
                description_placeholders={
                    "default_port": str(DEFAULT_PORT),
                    "default_rack": str(DEFAULT_RACK),
                    "default_slot": str(DEFAULT_SLOT),
                    "default_scan": str(DEFAULT_SCAN_INTERVAL),
                    "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
                    "default_retries": str(DEFAULT_MAX_RETRIES),
                    "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
                    "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
                },
                errors=errors,
            )

        try:
            host = user_input[CONF_HOST]
            rack = int(user_input.get(CONF_RACK, DEFAULT_RACK))
            slot = int(user_input.get(CONF_SLOT, DEFAULT_SLOT))
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            scan_s = float(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            op_timeout = float(user_input.get(CONF_OP_TIMEOUT, DEFAULT_OP_TIMEOUT))
            max_retries = int(user_input.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES))
            backoff_initial = float(
                user_input.get(CONF_BACKOFF_INITIAL, DEFAULT_BACKOFF_INITIAL)
            )
            backoff_max = float(user_input.get(CONF_BACKOFF_MAX, DEFAULT_BACKOFF_MAX))
            name = user_input.get(CONF_NAME, "S7 PLC")
        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user", data_schema=data_schema, errors=errors
            )

        if scan_s <= 0:
            scan_s = DEFAULT_SCAN_INTERVAL

        if op_timeout <= 0:
            op_timeout = DEFAULT_OP_TIMEOUT

        if max_retries < 0:
            max_retries = DEFAULT_MAX_RETRIES

        if backoff_initial <= 0:
            backoff_initial = DEFAULT_BACKOFF_INITIAL

        if backoff_max < backoff_initial:
            backoff_max = max(backoff_initial, backoff_max)

        unique_id = f"{host}-{rack}-{slot}"
        await self.async_set_unique_id(unique_id, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        coordinator = S7Coordinator(
            self.hass,
            host=host,
            rack=rack,
            slot=slot,
            port=port,
            scan_interval=scan_s,
            op_timeout=op_timeout,
            max_retries=max_retries,
            backoff_initial=backoff_initial,
            backoff_max=backoff_max,
        )
        try:
            await self.hass.async_add_executor_job(coordinator.connect)
            await self.hass.async_add_executor_job(coordinator.disconnect)
        except (OSError, RuntimeError):
            _LOGGER.warning(
                "Cannot connect to S7 PLC at %s (rack %s slot %s)", host, rack, slot
            )
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user", data_schema=data_schema, errors=errors
            )

        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_RACK: rack,
                CONF_SLOT: slot,
                CONF_SCAN_INTERVAL: scan_s,
                CONF_OP_TIMEOUT: op_timeout,
                CONF_MAX_RETRIES: max_retries,
                CONF_BACKOFF_INITIAL: backoff_initial,
                CONF_BACKOFF_MAX: backoff_max,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return S7PLCOptionsFlow(config_entry)

    async def _async_get_discovered_hosts(self) -> list[str]:
        """Return cached or freshly discovered PLC hosts on the local network."""

        if self._discovered_hosts is not None:
            return self._discovered_hosts

        hosts_to_scan: list[str] = []
        adapters = await network.async_get_adapters(self.hass)

        for adapter in adapters:
            if not adapter.get("enabled", False):
                continue

            for ip_info in adapter.get("ipv4", []):
                address = ip_info.get("address")
                prefix = ip_info.get("network_prefix")

                if not address or prefix is None:
                    continue

                try:
                    interface = ip_interface(f"{address}/{prefix}")
                except ValueError:
                    continue

                if interface.ip.is_loopback:
                    continue

                network_obj = interface.network

                # Avoid scanning excessively large networks; narrow to /24 when needed.
                if network_obj.num_addresses > 1024:
                    try:
                        network_obj = ip_network(f"{interface.ip}/24", strict=False)
                    except ValueError:
                        continue

                for host in network_obj.hosts():
                    if host == interface.ip:
                        continue

                    host_str = str(host)
                    if host_str in hosts_to_scan:
                        continue

                    hosts_to_scan.append(host_str)

                    if len(hosts_to_scan) >= 256:
                        break

                if len(hosts_to_scan) >= 256:
                    break

            if len(hosts_to_scan) >= 256:
                break

        discovered: list[str] = []
        semaphore = asyncio.Semaphore(32)

        async def _probe(host: str) -> None:
            try:
                async with semaphore:
                    _reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, DEFAULT_PORT),
                        timeout=0.5,
                    )
            except (asyncio.TimeoutError, OSError):
                return
            except asyncio.CancelledError:
                raise
            else:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                discovered.append(host)

        await asyncio.gather(*(_probe(host) for host in hosts_to_scan))

        discovered.sort()
        self._discovered_hosts = discovered
        if discovered:
            _LOGGER.debug("Discovered potential S7 PLC hosts: %s", discovered)

        return discovered


class S7PLCOptionsFlow(config_entries.OptionsFlow):
    """Handle options for S7 PLC."""

    _MIN_ITEM_SCAN_INTERVAL = 0.05
    _MAX_ITEM_SCAN_INTERVAL = 3600.0

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._options = {
            CONF_SENSORS: list(config_entry.options.get(CONF_SENSORS, [])),
            CONF_BINARY_SENSORS: list(
                config_entry.options.get(CONF_BINARY_SENSORS, [])
            ),
            CONF_SWITCHES: list(config_entry.options.get(CONF_SWITCHES, [])),
            CONF_LIGHTS: list(config_entry.options.get(CONF_LIGHTS, [])),
            CONF_BUTTONS: list(config_entry.options.get(CONF_BUTTONS, [])),
            CONF_NUMBERS: list(config_entry.options.get(CONF_NUMBERS, [])),
        }
        self._action: str | None = None  # "add" | "remove" | "edit"
        self._edit_target: tuple[str, int] | None = None

    @staticmethod
    def _sanitize_address(address: Any | None) -> str | None:
        """Return a trimmed string representation of an address."""

        if address is None:
            return None

        if not isinstance(address, str):
            address = str(address)

        address = address.strip()
        return address or None

    @staticmethod
    def _normalized_address(address: Any | None) -> str | None:
        """Return a normalized representation used for comparisons."""

        sanitized = S7PLCOptionsFlow._sanitize_address(address)
        if sanitized is None:
            return None

        return sanitized.upper()

    @staticmethod
    def _normalize_scan_interval_value(value: Any | None) -> float | None:
        if value in (None, ""):
            return None
        try:
            interval = float(value)
        except (TypeError, ValueError):
            return None
        if interval <= 0:
            return None
        return min(
            max(interval, S7PLCOptionsFlow._MIN_ITEM_SCAN_INTERVAL),
            S7PLCOptionsFlow._MAX_ITEM_SCAN_INTERVAL,
        )

    @staticmethod
    def _apply_scan_interval(item: dict[str, Any], value: Any | None) -> None:
        normalized = S7PLCOptionsFlow._normalize_scan_interval_value(value)
        if normalized is None:
            item.pop(CONF_SCAN_INTERVAL, None)
        else:
            item[CONF_SCAN_INTERVAL] = normalized

    @staticmethod
    def _normalize_value_multiplier(value: Any | None) -> float | None:
        if value in (None, ""):
            return None

        candidate = value
        if isinstance(candidate, str):
            candidate = candidate.strip()
            if not candidate:
                return None
            candidate = candidate.replace(",", ".")

        try:
            multiplier = float(candidate)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid multiplier") from exc

        if not math.isfinite(multiplier):
            raise ValueError("invalid multiplier")

        return multiplier

    @staticmethod
    def _apply_value_multiplier(item: dict[str, Any], value: Any | None) -> None:
        normalized = S7PLCOptionsFlow._normalize_value_multiplier(value)
        if normalized is None:
            item.pop(CONF_VALUE_MULTIPLIER, None)
        else:
            item[CONF_VALUE_MULTIPLIER] = normalized

    def _has_duplicate(
        self,
        option_key: str,
        address: str,
        *,
        keys: tuple[str, ...] = (CONF_ADDRESS,),
        skip_idx: int | None = None,
    ) -> bool:
        """Return ``True`` if ``address`` already exists in the options."""

        normalized = self._normalized_address(address)
        if normalized is None:
            return False

        for idx, item in enumerate(self._options.get(option_key, [])):
            if skip_idx is not None and idx == skip_idx:
                continue
            for key in keys:
                if self._normalized_address(item.get(key)) == normalized:
                    return True

        return False

    @staticmethod
    def _labelize(prefix: str, item: dict[str, Any]) -> str:
        name = item.get(CONF_NAME)
        address = item.get(CONF_ADDRESS) or item.get(CONF_STATE_ADDRESS) or "?"
        type_label = {
            "s": "Sensor",
            "bs": "Binary",
            "sw": "Switch",
            "bt": "Button",
            "lt": "Light",
            "nm": "Number",
        }[prefix]
        base = name or address
        return f"{type_label} • {base} [{address}]"

    def _build_items_map(self) -> Dict[str, str]:
        items: Dict[str, str] = {}
        for i, it in enumerate(self._options.get(CONF_SENSORS, [])):
            items[f"s:{i}"] = self._labelize("s", it)
        for i, it in enumerate(self._options.get(CONF_BINARY_SENSORS, [])):
            items[f"bs:{i}"] = self._labelize("bs", it)
        for i, it in enumerate(self._options.get(CONF_SWITCHES, [])):
            switch_item = {**it}
            switch_item.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"sw:{i}"] = self._labelize("sw", switch_item)
        for i, it in enumerate(self._options.get(CONF_BUTTONS, [])):
            items[f"bt:{i}"] = self._labelize("bt", it)
        for i, it in enumerate(self._options.get(CONF_LIGHTS, [])):
            light_item = {**it}
            light_item.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"lt:{i}"] = self._labelize("lt", light_item)
        for i, it in enumerate(self._options.get(CONF_NUMBERS, [])):
            number_item = {**it}
            number_item.setdefault(CONF_COMMAND_ADDRESS, it.get(CONF_ADDRESS))
            items[f"nm:{i}"] = self._labelize("nm", number_item)
        return items

    def _exportable_options(self) -> dict[str, list[dict[str, Any]]]:
        return build_export_payload(self._options)

    def _build_export_data(self) -> str:
        return build_export_json(self._options)

    def _sanitize_import_payload(
        self, payload: Any
    ) -> dict[str, list[dict[str, Any]]] | None:
        if not isinstance(payload, dict):
            return None

        sanitized: dict[str, list[dict[str, Any]]] = {}
        for key in OPTION_KEYS:
            raw_items = payload.get(key, [])
            if raw_items is None:
                raw_items = []
            if not isinstance(raw_items, list):
                return None
            sanitized[key] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    return None
                sanitized[key].append(dict(item))

        # Preserve any other option keys currently in use to avoid losing data.
        for key, value in self._options.items():
            if key not in sanitized:
                if isinstance(value, list):
                    sanitized[key] = [
                        dict(item) if isinstance(item, dict) else item for item in value
                    ]
                else:
                    sanitized[key] = value

        return sanitized

    def _clear_edit_state(self) -> None:
        self._action = None
        self._edit_target = None

    async def async_step_connection(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data = self._config_entry.data
        defaults = {
            CONF_NAME: data.get(CONF_NAME) or self._config_entry.title or "S7 PLC",
            CONF_HOST: data.get(CONF_HOST, ""),
            CONF_PORT: int(data.get(CONF_PORT, DEFAULT_PORT)),
            CONF_RACK: int(data.get(CONF_RACK, DEFAULT_RACK)),
            CONF_SLOT: int(data.get(CONF_SLOT, DEFAULT_SLOT)),
            CONF_SCAN_INTERVAL: float(
                data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            CONF_OP_TIMEOUT: float(data.get(CONF_OP_TIMEOUT, DEFAULT_OP_TIMEOUT)),
            CONF_MAX_RETRIES: int(data.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)),
            CONF_BACKOFF_INITIAL: float(
                data.get(CONF_BACKOFF_INITIAL, DEFAULT_BACKOFF_INITIAL)
            ),
            CONF_BACKOFF_MAX: float(data.get(CONF_BACKOFF_MAX, DEFAULT_BACKOFF_MAX)),
        }

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
                vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
                vol.Optional(CONF_PORT, default=defaults[CONF_PORT]): int,
                vol.Optional(CONF_RACK, default=defaults[CONF_RACK]): int,
                vol.Optional(CONF_SLOT, default=defaults[CONF_SLOT]): int,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=3600)),
                vol.Optional(
                    CONF_OP_TIMEOUT, default=defaults[CONF_OP_TIMEOUT]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=120)),
                vol.Optional(
                    CONF_MAX_RETRIES, default=defaults[CONF_MAX_RETRIES]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Optional(
                    CONF_BACKOFF_INITIAL, default=defaults[CONF_BACKOFF_INITIAL]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=30)),
                vol.Optional(
                    CONF_BACKOFF_MAX, default=defaults[CONF_BACKOFF_MAX]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=120)),
            }
        )

        description_placeholders = {
            "default_port": str(DEFAULT_PORT),
            "default_rack": str(DEFAULT_RACK),
            "default_slot": str(DEFAULT_SLOT),
            "default_scan": str(DEFAULT_SCAN_INTERVAL),
            "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
            "default_retries": str(DEFAULT_MAX_RETRIES),
            "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
            "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
        }

        if user_input is None:
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                description_placeholders=description_placeholders,
            )

        try:
            host = str(user_input[CONF_HOST]).strip()
            rack = int(user_input.get(CONF_RACK, defaults[CONF_RACK]))
            slot = int(user_input.get(CONF_SLOT, defaults[CONF_SLOT]))
            port = int(user_input.get(CONF_PORT, defaults[CONF_PORT]))
            scan_s = float(
                user_input.get(CONF_SCAN_INTERVAL, defaults[CONF_SCAN_INTERVAL])
            )
            op_timeout = float(
                user_input.get(CONF_OP_TIMEOUT, defaults[CONF_OP_TIMEOUT])
            )
            max_retries = int(
                user_input.get(CONF_MAX_RETRIES, defaults[CONF_MAX_RETRIES])
            )
            backoff_initial = float(
                user_input.get(CONF_BACKOFF_INITIAL, defaults[CONF_BACKOFF_INITIAL])
            )
            backoff_max = float(
                user_input.get(CONF_BACKOFF_MAX, defaults[CONF_BACKOFF_MAX])
            )
            name = (
                user_input.get(CONF_NAME) or defaults[CONF_NAME]
            ).strip() or "S7 PLC"
        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors=errors,
                description_placeholders=description_placeholders,
            )

        if scan_s <= 0:
            scan_s = DEFAULT_SCAN_INTERVAL

        if op_timeout <= 0:
            op_timeout = DEFAULT_OP_TIMEOUT

        if max_retries < 0:
            max_retries = DEFAULT_MAX_RETRIES

        if backoff_initial <= 0:
            backoff_initial = DEFAULT_BACKOFF_INITIAL

        if backoff_max < backoff_initial:
            backoff_max = max(backoff_initial, backoff_max)

        new_unique_id = f"{host}-{rack}-{slot}"
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == self._config_entry.entry_id:
                continue
            if entry.unique_id == new_unique_id:
                errors["base"] = "already_configured"
                break

        if errors:
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors=errors,
                description_placeholders=description_placeholders,
            )

        coordinator = S7Coordinator(
            self.hass,
            host=host,
            rack=rack,
            slot=slot,
            port=port,
            scan_interval=scan_s,
            op_timeout=op_timeout,
            max_retries=max_retries,
            backoff_initial=backoff_initial,
            backoff_max=backoff_max,
        )

        try:
            await self.hass.async_add_executor_job(coordinator.connect)
            await self.hass.async_add_executor_job(coordinator.disconnect)
        except (OSError, RuntimeError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors=errors,
                description_placeholders=description_placeholders,
            )

        new_data = {
            CONF_NAME: name,
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_RACK: rack,
            CONF_SLOT: slot,
            CONF_SCAN_INTERVAL: scan_s,
            CONF_OP_TIMEOUT: op_timeout,
            CONF_MAX_RETRIES: max_retries,
            CONF_BACKOFF_INITIAL: backoff_initial,
            CONF_BACKOFF_MAX: backoff_max,
        }

        update_result = self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=new_data,
            title=name,
        )

        if inspect.isawaitable(update_result):
            await update_result

        return self.async_create_entry(title="", data=self._options)

    # ====== STEP 0: choose action (add or remove) ======
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Show a menu with the next steps; labels come from strings.json
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "connection",  # modify connection parameters
                "add",  # guided item addition flow
                "edit",  # modify existing entities
                "remove",  # remove existing entities
                "export",  # export configuration
                "import",  # import configuration from JSON
            ],
        )

    async def async_step_add(self, user_input: dict[str, Any] | None = None):
        data_schema = vol.Schema(
            {
                vol.Required("item_type"): add_item_selector,
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="add", data_schema=data_schema)

        selection = user_input.get("item_type")

        if selection not in ADD_ENTITY_STEP_IDS:
            return self.async_show_form(
                step_id="add",
                data_schema=data_schema,
                errors={"base": "invalid_selection"},
            )

        handler = getattr(self, f"async_step_{selection}")
        return await handler()

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_DEVICE_CLASS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=s_device_class_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_VALUE_MULTIPLIER): value_multiplier_selector,
                vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            if address:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_SENSORS, address):
                        errors["base"] = "duplicate_entry"
                    else:
                        item: dict[str, Any] = {CONF_ADDRESS: address}
                        if user_input.get(CONF_NAME):
                            item[CONF_NAME] = user_input[CONF_NAME]
                        if user_input.get(CONF_DEVICE_CLASS):
                            item[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
                        self._apply_value_multiplier(
                            item, user_input.get(CONF_VALUE_MULTIPLIER)
                        )
                        self._apply_scan_interval(
                            item, user_input.get(CONF_SCAN_INTERVAL)
                        )
                        self._options[CONF_SENSORS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="sensors", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_sensors()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="sensors", data_schema=data_schema)

    async def async_step_binary_sensors(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_DEVICE_CLASS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=bs_device_class_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))

            if address:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_BINARY_SENSORS, address):
                        errors["base"] = "duplicate_entry"
                    else:
                        item: dict[str, Any] = {CONF_ADDRESS: address}
                        if user_input.get(CONF_NAME):
                            item[CONF_NAME] = user_input[CONF_NAME]
                        if user_input.get(CONF_DEVICE_CLASS):
                            item[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
                        self._apply_scan_interval(
                            item, user_input.get(CONF_SCAN_INTERVAL)
                        )
                        self._options[CONF_BINARY_SENSORS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="binary_sensors", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_binary_sensors()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="binary_sensors", data_schema=data_schema)

    async def async_step_switches(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATE_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(
                    CONF_SYNC_STATE, default=False
                ): selector.BooleanSelector(),
                vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            state_address = self._sanitize_address(user_input.get(CONF_STATE_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            if state_address:
                try:
                    parse_tag(state_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(
                        CONF_SWITCHES,
                        state_address,
                        keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
                    ):
                        errors["base"] = "duplicate_entry"

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors and state_address:
                item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if command_address:
                    item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))
                self._options[CONF_SWITCHES].append(item)

            if errors:
                return self.async_show_form(
                    step_id="switches", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_switches()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="switches", data_schema=data_schema)

    async def async_step_buttons(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_BUTTON_PULSE, default=DEFAULT_BUTTON_PULSE): int,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            if address:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_BUTTONS, address):
                        errors["base"] = "duplicate_entry"
                    else:
                        item: dict[str, Any] = {CONF_ADDRESS: address}
                        if user_input.get(CONF_NAME):
                            item[CONF_NAME] = user_input[CONF_NAME]

                        button_pulse_input = user_input.get(CONF_BUTTON_PULSE)
                        if button_pulse_input is None:
                            button_pulse = DEFAULT_BUTTON_PULSE
                        else:
                            try:
                                button_pulse = int(button_pulse_input)
                            except (TypeError, ValueError):
                                button_pulse = DEFAULT_BUTTON_PULSE
                            else:
                                if button_pulse < 0:
                                    button_pulse = DEFAULT_BUTTON_PULSE

                        item[CONF_BUTTON_PULSE] = button_pulse
                        self._options[CONF_BUTTONS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="buttons", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_buttons()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="buttons", data_schema=data_schema)

    async def async_step_lights(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATE_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(
                    CONF_SYNC_STATE, default=False
                ): selector.BooleanSelector(),
                vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            state_address = self._sanitize_address(user_input.get(CONF_STATE_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            if state_address:
                try:
                    parse_tag(state_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(
                        CONF_LIGHTS,
                        state_address,
                        keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
                    ):
                        errors["base"] = "duplicate_entry"

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors and state_address:
                item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if command_address:
                    item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))
                self._options[CONF_LIGHTS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="lights", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_lights()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="lights", data_schema=data_schema)

    async def async_step_numbers(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        number_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
        )

        positive_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_MIN_VALUE): number_selector,
                vol.Optional(CONF_MAX_VALUE): number_selector,
                vol.Optional(CONF_STEP): positive_selector,
                vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            address_tag = None
            if address:
                try:
                    address_tag = parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_NUMBERS, address):
                        errors["base"] = "duplicate_entry"

            min_value: float | None = None
            max_value: float | None = None
            step_value: float | None = None

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors:
                try:
                    if user_input.get(CONF_MIN_VALUE) is not None:
                        min_value = float(user_input[CONF_MIN_VALUE])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"

            if not errors:
                try:
                    if user_input.get(CONF_MAX_VALUE) is not None:
                        max_value = float(user_input[CONF_MAX_VALUE])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"

            if not errors:
                try:
                    if user_input.get(CONF_STEP) is not None:
                        step_value = float(user_input[CONF_STEP])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"
                else:
                    if step_value is not None and step_value <= 0:
                        errors["base"] = "invalid_number"

            if not errors and address_tag is not None:
                limits = get_numeric_limits(address_tag.data_type)
                if limits is not None:
                    dtype_min, dtype_max = limits
                    if min_value is not None:
                        min_value = min(max(min_value, dtype_min), dtype_max)
                    if max_value is not None:
                        max_value = min(max(max_value, dtype_min), dtype_max)

            if not errors and min_value is not None and max_value is not None:
                if min_value > max_value:
                    errors["base"] = "invalid_range"

            if not errors and address:
                item: dict[str, Any] = {CONF_ADDRESS: address}
                if command_address:
                    item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                if min_value is not None:
                    item[CONF_MIN_VALUE] = min_value
                if max_value is not None:
                    item[CONF_MAX_VALUE] = max_value
                if step_value is not None:
                    item[CONF_STEP] = step_value
                self._apply_scan_interval(item, user_input.get(CONF_SCAN_INTERVAL))
                self._options[CONF_NUMBERS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="numbers", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_numbers()

            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="numbers", data_schema=data_schema)

    async def async_step_export(self, user_input: dict[str, Any] | None = None):
        export_text = self._build_export_data()

        data_schema = vol.Schema(
            {vol.Required("export_json", default=export_text): str}
        )

        if user_input is None:
            item_count = sum(len(self._options.get(key, [])) for key in OPTION_KEYS)
            download_link = register_export_download(
                self.hass,
                self._config_entry.title,
                self._config_entry.data.get(CONF_NAME),
                export_text,
            )
            return self.async_show_form(
                step_id="export",
                data_schema=data_schema,
                description_placeholders={
                    "item_count": str(item_count),
                    "download_filename": download_link.filename,
                    "download_link_start": (
                        f'<a href="{download_link.url}" '
                        f'download="{download_link.filename}" '
                        'target="_blank" rel="noopener">'
                    ),
                    "download_link_end": "</a>",
                },
            )

        return self.async_create_entry(title="", data=self._options)

    async def async_step_import(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current_text = ""

        if user_input is not None:
            raw_value = user_input.get("import_json")
            if raw_value is None:
                errors["base"] = "invalid_json"
            else:
                current_text = str(raw_value)
                raw_text = current_text.strip()
                if not raw_text:
                    errors["base"] = "invalid_json"
                else:
                    try:
                        payload = json.loads(raw_text)
                    except ValueError:
                        errors["base"] = "invalid_json"
                    else:
                        sanitized = self._sanitize_import_payload(payload)
                        if sanitized is None:
                            errors["base"] = "invalid_json"
                        else:
                            self._options = sanitized
                            return self.async_create_entry(title="", data=self._options)

        data_schema = vol.Schema(
            {vol.Required("import_json", default=current_text): str}
        )

        item_count = sum(len(self._options.get(key, [])) for key in OPTION_KEYS)
        return self.async_show_form(
            step_id="import",
            data_schema=data_schema,
            description_placeholders={"item_count": str(item_count)},
            errors=errors if errors else None,
        )

    # ====== STEP B: remove ======
    async def async_step_remove(self, user_input: dict[str, Any] | None = None):
        # Build a key->label map for all configured items
        # Unique key: type prefix + index, e.g. "s:0", "bs:1", "sw:2", "lt:0"
        items: Dict[str, str] = self._build_items_map()

        if user_input is not None:
            to_remove: List[str] = user_input.get("remove_items", [])
            # filter each list removing the selected indices
            if to_remove:
                # build set of indices for type
                rm_s = {int(k.split(":")[1]) for k in to_remove if k.startswith("s:")}
                rm_bs = {int(k.split(":")[1]) for k in to_remove if k.startswith("bs:")}
                rm_sw = {int(k.split(":")[1]) for k in to_remove if k.startswith("sw:")}
                rm_bt = {int(k.split(":")[1]) for k in to_remove if k.startswith("bt:")}
                rm_lt = {int(k.split(":")[1]) for k in to_remove if k.startswith("lt:")}
                rm_nm = {int(k.split(":")[1]) for k in to_remove if k.startswith("nm:")}

                self._options[CONF_SENSORS] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_SENSORS, []))
                    if idx not in rm_s
                ]
                self._options[CONF_BINARY_SENSORS] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_BINARY_SENSORS, []))
                    if idx not in rm_bs
                ]
                self._options[CONF_SWITCHES] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_SWITCHES, []))
                    if idx not in rm_sw
                ]
                self._options[CONF_BUTTONS] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_BUTTONS, []))
                    if idx not in rm_bt
                ]
                self._options[CONF_LIGHTS] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_LIGHTS, []))
                    if idx not in rm_lt
                ]
                self._options[CONF_NUMBERS] = [
                    v
                    for idx, v in enumerate(self._options.get(CONF_NUMBERS, []))
                    if idx not in rm_nm
                ]

            # Save and close: __init__.py will reload the entry
            # and the entities will disappear
            return self.async_create_entry(title="", data=self._options)

        # Preselect nothing: the user chooses what to remove
        data_schema = vol.Schema(
            {vol.Optional("remove_items", default=[]): cv.multi_select(items)}
        )
        # Title/description from translations: options.step.remove.*
        return self.async_show_form(step_id="remove", data_schema=data_schema)

    # ====== STEP C: edit ======
    async def async_step_edit(self, user_input: dict[str, Any] | None = None):
        items = self._build_items_map()

        if not items:
            return self.async_show_form(
                step_id="edit",
                data_schema=vol.Schema({}),
                errors={"base": "no_items"},
            )

        select_options = [
            selector.SelectOptionDict(value=key, label=label)
            for key, label in items.items()
        ]
        data_schema = vol.Schema(
            {
                vol.Required("edit_item"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=select_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="edit", data_schema=data_schema)

        selection = user_input.get("edit_item")
        if selection not in items:
            return await self.async_step_edit()

        prefix, _, idx_str = selection.partition(":")
        try:
            idx = int(idx_str)
        except ValueError:
            return await self.async_step_edit()

        self._action = "edit"
        self._edit_target = (prefix, idx)

        if prefix == "s":
            return await self.async_step_edit_sensor()
        if prefix == "bs":
            return await self.async_step_edit_binary_sensor()
        if prefix == "sw":
            return await self.async_step_edit_switch()
        if prefix == "bt":
            return await self.async_step_edit_button()
        if prefix == "lt":
            return await self.async_step_edit_light()
        if prefix == "nm":
            return await self.async_step_edit_number()

        return await self.async_step_edit()

    def _get_edit_item(
        self, option_key: str, prefix: str
    ) -> tuple[int, dict[str, Any]] | None:
        if self._edit_target is None:
            return None
        target_prefix, index = self._edit_target
        if target_prefix != prefix:
            return None
        items = self._options.get(option_key, [])
        if not 0 <= index < len(items):
            return None
        return index, items[index]

    async def async_step_edit_sensor(self, user_input: dict[str, Any] | None = None):
        lookup = self._get_edit_item(CONF_SENSORS, "s")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NAME, default=item.get(CONF_NAME, "")
            ): selector.TextSelector(),
        }

        if item.get(CONF_DEVICE_CLASS) is not None:
            schema_dict[
                vol.Optional(CONF_DEVICE_CLASS, default=item.get(CONF_DEVICE_CLASS))
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=s_device_class_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            schema_dict[vol.Optional(CONF_DEVICE_CLASS)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=s_device_class_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        if item.get(CONF_SCAN_INTERVAL) is not None:
            schema_dict[
                vol.Optional(CONF_SCAN_INTERVAL, default=item.get(CONF_SCAN_INTERVAL))
            ] = scan_interval_selector
        else:
            schema_dict[vol.Optional(CONF_SCAN_INTERVAL)] = scan_interval_selector

        if item.get(CONF_VALUE_MULTIPLIER) is not None:
            schema_dict[
                vol.Optional(
                    CONF_VALUE_MULTIPLIER, default=item.get(CONF_VALUE_MULTIPLIER)
                )
            ] = value_multiplier_selector
        else:
            schema_dict[vol.Optional(CONF_VALUE_MULTIPLIER)] = value_multiplier_selector

        data_schema = vol.Schema(schema_dict)

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            if not address:
                errors["base"] = "invalid_address"
            else:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_SENSORS, address, skip_idx=idx):
                        errors["base"] = "duplicate_entry"

            if not errors and address:
                new_item: dict[str, Any] = {CONF_ADDRESS: address}
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]
                if user_input.get(CONF_DEVICE_CLASS):
                    new_item[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
                self._apply_value_multiplier(
                    new_item, user_input.get(CONF_VALUE_MULTIPLIER)
                )
                self._apply_scan_interval(new_item, user_input.get(CONF_SCAN_INTERVAL))

                self._options[CONF_SENSORS][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_sensor", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_binary_sensor(
        self, user_input: dict[str, Any] | None = None
    ):
        lookup = self._get_edit_item(CONF_BINARY_SENSORS, "bs")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NAME, default=item.get(CONF_NAME, "")
            ): selector.TextSelector(),
        }

        if item.get(CONF_DEVICE_CLASS) is not None:
            schema_dict[
                vol.Optional(CONF_DEVICE_CLASS, default=item.get(CONF_DEVICE_CLASS))
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=bs_device_class_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            schema_dict[vol.Optional(CONF_DEVICE_CLASS)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=bs_device_class_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        if item.get(CONF_SCAN_INTERVAL) is not None:
            schema_dict[
                vol.Optional(CONF_SCAN_INTERVAL, default=item.get(CONF_SCAN_INTERVAL))
            ] = scan_interval_selector
        else:
            schema_dict[vol.Optional(CONF_SCAN_INTERVAL)] = scan_interval_selector

        data_schema = vol.Schema(schema_dict)

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            if not address:
                errors["base"] = "invalid_address"
            else:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_BINARY_SENSORS, address, skip_idx=idx):
                        errors["base"] = "duplicate_entry"

            if not errors and address:
                new_item: dict[str, Any] = {CONF_ADDRESS: address}
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]
                if user_input.get(CONF_DEVICE_CLASS):
                    new_item[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
                self._apply_scan_interval(new_item, user_input.get(CONF_SCAN_INTERVAL))

                self._options[CONF_BINARY_SENSORS][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_binary_sensor",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_edit_switch(self, user_input: dict[str, Any] | None = None):
        lookup = self._get_edit_item(CONF_SWITCHES, "sw")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_STATE_ADDRESS, default=item.get(CONF_STATE_ADDRESS, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COMMAND_ADDRESS,
                default=item.get(CONF_COMMAND_ADDRESS, ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NAME, default=item.get(CONF_NAME, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_SYNC_STATE,
                default=bool(item.get(CONF_SYNC_STATE, False)),
            ): selector.BooleanSelector(),
        }

        if item.get(CONF_SCAN_INTERVAL) is not None:
            schema_dict[
                vol.Optional(CONF_SCAN_INTERVAL, default=item.get(CONF_SCAN_INTERVAL))
            ] = scan_interval_selector
        else:
            schema_dict[vol.Optional(CONF_SCAN_INTERVAL)] = scan_interval_selector

        data_schema = vol.Schema(schema_dict)

        if user_input is not None:
            state_address = self._sanitize_address(
                user_input.get(CONF_STATE_ADDRESS)
            ) or self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            if not state_address:
                errors["base"] = "invalid_address"
            else:
                try:
                    parse_tag(state_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(
                        CONF_SWITCHES,
                        state_address,
                        keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
                        skip_idx=idx,
                    ):
                        errors["base"] = "duplicate_entry"

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors and state_address:
                new_item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if command_address:
                    new_item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]
                new_item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._apply_scan_interval(new_item, user_input.get(CONF_SCAN_INTERVAL))

                self._options[CONF_SWITCHES][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_switch", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_button(self, user_input: dict[str, Any] | None = None):
        lookup = self._get_edit_item(CONF_BUTTONS, "bt")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_NAME, default=item.get(CONF_NAME, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_BUTTON_PULSE,
                    default=int(item.get(CONF_BUTTON_PULSE, DEFAULT_BUTTON_PULSE)),
                ): int,
            }
        )

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            if not address:
                errors["base"] = "invalid_address"
            else:
                try:
                    parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_BUTTONS, address, skip_idx=idx):
                        errors["base"] = "duplicate_entry"

            if not errors and address:
                new_item: dict[str, Any] = {CONF_ADDRESS: address}
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]

                button_pulse_input = user_input.get(CONF_BUTTON_PULSE)
                if button_pulse_input is None:
                    button_pulse = DEFAULT_BUTTON_PULSE
                else:
                    try:
                        button_pulse = int(button_pulse_input)
                    except (TypeError, ValueError):
                        button_pulse = DEFAULT_BUTTON_PULSE
                    else:
                        if button_pulse < 0:
                            button_pulse = DEFAULT_BUTTON_PULSE

                new_item[CONF_BUTTON_PULSE] = button_pulse

                self._options[CONF_BUTTONS][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_button", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_light(self, user_input: dict[str, Any] | None = None):
        lookup = self._get_edit_item(CONF_LIGHTS, "lt")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_STATE_ADDRESS, default=item.get(CONF_STATE_ADDRESS, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COMMAND_ADDRESS,
                default=item.get(CONF_COMMAND_ADDRESS, ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NAME, default=item.get(CONF_NAME, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_SYNC_STATE,
                default=bool(item.get(CONF_SYNC_STATE, False)),
            ): selector.BooleanSelector(),
        }

        if item.get(CONF_SCAN_INTERVAL) is not None:
            schema_dict[
                vol.Optional(CONF_SCAN_INTERVAL, default=item.get(CONF_SCAN_INTERVAL))
            ] = scan_interval_selector
        else:
            schema_dict[vol.Optional(CONF_SCAN_INTERVAL)] = scan_interval_selector

        data_schema = vol.Schema(schema_dict)

        if user_input is not None:
            state_address = self._sanitize_address(
                user_input.get(CONF_STATE_ADDRESS)
            ) or self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            if not state_address:
                errors["base"] = "invalid_address"
            else:
                try:
                    parse_tag(state_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(
                        CONF_LIGHTS,
                        state_address,
                        keys=(CONF_STATE_ADDRESS, CONF_ADDRESS),
                        skip_idx=idx,
                    ):
                        errors["base"] = "duplicate_entry"

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors and state_address:
                new_item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if command_address:
                    new_item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]
                new_item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._apply_scan_interval(new_item, user_input.get(CONF_SCAN_INTERVAL))

                self._options[CONF_LIGHTS][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_light", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_number(self, user_input: dict[str, Any] | None = None):
        lookup = self._get_edit_item(CONF_NUMBERS, "nm")
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}

        number_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
        )
        positive_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
            )
        )

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COMMAND_ADDRESS,
                default=item.get(CONF_COMMAND_ADDRESS, ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NAME, default=item.get(CONF_NAME, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_MIN_VALUE, default=item.get(CONF_MIN_VALUE)
            ): number_selector,
            vol.Optional(
                CONF_MAX_VALUE, default=item.get(CONF_MAX_VALUE)
            ): number_selector,
        }

        if item.get(CONF_STEP) is not None:
            schema_dict[vol.Optional(CONF_STEP, default=item.get(CONF_STEP))] = (
                positive_selector
            )
        else:
            schema_dict[vol.Optional(CONF_STEP)] = positive_selector

        if item.get(CONF_SCAN_INTERVAL) is not None:
            schema_dict[
                vol.Optional(CONF_SCAN_INTERVAL, default=item.get(CONF_SCAN_INTERVAL))
            ] = scan_interval_selector
        else:
            schema_dict[vol.Optional(CONF_SCAN_INTERVAL)] = scan_interval_selector

        data_schema = vol.Schema(schema_dict)

        if user_input is not None:
            address = self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(
                user_input.get(CONF_COMMAND_ADDRESS)
            )

            address_tag = None
            if not address:
                errors["base"] = "invalid_address"
            else:
                try:
                    address_tag = parse_tag(address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"
                else:
                    if self._has_duplicate(CONF_NUMBERS, address, skip_idx=idx):
                        errors["base"] = "duplicate_entry"

            min_value: float | None = None
            max_value: float | None = None
            step_value: float | None = None

            if not errors and command_address:
                try:
                    parse_tag(command_address)
                except (RuntimeError, ValueError):
                    errors["base"] = "invalid_address"

            if not errors:
                try:
                    if user_input.get(CONF_MIN_VALUE) is not None:
                        min_value = float(user_input[CONF_MIN_VALUE])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"

            if not errors:
                try:
                    if user_input.get(CONF_MAX_VALUE) is not None:
                        max_value = float(user_input[CONF_MAX_VALUE])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"

            if not errors:
                try:
                    if user_input.get(CONF_STEP) is not None:
                        step_value = float(user_input[CONF_STEP])
                except (TypeError, ValueError):
                    errors["base"] = "invalid_number"
                else:
                    if step_value is not None and step_value <= 0:
                        errors["base"] = "invalid_number"

            if not errors and address_tag is not None:
                limits = get_numeric_limits(address_tag.data_type)
                if limits is not None:
                    dtype_min, dtype_max = limits
                    if min_value is not None:
                        min_value = min(max(min_value, dtype_min), dtype_max)
                    if max_value is not None:
                        max_value = min(max(max_value, dtype_min), dtype_max)

            if not errors and min_value is not None and max_value is not None:
                if min_value > max_value:
                    errors["base"] = "invalid_range"

            if not errors and address:
                new_item: dict[str, Any] = {CONF_ADDRESS: address}
                if command_address:
                    new_item[CONF_COMMAND_ADDRESS] = command_address
                if user_input.get(CONF_NAME):
                    new_item[CONF_NAME] = user_input[CONF_NAME]
                if min_value is not None:
                    new_item[CONF_MIN_VALUE] = min_value
                if max_value is not None:
                    new_item[CONF_MAX_VALUE] = max_value
                if step_value is not None:
                    new_item[CONF_STEP] = step_value
                self._apply_scan_interval(new_item, user_input.get(CONF_SCAN_INTERVAL))

                self._options[CONF_NUMBERS][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="edit_number", data_schema=data_schema, errors=errors
        )
