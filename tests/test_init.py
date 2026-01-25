from __future__ import annotations

import asyncio

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc import const
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class DummyCoordinator:
    def __init__(
        self,
        hass,
        host,
        connection_type,
        rack,
        slot,
        local_tsap,
        remote_tsap,
        pys7_connection_type,
        port,
        scan_interval,
        op_timeout,
        max_retries,
        backoff_initial,
        backoff_max,
        optimize_read,
        enable_write_batching,
    ):
        self.hass = hass
        self.host = host
        self.connection_type = connection_type
        self.rack = rack
        self.slot = slot
        self.local_tsap = local_tsap
        self.remote_tsap = remote_tsap
        self.pys7_connection_type = pys7_connection_type
        self._pys7_connection_type_str = pys7_connection_type
        self.port = port
        self.scan_interval = scan_interval
        self.op_timeout = op_timeout
        self.max_retries = max_retries
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.optimize_read = optimize_read
        self.enable_write_batching = enable_write_batching
        self.connected = False
        self.disconnected = False
        self.refresh_called = False

    async def async_config_entry_first_refresh(self):
        self.refresh_called = True

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.disconnected = True


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
    assert hass.data[const.DOMAIN][entry.entry_id]["coordinator"] is coordinator_obj
    assert forward_calls == [("entry1", tuple(const.PLATFORMS))]

    unload_ok = asyncio.run(s7init.async_unload_entry(hass, entry))
    assert unload_ok is True
    assert ("entry1", tuple(const.PLATFORMS)) in unload_calls
    assert coordinator_obj.disconnected
    assert entry.entry_id not in hass.data.get(const.DOMAIN, {})


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
