"""Exercise real pyS7 string decoding and HA entity availability together."""

import struct

import pytest
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pyS7.constants import READ_RES_OVERHEAD, DataType
from pyS7.requests import WriteRequest
from pyS7.responses import parse_optimized_read_response, parse_read_response

from custom_components.s7plc.const import (
    CONF_ENABLE_WRITE_BATCHING,
    CONF_MAX_RETRIES,
    CONF_OPTIMIZE_READ,
    DOMAIN,
)
from custom_components.s7plc.plc.address import parse_tag


@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize("invalid_on_setup", [False, True])
async def test_latin1_and_invalid_wstring_only_affect_their_own_entities(
    hass, config_entry, plc_client, freezer, optimize, invalid_on_setup
):
    """Keep a healthy session, publish other readings and recover on the next poll."""
    memory = {"temperature": 21, "wide": None if invalid_on_setup else "Ready"}

    def read(tags, *, optimize):
        (tag,) = tags
        if tag.data_type == DataType.INT:
            payload = struct.pack(">h", memory["temperature"])
        elif tag.data_type == DataType.STRING:
            # Same DB/type/length as issue #205, including bytes B0 and FC.
            raw = b"Rezept 25\xb0C k\xfchl"
            payload = bytes([tag.length, len(raw)]) + raw.ljust(tag.length, b"\x00")
        else:
            assert tag.data_type == DataType.WSTRING
            text = memory["wide"]
            # An unpaired UTF-16 surrogate in a complete, correctly sized item.
            raw = b"\xd8\x00" if text is None else text.encode("utf-16-be")
            payload = struct.pack(">HH", tag.length, 1 if text is None else len(text))
            payload += raw.ljust(2 * tag.length, b"\x00")
        response = bytes(READ_RES_OVERHEAD)
        response += b"\xff\x04" + struct.pack(">H", len(payload) * 8) + payload
        if optimize:
            return parse_optimized_read_response([response], [{tag: [(0, tag)]}])
        return parse_read_response(response, [tag])

    plc_client.read.side_effect = read
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_OPTIMIZE_READ: optimize, CONF_MAX_RETRIES: 3},
        options={
            "sensors": [
                {"uid": "temperature", "name": "Temperature", "address": "DB1,INT0"},
                {"uid": "wide", "name": "Wide label", "address": "DB1,WS4.12"},
                {"uid": "recipe", "name": "Recipe", "address": "DB1013,S0.26"},
                {
                    "uid": "always_wide",
                    "name": "Always wide",
                    "address": "DB1,WS4.12",
                    "availability_mode": "always",
                },
            ]
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coord = config_entry.runtime_data.coordinator
    await coord.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def state(uid):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, uid)
        return hass.states.get(entity_id).state

    assert state("temperature") == "21"
    assert state("recipe") == "Rezept 25°C kühl"
    assert state("wide") == (STATE_UNAVAILABLE if invalid_on_setup else "Ready")
    assert state("always_wide") == (STATE_UNKNOWN if invalid_on_setup else "Ready")
    reads_before = plc_client.read.await_count
    connects_before = plc_client.connect.await_count

    memory.update(temperature=22, wide=None)
    freezer.tick(3601)
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert state("temperature") == "22"
    assert state("wide") == STATE_UNAVAILABLE
    assert state("always_wide") == STATE_UNKNOWN
    assert state("recipe") == "Rezept 25°C kühl"
    assert coord.last_update_success
    assert coord.last_health_ok is True
    assert coord.is_connected()
    # Three distinct topics: both wide entities share the same failed reading.
    assert plc_client.read.await_count == reads_before + 3
    plc_client.disconnect.assert_not_awaited()
    assert plc_client.connect.await_count == connects_before
    control_id = registry.async_get_entity_id(
        "switch", DOMAIN, f"{config_entry.runtime_data.device_id}:connection_enable"
    )
    assert hass.states.get(control_id).state == STATE_ON

    # Empty text is a valid recovered value, distinct from failed decoding.
    memory.update(temperature=23, wide="")
    freezer.tick(3601)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert state("temperature") == "23"
    assert state("wide") == ""
    assert state("always_wide") == ""
    assert coord.last_update_success
    plc_client.disconnect.assert_not_awaited()
    assert plc_client.connect.await_count == connects_before


@pytest.mark.parametrize("batching", [False, True])
async def test_text_service_rejects_unencodable_value_and_accepts_latin1(
    hass, config_entry, plc_client, batching
):
    """HA surfaces a failed write while the next valid service call still works."""
    plc_client.read.side_effect = lambda tags, **kwargs: ["Ready"] * len(tags)
    packets = []

    def write(tags, values):
        packets.append(WriteRequest(tags, values).serialize())

    plc_client.write.side_effect = write
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ENABLE_WRITE_BATCHING: batching},
        options={
            "texts": [{"uid": "recipe", "name": "Recipe", "address": "DB1013,S0.26"}]
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coord = config_entry.runtime_data.coordinator
    await coord.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("text", DOMAIN, "recipe")
    assert hass.states.get(entity_id).state == "Ready"
    connects_before = plc_client.connect.await_count

    with pytest.raises((HomeAssistantError, ValueError)):
        await hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": entity_id, "value": "10 €"},
            blocking=True,
        )
    plc_client.write.assert_not_awaited()
    plc_client.disconnect.assert_not_awaited()
    assert coord.is_connected()

    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": entity_id, "value": "25°C kühl"},
        blocking=True,
    )
    plc_client.write.assert_awaited_once_with(
        [parse_tag("DB1013,S0.26")], ["25°C kühl"]
    )
    assert b"25\xb0C k\xfchl" in packets[0]
    plc_client.disconnect.assert_not_awaited()
    assert plc_client.connect.await_count == connects_before
