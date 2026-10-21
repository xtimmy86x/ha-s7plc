"""Apply a deliberately limited set of options without rebuilding the PLC entry."""

from copy import deepcopy

from .const import CONF_UID, OPTION_KEYS
from .helpers import RuntimeEntryData
from .value_conversion import ValueConversionError


async def async_apply_live_options(entry, runtime: RuntimeEntryData) -> bool:
    """Preflight the entire change before touching any running entity or poller."""
    if runtime.applied_data != dict(entry.data) or runtime.applied_options is None:
        return False
    options = deepcopy(dict(entry.options))
    previous = runtime.applied_options
    if any(
        previous.get(key) != options.get(key)
        for key in previous.keys() | options.keys()
        if key not in OPTION_KEYS
    ):
        return False

    coordinator = runtime.coordinator
    prepared = []
    polling = {}
    for entity_type in OPTION_KEYS:
        old_items = previous.get(entity_type, [])
        new_items = options.get(entity_type, [])
        # Additions, deletions, moves and address/type changes use the normal reload.
        if [item.get(CONF_UID) for item in old_items] != [
            item.get(CONF_UID) for item in new_items
        ]:
            return False
        for old, new in zip(old_items, new_items):
            changed = {
                key for key in old.keys() | new.keys() if old.get(key) != new.get(key)
            }
            if not changed:
                continue
            uid = new.get(CONF_UID)
            if not uid:
                return False
            uids = (uid, f"{uid}:active") if entity_type == "alarm_groups" else (uid,)
            for entity_uid in uids:
                entity = coordinator.config_entities.get(entity_uid)
                if entity is None:
                    # Area assignments also work for disabled registry entities.
                    if changed <= {"area"}:
                        continue
                    return False
                try:
                    attributes = entity.prepare_live_config(new, changed)
                except (ValueConversionError, TypeError, ValueError):
                    return False
                if attributes is None:
                    return False
                prepared.append((entity, attributes, "value_conversions" in changed))
                if "scan_interval" in changed:
                    topics = entity._restorable_topics | {entity._availability_topic}
                    for topic in topics:
                        if topic in coordinator._items:
                            polling.setdefault(topic, {})["scan_interval"] = new.get(
                                "scan_interval"
                            )
                if "real_precision" in changed:
                    polling.setdefault(entity._topic, {})["real_precision"] = new.get(
                        "real_precision"
                    )

    if polling:
        await coordinator.async_update_polling(polling)
    # No await between applying prepared attributes and recording their snapshot.
    for entity, attributes, conversion_changed in prepared:
        entity.apply_live_config(attributes, conversion_changed=conversion_changed)
    runtime.applied_options = options
    return True
