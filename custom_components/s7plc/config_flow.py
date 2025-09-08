from __future__ import annotations

import logging
from typing import Any, Dict, List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv  # <-- IMPORT IMPORTANTE
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_ADDRESS,
    CONF_BINARY_SENSORS,
    CONF_COMMAND_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_HOST,
    CONF_LIGHTS,
    CONF_NAME,
    CONF_PORT,
    CONF_RACK,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): selector.TextSelector(),
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
        except Exception:
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
        except Exception:  # pylint: disable=broad-except
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
        }
        self._action: str | None = None  # "add" | "remove"

    # ====== STEP 0: scegli azione (aggiungi o rimuovi) ======
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._action = user_input.get("action")
            if self._action == "add":
                return await self.async_step_sensors()
            if self._action == "remove":
                return await self.async_step_remove()
            # default
            self._action = "add"
            return await self.async_step_sensors()

        # 1) Prendo la lingua corrente e le traduzioni per questo dominio/categoria
        lang = self.hass.config.language
        trans = await async_get_translations(
            self.hass,
            language=lang,
            category="options",
            integrations=[
                DOMAIN
            ],  # molto importante: limita alle traduzioni del tuo dominio
            config_flow=True,  # include le chiavi del config/options flow
        )

        # 2) Estraggo le due stringhe con fallback
        t_add = trans.get(f"component.{DOMAIN}.options.action.add", "Add / Configure")
        t_remove = trans.get(
            f"component.{DOMAIN}.options.action.remove", "Remove items"
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    "action",
                    default="add",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label=t_add),
                            selector.SelectOptionDict(value="remove", label=t_remove),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        # Title/description presi da translations: options.step.init.*
        return self.async_show_form(step_id="init", data_schema=data_schema)

    # ====== STEP A: add (come già avevi) ======
    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if address:
                item: dict[str, Any] = {CONF_ADDRESS: address}
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                self._options[CONF_SENSORS].append(item)

            if user_input.get("add_another"):
                return await self.async_step_sensors()

            return await self.async_step_binary_sensors()

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_ADDRESS): selector.TextSelector(),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional("add_another", default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="sensors", data_schema=data_schema)

    async def async_step_binary_sensors(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if address:
                item: dict[str, Any] = {CONF_ADDRESS: address}
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                if user_input.get(CONF_DEVICE_CLASS):
                    item[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
                self._options[CONF_BINARY_SENSORS].append(item)

            if user_input.get("add_another"):
                return await self.async_step_binary_sensors()

            return await self.async_step_switches()

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
        return self.async_show_form(step_id="binary_sensors", data_schema=data_schema)

    async def async_step_switches(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            state_address = user_input.get(CONF_STATE_ADDRESS) or user_input.get(
                CONF_ADDRESS
            )
            if state_address:
                item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if user_input.get(CONF_COMMAND_ADDRESS):
                    item[CONF_COMMAND_ADDRESS] = user_input[CONF_COMMAND_ADDRESS]
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._options[CONF_SWITCHES].append(item)

            if user_input.get("add_another"):
                return await self.async_step_switches()

            return await self.async_step_lights()

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
        return self.async_show_form(step_id="switches", data_schema=data_schema)

    async def async_step_lights(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            state_address = user_input.get(CONF_STATE_ADDRESS) or user_input.get(
                CONF_ADDRESS
            )
            if state_address:
                item: dict[str, Any] = {CONF_STATE_ADDRESS: state_address}
                if user_input.get(CONF_COMMAND_ADDRESS):
                    item[CONF_COMMAND_ADDRESS] = user_input[CONF_COMMAND_ADDRESS]
                if user_input.get(CONF_NAME):
                    item[CONF_NAME] = user_input[CONF_NAME]
                item[CONF_SYNC_STATE] = bool(user_input.get(CONF_SYNC_STATE, False))
                self._options[CONF_LIGHTS].append(item)

            if user_input.get("add_another"):
                return await self.async_step_lights()

            # finisce il ramo "add"
            return self.async_create_entry(title="", data=self._options)

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
