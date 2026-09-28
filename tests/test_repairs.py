"""Tests for S7 PLC repairs."""

import asyncio
from dataclasses import dataclass

import pytest

from custom_components.s7plc import repairs
from custom_components.s7plc.const import DOMAIN


@dataclass
class RuntimeEntryData:
    """Mock runtime data."""
    coordinator: object
    name: str
    host: str
    device_id: str


@pytest.fixture
def entry_with_orphans(monkeypatch):
    """Create a config entry with orphaned entities."""
    import sys

    from conftest import ConfigEntry, HomeAssistant
    
    # Get MockEntityRegistryEntry from the mock module
    MockEntityRegistryEntry = sys.modules["homeassistant.helpers.entity_registry"].MockEntityRegistryEntry
    from homeassistant.helpers import entity_registry as er
    
    hass = HomeAssistant()
    
    # Create config entry
    entry = ConfigEntry(
        data={
            "host": "192.168.1.10",
            "rack": 0,
            "slot": 1,
        },
        options={
            "sensors": [
                {"address": "DB1,REAL0", "name": "Active Sensor", "uid": "s1"}
            ],
            "switches": [
                {"state_address": "DB1,X0.0", "name": "Active Switch", "uid": "sw1"}
            ],
        },
        entry_id="test_entry",
    )
    
    # Setup runtime data on the entry
    entry.runtime_data = RuntimeEntryData(
        coordinator=None,
        name="Test PLC",
        host="192.168.1.10",
        device_id="test_device",
    )
    
    # Add config entry to hass
    hass.config_entries._entries.append(entry)
    
    # Create entity registry with some entities
    entity_reg = er.async_get(hass)
    
    # Add active entities (should NOT be removed)
    entity_reg.entities["sensor.active_sensor"] = MockEntityRegistryEntry(
        entity_id="sensor.active_sensor",
        unique_id="s1",
        config_entry_id="test_entry",
    )
    entity_reg.entities["switch.active_switch"] = MockEntityRegistryEntry(
        entity_id="switch.active_switch",
        unique_id="sw1",
        config_entry_id="test_entry",
    )
    entity_reg.entities["binary_sensor.connection"] = MockEntityRegistryEntry(
        entity_id="binary_sensor.connection",
        unique_id="test_device:connection",
        config_entry_id="test_entry",
    )

    # Add orphaned entities (should be removed) - uids not present in options
    entity_reg.entities["sensor.old_sensor"] = MockEntityRegistryEntry(
        entity_id="sensor.old_sensor",
        unique_id="test_device:old-sensor-uid",
        config_entry_id="test_entry",
    )
    entity_reg.entities["switch.old_switch"] = MockEntityRegistryEntry(
        entity_id="switch.old_switch",
        unique_id="test_device:old-switch-uid",
        config_entry_id="test_entry",
    )
    
    return hass, entry, entity_reg


def test_orphaned_entities_repair_flow_init():
    """Test repair flow initialization."""
    flow = repairs.OrphanedEntitiesRepairFlow("test_entry_id")
    assert flow.entry_id == "test_entry_id"


def test_async_step_init_redirects_to_confirm():
    """Test that init step redirects to confirm."""
    flow = repairs.OrphanedEntitiesRepairFlow("test_entry_id")
    
    # Mock the async_step_confirm method
    confirm_called = False
    
    async def mock_confirm(user_input=None):
        nonlocal confirm_called
        confirm_called = True
        return {"type": "form"}
    
    flow.async_step_confirm = mock_confirm
    
    asyncio.run(flow.async_step_init())
    assert confirm_called


def test_async_step_confirm_shows_form_without_input(entry_with_orphans):
    """Test that confirm step shows form when no input provided."""
    hass, entry, _ = entry_with_orphans
    flow = repairs.OrphanedEntitiesRepairFlow(entry.entry_id)
    flow.hass = hass
    flow.async_show_form = lambda step_id: {"type": "form", "step_id": step_id}
    
    result = asyncio.run(flow.async_step_confirm(user_input=None))
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"


def test_async_step_confirm_removes_orphans(entry_with_orphans):
    """Test that confirm step removes orphaned entities."""
    hass, entry, entity_reg = entry_with_orphans
    
    flow = repairs.OrphanedEntitiesRepairFlow(entry.entry_id)
    flow.hass = hass
    flow.async_create_entry = lambda data: {"type": "create_entry", "data": data}
    
    # Before removal - should have 5 entities
    assert len(entity_reg.entities) == 5
    
    result = asyncio.run(flow.async_step_confirm(user_input={}))
    
    # After removal - should have 3 entities (2 orphans removed)
    assert len(entity_reg.entities) == 3
    assert "sensor.active_sensor" in entity_reg.entities
    assert "switch.active_switch" in entity_reg.entities
    assert "binary_sensor.connection" in entity_reg.entities
    assert "sensor.old_sensor" not in entity_reg.entities
    assert "switch.old_switch" not in entity_reg.entities
    
    assert result["type"] == "create_entry"


@pytest.mark.parametrize("user_input", [None, {}])
def test_async_step_confirm_completes_if_entry_not_found(user_input):
    """A stale repair completes so HA's flow manager removes the issue."""
    from conftest import HomeAssistant
    
    hass = HomeAssistant()
    hass.data[DOMAIN] = {}
    
    flow = repairs.OrphanedEntitiesRepairFlow("nonexistent_entry")
    flow.hass = hass
    flow.async_create_entry = lambda data: {"type": "create_entry", "data": data}
    
    result = asyncio.run(flow.async_step_confirm(user_input=user_input))
    assert result["type"] == "create_entry"
    assert result["data"] == {}


def test_entry_removed_while_repair_form_is_open(entry_with_orphans):
    """Confirming after entry removal must finish without touching entities."""
    hass, entry, entity_reg = entry_with_orphans
    flow = repairs.OrphanedEntitiesRepairFlow(entry.entry_id)
    flow.hass = hass
    flow.async_show_form = lambda step_id: {"type": "form", "step_id": step_id}
    flow.async_create_entry = lambda data: {"type": "create_entry", "data": data}

    assert asyncio.run(flow.async_step_init())["type"] == "form"
    hass.config_entries._entries.remove(entry)
    before = dict(entity_reg.entities)

    assert asyncio.run(flow.async_step_confirm({}))["type"] == "create_entry"
    assert entity_reg.entities == before


@pytest.mark.parametrize("keep_entities", [False, True])
def test_check_clears_stale_repair_without_orphans(
    entry_with_orphans, monkeypatch, keep_entities
):
    """Clear obsolete issues even when the entity registry is empty."""
    from unittest.mock import Mock

    import custom_components.s7plc as integration

    hass, entry, entity_reg = entry_with_orphans
    entity_reg.async_remove("sensor.old_sensor")
    entity_reg.async_remove("switch.old_switch")
    if not keep_entities:
        entity_reg.entities.clear()
    delete_issue = Mock()
    create_issue = Mock()
    monkeypatch.setattr(integration.ir, "async_delete_issue", delete_issue)
    monkeypatch.setattr(integration.ir, "async_create_issue", create_issue)

    asyncio.run(integration._async_check_orphaned_entities(hass, entry, None))

    delete_issue.assert_called_once_with(
        hass, DOMAIN, f"orphaned_entities_{entry.entry_id}"
    )
    create_issue.assert_not_called()


def test_remove_entry_only_clears_its_own_repair(entry_with_orphans, monkeypatch):
    """Removal is scoped to the PLC and works without runtime data."""
    import custom_components.s7plc as integration

    hass, entry, _ = entry_with_orphans
    issue_key = (DOMAIN, f"orphaned_entities_{entry.entry_id}")
    other_key = (DOMAIN, "orphaned_entities_other_plc")
    issues = {issue_key, other_key}
    monkeypatch.setattr(
        integration.ir,
        "async_delete_issue",
        lambda hass, domain, issue_id: issues.discard((domain, issue_id)),
    )
    del entry.runtime_data

    asyncio.run(integration.async_remove_entry(hass, entry))
    asyncio.run(integration.async_remove_entry(hass, entry))

    assert issues == {other_key}


def test_unload_preserves_pending_repair(entry_with_orphans, monkeypatch):
    """Unloading for a reload must not clear an unresolved issue."""
    from unittest.mock import AsyncMock, Mock

    import custom_components.s7plc as integration

    hass, entry, _ = entry_with_orphans
    hass.data[DOMAIN] = {}
    entry.runtime_data.coordinator = Mock(async_shutdown=AsyncMock())
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    delete_issue = Mock()
    monkeypatch.setattr(integration.ir, "async_delete_issue", delete_issue)

    assert asyncio.run(integration.async_unload_entry(hass, entry))
    delete_issue.assert_not_called()


def test_get_expected_unique_ids_all_entity_types(entry_with_orphans):
    """Test that all entity types are included in expected unique IDs."""
    hass, entry, _ = entry_with_orphans
    
    # Add all entity types to config
    entry.options = {
        "sensors": [{"address": "DB1,REAL0", "uid": "uid-sensor"}],
        "binary_sensors": [{"address": "DB1,X0.0", "uid": "uid-binary"}],
        "switches": [{"state_address": "DB1,X0.1", "uid": "uid-switch"}],
        "covers": [
            {"position_state_address": "DB1,INT0", "uid": "uid-cover-pos"},  # Position cover
            {
                "open_command_address": "DB1,X1.0",
                "close_command_address": "DB1,X1.1",
                "opening_state_address": "DB1,X1.2",
                "uid": "uid-cover-trad",
            },  # Traditional cover
        ],
        "buttons": [{"address": "DB1,X2.0", "uid": "uid-button"}],
        "lights": [
            {"state_address": "DB1,X2.1", "uid": "uid-light-1"},
            {"state_address": "DB1,B10", "brightness_scale": 255, "uid": "uid-light-2"},
        ],
        "numbers": [{"address": "DB1,INT10", "uid": "uid-number"}],
        "texts": [{"address": "DB1,STRING0", "uid": "uid-text"}],
        "entity_sync": [
            {"address": "DB1,REAL100", "source_entity": "sensor.test", "uid": "uid-sync"}
        ],
    }

    flow = repairs.OrphanedEntitiesRepairFlow(entry.entry_id)
    flow.hass = hass

    expected = asyncio.run(flow._get_expected_unique_ids(entry))

    assert "uid-sensor" in expected
    assert "uid-binary" in expected
    assert "uid-switch" in expected
    assert "uid-cover-pos" in expected
    assert "uid-cover-trad" in expected
    assert "uid-button" in expected
    assert "uid-light-1" in expected
    assert "uid-light-2" in expected
    assert "uid-number" in expected
    assert "uid-text" in expected
    assert "uid-sync" in expected
    assert "test_device:connection" in expected


def test_get_expected_unique_ids_traditional_cover_variants():
    """Test traditional cover unique ID generation with different state addresses."""
    from conftest import ConfigEntry, HomeAssistant
    
    hass = HomeAssistant()
    
    # Test with opened_state
    entry = ConfigEntry(
        options={
            "covers": [
                {
                    "open_command_address": "DB1,X0.0",
                    "close_command_address": "DB1,X0.1",
                    "opening_state_address": "DB1,X0.2",
                    "uid": "uid-opened",
                }
            ]
        },
        entry_id="test1",
    )
    entry.runtime_data = RuntimeEntryData(
        coordinator=None, name="PLC1", host="192.168.1.1", device_id="dev1"
    )
    hass.data[DOMAIN] = {}
    hass.config_entries._entries.append(entry)

    flow = repairs.OrphanedEntitiesRepairFlow("test1")
    flow.hass = hass
    expected = asyncio.run(flow._get_expected_unique_ids(entry))
    assert "uid-opened" in expected

    # Test with closed_state only
    entry2 = ConfigEntry(
        options={
            "covers": [
                {
                    "open_command_address": "DB1,X0.0",
                    "close_command_address": "DB1,X0.1",
                    "closing_state_address": "DB1,X0.3",
                    "uid": "uid-closed",
                }
            ]
        },
        entry_id="test2",
    )
    entry2.runtime_data = RuntimeEntryData(
        coordinator=None, name="PLC2", host="192.168.1.2", device_id="dev2"
    )
    hass.config_entries._entries.append(entry2)

    flow2 = repairs.OrphanedEntitiesRepairFlow("test2")
    flow2.hass = hass
    expected2 = asyncio.run(flow2._get_expected_unique_ids(entry2))
    assert "uid-closed" in expected2

    # Test with command only (no state addresses)
    entry3 = ConfigEntry(
        options={
            "covers": [
                {
                    "open_command_address": "DB1,X0.0",
                    "close_command_address": "DB1,X0.1",
                    "uid": "uid-command",
                }
            ]
        },
        entry_id="test3",
    )
    entry3.runtime_data = RuntimeEntryData(
        coordinator=None, name="PLC3", host="192.168.1.3", device_id="dev3"
    )
    hass.config_entries._entries.append(entry3)

    flow3 = repairs.OrphanedEntitiesRepairFlow("test3")
    flow3.hass = hass
    expected3 = asyncio.run(flow3._get_expected_unique_ids(entry3))
    assert "uid-command" in expected3


def test_async_create_fix_flow_extracts_entry_id():
    """Test that async_create_fix_flow extracts entry_id from issue_id."""
    from conftest import HomeAssistant
    
    hass = HomeAssistant()
    issue_id = "orphaned_entities_test_entry_123"
    
    flow = asyncio.run(repairs.async_create_fix_flow(hass, issue_id, None))
    
    assert isinstance(flow, repairs.OrphanedEntitiesRepairFlow)
    assert flow.entry_id == "test_entry_123"
