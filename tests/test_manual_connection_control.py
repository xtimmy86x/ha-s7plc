"""Tests for persisted manual PLC connection control."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

import custom_components.s7plc.__init__ as s7init
from custom_components.s7plc import config_flow, const
from custom_components.s7plc.const import CONF_MANUAL_CONNECTION_CONTROL, CONF_SWITCHES
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.entity import S7BaseEntity
from custom_components.s7plc.helpers import build_device_id
from custom_components.s7plc.switch import S7ConnectionControlSwitch, async_setup_entry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_state", "expected_enabled", "expected_connects"),
    [({"enabled": False}, False, 0), (None, True, 1)],
)
async def test_real_setup_restores_connection_control_state(
    fake_hass, stored_state, expected_enabled, expected_connects
):
    """Setup restores OFF, while an empty store follows the normal connect path."""
    entry = MagicMock()
    entry.entry_id = "entry-setup"
    entry.data = _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: True})
    entry.options = {CONF_SWITCHES: []}
    entry.add_update_listener.return_value = lambda: None
    entry.async_on_unload = MagicMock()
    store = MagicMock()
    store.async_load = AsyncMock(return_value=stored_state)
    ensure_connected = AsyncMock()
    created = []
    added = []
    real_coordinator = S7Coordinator

    def coordinator_factory(*args, **kwargs):
        coordinator = real_coordinator(*args, **kwargs)
        coordinator._ensure_connected = ensure_connected

        async def first_refresh():
            await coordinator.add_item("setup:probe", "DB1,BYTE0")

            async def read_all(*_args):
                await coordinator._ensure_connected()
                return {"setup:probe": 0}

            coordinator._read_all = read_all
            await coordinator._async_update_data()

        coordinator.async_config_entry_first_refresh = first_refresh
        created.append(coordinator)
        return coordinator

    async def forward_platforms(forward_entry, platforms):
        assert forward_entry is entry
        assert "switch" in platforms
        await async_setup_entry(fake_hass, entry, added.extend)

    fake_hass.config_entries.async_forward_entry_setups = forward_platforms
    with (
        patch.object(s7init, "Store", return_value=store),
        patch.object(s7init, "S7Coordinator", side_effect=coordinator_factory),
        patch.object(s7init, "_async_check_orphaned_entities", new=AsyncMock()),
    ):
        assert await s7init.async_setup_entry(fake_hass, entry) is True

    coordinator = created[0]
    control = next(
        entity for entity in added if isinstance(entity, S7ConnectionControlSwitch)
    )
    assert coordinator.connection_enabled is expected_enabled
    assert control.is_on is expected_enabled
    assert control._attr_available is True
    assert coordinator._client is None
    assert ensure_connected.await_count == expected_connects
    assert coordinator._write_batch_timer is None
    assert not coordinator._write_batch_buffer
    assert not coordinator._write_batch_waiters
    assert not coordinator._write_batch_inflight_waiters
    coordinator.async_set_updated_data = MagicMock()
    coordinator._drop_connection = AsyncMock()
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_disabled_coordinator_skips_polling_and_rejects_writes(fake_hass):
    coordinator = S7Coordinator(fake_hass, "192.0.2.1", connection_enabled=False)
    coordinator._items["test"] = "DB1.DBX0.0"
    coordinator._item_next_read["test"] = 0
    coordinator._ensure_connected = AsyncMock()

    assert await coordinator._async_update_data() == {}
    with pytest.raises(HomeAssistantError, match="manually disabled"):
        await coordinator.write("DB1.DBX0.0", True)
    with pytest.raises(HomeAssistantError, match="manually disabled"):
        await coordinator.write_multi([("DB1.DBX0.0", True)])
    coordinator._ensure_connected.assert_not_awaited()


@pytest.mark.asyncio
async def test_disable_closes_connection_and_cancels_retry(fake_hass):
    coordinator = S7Coordinator(
        fake_hass, "192.0.2.1", backoff_initial=60, max_retries=2
    )
    coordinator.async_set_updated_data = MagicMock()
    coordinator._ensure_connected = AsyncMock(side_effect=RuntimeError("offline"))
    coordinator._drop_connection = AsyncMock()
    retry = asyncio.create_task(coordinator._retry(lambda: None))
    await asyncio.sleep(0)

    await coordinator.async_disable_connection()

    with pytest.raises(HomeAssistantError, match="manually disabled"):
        await retry
    coordinator._drop_connection.assert_awaited()


@pytest.mark.asyncio
async def test_enable_requests_immediate_refresh_and_entries_are_independent(fake_hass):
    first = S7Coordinator(fake_hass, "192.0.2.1", connection_enabled=False)
    second = S7Coordinator(fake_hass, "192.0.2.2", connection_enabled=True)
    first.async_set_updated_data = MagicMock()
    first.async_request_refresh = AsyncMock()

    await first.async_enable_connection()

    first.async_request_refresh.assert_awaited_once()
    assert first.connection_enabled is True
    assert second.connection_enabled is True


@pytest.mark.asyncio
async def test_control_switch_created_without_normal_switches(fake_hass):
    coordinator = MagicMock()
    coordinator.connection_enabled = True
    coordinator.async_add_listener.return_value = lambda: None
    device_info = {"identifiers": {("s7plc", "test-device")}, "name": "Test PLC"}
    entry = MagicMock()
    entry.data = {CONF_MANUAL_CONNECTION_CONTROL: True}
    entry.options = {CONF_SWITCHES: []}
    entry.runtime_data.connection_state_store = MagicMock()
    add_entities = MagicMock()

    with patch(
        "custom_components.s7plc.switch.get_coordinator_and_device_info",
        return_value=(coordinator, device_info, "test-device"),
    ):
        await async_setup_entry(fake_hass, entry, add_entities)

    control = add_entities.call_args.args[0][0]
    assert isinstance(control, S7ConnectionControlSwitch)
    assert control._attr_unique_id == "test-device:connection_enable"
    assert control._attr_device_info == device_info
    assert control._attr_available is True


@pytest.mark.asyncio
async def test_control_switch_persists_off_and_on(fake_hass):
    coordinator = MagicMock()
    coordinator.connection_enabled = True
    coordinator.async_add_listener.return_value = lambda: None
    coordinator.async_disable_connection = AsyncMock(
        side_effect=lambda: setattr(coordinator, "connection_enabled", False)
    )
    coordinator.async_enable_connection = AsyncMock(
        side_effect=lambda: setattr(coordinator, "connection_enabled", True)
    )
    store = MagicMock()
    store.async_save = AsyncMock()
    control = S7ConnectionControlSwitch(
        coordinator, {}, "test-device:connection_enable", store
    )

    await control.async_turn_off()
    store.async_save.assert_awaited_with({"enabled": False})
    await control.async_turn_on()
    store.async_save.assert_awaited_with({"enabled": True})


@pytest.mark.asyncio
async def test_entities_availability_when_manually_disabled(fake_hass):
    coordinator = S7Coordinator(fake_hass, "192.0.2.1", connection_enabled=False)
    coordinator.data = {"sensor:value": 42, "availability:uid": True}
    entity = S7BaseEntity(
        coordinator,
        unique_id="uid",
        device_info={},
        topic="sensor:value",
    )

    await entity.async_configure_availability(
        {"uid": "uid", "availability_mode": "always"}
    )
    assert entity.available is True
    assert coordinator.data["sensor:value"] == 42

    await entity.async_configure_availability(
        {"uid": "uid", "availability_mode": "connection"}
    )
    assert entity.available is False

    await entity.async_configure_availability(
        {
            "uid": "uid",
            "availability_mode": "bit",
            "availability_address": "DB1,X0.0",
        }
    )
    coordinator.data[entity._availability_topic] = True
    assert entity.available is False

    control = S7ConnectionControlSwitch(
        coordinator, {}, "device:connection_enable", None
    )
    assert control._attr_available is True
    assert control.is_on is False


@pytest.mark.asyncio
async def test_disable_cancels_queued_batch_and_it_never_runs_after_enable(fake_hass):
    coordinator = S7Coordinator(fake_hass, "192.0.2.1")
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.write_multi = AsyncMock(return_value={"DB1.DBX0.0": True})

    write = asyncio.create_task(coordinator.write_batched("DB1.DBX0.0", True))
    await asyncio.sleep(0)
    await coordinator.async_disable_connection()

    with pytest.raises(HomeAssistantError, match="manually disabled"):
        await write
    assert coordinator._write_batch_timer is None
    assert not coordinator._write_batch_buffer
    assert not coordinator._write_batch_waiters

    await coordinator.async_enable_connection()
    await asyncio.sleep(coordinator._write_batch_delay * 2)
    coordinator.write_multi.assert_not_awaited()


@pytest.mark.asyncio
async def test_disable_cancels_two_concurrent_inflight_flushes(fake_hass):
    """A late pyS7 completion cannot overwrite either flush's disable error."""
    coordinator = S7Coordinator(fake_hass, "192.0.2.1")
    coordinator._write_batch_delay = 60
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    entered = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]
    calls = 0

    async def controlled_write_multi(writes):
        nonlocal calls
        call = calls
        calls += 1
        entered[call].set()
        await release[call].wait()
        return {address: True for address, _ in writes}

    coordinator.write_multi = controlled_write_multi

    write_a = asyncio.create_task(coordinator.write_batched("DB1.DBX0.0", True))
    await asyncio.sleep(0)
    flush_a = asyncio.create_task(coordinator._flush_write_batch())
    await entered[0].wait()
    write_b = asyncio.create_task(coordinator.write_batched("DB1.DBX0.1", True))
    await asyncio.sleep(0)
    flush_b = asyncio.create_task(coordinator._flush_write_batch())
    await entered[1].wait()

    assert len(coordinator._write_batch_inflight_waiters) == 2
    await coordinator.async_disable_connection()
    for write in (write_a, write_b):
        with pytest.raises(HomeAssistantError, match="manually disabled"):
            await asyncio.wait_for(write, timeout=0.1)
    assert not coordinator._write_batch_inflight_waiters

    release[0].set()
    release[1].set()
    await asyncio.gather(flush_a, flush_b)
    await coordinator.async_enable_connection()
    await asyncio.sleep(0)
    assert calls == 2
    assert not coordinator._write_batch_buffer
    assert not coordinator._write_batch_waiters
    assert not coordinator._write_batch_inflight_waiters


@pytest.mark.asyncio
async def test_repeated_disable_and_disconnect_are_idempotent(fake_hass):
    coordinator = S7Coordinator(fake_hass, "192.0.2.1")
    coordinator.async_set_updated_data = MagicMock()
    coordinator._drop_connection = AsyncMock()

    await coordinator.async_disable_connection()
    await coordinator.async_disable_connection()
    await coordinator.disconnect()
    await coordinator.disconnect()

    assert coordinator.connection_enabled is False
    assert coordinator._write_batch_timer is None
    assert not coordinator._write_batch_buffer
    assert not coordinator._write_batch_waiters
    assert not coordinator._write_batch_inflight_waiters
    assert coordinator._drop_connection.await_count == 4


@pytest.mark.asyncio
async def test_shutdown_cleans_retry_queued_and_inflight_work(fake_hass):
    coordinator = S7Coordinator(
        fake_hass, "192.0.2.1", backoff_initial=60, max_retries=2
    )
    coordinator._write_batch_delay = 60
    coordinator.async_set_updated_data = MagicMock()
    coordinator._drop_connection = AsyncMock()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_write(writes):
        entered.set()
        await release.wait()
        return {address: True for address, _ in writes}

    coordinator.write_multi = blocked_write
    retry_started = asyncio.Event()

    async def connection_failure():
        retry_started.set()
        raise RuntimeError("offline")

    coordinator._ensure_connected = connection_failure
    retry = asyncio.create_task(coordinator._retry(lambda: None))
    await retry_started.wait()
    write_inflight = asyncio.create_task(coordinator.write_batched("DB1.DBX0.0", True))
    await asyncio.sleep(0)
    flush = asyncio.create_task(coordinator._flush_write_batch())
    await entered.wait()
    write_queued = asyncio.create_task(coordinator.write_batched("DB1.DBX0.1", True))
    await asyncio.sleep(0)

    await coordinator.async_shutdown()
    for task in (retry, write_inflight, write_queued):
        with pytest.raises(HomeAssistantError, match="manually disabled"):
            await asyncio.wait_for(task, timeout=0.1)

    assert coordinator._write_batch_timer is None
    assert not coordinator._write_batch_buffer
    assert not coordinator._write_batch_waiters
    assert not coordinator._write_batch_inflight_waiters
    fake_hass.services.async_call.assert_not_called()

    release.set()
    await flush
    assert flush.done() and not flush.cancelled()


def _connection_data(**overrides):
    data = {
        "name": "PLC",
        "host": "plc.local",
        "port": const.DEFAULT_PORT,
        const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        const.CONF_PYS7_CONNECTION_TYPE: const.DEFAULT_PYS7_CONNECTION_TYPE,
        "scan_interval": const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        const.CONF_OPTIMIZE_READ: const.DEFAULT_OPTIMIZE_READ,
        const.CONF_ENABLE_WRITE_BATCHING: const.DEFAULT_ENABLE_WRITE_BATCHING,
        const.CONF_ENABLE_METRICS: const.DEFAULT_ENABLE_METRICS,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_options_only_manual_control_change_skips_offline_test():
    entry = MagicMock()
    entry.data = _connection_data()
    entry.options = {}
    entry.title = "PLC"
    entry.unique_id = "plc.local-0-1"
    entry.entry_id = "entry"
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_update_entry = MagicMock()
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass
    submitted = _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: True})

    with patch(
        "custom_components.s7plc.config_flow._test_plc_connection",
        new=AsyncMock(side_effect=OSError("offline")),
    ) as connection_test:
        result = await flow.async_step_connection(submitted)
        if asyncio.iscoroutine(result):
            result = await result

    assert result["type"] == "create_entry"
    connection_test.assert_not_awaited()
    saved = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert saved[CONF_MANUAL_CONNECTION_CONTROL] is True


@pytest.mark.asyncio
async def test_options_connection_change_still_tests_and_rejects_offline():
    entry = MagicMock()
    entry.data = _connection_data()
    entry.options = {}
    entry.title = "PLC"
    entry.unique_id = "plc.local-0-1"
    entry.entry_id = "entry"
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass
    submitted = _connection_data(port=103)

    with patch(
        "custom_components.s7plc.config_flow._test_plc_connection",
        new=AsyncMock(side_effect=OSError("offline")),
    ) as connection_test:
        result = await flow.async_step_connection(submitted)

    assert result["type"] == "form"
    assert result["kwargs"]["errors"] == {"base": "cannot_connect"}
    connection_test.assert_awaited_once()
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "requires_test"),
    [
        ("host", "plc-new.local", True),
        ("port", 103, True),
        (const.CONF_RACK, 1, True),
        (const.CONF_SLOT, 2, True),
        (const.CONF_PYS7_CONNECTION_TYPE, "op", True),
        (CONF_MANUAL_CONNECTION_CONTROL, True, False),
        ("name", "Renamed PLC", False),
        ("scan_interval", 3.0, False),
        (const.CONF_OP_TIMEOUT, 8.0, False),
        (const.CONF_MAX_RETRIES, 4, False),
        (const.CONF_BACKOFF_INITIAL, 2.0, False),
        (const.CONF_BACKOFF_MAX, 20.0, False),
        (const.CONF_OPTIMIZE_READ, False, False),
        (const.CONF_ENABLE_WRITE_BATCHING, False, False),
        (const.CONF_ENABLE_METRICS, True, False),
        (const.CONF_PLC_FAMILY, const.PLC_FAMILY_LOGO_0BA8, False),
    ],
)
async def test_rack_slot_fields_requiring_connection_test(field, value, requires_test):
    entry = MagicMock()
    entry.data = _connection_data()
    entry.options = {}
    entry.title = "PLC"
    entry.unique_id = "plc.local-0-1"
    entry.entry_id = "entry"
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_update_entry = MagicMock()
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass

    with patch.object(config_flow, "_test_plc_connection", new=AsyncMock()) as test_plc:
        result = await flow.async_step_connection(_connection_data(**{field: value}))
        if asyncio.iscoroutine(result):
            await result

    assert test_plc.await_count == int(requires_test)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "requires_test"),
    [
        ("host", "plc-new.local", True),
        ("port", 103, True),
        (const.CONF_LOCAL_TSAP, "02.00", True),
        (const.CONF_REMOTE_TSAP, "02.01", True),
        (const.CONF_PYS7_CONNECTION_TYPE, "op", True),
        ("name", "Renamed PLC", False),
        ("scan_interval", 3.0, False),
        (const.CONF_OP_TIMEOUT, 8.0, False),
        (const.CONF_MAX_RETRIES, 4, False),
        (const.CONF_BACKOFF_INITIAL, 2.0, False),
        (const.CONF_BACKOFF_MAX, 20.0, False),
        (const.CONF_OPTIMIZE_READ, False, False),
        (const.CONF_ENABLE_WRITE_BATCHING, False, False),
        (const.CONF_ENABLE_METRICS, True, False),
        (CONF_MANUAL_CONNECTION_CONTROL, True, False),
        (const.CONF_PLC_FAMILY, const.PLC_FAMILY_LOGO_0BA8, False),
    ],
)
async def test_tsap_fields_requiring_connection_test(field, value, requires_test):
    tsap_data = _connection_data(
        **{
            const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_TSAP,
            const.CONF_LOCAL_TSAP: "01.00",
            const.CONF_REMOTE_TSAP: "01.01",
        }
    )
    tsap_data.pop(const.CONF_RACK)
    tsap_data.pop(const.CONF_SLOT)
    entry = MagicMock(data=tsap_data, options={})
    entry.data = tsap_data
    entry.options = {}
    entry.title = "PLC"
    entry.unique_id = "plc.local-tsap"
    entry.entry_id = "entry"
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_update_entry = MagicMock()
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass
    submitted = {**tsap_data, field: value}

    with patch.object(config_flow, "_test_plc_connection", new=AsyncMock()) as test_plc:
        result = await flow.async_step_connection(submitted)
        if asyncio.iscoroutine(result):
            await result

    assert test_plc.await_count == int(requires_test)


@pytest.mark.asyncio
async def test_option_removal_uses_device_id_fallback_and_exact_registry_match():
    entry = MagicMock()
    entry.data = _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: True})
    entry.options = {}
    entry.title = "PLC"
    entry.unique_id = "plc.local-0-1"
    entry.entry_id = "entry"
    entry.runtime_data = None
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_update_entry = MagicMock()
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass
    device_id = build_device_id(entry.data)
    entities = [
        SimpleNamespace(
            entity_id="switch.connection",
            unique_id=f"{device_id}:connection_enable",
            platform=const.DOMAIN,
            config_entry_id="entry",
        ),
        SimpleNamespace(
            entity_id="switch.normal",
            unique_id="normal-switch-uid",
            platform=const.DOMAIN,
            config_entry_id="entry",
        ),
        SimpleNamespace(
            entity_id="switch.other_entry",
            unique_id=f"{device_id}:connection_enable",
            platform=const.DOMAIN,
            config_entry_id="other",
        ),
        SimpleNamespace(
            entity_id="switch.other_platform",
            unique_id=f"{device_id}:connection_enable",
            platform="other",
            config_entry_id="entry",
        ),
    ]
    registry = MagicMock()
    store = MagicMock()
    store.async_remove = AsyncMock()
    submitted = _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: False})

    with (
        patch.object(config_flow, "Store", return_value=store),
        patch.object(config_flow.er, "async_get", return_value=registry),
        patch.object(
            config_flow.er,
            "async_entries_for_config_entry",
            return_value=entities,
        ),
        patch.object(config_flow, "_test_plc_connection", new=AsyncMock()) as test_plc,
    ):
        result = await flow.async_step_connection(submitted)
        if asyncio.iscoroutine(result):
            result = await result

    assert result["type"] == "create_entry"
    store.async_remove.assert_awaited_once()
    registry.async_remove.assert_called_once_with("switch.connection")
    test_plc.assert_not_awaited()
    saved = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert saved[CONF_MANUAL_CONNECTION_CONTROL] is False


@pytest.mark.asyncio
async def test_manual_control_option_full_off_remove_reenable_lifecycle(fake_hass):
    """Removing the option deletes OFF state; re-enabling therefore starts ON."""
    entry = MagicMock()
    entry.entry_id = "lifecycle-entry"
    entry.title = "PLC"
    entry.unique_id = "plc.local-0-1"
    entry.options = {CONF_SWITCHES: []}
    entry.add_update_listener.return_value = lambda: None
    entry.async_on_unload = MagicMock()
    entry.data = _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: True})
    device_id = build_device_id(entry.data)
    stored_state = {"enabled": False}
    store = MagicMock()
    store.async_load = AsyncMock(side_effect=lambda: stored_state)

    async def remove_state():
        nonlocal stored_state
        stored_state = None

    store.async_remove = AsyncMock(side_effect=remove_state)
    registry_entities = [
        SimpleNamespace(
            entity_id="switch.connection",
            unique_id=f"{device_id}:connection_enable",
            platform=const.DOMAIN,
            config_entry_id=entry.entry_id,
        ),
        SimpleNamespace(
            entity_id="sensor.real_orphan",
            unique_id="genuine-orphan",
            platform=const.DOMAIN,
            config_entry_id=entry.entry_id,
        ),
    ]
    registry = MagicMock()

    def remove_entity(entity_id):
        registry_entities[:] = [
            e for e in registry_entities if e.entity_id != entity_id
        ]

    registry.async_remove.side_effect = remove_entity
    fake_hass.config_entries.async_entries.return_value = [entry]

    def update_entry(_entry, **kwargs):
        if "data" in kwargs:
            entry.data = kwargs["data"]

    fake_hass.config_entries.async_update_entry.side_effect = update_entry
    coordinators = []
    switches = []
    real_coordinator = S7Coordinator

    def coordinator_factory(*args, **kwargs):
        coordinator = real_coordinator(*args, **kwargs)
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_set_updated_data = MagicMock()
        coordinator._drop_connection = AsyncMock()
        coordinators.append(coordinator)
        return coordinator

    async def forward_platforms(_entry, _platforms):
        added = []
        await async_setup_entry(fake_hass, entry, added.extend)
        switches.extend(
            entity for entity in added if isinstance(entity, S7ConnectionControlSwitch)
        )

    fake_hass.config_entries.async_forward_entry_setups = forward_platforms

    with (
        patch.object(s7init, "Store", return_value=store),
        patch.object(config_flow, "Store", return_value=store),
        patch.object(s7init, "S7Coordinator", side_effect=coordinator_factory),
        patch.object(s7init.er, "async_get", return_value=registry),
        patch.object(
            s7init.er,
            "async_entries_for_config_entry",
            side_effect=lambda *_: list(registry_entities),
        ),
        patch.object(s7init.ir, "async_create_issue") as create_issue,
    ):
        # Persisted OFF is restored on the first setup.
        assert await s7init.async_setup_entry(fake_hass, entry)
        assert coordinators[-1].connection_enabled is False
        assert switches[-1].is_on is False
        create_issue.reset_mock()

        # Disable the option: storage and only the exact switch are removed.
        flow = config_flow.S7PLCOptionsFlow(entry)
        flow.hass = fake_hass
        result = await flow.async_step_connection(
            _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: False})
        )
        if asyncio.iscoroutine(result):
            await result
        store.async_remove.assert_awaited_once()
        registry.async_remove.assert_called_once_with("switch.connection")
        assert [e.entity_id for e in registry_entities] == ["sensor.real_orphan"]

        # Cleanup preceded orphan checking: only the genuine orphan is reported.
        await s7init._async_check_orphaned_entities(fake_hass, entry, coordinators[-1])
        create_issue.assert_called_once()
        placeholders = create_issue.call_args.kwargs["translation_placeholders"]
        assert "sensor.real_orphan" in placeholders["entity_list"]
        assert "switch.connection" not in placeholders["entity_list"]

        # Reload without manual control implicitly enables communication.
        switches.clear()
        assert await s7init.async_setup_entry(fake_hass, entry)
        assert coordinators[-1].connection_enabled is True
        assert not switches

        # Re-enable and reload with the now-empty Store: switch starts ON.
        flow = config_flow.S7PLCOptionsFlow(entry)
        flow.hass = fake_hass
        result = await flow.async_step_connection(
            _connection_data(**{CONF_MANUAL_CONNECTION_CONTROL: True})
        )
        if asyncio.iscoroutine(result):
            await result
        assert stored_state is None
        assert await s7init.async_setup_entry(fake_hass, entry)
        assert coordinators[-1].connection_enabled is True
        assert switches[-1].is_on is True

    for coordinator in coordinators:
        await coordinator.async_shutdown()
