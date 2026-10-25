"""Apply a deliberately limited set of options without rebuilding the PLC entry."""

from copy import deepcopy
from dataclasses import dataclass, field

from .const import CONF_UID, OPTION_KEYS
from .helpers import RuntimeEntryData
from .value_conversion import ValueConversionError


@dataclass
class LiveOptionsPlan:
    """Side-effect-free preflight shared by previews and the update listener."""

    options: dict
    prepared: list = field(default_factory=list)
    polling: dict = field(default_factory=dict)
    reload_reason: dict | None = None

    def require_reload(self, reason: str, **details):
        self.reload_reason = {"reason": reason, **details}
        return self


def prepare_live_options(
    entry, runtime, options: dict | None = None
) -> LiveOptionsPlan:
    """Prepare the whole update without publishing state, polling or PLC I/O."""
    options = deepcopy(dict(entry.options) if options is None else options)
    plan = LiveOptionsPlan(options)
    if not isinstance(runtime, RuntimeEntryData) or runtime.applied_options is None:
        return plan.require_reload("runtime_unavailable")
    if runtime.applied_data != dict(entry.data):
        return plan.require_reload("connection_changed")
    previous = runtime.applied_options
    if any(
        previous.get(key) != options.get(key)
        for key in previous.keys() | options.keys()
        if key not in OPTION_KEYS
    ):
        return plan.require_reload("options_changed")

    coordinator = runtime.coordinator
    prepared = plan.prepared
    polling = plan.polling
    for entity_type in OPTION_KEYS:
        old_items = previous.get(entity_type, [])
        new_items = options.get(entity_type, [])
        # Additions, deletions, moves and address/type changes use the normal reload.
        if [item.get(CONF_UID) for item in old_items] != [
            item.get(CONF_UID) for item in new_items
        ]:
            return plan.require_reload("entities_changed")
        for old, new in zip(old_items, new_items):
            changed = {
                key for key in old.keys() | new.keys() if old.get(key) != new.get(key)
            }
            if not changed:
                continue
            uid = new.get(CONF_UID)
            if not uid:
                return plan.require_reload("entities_changed")
            details = {
                "entity_type": entity_type,
                "uid": uid,
                "fields": sorted(changed),
            }
            uids = (uid, f"{uid}:active") if entity_type == "alarm_groups" else (uid,)
            for entity_uid in uids:
                entity = coordinator.config_entities.get(entity_uid)
                if entity is None:
                    # Area assignments also work for disabled registry entities.
                    if changed <= {"area"}:
                        continue
                    return plan.require_reload("entity_unavailable", **details)
                try:
                    attributes = entity.prepare_live_config(new, changed)
                except (ValueConversionError, TypeError, ValueError):
                    return plan.require_reload("invalid_live_config", **details)
                if attributes is None:
                    details["fields"] = sorted(
                        changed - entity._live_config_fields
                    ) or sorted(changed)
                    return plan.require_reload("unsupported_fields", **details)
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

    return plan


def preview_options_update(
    entry, options: dict, *, has_changes: bool, has_errors: bool
) -> dict:
    """Explain the next save using the same preflight as the update listener."""
    if has_errors:
        return {"mode": "blocked"}
    if not has_changes:
        return {"mode": "none"}
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, RuntimeEntryData) and (
        runtime.config_update_lock.locked()
        or (
            runtime.applied_options is not None
            and runtime.applied_options != dict(entry.options)
        )
    ):
        return {"mode": "pending"}
    plan = prepare_live_options(entry, runtime, options)
    if plan.reload_reason:
        return {"mode": "reload", **plan.reload_reason}
    return {"mode": "live"}


async def async_apply_live_options(entry, runtime: RuntimeEntryData) -> bool:
    """Apply the preflight only when every change supports a live update."""
    plan = prepare_live_options(entry, runtime)
    if plan.reload_reason:
        return False
    if plan.polling:
        await runtime.coordinator.async_update_polling(plan.polling)
    # No await between applying prepared attributes and recording their snapshot.
    for entity, attributes, conversion_changed in plan.prepared:
        entity.apply_live_config(attributes, conversion_changed=conversion_changed)
    runtime.applied_options = plan.options
    return True
