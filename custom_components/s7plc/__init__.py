from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import (
    CONF_BACKOFF_INITIAL,
    CONF_BACKOFF_MAX,
    CONF_CONNECTION_TYPE,
    CONF_ENABLE_WRITE_BATCHING,
    CONF_ENTITY_SYNC,
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
    DEFAULT_ENABLE_WRITE_BATCHING,
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
SERVICE_WRITE_MULTI = "write_multi"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Migrate old "writers" key to "entity_sync"
    # TODO: Remove this migration in version 6.0.0
    if "writers" in entry.options:
        new_options = dict(entry.options)
        new_options[CONF_ENTITY_SYNC] = new_options.pop("writers")
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.warning(
            "Migrated deprecated 'writers' configuration to 'entity_sync' for entry %s."
            "This automatic migration will be removed in version 6.0.0. "
            "Please reconfigure the integration via the UI to avoid future issues.",
            entry.entry_id,
        )

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
    enable_write_batching = bool(
        data.get(CONF_ENABLE_WRITE_BATCHING, DEFAULT_ENABLE_WRITE_BATCHING)
    )
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
        enable_write_batching=enable_write_batching,
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

        async def _async_write_multi_service(call) -> None:
            entry_id = call.data["entry_id"]
            writes = call.data["writes"]

            runtime = hass.data[DOMAIN].get(entry_id)
            if not runtime:
                raise vol.Invalid(f"Unknown entry_id: {entry_id}")

            coord: S7Coordinator = runtime["coordinator"]

            # Convert list of dicts to list of tuples
            write_list = [(w["address"], w["value"]) for w in writes]

            # Execute batch write
            results = await hass.async_add_executor_job(coord.write_multi, write_list)

            # Log results
            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)
            _LOGGER.info(
                "Batch write for %s: %d/%d successful",
                entry_id,
                success_count,
                total_count,
            )

            # Log failures
            for address, success in results.items():
                if not success:
                    _LOGGER.warning("Failed to write to %s in batch operation", address)

        hass.services.async_register(
            DOMAIN,
            SERVICE_WRITE_MULTI,
            _async_write_multi_service,
            schema=vol.Schema(
                {
                    vol.Required("entry_id"): str,
                    vol.Required("writes"): [
                        vol.Schema(
                            {
                                vol.Required("address"): str,
                                vol.Required("value"): object,
                            }
                        )
                    ],
                }
            ),
        )

        hass.data[DOMAIN]["_services_registered"] = True

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Check for orphaned entities and create repair issue if found
    await _async_check_orphaned_entities(hass, entry, coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_check_orphaned_entities(
    hass: HomeAssistant, entry: ConfigEntry, coordinator
) -> None:
    """Check for orphaned entities and create a repair issue if any are found."""
    entity_reg = er.async_get(hass)

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    if not entities:
        return

    # Build set of expected unique_ids from current configuration
    expected_unique_ids = set()
    device_id = hass.data[DOMAIN][entry.entry_id]["device_id"]

    # Add unique_ids for all configured items
    options = entry.options

    # Sensors - format: device_id:sensor:address
    for item in options.get("sensors", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:sensor:{address}")

    # Binary sensors - format: device_id:binary_sensor:address
    for item in options.get("binary_sensors", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:binary_sensor:{address}")

    # Switches - format: device_id:switch:state_address
    for item in options.get("switches", []):
        state_addr = item.get("state_address", "")
        if state_addr:
            expected_unique_ids.add(f"{device_id}:switch:{state_addr}")

    # Covers (both traditional and position-based)
    for item in options.get("covers", []):
        position_state = item.get("position_state_address")
        if position_state:
            # Position cover - format: device_id:cover:position:position_state_address
            expected_unique_ids.add(f"{device_id}:cover:position:{position_state}")
        else:
            # Traditional cover -
            # format: device_id:cover:opened:xxx or cover:closed:xxx
            # or cover:command:open_addr
            open_command = item.get("open_command_address", "")
            opened_state = item.get("opening_state_address")
            closed_state = item.get("closing_state_address")

            if opened_state:
                expected_unique_ids.add(f"{device_id}:cover:opened:{opened_state}")
            elif closed_state:
                expected_unique_ids.add(f"{device_id}:cover:closed:{closed_state}")
            elif open_command:
                expected_unique_ids.add(f"{device_id}:cover:command:{open_command}")

    # Buttons - format: device_id:button:address
    for item in options.get("buttons", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:button:{address}")

    # Lights - format: device_id:light:state_address
    for item in options.get("lights", []):
        state_addr = item.get("state_address", "")
        if state_addr:
            expected_unique_ids.add(f"{device_id}:light:{state_addr}")

    # Numbers - format: device_id:number:address
    for item in options.get("numbers", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:number:{address}")

    # Texts - format: device_id:text:address
    for item in options.get("texts", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:text:{address}")

    # Entity syncs - format: device_id:entity_sync:address
    for item in options.get("entity_sync", []):
        address = item.get("address", "")
        if address:
            expected_unique_ids.add(f"{device_id}:entity_sync:{address}")

    # Always keep the connection status binary sensor - format: device_id:connection
    expected_unique_ids.add(f"{device_id}:connection")

    # Find orphaned entities
    orphaned_entities = []
    for entity in entities:
        if entity.unique_id not in expected_unique_ids:
            orphaned_entities.append(entity)

    if orphaned_entities:
        # Create a repair issue
        orphaned_list = "\n".join([f"- {e.entity_id}" for e in orphaned_entities[:10]])
        if len(orphaned_entities) > 10:
            orphaned_list += f"\n... and {len(orphaned_entities) - 10} more"

        ir.async_create_issue(
            hass,
            DOMAIN,
            f"orphaned_entities_{entry.entry_id}",
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="orphaned_entities",
            translation_placeholders={
                "entry_name": entry.title,
                "count": str(len(orphaned_entities)),
                "entity_list": orphaned_list,
            },
        )
        _LOGGER.info(
            "Found %d orphaned entity(ies) for config entry %s. "
            "A repair issue has been created.",
            len(orphaned_entities),
            entry.entry_id,
        )
    else:
        # Delete repair issue if it exists but no orphaned entities found
        ir.async_delete_issue(hass, DOMAIN, f"orphaned_entities_{entry.entry_id}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data["coordinator"].disconnect)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
