from __future__ import annotations

import asyncio
import contextlib
import logging
from ipaddress import ip_interface, ip_network
from typing import Any, Dict, List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .address import parse_tag
from .const import (
    CONF_ADDRESS,
    CONF_BINARY_SENSORS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    CONF_COMMAND_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_LIGHTS,
    CONF_RACK,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    DEFAULT_BUTTON_PULSE,
    DEFAULT_PORT,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)

bs_device_class_options = [
    selector.SelectOptionDict(value=dc.value, label=dc.value)
    for dc in BinarySensorDeviceClass
]

s_device_class_options = [
    selector.SelectOptionDict(value=dc.value, label=dc.value)
    for dc in SensorDeviceClass
]


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
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
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
                },
                errors=errors,
            )

        try:
            host = user_input[CONF_HOST]
            rack = int(user_input.get(CONF_RACK, DEFAULT_RACK))
            slot = int(user_input.get(CONF_SLOT, DEFAULT_SLOT))
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            scan_s = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            name = user_input.get(CONF_NAME, "S7 PLC")
        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user", data_schema=data_schema, errors=errors
            )

        if scan_s <= 0:
            scan_s = DEFAULT_SCAN_INTERVAL

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
        )
        try:
            await self.hass.async_add_executor_job(coordinator.connect)
            await self.hass.async_add_executor_job(coordinator.disconnect)
        except (OSError, RuntimeError):
            _LOGGER.exception(
                "Cannot connect to S7 PLC at %s (rack %s slot %s)", host, rack, slot
            )
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user", data_schema=data_schema, errors=errors
            )

        return self.async_create_entry(title=name, data=user_input)

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
        }
        self._action: str | None = None  # "add" | "remove"

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

    def _has_duplicate(
        self,
        option_key: str,
        address: str,
        *,
        keys: tuple[str, ...] = (CONF_ADDRESS,),
    ) -> bool:
        """Return ``True`` if ``address`` already exists in the options."""

        normalized = self._normalized_address(address)
        if normalized is None:
            return False

        for item in self._options.get(option_key, []):
            for key in keys:
                if self._normalized_address(item.get(key)) == normalized:
                    return True

        return False

    # ====== STEP 0: scegli azione (aggiungi o rimuovi) ======
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Mostra un menu con le prossime tappe; le etichette arrivano da strings.json
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add",  # percorso guidato: sensors ->
                # binary_sensors -> switches -> buttons -> lights
                "sensors",  # salta direttamente a "Add Sensor"
                "binary_sensors",  # salta direttamente a "Add Binary Sensor"
                "switches",  # salta direttamente a "Add Switch"
                "buttons",  # salta direttamente a "Add Button"
                "lights",  # salta direttamente a "Add Light"
                "remove",  # rimozione
            ],
        )

    async def async_step_add(self, user_input: dict[str, Any] | None = None):
        self._action = "add"
        return await self.async_step_sensors()

    # ====== STEP A: add (come già avevi) ======
    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
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
                        self._options[CONF_SENSORS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="sensors", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_sensors()

            return await self.async_step_binary_sensors()

        return self.async_show_form(step_id="sensors", data_schema=data_schema)

    async def async_step_binary_sensors(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_DEVICE_CLASS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=bs_device_class_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
                        self._options[CONF_BINARY_SENSORS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="binary_sensors", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_binary_sensors()

            return await self.async_step_switches()
        
        return self.async_show_form(step_id="binary_sensors", data_schema=data_schema)

    async def async_step_switches(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_STATE_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(
                    CONF_SYNC_STATE, default=False
                ): selector.BooleanSelector(),
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            state_address = self._sanitize_address(
                user_input.get(CONF_STATE_ADDRESS)
            ) or self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(user_input.get(CONF_COMMAND_ADDRESS))

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
                self._options[CONF_SWITCHES].append(item)

            if errors:
                return self.async_show_form(
                    step_id="switches", data_schema=data_schema, errors=errors
                )
            
            if user_input.get("add_another"):
                return await self.async_step_switches()

            return await self.async_step_buttons()

        return self.async_show_form(step_id="switches", data_schema=data_schema)

    async def async_step_buttons(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_ADDRESS): selector.TextSelector(),
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
                        if user_input.get(CONF_BUTTON_PULSE):
                            item[CONF_BUTTON_PULSE] = user_input[CONF_BUTTON_PULSE]
                        self._options[CONF_BUTTONS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="buttons", data_schema=data_schema, errors=errors
                )

            if user_input.get("add_another"):
                return await self.async_step_buttons()

            return await self.async_step_lights()

        return self.async_show_form(step_id="buttons", data_schema=data_schema)

    async def async_step_lights(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_STATE_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(
                    CONF_SYNC_STATE, default=False
                ): selector.BooleanSelector(),
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )

        if user_input is not None:
            state_address = self._sanitize_address(
                user_input.get(CONF_STATE_ADDRESS)
            ) or self._sanitize_address(user_input.get(CONF_ADDRESS))
            command_address = self._sanitize_address(user_input.get(CONF_COMMAND_ADDRESS))

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
                self._options[CONF_LIGHTS].append(item)

            if errors:
                return self.async_show_form(
                    step_id="lights", data_schema=data_schema, errors=errors
                )
            
            if user_input.get("add_another"):
                return await self.async_step_lights()

            # finisce il ramo "add"
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(step_id="lights", data_schema=data_schema)

    # ====== STEP B: remove ======
    async def async_step_remove(self, user_input: dict[str, Any] | None = None):
        # Costruisci mappa chiave->label per tutti gli elementi configurati
        # chiave unica: prefisso tipo + indice, es. "s:0", "bs:1", "sw:2", "lt:0"
        items: Dict[str, str] = {}

        def _labelize(prefix: str, idx: int, item: dict[str, Any]) -> str:
            name = item.get(CONF_NAME)
            addr = item.get(CONF_ADDRESS) or item.get(CONF_STATE_ADDRESS) or "?"
            typ = {
                "s": "Sensor",
                "bs": "Binary",
                "sw": "Switch",
                "bt": "Button",
                "lt": "Light",
            }[prefix]
            base = name or addr
            return f"{typ} • {base} [{addr}]"

        for i, it in enumerate(self._options.get(CONF_SENSORS, [])):
            items[f"s:{i}"] = _labelize("s", i, it)
        for i, it in enumerate(self._options.get(CONF_BINARY_SENSORS, [])):
            items[f"bs:{i}"] = _labelize("bs", i, it)
        for i, it in enumerate(self._options.get(CONF_SWITCHES, [])):
            # negli switch/luci usiamo STATE_ADDRESS come indirizzo
            it2 = {**it}
            it2.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"sw:{i}"] = _labelize("sw", i, it2)
        for i, it in enumerate(self._options.get(CONF_BUTTONS, [])):
            items[f"bt:{i}"] = _labelize("bt", i, it)
        for i, it in enumerate(self._options.get(CONF_LIGHTS, [])):
            it2 = {**it}
            it2.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"lt:{i}"] = _labelize("lt", i, it2)

        if user_input is not None:
            to_remove: List[str] = user_input.get("remove_items", [])
            # filtra ogni lista rimuovendo gli indici selezionati
            if to_remove:
                # costruisci set di indici per tipo
                rm_s = {int(k.split(":")[1]) for k in to_remove if k.startswith("s:")}
                rm_bs = {int(k.split(":")[1]) for k in to_remove if k.startswith("bs:")}
                rm_sw = {int(k.split(":")[1]) for k in to_remove if k.startswith("sw:")}
                rm_bt = {int(k.split(":")[1]) for k in to_remove if k.startswith("bt:")}
                rm_lt = {int(k.split(":")[1]) for k in to_remove if k.startswith("lt:")}

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

            # salva e chiudi: __init__.py farà reload dell’entry e le entità spariranno
            return self.async_create_entry(title="", data=self._options)

        # Preseleziona niente: l’utente sceglie cosa rimuovere
        data_schema = vol.Schema(
            {vol.Optional("remove_items", default=[]): cv.multi_select(items)}
        )
        # Title/description da translations: options.step.remove.*
        return self.async_show_form(step_id="remove", data_schema=data_schema)
