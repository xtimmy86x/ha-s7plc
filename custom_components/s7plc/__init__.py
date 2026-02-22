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
from .helpers import RuntimeEntryData, build_entity_area_map, build_expected_unique_ids

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

    # Store runtime data directly in the config entry
    entry.runtime_data = RuntimeEntryData(
        coordinator=coordinator,
        name=name,
        host=host,
        device_id=device_id,
    )

    hass.data.setdefault(DOMAIN, {})

    # Register services once
    if not hass.data[DOMAIN].get("_services_registered"):

        async def _async_health_check_service(call) -> None:
            entry_id = call.data["entry_id"]
            # Find the config entry
            target_entry = hass.config_entries.async_get_entry(entry_id)
            if not target_entry or not hasattr(target_entry, "runtime_data"):
                raise vol.Invalid(f"Unknown entry_id: {entry_id}")
            coord: S7Coordinator = target_entry.runtime_data.coordinator
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

            # Find the config entry
            target_entry = hass.config_entries.async_get_entry(entry_id)
            if not target_entry or not hasattr(target_entry, "runtime_data"):
                raise vol.Invalid(f"Unknown entry_id: {entry_id}")

            coord: S7Coordinator = target_entry.runtime_data.coordinator

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

    device_id = entry.runtime_data.device_id
    expected_unique_ids = build_expected_unique_ids(device_id, entry.options)

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
    """Unload a config entry and cleanup resources."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Disconnect coordinator (runtime_data is automatically cleaned up by HA)
        await hass.async_add_executor_job(entry.runtime_data.coordinator.disconnect)

        # Unregister services if this is the last config entry
        remaining_entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]

        if not remaining_entries and hass.data[DOMAIN].get("_services_registered"):
            _LOGGER.debug(
                "Unregistering services as last config entry is being removed"
            )
            hass.services.async_remove(DOMAIN, SERVICE_HEALTH_CHECK)
            hass.services.async_remove(DOMAIN, SERVICE_WRITE_MULTI)
            hass.data[DOMAIN].pop("_services_registered", None)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Update areas in entity registry before reloading
    await _async_update_entity_areas(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_update_entity_areas(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update entity areas in the registry based on configuration."""
    # Skip if runtime_data is not available (e.g., during tests or initial setup)
    if not hasattr(entry, "runtime_data") or entry.runtime_data is None:
        return

    entity_reg = er.async_get(hass)
    device_id = entry.runtime_data.device_id

    entity_areas = build_entity_area_map(device_id, entry.options)

    # Update areas in entity registry
    for unique_id, area_id in entity_areas.items():
        entity_entry = entity_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if not entity_entry:
            # Try other platforms
            for platform in [
                "binary_sensor",
                "switch",
                "cover",
                "button",
                "light",
                "number",
                "text",
                "climate",
            ]:
                entity_entry = entity_reg.async_get_entity_id(
                    platform, DOMAIN, unique_id
                )
                if entity_entry:
                    break

        if entity_entry:
            entity_reg.async_update_entity(entity_entry, area_id=area_id)
