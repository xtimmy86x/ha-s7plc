"""Repairs for S7 PLC integration."""

from __future__ import annotations

import logging

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .helpers import build_expected_unique_ids

_LOGGER = logging.getLogger(__name__)


class OrphanedEntitiesRepairFlow(RepairsFlow):
    """Handler for orphaned entities repair."""

    def __init__(self, entry_id: str) -> None:
        """Initialize the repair flow."""
        self.entry_id = entry_id
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step."""
        # Check both when opening the repair and when confirming it: the entry
        # may have been removed while the confirmation form was open.
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry is None:
            # Successful completion lets HA remove this now-obsolete issue.
            return self.async_create_entry(data={})

        if user_input is not None:
            # Get the entity registry
            entity_reg = er.async_get(self.hass)

            # Get all entities for this config entry
            entities = er.async_entries_for_config_entry(entity_reg, self.entry_id)

            # Get expected unique_ids from config
            expected_unique_ids = await self._get_expected_unique_ids(entry)

            # Remove orphaned entities
            removed_count = 0
            for entity in entities:
                if entity.unique_id not in expected_unique_ids:
                    entity_reg.async_remove(entity.entity_id)
                    removed_count += 1
                    _LOGGER.info(
                        "Removed orphaned entity: %s (unique_id: %s)",
                        entity.entity_id,
                        entity.unique_id,
                    )

            _LOGGER.info(
                "Removed %d orphaned entity(ies) for config entry %s",
                removed_count,
                self.entry_id,
            )

            return self.async_create_entry(data={})

        return self.async_show_form(step_id="confirm")

    async def _get_expected_unique_ids(self, entry) -> set[str]:
        """Get the set of expected unique IDs from configuration."""
        return build_expected_unique_ids(
            entry.runtime_data.device_id, entry.options, data=entry.data
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    # Extract entry_id from issue_id (format: "orphaned_entities_{entry_id}")
    entry_id = issue_id.replace("orphaned_entities_", "")
    return OrphanedEntitiesRepairFlow(entry_id)
