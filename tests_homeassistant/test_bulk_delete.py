"""The admin bulk command makes one update and one reload across entity types."""

from unittest.mock import patch


async def test_bulk_delete_one_reload(hass, config_entry, plc_client, hass_ws_client):
    options = dict(config_entry.options)
    options["sensors"] = [*options["sensors"], {"uid": "keep", "address": "DB1,INT2"}]
    options["numbers"] = [{"uid": "setpoint", "address": "DB1,INT4"}]
    hass.config_entries.async_update_entry(config_entry, options=options)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    await runtime.coordinator.async_refresh()
    ws = await hass_ws_client(hass)
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        await ws.send_json(
            {
                "id": 1,
                "type": "s7plc/config/delete_entities",
                "entry_id": config_entry.entry_id,
                "entities": [
                    {"entity_type": "sensors", "uid": "temperature"},
                    {"entity_type": "numbers", "uid": "setpoint"},
                ],
            }
        )
        response = await ws.receive_json()
        assert response["success"]
        assert response["result"] == {"deleted": 2}
        await hass.async_block_till_done()
        assert update.call_count == 1
    assert config_entry.options["sensors"] == [{"uid": "keep", "address": "DB1,INT2"}]
    assert config_entry.options["numbers"] == []
    assert config_entry.runtime_data is not runtime
    await config_entry.runtime_data.coordinator.async_refresh()
    assert plc_client.connect.await_count == 2
    assert plc_client.disconnect.await_count == 1


async def test_bulk_delete_requires_admin(
    hass, loaded_entry, hass_ws_client, hass_read_only_access_token
):
    original = loaded_entry.options
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json(
        {
            "id": 1,
            "type": "s7plc/config/delete_entities",
            "entry_id": loaded_entry.entry_id,
            "entities": [{"entity_type": "sensors", "uid": "temperature"}],
        }
    )
    response = await ws.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"
    assert loaded_entry.options == original
