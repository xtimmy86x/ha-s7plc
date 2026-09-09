from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
import voluptuous as vol
from conftest import DummyCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc import const


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


def test_update_listener_applies_area_to_new_entity_after_reload(monkeypatch):
    """Test that areas are applied after newly imported entities are created."""
    hass = HomeAssistant()

    entry = DummyConfigEntry(
        options={
            const.CONF_SENSORS: [
                {
                    const.CONF_ADDRESS: "DB1,REAL0",
                    const.CONF_AREA: "kitchen",
                    const.CONF_UID: "sensor-uid-1",
                }
            ]
        },
        entry_id="entry1",
    )

    entry.runtime_data = s7init.RuntimeEntryData(
        coordinator=None,
        name="Test PLC",
        host="plc.local",
        device_id="test-device",
    )

    class FakeEntityRegistry:
        def __init__(self):
            self.entity_available = False
            self.updated = []

        def async_get_entity_id(self, platform, domain, unique_id):
            if (
                self.entity_available
                and domain == const.DOMAIN
                and unique_id == "sensor-uid-1"
            ):
                return "sensor.imported_sensor"
            return None

        def async_update_entity(self, entity_id, **kwargs):
            self.updated.append((entity_id, kwargs))

    entity_registry = FakeEntityRegistry()

    monkeypatch.setattr(
        s7init.er,
        "async_get",
        lambda hass: entity_registry,
    )

    async def fake_reload(entry_id):
        assert entry_id == "entry1"

        # Simulate the entity being created during integration reload.
        entity_registry.entity_available = True

    hass.config_entries.async_reload = fake_reload

    asyncio.run(s7init._async_update_listener(hass, entry))

    assert entity_registry.updated == [
        (
            "sensor.imported_sensor",
            {"area_id": "kitchen"},
        )
    ]


@pytest.fixture
def service_schemas(monkeypatch):
    """Capture the real schemas registered during integration setup."""
    hass = HomeAssistant()
    register = Mock(wraps=hass.services.async_register)
    monkeypatch.setattr(hass.services, "async_register", register)
    monkeypatch.setattr(s7init, "S7Coordinator", DummyCoordinator)
    entry = DummyConfigEntry(data={s7init.CONF_HOST: "plc.local"}, entry_id="entry1")
    assert asyncio.run(s7init.async_setup_entry(hass, entry)) is True
    try:
        assert register.call_count == 2
        yield {
            key: registration["schema"]
            for key, registration in hass._services_registry.items()
        }
    finally:
        assert asyncio.run(s7init.async_unload_entry(hass, entry)) is True


def test_service_schemas_accept_valid_payloads_without_changing_values(service_schemas):
    assert set(service_schemas) == {"s7plc.health_check", "s7plc.write_multi"}
    health_payload = {"entry_id": "entry1"}
    assert service_schemas["s7plc.health_check"](health_payload) == health_payload
    payload = {
        "entry_id": "entry1",
        "writes": [
            {"address": "DB1,X0.0", "value": False},
            {"address": "DB1,REAL4", "value": 1.5},
            {"address": "DB1,INT8", "value": 0},
            {"address": "DB1,S10.8", "value": "hello"},
        ],
    }
    assert service_schemas["s7plc.write_multi"](payload) == payload
    # The schema leaves datatype validation to the write pipeline.
    empty_batch = {"entry_id": "entry1", "writes": []}
    assert service_schemas["s7plc.write_multi"](empty_batch) == empty_batch


@pytest.mark.parametrize(
    "service,payload,error_path",
    [
        ("health_check", {}, ["entry_id"]),
        ("health_check", {"entry_id": 1}, ["entry_id"]),
        ("health_check", {"entry_id": "entry1", "extra": True}, ["extra"]),
        ("write_multi", {"writes": []}, ["entry_id"]),
        ("write_multi", {"entry_id": 1, "writes": []}, ["entry_id"]),
        ("write_multi", {"entry_id": "entry1"}, ["writes"]),
        ("write_multi", {"entry_id": "entry1", "writes": {}}, ["writes"]),
        ("write_multi", {"entry_id": "entry1", "writes": [None]}, ["writes", 0]),
        (
            "write_multi",
            {"entry_id": "entry1", "writes": [{"value": 0}]},
            ["writes", 0, "address"],
        ),
        (
            "write_multi",
            {"entry_id": "entry1", "writes": [{"address": "DB1,INT0"}]},
            ["writes", 0, "value"],
        ),
        (
            "write_multi",
            {"entry_id": "entry1", "writes": [{"address": 1, "value": 0}]},
            ["writes", 0, "address"],
        ),
        (
            "write_multi",
            {
                "entry_id": "entry1",
                "writes": [{"address": "DB1,INT0", "value": 0, "extra": True}],
            },
            ["writes", 0, "extra"],
        ),
    ],
)
def test_service_schemas_reject_malformed_payloads(
    service_schemas, service, payload, error_path
):
    with pytest.raises(vol.Invalid) as exc:
        service_schemas[f"s7plc.{service}"](payload)
    assert exc.value.path == error_path


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

    # A uid was assigned and persisted.
    assert len(update_calls) == 1
    new_options = update_calls[0][1]["options"]
    sensor_item = new_options["sensors"][0]
    assert sensor_item["uid"] == "s7plc-plc.local-0-1:sensor:DB1,REAL0"
    # The item's own address/name are untouched.
    assert sensor_item["address"] == "DB1,REAL0"
    assert sensor_item["name"] == "Legacy Sensor"


def test_migrate_uid_backfill_is_a_noop_once_uid_present(monkeypatch):
    """No further migration once every item already has a uid."""
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
    assert entry.options["sensors"][0]["uid"] == "already-set"
    