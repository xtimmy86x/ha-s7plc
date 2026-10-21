"""Preview/apply via HA's real WebSocket schema, registry and config listener."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er


async def request(ws, entry, targets, changes, *, token=None, msg_id=1):
    message = {
        "id": msg_id,
        "type": (
            "s7plc/config/preview_update_entities"
            if token is None
            else "s7plc/config/update_entities"
        ),
        "entry_id": entry.entry_id,
        "entities": targets,
        "changes": changes,
    }
    if token is not None:
        message["preview_token"] = token
    await ws.send_json(message)
    return await ws.receive_json()


@pytest.mark.parametrize("other_type", ["numbers", "binary_sensors"])
async def test_preview_then_one_save_uses_live_or_one_reload(
    hass, config_entry, plc_client, hass_ws_client, other_type
):
    options = deepcopy(dict(config_entry.options))
    options["sensors"].append({"uid": "keep", "address": "DB1,INT2"})
    address = "DB1,INT4" if other_type == "numbers" else "DB1,X4.0"
    options[other_type] = [{"uid": "other", "address": address}]
    hass.config_entries.async_update_entry(config_entry, options=options)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    runtime = config_entry.runtime_data
    coord = runtime.coordinator
    await coord.async_refresh()
    reads = plc_client.read.await_count
    area = ar.async_get(hass).async_create("Machine room")
    targets = [
        {"entity_type": "sensors", "uid": "temperature"},
        {"entity_type": other_type, "uid": "other"},
    ]
    changes = {"area": area.id, "scan_interval": 10.5}
    ws = await hass_ws_client(hass)
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        response = await request(ws, config_entry, targets, changes)
        assert response["success"]
        preview = response["result"]
        assert preview["changed_count"] == 2
        assert config_entry.options == options
        update.assert_not_called()
        assert plc_client.read.await_count == reads
        response = await request(
            ws, config_entry, targets, changes, token=preview["preview_token"], msg_id=2
        )
        assert response["success"]
        assert response["result"] == {"updated": 2}
        await hass.async_block_till_done()
        assert update.call_count == 1
    assert config_entry.options["sensors"][1] == options["sensors"][1]
    entity = config_entry.runtime_data.coordinator.config_entities["temperature"]
    assert er.async_get(hass).async_get(entity.entity_id).area_id == area.id
    assert (
        config_entry.runtime_data.coordinator.get_scan_interval(entity._topic) == 10.5
    )
    if other_type == "numbers":
        assert config_entry.runtime_data is runtime
        assert plc_client.read.await_count == reads
        assert plc_client.connect.await_count == 1
        plc_client.disconnect.assert_not_awaited()
    else:
        assert config_entry.runtime_data is not runtime
        await config_entry.runtime_data.coordinator.async_refresh()
        assert plc_client.connect.await_count == 2
        assert plc_client.disconnect.await_count == 1
    plc_client.write.assert_not_awaited()


async def test_clear_area_and_scan_restores_defaults_without_reconnecting(
    hass, loaded_entry, hass_ws_client, plc_client
):
    entry = loaded_entry
    runtime = entry.runtime_data
    entity = runtime.coordinator.config_entities["temperature"]
    area = ar.async_get(hass).async_create("Workshop")
    targets = [{"entity_type": "sensors", "uid": "temperature"}]
    ws = await hass_ws_client(hass)
    for index, changes in enumerate(
        [{"area": area.id, "scan_interval": 2}, {"area": None, "scan_interval": None}]
    ):
        response = await request(ws, entry, targets, changes, msg_id=index * 2 + 1)
        assert response["success"]
        response = await request(
            ws,
            entry,
            targets,
            changes,
            token=response["result"]["preview_token"],
            msg_id=index * 2 + 2,
        )
        assert response["success"]
        await hass.async_block_till_done()
    assert "area" not in entry.options["sensors"][0]
    assert "scan_interval" not in entry.options["sensors"][0]
    assert er.async_get(hass).async_get(entity.entity_id).area_id is None
    assert (
        runtime.coordinator.get_scan_interval(entity._topic)
        == entry.data["scan_interval"]
    )
    assert entry.runtime_data is runtime
    assert plc_client.connect.await_count == 1
    plc_client.disconnect.assert_not_awaited()


@pytest.mark.parametrize(
    "conflict", ["other_edit", "requested_changes", "removed_target", "removed_area"]
)
async def test_stale_preview_is_atomic(hass, loaded_entry, hass_ws_client, conflict):
    entry = loaded_entry
    area = ar.async_get(hass).async_create("Workshop")
    targets = [{"entity_type": "sensors", "uid": "temperature"}]
    changes = {"area": area.id}
    ws = await hass_ws_client(hass)
    response = await request(ws, entry, targets, changes)
    token = response["result"]["preview_token"]
    if conflict == "other_edit":
        hass.config_entries.async_update_entry(
            entry,
            options={"sensors": [{**entry.options["sensors"][0], "scan_interval": 12}]},
        )
    elif conflict == "requested_changes":
        changes = {"scan_interval": 2}
    elif conflict == "removed_target":
        hass.config_entries.async_update_entry(entry, options={"sensors": []})
    else:
        ar.async_get(hass).async_delete(area.id)
    await hass.async_block_till_done()
    current = deepcopy(dict(entry.options))
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        response = await request(ws, entry, targets, changes, token=token, msg_id=2)
        assert not response["success"]
        assert response["error"]["code"] in {
            "bulk_edit_conflict",
            "invalid_selection",
            "invalid_bulk_area",
        }
        update.assert_not_called()
    assert entry.options == current


async def test_unchanged_apply_does_not_save_or_reload(
    hass, loaded_entry, hass_ws_client
):
    targets = [{"entity_type": "sensors", "uid": "temperature"}]
    ws = await hass_ws_client(hass)
    response = await request(ws, loaded_entry, targets, {"area": None})
    preview = response["result"]
    assert preview["changed_count"] == 0
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        response = await request(
            ws,
            loaded_entry,
            targets,
            {"area": None},
            token=preview["preview_token"],
            msg_id=2,
        )
        assert response["result"] == {"updated": 0}
        update.assert_not_called()


@pytest.mark.parametrize("applying", [False, True])
async def test_preview_and_apply_require_admin(
    hass, loaded_entry, hass_ws_client, hass_read_only_access_token, applying
):
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    original = loaded_entry.options
    response = await request(
        ws,
        loaded_entry,
        [{"entity_type": "sensors", "uid": "temperature"}],
        {"area": None},
        token="0" * 64 if applying else None,
    )
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"
    assert loaded_entry.options == original


@pytest.mark.parametrize(
    "overrides",
    [
        {"changes": {"name": "unsupported"}},
        {"changes": {}},
        {"entities": []},
        {"changes": {"scan_interval": True}},
        {"changes": {"scan_interval": -1}},
        {"changes": {"scan_interval": 3601}},
        {"changes": {"scan_interval": "2"}},
        {"changes": {"area": "deleted"}},
        {"entities": [{"entity_type": "sensors", "uid": "missing"}]},
        {"type": "s7plc/config/update_entities"},
    ],
)
async def test_bad_requests_cannot_save(hass, loaded_entry, hass_ws_client, overrides):
    ws = await hass_ws_client(hass)
    original = loaded_entry.options
    await ws.send_json(
        {
            "id": 1,
            "type": "s7plc/config/preview_update_entities",
            "entry_id": loaded_entry.entry_id,
            "entities": [{"entity_type": "sensors", "uid": "temperature"}],
            "changes": {"scan_interval": 2},
            **overrides,
        }
    )
    assert not (await ws.receive_json())["success"]
    assert loaded_entry.options == original
