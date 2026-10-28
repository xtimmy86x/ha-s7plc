"""Dual-output commands through real HA services, reload and PLC batching."""

import asyncio
from unittest.mock import call

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.s7plc.const import CONF_ENABLE_WRITE_BATCHING, DOMAIN
from custom_components.s7plc.plc.address import parse_tag


@pytest.mark.parametrize("platform", ["switch", "light"])
@pytest.mark.parametrize("feedback", [True, False])
@pytest.mark.parametrize("batching", [True, False])
async def test_dual_pulse_services_reload_and_feedback(
    hass, config_entry, plc_client, freezer, platform, feedback, batching
):
    item = {
        "uid": "dual",
        "name": "Dual output",
        "command_address": "Q1.0",
        "off_command_address": "Q1.1",
        "pulse_command": True,
        "pulse_duration": 0.1,
    }
    if feedback:
        item["state_address"] = "I1.3"
    entity_type = "lights" if platform == "light" else "switches"
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ENABLE_WRITE_BATCHING: batching},
        options={entity_type: [item]},
    )
    plc_client.read.side_effect = lambda tags, **kwargs: [False] * len(tags)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, "dual")
    assert hass.states.get(entity_id).state == (
        STATE_OFF if feedback else STATE_UNKNOWN
    )
    assert hass.states.get(entity_id).attributes["pulse_command"] is True
    if not feedback:
        assert hass.states.get(entity_id).attributes["assumed_state"] is True
        plc_client.read.assert_not_awaited()
    plc_client.write.reset_mock()

    activated = asyncio.Event()

    async def write(tags, values):
        if values == [True]:
            activated.set()

    plc_client.write.side_effect = write
    for service in ("turn_on", "turn_off"):
        activated.clear()
        command = asyncio.create_task(
            hass.services.async_call(
                platform, service, {"entity_id": entity_id}, blocking=True
            )
        )
        await activated.wait()
        # HA freezes monotonic time; advance the real pulse timer explicitly.
        freezer.tick(1)
        await command
        if not feedback:
            assert hass.states.get(entity_id).state == (
                STATE_ON if service == "turn_on" else STATE_OFF
            )
    assert plc_client.write.await_args_list == [
        call([parse_tag("Q1.0")], [True]),
        call([parse_tag("Q1.0")], [False]),
        call([parse_tag("Q1.1")], [True]),
        call([parse_tag("Q1.1")], [False]),
    ]
    if feedback:
        plc_client.read.side_effect = lambda tags, **kwargs: [True] * len(tags)
        freezer.tick(3601)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_ON
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    assert er.async_get(hass).async_get_entity_id(platform, DOMAIN, "dual") == entity_id
    assert config_entry.options == {entity_type: [item]}
    if not feedback:
        assert hass.states.get(entity_id).state == STATE_UNKNOWN
        plc_client.read.assert_not_awaited()


async def test_unload_waits_for_active_pulse_reset(
    hass, config_entry, plc_client, freezer
):
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "switches": [
                {
                    "uid": "dual",
                    "command_address": "Q1.0",
                    "off_command_address": "Q1.1",
                    "pulse_command": True,
                    "pulse_duration": 0.1,
                }
            ]
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, "dual")
    started, release = asyncio.Event(), asyncio.Event()
    events = []

    async def write(tags, values):
        events.append(values[0])
        if values == [True]:
            started.set()
            await release.wait()

    disconnect = plc_client.disconnect.side_effect

    async def record_disconnect():
        events.append("disconnect")
        await disconnect()

    plc_client.write.side_effect = write
    plc_client.disconnect.side_effect = record_disconnect
    command = asyncio.create_task(
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": entity_id}, blocking=True
        )
    )
    await started.wait()
    unload = asyncio.create_task(
        hass.config_entries.async_unload(config_entry.entry_id)
    )
    # Let HA start removal while transport acknowledgement is still pending.
    await asyncio.sleep(0)
    release.set()
    await asyncio.sleep(0)
    freezer.tick(1)
    assert await unload
    await command
    assert events == [True, False, "disconnect"]
