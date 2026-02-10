"""Tests for service registration and deregistration lifecycle."""

from __future__ import annotations

import asyncio

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc import const
from conftest import DummyCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class DummyConfigEntry(ConfigEntry):
    def __init__(self, data=None, options=None, entry_id="test"):
        super().__init__()
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id
        self._on_unload = []

    def async_on_unload(self, callback):
        """Override to return None instead of coroutine."""
        self._on_unload.append(callback)
        return None


def test_services_registered_once_and_removed_with_last_entry(monkeypatch):
    """Test that services are registered once and removed when last entry is unloaded."""
    hass = HomeAssistant()
    
    # Initialize domain storage
    asyncio.run(s7init.async_setup(hass, {}))
    
    # Mock async_forward_entry_setups
    forward_calls = []
    async def fake_forward(entry, platforms):
        forward_calls.append((entry.entry_id, tuple(platforms)))
    hass.config_entries.async_forward_entry_setups = fake_forward
    
    # Mock async_unload_platforms
    async def fake_unload(entry, platforms):
        return True
    hass.config_entries.async_unload_platforms = fake_unload
    
    # Mock coordinator
    def fake_coordinator(*args, **kwargs):
        coordinator = DummyCoordinator(*args, **kwargs)
        coordinator.async_config_entry_first_refresh = lambda: asyncio.sleep(0)
        return coordinator
    monkeypatch.setattr(s7init, "S7Coordinator", fake_coordinator)
    
    # Mock _async_check_orphaned_entities
    async def fake_check_orphaned(*args, **kwargs):
        pass
    monkeypatch.setattr(s7init, "_async_check_orphaned_entities", fake_check_orphaned)
    
    # Create first entry
    entry1 = DummyConfigEntry(
        data={
            "host": "192.168.1.1",
            "port": 102,
            "rack": 0,
            "slot": 1,
            "name": "PLC 1",
        },
        options={},
        entry_id="entry1"
    )
    
    # Setup first entry
    asyncio.run(s7init.async_setup_entry(hass, entry1))
    
    # Services should be registered
    assert hass.services.has_service(const.DOMAIN, "health_check")
    assert hass.services.has_service(const.DOMAIN, "write_multi")
    assert hass.data[const.DOMAIN].get("_services_registered") is True
    
    # Create second entry
    entry2 = DummyConfigEntry(
        data={
            "host": "192.168.1.2",
            "port": 102,
            "rack": 0,
            "slot": 1,
            "name": "PLC 2",
        },
        options={},
        entry_id="entry2"
    )
    
    # Setup second entry
    asyncio.run(s7init.async_setup_entry(hass, entry2))
    
    # Services should still be registered (only registered once)
    assert hass.services.has_service(const.DOMAIN, "health_check")
    assert hass.services.has_service(const.DOMAIN, "write_multi")
    
    # Mock async_entries to return both entries initially
    def mock_async_entries(domain):
        if domain == const.DOMAIN:
            return [entry1, entry2]
        return []
    hass.config_entries.async_entries = mock_async_entries
    
    # Unload first entry
    asyncio.run(s7init.async_unload_entry(hass, entry1))
    
    # Services should still be registered (second entry still loaded)
    assert hass.services.has_service(const.DOMAIN, "health_check")
    assert hass.services.has_service(const.DOMAIN, "write_multi")
    assert hass.data[const.DOMAIN].get("_services_registered") is True
    
    # Mock async_entries to return only entry2 (entry1 removed)
    def mock_async_entries_after_first_unload(domain):
        if domain == const.DOMAIN:
            return [entry2]
        return []
    hass.config_entries.async_entries = mock_async_entries_after_first_unload
    
    # Unload second entry (last one)
    asyncio.run(s7init.async_unload_entry(hass, entry2))
    
    # Services should now be unregistered
    assert not hass.services.has_service(const.DOMAIN, "health_check")
    assert not hass.services.has_service(const.DOMAIN, "write_multi")
    assert hass.data[const.DOMAIN].get("_services_registered") is None


def test_services_deregistered_on_single_entry_unload(monkeypatch):
    """Test that services are removed when the only entry is unloaded."""
    hass = HomeAssistant()
    
    # Initialize domain storage
    asyncio.run(s7init.async_setup(hass, {}))
    
    # Mock async_forward_entry_setups
    async def fake_forward(entry, platforms):
        pass
    hass.config_entries.async_forward_entry_setups = fake_forward
    
    # Mock async_unload_platforms
    async def fake_unload(entry, platforms):
        return True
    hass.config_entries.async_unload_platforms = fake_unload
    
    # Mock coordinator
    def fake_coordinator(*args, **kwargs):
        coordinator = DummyCoordinator(*args, **kwargs)
        coordinator.async_config_entry_first_refresh = lambda: asyncio.sleep(0)
        return coordinator
    monkeypatch.setattr(s7init, "S7Coordinator", fake_coordinator)
    
    # Mock _async_check_orphaned_entities
    async def fake_check_orphaned(*args, **kwargs):
        pass
    monkeypatch.setattr(s7init, "_async_check_orphaned_entities", fake_check_orphaned)
    
    # Create single entry
    entry = DummyConfigEntry(
        data={
            "host": "192.168.1.1",
            "port": 102,
            "rack": 0,
            "slot": 1,
            "name": "PLC",
        },
        options={},
        entry_id="entry1"
    )
    
    # Setup entry
    asyncio.run(s7init.async_setup_entry(hass, entry))
    
    # Services should be registered
    assert hass.services.has_service(const.DOMAIN, "health_check")
    assert hass.services.has_service(const.DOMAIN, "write_multi")
    
    # Mock async_entries to return only this entry
    def mock_async_entries(domain):
        if domain == const.DOMAIN:
            return [entry]
        return []
    hass.config_entries.async_entries = mock_async_entries
    
    # Unload the entry
    asyncio.run(s7init.async_unload_entry(hass, entry))
    
    # Services should be unregistered
    assert not hass.services.has_service(const.DOMAIN, "health_check")
    assert not hass.services.has_service(const.DOMAIN, "write_multi")
    assert hass.data[const.DOMAIN].get("_services_registered") is None
