"""Tests for persisted manual PLC connection control."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc import config_flow, const
from custom_components.s7plc.const import CONF_MANUAL_CONNECTION_CONTROL, CONF_SWITCHES
from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.switch import S7ConnectionControlSwitch, async_setup_entry


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
