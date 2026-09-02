from __future__ import annotations

import logging
from copy import deepcopy

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .config_entry_migration import canonicalize_legacy_sync_addresses
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
    CONF_PYS7_CONNECTION_TYPE,
    CONF_RACK,
    CONF_REMOTE_TSAP,
    CONF_SLOT,
    CONNECTION_CONTROL_STORAGE_VERSION,
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
    OPTION_KEYS,
    PLATFORMS,
)
from .coordinator import S7Coordinator
from .helpers import (
    RuntimeEntryData,
    build_device_id,
    build_entity_area_map,
    build_expected_unique_ids,
    ensure_item_uids,
)
from .value_conversion import (
    VALUE_CHANNEL_SPECS,
    ValueConversionError,
    conversion_contexts,
    validate_value_conversion,
)
from .value_conversion_migration import migrate_legacy_value_conversions

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_HEALTH_CHECK = "health_check"
SERVICE_WRITE_MULTI = "write_multi"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Atomically migrate only versioned legacy fields before setup.

    Deliberately do not pass persisted entities through the current panel
    builder: unrelated rules added after an entry was saved are not migration
    rules and must not prevent a direct 7.x upgrade.
    """
    if entry.version >= 2:
        return True
    options = deepcopy(dict(entry.options))
    totals = [0, 0, 0]
    sync_configurations = 0
    discarded_sensor_limits = 0
    conflict_logs: list[tuple[str, str, str]] = []
    for entity_type in OPTION_KEYS:
        migrated_items = []
        for index, entity in enumerate(options.get(entity_type, [])):
            channel = (
                "brightness"
                if "brightness_scale" in entity
                else (
                    "value"
                    if any(
                        key in entity
                        for key in (
                            "value_multiplier",
                            "scale_raw_min",
                            "scale_raw_max",
                        )
                    )
                    else "configuration"
                )
            )
            try:
                canonicalized, sync_report = canonicalize_legacy_sync_addresses(
                    entity_type, entity
                )
                migrated, report = migrate_legacy_value_conversions(
                    entity_type, canonicalized
                )

                conversions = migrated.get("value_conversions")
                if conversions is not None:
                    if not isinstance(conversions, dict):
                        raise ValueConversionError(
                            "value_conversions must be a mapping"
                        )
                    for channel, conversion in conversions.items():
                        if channel not in VALUE_CHANNEL_SPECS.get(entity_type, {}):
                            raise ValueConversionError(
                                f"unsupported conversion channel '{channel}'"
                            )
                        for context in conversion_contexts(
                            entity_type, migrated, channel
                        ):
                            validate_value_conversion(conversion, context)
            except (ValueConversionError, ValueError, TypeError) as err:
                _LOGGER.error(
                    "Config entry %s migration failed for entity type %s "
                    "index %d channel %s: %s",
                    entry.entry_id,
                    entity_type,
                    index,
                    channel,
                    err,
                )
                return False

            migrated_items.append(migrated)
            totals[0] += report.multipliers
            totals[1] += report.linear_scales
            totals[2] += report.brightness_scales
            discarded_sensor_limits += report.discarded_sensor_limits
            sync_configurations += int(sync_report.changed)
            identity = str(entity.get("uid") or entity.get("name") or index)
            conflict_logs.extend(
                (entity_type, identity, conflict_channel)
                for conflict_channel in report.conflicts
            )
        if entity_type in options:
            options[entity_type] = migrated_items

    for entity_type, identity, channel in conflict_logs:
        _LOGGER.warning(
            "Config entry %s %s %s channel %s has different legacy and "
            "value_conversions settings; kept authoritative value_conversions",
            entry.entry_id,
            entity_type,
            identity,
            channel,
        )
    hass.config_entries.async_update_entry(entry, options=options, version=3)
    _LOGGER.info(
        "Migrated legacy value conversions for config entry %s: "
        "%d multipliers, %d linear scales, %d brightness scales, "
        "%d redundant sync configurations normalized",
        entry.entry_id,
        *totals,
        sync_configurations,
    )
    if discarded_sensor_limits:
        _LOGGER.debug(
            "Removed %d obsolete sensor min/max fields from config entry %s",
            discarded_sensor_limits,
            entry.entry_id,
        )
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    # Lightweight test harnesses and config validation do not expose HTTP.
    if hasattr(hass, "http"):
        from .panel import async_setup_panel

        await async_setup_panel(hass)
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
    enable_write_batching = bool(
        data.get(CONF_ENABLE_WRITE_BATCHING, DEFAULT_ENABLE_WRITE_BATCHING)
    )
    enable_metrics = bool(data.get(CONF_ENABLE_METRICS, DEFAULT_ENABLE_METRICS))
    manual_connection_control = bool(
        data.get(CONF_MANUAL_CONNECTION_CONTROL, DEFAULT_MANUAL_CONNECTION_CONTROL)
    )
    connection_state_store = None
    connection_enabled = True
    if manual_connection_control:
        connection_state_store = Store(
            hass,
            CONNECTION_CONTROL_STORAGE_VERSION,
            f"{DOMAIN}.connection_control.{entry.entry_id}",
        )
        stored_state = await connection_state_store.async_load()
        if isinstance(stored_state, dict):
            connection_enabled = bool(stored_state.get("enabled", True))
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
    else:
        rack = data.get(CONF_RACK, DEFAULT_RACK)
        slot = data.get(CONF_SLOT, DEFAULT_SLOT)
        local_tsap = None
        remote_tsap = None
    device_id = build_device_id(data)

    # Assign a permanent identity to every config item that doesn't have one
    # yet, so unique_id no longer depends on any editable address field.
    # Items that already correspond to a registered entity keep the exact
    # same unique_id (see ensure_item_uids docstring); only brand-new items
    # get a fresh one. Must run before platforms are set up.
    if ensure_item_uids(device_id, entry.options):
        hass.config_entries.async_update_entry(entry, options=entry.options)

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
        enable_metrics=enable_metrics,
        connection_enabled=connection_enabled,
    )

    # Store runtime data directly in the config entry
    entry.runtime_data = RuntimeEntryData(
        coordinator=coordinator,
        name=name,
        host=host,
        device_id=device_id,
        connection_state_store=connection_state_store,
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
            results = await coord.write_multi(write_list)

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
    expected_unique_ids = build_expected_unique_ids(
        device_id, entry.options, data=entry.data
    )

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
        await entry.runtime_data.coordinator.async_shutdown()

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
    await hass.config_entries.async_reload(entry.entry_id)

    # Apply configured areas after reload, when newly added entities
    # are available in the entity registry.
    await _async_update_entity_areas(hass, entry)


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
        entity_entry = None
        for platform in PLATFORMS:
            entity_entry = entity_reg.async_get_entity_id(platform, DOMAIN, unique_id)
            if entity_entry:
                break

        if entity_entry:
            entity_reg.async_update_entity(entity_entry, area_id=area_id)
