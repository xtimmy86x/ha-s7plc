"""Pure helpers for migrating persisted config-entry entities."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .address import parse_tag

_SYNC_ENTITY_TYPES = frozenset(("switches", "lights"))


@dataclass(frozen=True)
class LegacySyncMigrationReport:
    """Describe normalization performed for one legacy sync entity."""

    sync_state_disabled: bool = False
    command_address_removed: bool = False

    @property
    def changed(self) -> bool:
        """Return whether the entity was normalized."""
        return self.sync_state_disabled or self.command_address_removed


def _sanitize_address(value: Any | None) -> str | None:
    """Match the normal entity builder's definition of an absent address."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return value.strip() or None


def _parsed_address(value: Any | None):
    """Return the parser's canonical tag representation, or ``None``."""
    sanitized = _sanitize_address(value)
    if sanitized is None:
        return None
    try:
        # pyS7's grammar is case-sensitive, while integration addresses are not.
        return parse_tag(sanitized.upper())
    except (RuntimeError, ValueError):
        return None


def canonicalize_legacy_sync_addresses(
    entity_type: str, entity: Mapping[str, Any]
) -> tuple[dict[str, Any], LegacySyncMigrationReport]:
    """Return a copy with redundant legacy switch/light sync mode disabled.

    New input must still pass the builder's strict sync validation. This helper
    is only for persisted legacy data encountered by the versioned migration.
    """
    result = deepcopy(dict(entity))
    unchanged = LegacySyncMigrationReport()
    if (
        entity_type not in _SYNC_ENTITY_TYPES
        or entity.get("sync_state") is not True
        or entity.get("pulse_command") is True
    ):
        return result, unchanged

    state_address = entity.get("state_address") or entity.get("address")
    has_command_key = "command_address" in entity
    command_present = _sanitize_address(entity.get("command_address")) is not None

    if command_present:
        state_tag = _parsed_address(state_address)
        command_tag = _parsed_address(entity.get("command_address"))
        # Invalid addresses remain untouched for normal validation to diagnose.
        if state_tag is None or command_tag is None or state_tag != command_tag:
            return result, unchanged
        result.pop("command_address", None)
    elif has_command_key:
        result.pop("command_address", None)

    result["sync_state"] = False
    return result, LegacySyncMigrationReport(
        sync_state_disabled=True,
        command_address_removed=has_command_key,
    )
