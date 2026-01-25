from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import (
    CONF_BACKOFF_INITIAL,
    CONF_BACKOFF_MAX,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_TSAP,
    CONF_MAX_RETRIES,
    CONF_OP_TIMEOUT,
    CONF_OPTIMIZE_READ,
    CONF_PYS7_CONNECTION_TYPE,
    CONF_RACK,
    CONF_REMOTE_TSAP,
    CONF_SLOT,
    CONNECTION_TYPE_TSAP,
    DEFAULT_BACKOFF_INITIAL,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_MAX_RETRIES,
    DEFAULT_OP_TIMEOUT,
    DEFAULT_OPTIMIZE_READ,
    DEFAULT_PORT,
    DEFAULT_PYS7_CONNECTION_TYPE,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import S7Coordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_HEALTH_CHECK = "health_check"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = entry.data
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_PORT)
    scan_s = float(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    name = data.get(CONF_NAME, "S7 PLC")
    op_timeout = float(data.get(CONF_OP_TIMEOUT, DEFAULT_OP_TIMEOUT))
    max_retries = int(data.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES))
    backoff_initial = float(data.get(CONF_BACKOFF_INITIAL, DEFAULT_BACKOFF_INITIAL))
    backoff_max = float(data.get(CONF_BACKOFF_MAX, DEFAULT_BACKOFF_MAX))
    optimize_read = bool(data.get(CONF_OPTIMIZE_READ, DEFAULT_OPTIMIZE_READ))
    pys7_connection_type = data.get(
        CONF_PYS7_CONNECTION_TYPE, DEFAULT_PYS7_CONNECTION_TYPE
    )

    # Get connection parameters based on type
    connection_type = data.get(CONF_CONNECTION_TYPE, "rack_slot")

    if connection_type == CONNECTION_TYPE_TSAP:
        local_tsap = data.get(CONF_LOCAL_TSAP, "01.00")
        remote_tsap = data.get(CONF_REMOTE_TSAP, "01.01")
        rack = None
        slot = None
        device_id = slugify(f"s7plc-{host}-tsap-{local_tsap}-{remote_tsap}")
    else:
        rack = data.get(CONF_RACK, DEFAULT_RACK)
        slot = data.get(CONF_SLOT, DEFAULT_SLOT)
        local_tsap = None
        remote_tsap = None
        device_id = slugify(f"s7plc-{host}-{rack}-{slot}")

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
        scan_interval=scan_s,
        op_timeout=op_timeout,
        max_retries=max_retries,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
        optimize_read=optimize_read,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "name": name,
        "host": host,
        "device_id": device_id,
    }

    # Register services once
    if not hass.data[DOMAIN].get("_services_registered"):

        async def _async_health_check_service(call) -> None:
            entry_id = call.data["entry_id"]
            runtime = hass.data[DOMAIN].get(entry_id)
            if not runtime:
                raise vol.Invalid(f"Unknown entry_id: {entry_id}")
            coord: S7Coordinator = runtime["coordinator"]
            result = await coord.async_health_check()
            _LOGGER.info(
                "Health check for %s: ok=%s latency=%.3fs error=%s",
                entry_id,
                result.get("ok"),
                result.get("latency"),
                result.get("error"),
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_HEALTH_CHECK,
            _async_health_check_service,
            schema=vol.Schema({vol.Required("entry_id"): str}),
        )
        hass.data[DOMAIN]["_services_registered"] = True

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data["coordinator"].disconnect)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
