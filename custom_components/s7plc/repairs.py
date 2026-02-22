"""Repairs for S7 PLC integration."""

from __future__ import annotations

import logging

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
        if user_input is not None:
            # Get the entity registry
            entity_reg = er.async_get(self.hass)

            # Get all entities for this config entry
            entities = er.async_entries_for_config_entry(entity_reg, self.entry_id)

            # Get expected unique_ids from config
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not entry:
                return self.async_abort(reason="entry_not_found")

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
        expected_unique_ids = set()
        device_id = entry.runtime_data.device_id
        options = entry.options

        # Sensors
        for item in options.get("sensors", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:sensor:{address}")

        # Binary sensors
        for item in options.get("binary_sensors", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:binary_sensor:{address}")

        # Switches
        for item in options.get("switches", []):
            state_addr = item.get("state_address", "")
            if state_addr:
                expected_unique_ids.add(f"{device_id}:switch:{state_addr}")

        # Covers
        for item in options.get("covers", []):
            position_state = item.get("position_state_address")
            if position_state:
                expected_unique_ids.add(f"{device_id}:cover:position:{position_state}")
            else:
                open_command = item.get("open_command_address", "")
                opened_state = item.get("opening_state_address")
                closed_state = item.get("closing_state_address")

                if opened_state:
                    expected_unique_ids.add(f"{device_id}:cover:opened:{opened_state}")
                elif closed_state:
                    expected_unique_ids.add(f"{device_id}:cover:closed:{closed_state}")
                elif open_command:
                    expected_unique_ids.add(f"{device_id}:cover:command:{open_command}")

        # Buttons
        for item in options.get("buttons", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:button:{address}")

        # Lights
        for item in options.get("lights", []):
            state_addr = item.get("state_address", "")
            if state_addr:
                if "brightness_scale" in item:
                    expected_unique_ids.add(f"{device_id}:dimmer_light:{state_addr}")
                else:
                    expected_unique_ids.add(f"{device_id}:light:{state_addr}")

        # Numbers
        for item in options.get("numbers", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:number:{address}")

        # Texts
        for item in options.get("texts", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:text:{address}")

        # Entity syncs
        for item in options.get("entity_sync", []):
            address = item.get("address", "")
            if address:
                expected_unique_ids.add(f"{device_id}:entity_sync:{address}")

        # Connection status
        expected_unique_ids.add(f"{device_id}:connection")

        return expected_unique_ids


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    # Extract entry_id from issue_id (format: "orphaned_entities_{entry_id}")
    entry_id = issue_id.replace("orphaned_entities_", "")
    return OrphanedEntitiesRepairFlow(entry_id)
