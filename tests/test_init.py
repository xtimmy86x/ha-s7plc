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


def test_async_setup_creates_domain_storage():
    hass = HomeAssistant()
    assert asyncio.run(s7init.async_setup(hass, {})) is True
    assert const.DOMAIN in hass.data


def test_async_setup_entry_initialises_coordinator(monkeypatch):
    hass = HomeAssistant()

    forward_calls = []

    async def fake_forward(entry, platforms):
        forward_calls.append((entry.entry_id, tuple(platforms)))

    unload_calls = []

    async def fake_unload(entry, platforms):
        unload_calls.append((entry.entry_id, tuple(platforms)))
        return True

    hass.config_entries.async_forward_entry_setups = fake_forward
    hass.config_entries.async_unload_platforms = fake_unload
    
    # Mock services
    from unittest.mock import MagicMock
    service_calls = []
    def fake_async_register(domain, service, handler, schema=None):
        service_calls.append((domain, service))
    hass.services = MagicMock()
    hass.services.async_register = fake_async_register

    created = []

    def fake_coordinator(*args, **kwargs):
        obj = DummyCoordinator(*args, **kwargs)
        created.append(obj)
        return obj

    monkeypatch.setattr(s7init, "S7Coordinator", fake_coordinator)

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
            s7init.CONF_PORT: 102,
            s7init.CONF_SCAN_INTERVAL: 2,
            s7init.CONF_NAME: "Test PLC",
            s7init.CONF_OP_TIMEOUT: 7.5,
            s7init.CONF_MAX_RETRIES: 5,
            s7init.CONF_BACKOFF_INITIAL: 1.0,
            s7init.CONF_BACKOFF_MAX: 6.0,
            s7init.CONF_OPTIMIZE_READ: True,
        },
        entry_id="entry1",
    )

    async def fake_async_add_executor_job(func, *args, **kwargs):
        return func(*args, **kwargs)

    hass.async_add_executor_job = fake_async_add_executor_job

    assert asyncio.run(s7init.async_setup_entry(hass, entry)) is True

    assert created, "Coordinator should be instantiated"
    coordinator_obj = created[0]
    assert coordinator_obj.refresh_called
    # After migration to runtime_data, coordinator is stored there
    assert entry.runtime_data.coordinator is coordinator_obj
    assert forward_calls == [("entry1", tuple(const.PLATFORMS))]

    unload_ok = asyncio.run(s7init.async_unload_entry(hass, entry))
    assert unload_ok is True
    assert ("entry1", tuple(const.PLATFORMS)) in unload_calls
    assert coordinator_obj.disconnected


def test_update_listener_triggers_reload():
    hass = HomeAssistant()
    entry = DummyConfigEntry()

    reload_called = []

    async def fake_reload(entry_id):
        reload_called.append(entry_id)

    hass.config_entries.async_reload = fake_reload

    asyncio.run(s7init._async_update_listener(hass, entry))
    assert reload_called == [entry.entry_id]


def test_write_multi_service_registration(monkeypatch):
    """Test that write_multi service is registered."""
    hass = HomeAssistant()
    
    service_calls = []
    def fake_async_register(*args, **kwargs):
        # args[0] = self (the services object)
        # args[1] = domain
        # args[2] = service
        # args[3] = handler
        if len(args) >= 3:
            service_calls.append((args[1], args[2]))
    hass.services = type('obj', (object,), {'async_register': fake_async_register})()

    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)
    
    def fake_coordinator(*args, **kwargs):
        obj = DummyCoordinator(*args, **kwargs)
        return obj
    
    monkeypatch.setattr(s7init, "S7Coordinator", fake_coordinator)
    
    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
        },
        entry_id="entry1",
    )
    
    hass.async_add_executor_job = lambda func, *args, **kwargs: func(*args, **kwargs)
    
    asyncio.run(s7init.async_setup_entry(hass, entry))
    
    # Should register both health_check and write_multi services
    assert len(service_calls) == 2, f"Expected 2 services, got {len(service_calls)}: {service_calls}"
    registered_services = [s for (d, s) in service_calls]
    assert "health_check" in registered_services, f"health_check not in {registered_services}"
    assert "write_multi" in registered_services, f"write_multi not in {registered_services}"


def test_migrate_backfills_uid_for_legacy_items(monkeypatch):
    """Legacy items with no 'uid' get one assigned, matching their current
    (address-based) unique_id, so the entity's identity doesn't change."""
    hass = HomeAssistant()

    hass.services = type(
        "obj", (object,), {"async_register": lambda *a, **k: None}
    )()

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
        },
        options={
            "sensors": [{"address": "DB1,REAL0", "name": "Legacy Sensor"}],
        },
        entry_id="test_uid_backfill",
    )

    update_calls = []

    def fake_update_entry(entry, **kwargs):
        update_calls.append((entry.entry_id, kwargs))

    hass.config_entries.async_update_entry = fake_update_entry
    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)

    monkeypatch.setattr(
        s7init, "S7Coordinator", lambda *a, **k: DummyCoordinator(*a, **k)
    )

    asyncio.run(s7init.async_setup_entry(hass, entry))

    # A "no uid values need a device_id prefix" marker call fires first
    # (nothing to prefix, since this item never had a uid at all), then a
    # uid was assigned and persisted for the legacy address-based item.
    assert len(update_calls) == 2
    assert update_calls[0][1]["data"][s7init.CONF_UID_DEVICE_PREFIX_MIGRATED] is True
    assert "options" not in update_calls[0][1]
    new_options = update_calls[1][1]["options"]
    sensor_item = new_options["sensors"][0]
    assert sensor_item["uid"] == "s7plc-plc.local-0-1:sensor:DB1,REAL0"
    # The item's own address/name are untouched.
    assert sensor_item["address"] == "DB1,REAL0"
    assert sensor_item["name"] == "Legacy Sensor"


def test_migrate_uid_backfill_is_a_noop_once_uid_present(monkeypatch):
    """No further migration once every item already has a fully-qualified,
    device_id-prefixed uid and the entry is marked as already migrated."""
    hass = HomeAssistant()

    hass.services = type(
        "obj", (object,), {"async_register": lambda *a, **k: None}
    )()

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
            s7init.CONF_UID_DEVICE_PREFIX_MIGRATED: True,
        },
        options={
            "sensors": [
                {
                    "address": "DB1,REAL0",
                    "name": "Sensor",
                    "uid": "s7plc-plc.local-0-1:already-set",
                }
            ],
        },
        entry_id="test_uid_noop",
    )

    update_calls = []

    def fake_update_entry(entry, **kwargs):
        update_calls.append((entry.entry_id, kwargs))

    hass.config_entries.async_update_entry = fake_update_entry
    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)

    monkeypatch.setattr(
        s7init, "S7Coordinator", lambda *a, **k: DummyCoordinator(*a, **k)
    )

    asyncio.run(s7init.async_setup_entry(hass, entry))

    assert len(update_calls) == 0
    assert entry.options["sensors"][0]["uid"] == "s7plc-plc.local-0-1:already-set"


def test_migrate_uid_device_prefix_upgrades_legacy_short_uid(monkeypatch):
    """Regression test: an entry created by an earlier build, where 'uid'
    stored only the device-relative suffix, gets that suffix upgraded to the
    complete unique_id on first startup with the new code — otherwise every
    existing entity would silently get a new, mismatched unique_id and the
    orphaned-entity repair flow would flag all of them at once."""
    hass = HomeAssistant()

    hass.services = type(
        "obj", (object,), {"async_register": lambda *a, **k: None}
    )()

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
        },
        options={
            "sensors": [
                {"address": "DB1,REAL0", "name": "Sensor", "uid": "already-set"}
            ],
        },
        entry_id="test_uid_legacy_prefix",
    )

    update_calls = []

    def fake_update_entry(entry, **kwargs):
        update_calls.append((entry.entry_id, kwargs))

    hass.config_entries.async_update_entry = fake_update_entry
    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)

    monkeypatch.setattr(
        s7init, "S7Coordinator", lambda *a, **k: DummyCoordinator(*a, **k)
    )

    asyncio.run(s7init.async_setup_entry(hass, entry))

    # A single combined update: the short uid is upgraded in place (so the
    # entity keeps its exact existing unique_id) and the migration is
    # marked done, both in one call since ensure_item_uids has nothing left
    # to do for an item that already has a uid.
    assert len(update_calls) == 1
    kwargs = update_calls[0][1]
    assert kwargs["data"][s7init.CONF_UID_DEVICE_PREFIX_MIGRATED] is True
    assert kwargs["options"]["sensors"][0]["uid"] == "s7plc-plc.local-0-1:already-set"


def test_migrate_folds_legacy_scale_fields_into_address_at_startup(monkeypatch):
    """A sensor still using the old separate scale/min/max keys gets them
    folded into an inline Scale(...) address suffix on first startup, and
    the four legacy keys are removed."""
    hass = HomeAssistant()

    hass.services = type(
        "obj", (object,), {"async_register": lambda *a, **k: None}
    )()

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
            # Already migrated to a device_id-prefixed uid, so this test can
            # focus purely on scale-field folding.
            s7init.CONF_UID_DEVICE_PREFIX_MIGRATED: True,
        },
        options={
            "sensors": [
                {
                    "address": "DB6,B23",
                    "name": "Legacy Scaled Sensor",
                    "uid": "already-set",
                    "scale_raw_min": 0.0,
                    "scale_raw_max": 1.0,
                    "min_value": 0.0,
                    "max_value": 10.0,
                }
            ],
        },
        entry_id="test_scale_migration",
    )

    update_calls = []

    def fake_update_entry(entry, **kwargs):
        update_calls.append((entry.entry_id, kwargs))

    hass.config_entries.async_update_entry = fake_update_entry
    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)

    monkeypatch.setattr(
        s7init, "S7Coordinator", lambda *a, **k: DummyCoordinator(*a, **k)
    )

    asyncio.run(s7init.async_setup_entry(hass, entry))

    # uid migration was a no-op (already migrated); only the scale migration
    # fired.
    assert len(update_calls) == 1
    new_options = update_calls[0][1]["options"]
    sensor_item = new_options["sensors"][0]
    assert sensor_item["address"] == "DB6,B23 Scale(0,1,0,10)"
    assert "scale_raw_min" not in sensor_item
    assert "scale_raw_max" not in sensor_item
    assert "min_value" not in sensor_item
    assert "max_value" not in sensor_item


def test_migrate_folds_legacy_brightness_scale_into_address_at_startup(monkeypatch):
    """A light still using the old brightness_scale key gets it folded into
    an inline Scale(...) address suffix on first startup, and the legacy
    key is removed."""
    hass = HomeAssistant()

    hass.services = type(
        "obj", (object,), {"async_register": lambda *a, **k: None}
    )()

    entry = DummyConfigEntry(
        data={
            s7init.CONF_HOST: "plc.local",
            s7init.CONF_RACK: 0,
            s7init.CONF_SLOT: 1,
            # Already migrated to a device_id-prefixed uid, so this test can
            # focus purely on brightness-scale folding.
            s7init.CONF_UID_DEVICE_PREFIX_MIGRATED: True,
        },
        options={
            "lights": [
                {
                    "state_address": "DB1,X0.0",
                    "name": "Legacy Dimmer",
                    "uid": "already-set",
                    "brightness_state_address": "DB1,B0",
                    "brightness_scale": 100,
                }
            ],
        },
        entry_id="test_brightness_scale_migration",
    )

    update_calls = []

    def fake_update_entry(entry, **kwargs):
        update_calls.append((entry.entry_id, kwargs))

    hass.config_entries.async_update_entry = fake_update_entry
    hass.config_entries.async_forward_entry_setups = lambda e, p: asyncio.sleep(0)

    monkeypatch.setattr(
        s7init, "S7Coordinator", lambda *a, **k: DummyCoordinator(*a, **k)
    )

    asyncio.run(s7init.async_setup_entry(hass, entry))

    # uid migration was a no-op (already migrated); only the brightness-scale
    # migration fired.
    assert len(update_calls) == 1
    new_options = update_calls[0][1]["options"]
    light_item = new_options["lights"][0]
    assert light_item["brightness_state_address"] == "DB1,B0 Scale(0,100,0,255)"
    assert "brightness_scale" not in light_item
