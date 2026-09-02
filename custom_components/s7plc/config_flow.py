from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from dataclasses import dataclass
from ipaddress import ip_interface, ip_network
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.storage import Store

# Import S7-specific exceptions if available
try:
    from pyS7.errors import S7CommunicationError, S7ConnectionError
except (ImportError, AttributeError):

    class S7ConnectionError(RuntimeError):
        """Fallback S7 connection error."""

    class S7CommunicationError(RuntimeError):
        """Fallback S7 communication error."""


from .const import (
    CONF_BACKOFF_INITIAL,
    CONF_BACKOFF_MAX,
    CONF_CONNECTION_TYPE,
    CONF_ENABLE_METRICS,
    CONF_ENABLE_WRITE_BATCHING,
    CONF_LOCAL_TSAP,
    CONF_MANUAL_CONNECTION_CONTROL,
    CONF_MAX_RETRIES,
    CONF_OP_TIMEOUT,
    CONF_OPTIMIZE_READ,
    CONF_PLC_FAMILY,
    CONF_PYS7_CONNECTION_TYPE,
    CONF_RACK,
    CONF_REMOTE_TSAP,
    CONF_SCAN_INTERVAL,
    CONF_SLOT,
    CONNECTION_CONTROL_STORAGE_VERSION,
    CONNECTION_TYPE_RACK_SLOT,
    CONNECTION_TYPE_TSAP,
    DEFAULT_BACKOFF_INITIAL,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_ENABLE_METRICS,
    DEFAULT_ENABLE_WRITE_BATCHING,
    DEFAULT_MANUAL_CONNECTION_CONTROL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_OP_TIMEOUT,
    DEFAULT_OPTIMIZE_READ,
    DEFAULT_PORT,
    DEFAULT_PYS7_CONNECTION_TYPE,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
    PLC_FAMILIES,
    PLC_FAMILY_LOGO_0BA7,
    PLC_FAMILY_LOGO_0BA8,
    PLC_FAMILY_LOGO_9,
    PLC_FAMILY_S7,
    PYS7_CONNECTION_TYPE_OP,
    PYS7_CONNECTION_TYPE_PG,
    PYS7_CONNECTION_TYPE_S7BASIC,
)
from .coordinator import S7Coordinator
from .helpers import build_device_id

_LOGGER = logging.getLogger(__name__)

_PLC_FAMILY_LABELS = {
    PLC_FAMILY_S7: "SIMATIC S7",
    PLC_FAMILY_LOGO_0BA7: "LOGO! 0BA7",
    PLC_FAMILY_LOGO_0BA8: "LOGO! 0BA8",
    PLC_FAMILY_LOGO_9: "LOGO! 9",
}


def _compatible_plc_families(connection_type: str) -> tuple[str, ...]:
    """Return families compatible with a fixed connection method."""
    if connection_type == CONNECTION_TYPE_RACK_SLOT:
        return tuple(
            family for family in PLC_FAMILIES if family != PLC_FAMILY_LOGO_0BA7
        )
    return PLC_FAMILIES


def _family_selector(families: tuple[str, ...]):
    """Build the shared PLC family selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=value, label=_PLC_FAMILY_LABELS[value])
                for value in families
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _get_connection_description(
    connection_type: str,
    local_tsap: str | None = None,
    remote_tsap: str | None = None,
    rack: int | None = None,
    slot: int | None = None,
) -> str:
    """Return human-readable connection description."""
    if connection_type == CONNECTION_TYPE_TSAP:
        return f"TSAP {local_tsap}/{remote_tsap}"
    return f"rack {rack} slot {slot}"


def _handle_connection_error(
    flow_instance,
    err: Exception,
    host: str,
    port: int,
    connection_type: str,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
    step_id: str,
    data_schema: vol.Schema,
    errors: dict[str, str],
    description_placeholders: dict[str, str] | None = None,
):
    """Handle connection test errors with logging."""
    connection_desc = _get_connection_description(
        connection_type, local_tsap, remote_tsap, rack, slot
    )

    if isinstance(err, S7ConnectionError):
        _LOGGER.error(
            "S7 connection error to PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, S7CommunicationError):
        _LOGGER.error(
            "S7 communication error with PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, OSError):
        _LOGGER.error(
            "Network error connecting to S7 PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, RuntimeError):
        _LOGGER.error(
            "Runtime error with S7 PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    else:
        _LOGGER.exception(
            "Unexpected error connecting to S7 PLC at %s:%s (%s)",
            host,
            port,
            connection_desc,
        )

    errors["base"] = "cannot_connect"

    if description_placeholders:
        return flow_instance.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
    return flow_instance.async_show_form(
        step_id=step_id,
        data_schema=data_schema,
        errors=errors,
    )


def _sanitize_connection_params(
    scan_s: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
) -> tuple[float, float, int, float, float]:
    """Sanitize connection parameters to valid defaults."""
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
    return scan_s, op_timeout, max_retries, backoff_initial, backoff_max


def _build_connection_parse_defaults(
    connection_type: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build parsing defaults for connection parameters."""
    source = data or {}

    defaults: dict[str, Any] = {
        CONF_PORT: int(source.get(CONF_PORT, DEFAULT_PORT)),
        CONF_PYS7_CONNECTION_TYPE: source.get(
            CONF_PYS7_CONNECTION_TYPE, DEFAULT_PYS7_CONNECTION_TYPE
        ),
        CONF_SCAN_INTERVAL: float(
            source.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        CONF_OP_TIMEOUT: float(source.get(CONF_OP_TIMEOUT, DEFAULT_OP_TIMEOUT)),
        CONF_MAX_RETRIES: int(source.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)),
        CONF_BACKOFF_INITIAL: float(
            source.get(CONF_BACKOFF_INITIAL, DEFAULT_BACKOFF_INITIAL)
        ),
        CONF_BACKOFF_MAX: float(source.get(CONF_BACKOFF_MAX, DEFAULT_BACKOFF_MAX)),
        CONF_OPTIMIZE_READ: bool(source.get(CONF_OPTIMIZE_READ, DEFAULT_OPTIMIZE_READ)),
        CONF_ENABLE_WRITE_BATCHING: bool(
            source.get(CONF_ENABLE_WRITE_BATCHING, DEFAULT_ENABLE_WRITE_BATCHING)
        ),
        CONF_ENABLE_METRICS: bool(
            source.get(CONF_ENABLE_METRICS, DEFAULT_ENABLE_METRICS)
        ),
    }

    if connection_type == CONNECTION_TYPE_TSAP:
        defaults[CONF_LOCAL_TSAP] = source.get(CONF_LOCAL_TSAP, "01.00")
        defaults[CONF_REMOTE_TSAP] = source.get(CONF_REMOTE_TSAP, "01.01")
    else:
        defaults[CONF_RACK] = int(source.get(CONF_RACK, DEFAULT_RACK))
        defaults[CONF_SLOT] = int(source.get(CONF_SLOT, DEFAULT_SLOT))

    return defaults


@dataclass(frozen=True, slots=True)
class ParsedConnectionParams:
    """Parsed and sanitized connection-related parameters."""

    port: int
    pys7_connection_type: str
    scan_interval: float
    op_timeout: float
    max_retries: int
    backoff_initial: float
    backoff_max: float
    optimize_read: bool
    enable_write_batching: bool
    enable_metrics: bool
    rack: int | None
    slot: int | None
    local_tsap: str | None
    remote_tsap: str | None


def _parse_connection_params(
    user_input: dict[str, Any],
    *,
    connection_type: str,
    defaults: dict[str, Any],
) -> ParsedConnectionParams:
    """Parse and sanitize shared connection parameters from user input."""
    port = int(user_input.get(CONF_PORT, defaults[CONF_PORT]))
    pys7_connection_type = user_input.get(
        CONF_PYS7_CONNECTION_TYPE, defaults[CONF_PYS7_CONNECTION_TYPE]
    )
    scan_interval = float(
        user_input.get(CONF_SCAN_INTERVAL, defaults[CONF_SCAN_INTERVAL])
    )
    op_timeout = float(user_input.get(CONF_OP_TIMEOUT, defaults[CONF_OP_TIMEOUT]))
    max_retries = int(user_input.get(CONF_MAX_RETRIES, defaults[CONF_MAX_RETRIES]))
    backoff_initial = float(
        user_input.get(CONF_BACKOFF_INITIAL, defaults[CONF_BACKOFF_INITIAL])
    )
    backoff_max = float(user_input.get(CONF_BACKOFF_MAX, defaults[CONF_BACKOFF_MAX]))
    optimize_read = bool(
        user_input.get(CONF_OPTIMIZE_READ, defaults[CONF_OPTIMIZE_READ])
    )
    enable_write_batching = bool(
        user_input.get(CONF_ENABLE_WRITE_BATCHING, defaults[CONF_ENABLE_WRITE_BATCHING])
    )
    enable_metrics = bool(
        user_input.get(CONF_ENABLE_METRICS, defaults[CONF_ENABLE_METRICS])
    )

    if connection_type == CONNECTION_TYPE_TSAP:
        local_tsap = user_input.get(CONF_LOCAL_TSAP, defaults[CONF_LOCAL_TSAP])
        remote_tsap = user_input.get(CONF_REMOTE_TSAP, defaults[CONF_REMOTE_TSAP])
        rack = None
        slot = None
    else:
        rack = int(user_input.get(CONF_RACK, defaults[CONF_RACK]))
        slot = int(user_input.get(CONF_SLOT, defaults[CONF_SLOT]))
        local_tsap = None
        remote_tsap = None

    scan_interval, op_timeout, max_retries, backoff_initial, backoff_max = (
        _sanitize_connection_params(
            scan_interval,
            op_timeout,
            max_retries,
            backoff_initial,
            backoff_max,
        )
    )

    return ParsedConnectionParams(
        port=port,
        pys7_connection_type=pys7_connection_type,
        scan_interval=scan_interval,
        op_timeout=op_timeout,
        max_retries=max_retries,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
        optimize_read=optimize_read,
        enable_write_batching=enable_write_batching,
        rack=rack,
        slot=slot,
        local_tsap=local_tsap,
        remote_tsap=remote_tsap,
        enable_metrics=enable_metrics,
    )


def _generate_connection_unique_id(
    host: str,
    connection_type: str,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
) -> str:
    """Generate unique ID based on connection type."""
    if connection_type == CONNECTION_TYPE_TSAP:
        return f"{host}-tsap-{local_tsap}-{remote_tsap}"
    return f"{host}-{rack}-{slot}"


async def _test_plc_connection(
    hass,
    *,
    host: str,
    connection_type: str,
    rack: int | None,
    slot: int | None,
    local_tsap: str | None,
    remote_tsap: str | None,
    pys7_connection_type: str,
    port: int,
    scan_interval: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
    optimize_read: bool,
    enable_write_batching: bool,
    enable_metrics: bool,
) -> None:
    """Test PLC connection. Raises on failure."""
    coordinator = S7Coordinator(
        hass,
        host=host,
        connection_type=connection_type,
        rack=rack,
        slot=slot,
        local_tsap=local_tsap,
        remote_tsap=remote_tsap,
        pys7_connection_type=pys7_connection_type,
        port=port,
        scan_interval=scan_interval,
        op_timeout=op_timeout,
        max_retries=max_retries,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
        optimize_read=optimize_read,
        enable_write_batching=enable_write_batching,
        enable_metrics=enable_metrics,
    )
    await coordinator.connect()
    await coordinator.disconnect()


def _build_connection_entry_data(
    *,
    name: str,
    host: str,
    port: int,
    connection_type: str,
    pys7_connection_type: str,
    scan_interval: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
    optimize_read: bool,
    enable_write_batching: bool,
    enable_metrics: bool,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
    plc_family: str = PLC_FAMILY_S7,
    manual_connection_control: bool = DEFAULT_MANUAL_CONNECTION_CONTROL,
) -> dict[str, Any]:
    """Build connection entry data dict."""
    data = {
        CONF_NAME: name,
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_CONNECTION_TYPE: connection_type,
        CONF_PYS7_CONNECTION_TYPE: pys7_connection_type,
        CONF_PLC_FAMILY: plc_family,
        CONF_SCAN_INTERVAL: scan_interval,
        CONF_OP_TIMEOUT: op_timeout,
        CONF_MAX_RETRIES: max_retries,
        CONF_BACKOFF_INITIAL: backoff_initial,
        CONF_BACKOFF_MAX: backoff_max,
        CONF_OPTIMIZE_READ: optimize_read,
        CONF_ENABLE_WRITE_BATCHING: enable_write_batching,
        CONF_ENABLE_METRICS: enable_metrics,
        CONF_MANUAL_CONNECTION_CONTROL: manual_connection_control,
    }
    if connection_type == CONNECTION_TYPE_TSAP:
        data[CONF_LOCAL_TSAP] = local_tsap
        data[CONF_REMOTE_TSAP] = remote_tsap
    else:
        data[CONF_RACK] = rack
        data[CONF_SLOT] = slot
    return data


class S7PLCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for S7 PLC."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialise the flow."""

        self._discovered_hosts: list[str] | None = None
        self._connection_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step - choose connection type."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_RACK_SLOT
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    selector.SelectOptionDict(
                                        value=CONNECTION_TYPE_RACK_SLOT,
                                        label="Rack/Slot",
                                    ),
                                    selector.SelectOptionDict(
                                        value=CONNECTION_TYPE_TSAP,
                                        label="TSAP",
                                    ),
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Required(
                            CONF_PLC_FAMILY, default=PLC_FAMILY_S7
                        ): _family_selector(PLC_FAMILIES),
                    }
                ),
            )

        connection_type = user_input[CONF_CONNECTION_TYPE]
        family = user_input.get(CONF_PLC_FAMILY, PLC_FAMILY_S7)
        if family not in _compatible_plc_families(connection_type):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CONNECTION_TYPE, default=connection_type
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    CONNECTION_TYPE_RACK_SLOT,
                                    CONNECTION_TYPE_TSAP,
                                ]
                            )
                        ),
                        vol.Required(CONF_PLC_FAMILY, default=family): _family_selector(
                            PLC_FAMILIES
                        ),
                    }
                ),
                errors={"base": "incompatible_family_connection"},
            )
        self._connection_data[CONF_CONNECTION_TYPE] = connection_type
        self._connection_data[CONF_PLC_FAMILY] = family

        if user_input[CONF_CONNECTION_TYPE] == CONNECTION_TYPE_RACK_SLOT:
            return await self.async_step_rack_slot()
        else:
            return await self.async_step_tsap()

    async def async_step_rack_slot(self, user_input: dict[str, Any] | None = None):
        """Handle rack/slot connection configuration."""
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

        family = self._connection_data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7)
        default_slot = (
            2 if family in (PLC_FAMILY_LOGO_0BA8, PLC_FAMILY_LOGO_9) else DEFAULT_SLOT
        )
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): host_selector,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_RACK, default=DEFAULT_RACK): int,
                vol.Optional(CONF_SLOT, default=default_slot): int,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE, default=DEFAULT_PYS7_CONNECTION_TYPE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG (Programming Console)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP (Operator Panel)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
                vol.Optional(CONF_OPTIMIZE_READ, default=DEFAULT_OPTIMIZE_READ): bool,
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING, default=DEFAULT_ENABLE_WRITE_BATCHING
                ): bool,
                vol.Optional(CONF_ENABLE_METRICS, default=DEFAULT_ENABLE_METRICS): bool,
                vol.Optional(
                    CONF_MANUAL_CONNECTION_CONTROL,
                    default=DEFAULT_MANUAL_CONNECTION_CONTROL,
                ): bool,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="rack_slot",
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

        return await self._async_validate_and_create(user_input, errors, data_schema)

    async def async_step_tsap(self, user_input: dict[str, Any] | None = None):
        """Handle TSAP connection configuration."""
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

        family = self._connection_data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7)
        logo_0ba7 = family == PLC_FAMILY_LOGO_0BA7
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): host_selector,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(
                    CONF_LOCAL_TSAP, default="10.00" if logo_0ba7 else "01.00"
                ): str,
                vol.Required(
                    CONF_REMOTE_TSAP, default="10.01" if logo_0ba7 else "01.01"
                ): str,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE, default=DEFAULT_PYS7_CONNECTION_TYPE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG (Programming Console)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP (Operator Panel)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING, default=DEFAULT_ENABLE_WRITE_BATCHING
                ): bool,
                vol.Optional(CONF_OPTIMIZE_READ, default=DEFAULT_OPTIMIZE_READ): bool,
                vol.Optional(CONF_ENABLE_METRICS, default=DEFAULT_ENABLE_METRICS): bool,
                vol.Optional(
                    CONF_MANUAL_CONNECTION_CONTROL,
                    default=DEFAULT_MANUAL_CONNECTION_CONTROL,
                ): bool,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="tsap",
                data_schema=data_schema,
                description_placeholders={
                    "default_port": str(DEFAULT_PORT),
                    "default_scan": str(DEFAULT_SCAN_INTERVAL),
                    "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
                    "default_retries": str(DEFAULT_MAX_RETRIES),
                    "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
                    "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
                },
                errors=errors,
            )

        return await self._async_validate_and_create(user_input, errors, data_schema)

    async def _async_validate_and_create(
        self, user_input: dict[str, Any], errors: dict[str, str], data_schema
    ):
        """Validate connection and create entry."""

        connection_type = self._connection_data.get(
            CONF_CONNECTION_TYPE, CONNECTION_TYPE_RACK_SLOT
        )
        parse_defaults = _build_connection_parse_defaults(connection_type)

        try:
            host = user_input[CONF_HOST]
            params = _parse_connection_params(
                user_input,
                connection_type=connection_type,
                defaults=parse_defaults,
            )
            name = user_input.get(CONF_NAME, "S7 PLC")

        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            step_id = (
                "tsap"
                if self._connection_data.get(CONF_CONNECTION_TYPE)
                == CONNECTION_TYPE_TSAP
                else "rack_slot"
            )
            return self.async_show_form(
                step_id=step_id, data_schema=data_schema, errors=errors
            )

        unique_id = _generate_connection_unique_id(
            host,
            connection_type,
            params.local_tsap,
            params.remote_tsap,
            params.rack,
            params.slot,
        )
        await self.async_set_unique_id(unique_id, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        try:
            await _test_plc_connection(
                self.hass,
                host=host,
                connection_type=connection_type,
                rack=params.rack,
                slot=params.slot,
                local_tsap=params.local_tsap,
                remote_tsap=params.remote_tsap,
                pys7_connection_type=params.pys7_connection_type,
                port=params.port,
                scan_interval=params.scan_interval,
                op_timeout=params.op_timeout,
                max_retries=params.max_retries,
                backoff_initial=params.backoff_initial,
                backoff_max=params.backoff_max,
                optimize_read=params.optimize_read,
                enable_write_batching=params.enable_write_batching,
                enable_metrics=params.enable_metrics,
            )
        except Exception as err:
            # Catch all connection errors (OSError, S7 errors, RuntimeError, etc.)
            # and present them to the user through the config flow UI
            step_id = "tsap" if connection_type == CONNECTION_TYPE_TSAP else "rack_slot"
            return _handle_connection_error(
                self,
                err,
                host,
                params.port,
                connection_type,
                params.local_tsap,
                params.remote_tsap,
                params.rack,
                params.slot,
                step_id,
                data_schema,
                errors,
            )

        entry_data = _build_connection_entry_data(
            name=name,
            host=host,
            port=params.port,
            connection_type=connection_type,
            pys7_connection_type=params.pys7_connection_type,
            scan_interval=params.scan_interval,
            op_timeout=params.op_timeout,
            max_retries=params.max_retries,
            backoff_initial=params.backoff_initial,
            backoff_max=params.backoff_max,
            optimize_read=params.optimize_read,
            enable_write_batching=params.enable_write_batching,
            local_tsap=params.local_tsap,
            remote_tsap=params.remote_tsap,
            rack=params.rack,
            slot=params.slot,
            plc_family=self._connection_data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7),
            enable_metrics=params.enable_metrics,
            manual_connection_control=bool(
                user_input.get(
                    CONF_MANUAL_CONNECTION_CONTROL,
                    DEFAULT_MANUAL_CONNECTION_CONTROL,
                )
            ),
        )

        return self.async_create_entry(title=name, data=entry_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return S7PLCOptionsFlow(config_entry)

    async def _async_get_discovered_hosts(self) -> list[str]:
        """Return cached or freshly discovered PLC hosts on the local network."""

        if self._discovered_hosts is not None:
            return self._discovered_hosts

        hosts_to_scan: list[str] = []
        hosts_seen: set[str] = set()
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
                    if host_str in hosts_seen:
                        continue
                    hosts_seen.add(host_str)
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

        # Filter out already configured hosts
        configured_hosts = {
            entry.data.get(CONF_HOST)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_HOST)
        }
        discovered = [host for host in discovered if host not in configured_hosts]

        discovered.sort()
        self._discovered_hosts = discovered
        if discovered:
            _LOGGER.debug("Discovered potential S7 PLC hosts: %s", discovered)

        return discovered


class S7PLCOptionsFlow(config_entries.OptionsFlow):
    """Handle connection options for S7 PLC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._options = dict(config_entry.options)

    async def async_step_connection(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data = self._config_entry.data

        # Determine connection type from existing data
        connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_RACK_SLOT)
        is_tsap = connection_type == CONNECTION_TYPE_TSAP
        parse_defaults = _build_connection_parse_defaults(connection_type, data)

        defaults = {
            CONF_NAME: data.get(CONF_NAME) or self._config_entry.title or "S7 PLC",
            CONF_HOST: data.get(CONF_HOST, ""),
            **parse_defaults,
            CONF_PLC_FAMILY: data.get(CONF_PLC_FAMILY, PLC_FAMILY_S7),
            CONF_MANUAL_CONNECTION_CONTROL: data.get(
                CONF_MANUAL_CONNECTION_CONTROL, DEFAULT_MANUAL_CONNECTION_CONTROL
            ),
        }

        # Build schema based on connection type
        schema_fields = {
            vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
            vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
            vol.Optional(CONF_PORT, default=defaults[CONF_PORT]): int,
            vol.Required(
                CONF_PLC_FAMILY, default=defaults[CONF_PLC_FAMILY]
            ): _family_selector(_compatible_plc_families(connection_type)),
        }

        if is_tsap:
            schema_fields[
                vol.Required(CONF_LOCAL_TSAP, default=defaults[CONF_LOCAL_TSAP])
            ] = str
            schema_fields[
                vol.Required(CONF_REMOTE_TSAP, default=defaults[CONF_REMOTE_TSAP])
            ] = str
        else:
            schema_fields[vol.Optional(CONF_RACK, default=defaults[CONF_RACK])] = int
            schema_fields[vol.Optional(CONF_SLOT, default=defaults[CONF_SLOT])] = int

        schema_fields.update(
            {
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
                vol.Optional(
                    CONF_OPTIMIZE_READ, default=defaults[CONF_OPTIMIZE_READ]
                ): bool,
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING,
                    default=defaults[CONF_ENABLE_WRITE_BATCHING],
                ): bool,
                vol.Optional(
                    CONF_ENABLE_METRICS, default=defaults[CONF_ENABLE_METRICS]
                ): bool,
                vol.Optional(
                    CONF_MANUAL_CONNECTION_CONTROL,
                    default=defaults[CONF_MANUAL_CONNECTION_CONTROL],
                ): bool,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE,
                    default=defaults[CONF_PYS7_CONNECTION_TYPE],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        data_schema = vol.Schema(schema_fields)

        description_placeholders = {
            "default_port": str(DEFAULT_PORT),
            "default_scan": str(DEFAULT_SCAN_INTERVAL),
            "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
            "default_retries": str(DEFAULT_MAX_RETRIES),
            "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
            "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
        }

        if not is_tsap:
            description_placeholders["default_rack"] = str(DEFAULT_RACK)
            description_placeholders["default_slot"] = str(DEFAULT_SLOT)

        if user_input is None:
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                description_placeholders=description_placeholders,
            )

        family = user_input.get(CONF_PLC_FAMILY, defaults[CONF_PLC_FAMILY])
        if family not in _compatible_plc_families(connection_type):
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors={"base": "incompatible_family_connection"},
                description_placeholders=description_placeholders,
            )

        try:
            host = str(user_input[CONF_HOST]).strip()
            params = _parse_connection_params(
                user_input,
                connection_type=(
                    CONNECTION_TYPE_TSAP if is_tsap else CONNECTION_TYPE_RACK_SLOT
                ),
                defaults=parse_defaults,
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

        connection_type = CONNECTION_TYPE_TSAP if is_tsap else CONNECTION_TYPE_RACK_SLOT
        new_unique_id = _generate_connection_unique_id(
            host,
            connection_type,
            params.local_tsap,
            params.remote_tsap,
            params.rack,
            params.slot,
        )

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

        candidate_connection_data = {
            CONF_HOST: host,
            CONF_PORT: params.port,
            CONF_PYS7_CONNECTION_TYPE: params.pys7_connection_type,
        }
        current_connection_data = {
            CONF_HOST: data.get(CONF_HOST, ""),
            CONF_PORT: int(data.get(CONF_PORT, DEFAULT_PORT)),
            CONF_PYS7_CONNECTION_TYPE: data.get(
                CONF_PYS7_CONNECTION_TYPE, DEFAULT_PYS7_CONNECTION_TYPE
            ),
        }
        if is_tsap:
            candidate_connection_data.update(
                {
                    CONF_LOCAL_TSAP: params.local_tsap,
                    CONF_REMOTE_TSAP: params.remote_tsap,
                }
            )
            current_connection_data.update(
                {
                    CONF_LOCAL_TSAP: data.get(CONF_LOCAL_TSAP, "01.00"),
                    CONF_REMOTE_TSAP: data.get(CONF_REMOTE_TSAP, "01.01"),
                }
            )
        else:
            candidate_connection_data.update(
                {CONF_RACK: params.rack, CONF_SLOT: params.slot}
            )
            current_connection_data.update(
                {
                    CONF_RACK: int(data.get(CONF_RACK, DEFAULT_RACK)),
                    CONF_SLOT: int(data.get(CONF_SLOT, DEFAULT_SLOT)),
                }
            )
        connection_changed = any(
            candidate_connection_data[key] != current_connection_data[key]
            for key in candidate_connection_data
        )

        try:
            if connection_changed:
                await _test_plc_connection(
                    self.hass,
                    host=host,
                    connection_type=connection_type,
                    rack=params.rack,
                    slot=params.slot,
                    local_tsap=params.local_tsap,
                    remote_tsap=params.remote_tsap,
                    pys7_connection_type=params.pys7_connection_type,
                    port=params.port,
                    scan_interval=params.scan_interval,
                    op_timeout=params.op_timeout,
                    max_retries=params.max_retries,
                    backoff_initial=params.backoff_initial,
                    backoff_max=params.backoff_max,
                    optimize_read=params.optimize_read,
                    enable_write_batching=params.enable_write_batching,
                    enable_metrics=params.enable_metrics,
                )
        except Exception as err:
            # Catch all connection errors during options flow connection test
            # to provide user-friendly error messages in the UI
            return _handle_connection_error(
                self,
                err,
                host,
                params.port,
                connection_type,
                params.local_tsap,
                params.remote_tsap,
                params.rack,
                params.slot,
                "connection",
                data_schema,
                errors,
                description_placeholders,
            )

        new_data = _build_connection_entry_data(
            name=name,
            host=host,
            port=params.port,
            connection_type=connection_type,
            pys7_connection_type=params.pys7_connection_type,
            scan_interval=params.scan_interval,
            op_timeout=params.op_timeout,
            max_retries=params.max_retries,
            backoff_initial=params.backoff_initial,
            backoff_max=params.backoff_max,
            optimize_read=params.optimize_read,
            enable_write_batching=params.enable_write_batching,
            enable_metrics=params.enable_metrics,
            local_tsap=params.local_tsap,
            remote_tsap=params.remote_tsap,
            rack=params.rack,
            slot=params.slot,
            plc_family=family,
            manual_connection_control=bool(
                user_input.get(CONF_MANUAL_CONNECTION_CONTROL, False)
            ),
        )

        was_manual = bool(data.get(CONF_MANUAL_CONNECTION_CONTROL, False))
        is_manual = bool(new_data[CONF_MANUAL_CONNECTION_CONTROL])
        if was_manual and not is_manual:
            state_store = Store(
                self.hass,
                CONNECTION_CONTROL_STORAGE_VERSION,
                f"{DOMAIN}.connection_control.{self._config_entry.entry_id}",
            )
            await state_store.async_remove()
            entity_registry = er.async_get(self.hass)
            runtime_data = getattr(self._config_entry, "runtime_data", None)
            device_id = getattr(runtime_data, "device_id", None)
            if not isinstance(device_id, str):
                device_id = build_device_id(data)
            connection_switch_unique_id = f"{device_id}:connection_enable"
            for entity in er.async_entries_for_config_entry(
                entity_registry, self._config_entry.entry_id
            ):
                if (
                    entity.config_entry_id == self._config_entry.entry_id
                    and entity.platform == DOMAIN
                    and entity.unique_id == connection_switch_unique_id
                ):
                    entity_registry.async_remove(entity.entity_id)

        update_result = self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=new_data,
            title=name,
            unique_id=new_unique_id,
        )

        if inspect.isawaitable(update_result):
            await update_result

        return self.async_create_entry(title="", data=self._options)

    # Open connection settings immediately when the options flow starts.
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Open the PLC connection form directly."""
        return await self.async_step_connection(user_input)
