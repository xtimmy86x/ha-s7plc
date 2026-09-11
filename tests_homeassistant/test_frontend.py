"""Exercise dashboard resources and HTTP delivery with real Home Assistant."""

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.setup import async_setup_component

from custom_components.s7plc.frontend import (
    SCHEDULE_CARD_MODULE,
    SCHEDULE_CARD_PATH,
    async_setup_dashboard,
)


async def test_schedule_card_loaded_on_setup_and_reload(
    hass, loaded_entry, hass_ws_client, hass_client
):
    modules = hass.data[DATA_EXTRA_MODULE_URL]
    assert SCHEDULE_CARD_MODULE in modules.urls
    await async_setup_dashboard(hass)
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert list(modules.urls).count(SCHEDULE_CARD_MODULE) == 1

    # This is the list requested by dashboards and by the Resources UI. An
    # extra frontend module alone is insufficient evidence of this contract.
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "lovelace/resources"})
    response = await ws.receive_json()
    assert response["success"]
    assert [item["url"] for item in response["result"]] == [SCHEDULE_CARD_MODULE]
    assert response["result"][0]["type"] == "module"

    client = await hass_client()
    asset = await client.get(SCHEDULE_CARD_MODULE)
    assert asset.status == 200
    assert asset.content_type in ("text/javascript", "application/javascript")
    assert "customElements.define(\"s7plc-schedule-card\"" in await asset.text()


async def test_existing_resource_updated_without_duplicates(
    hass, hass_storage, config_entry, plc_client
):
    hass_storage["lovelace_resources"] = {
        "version": 1,
        "data": {
            "items": [
                {"id": "schedule", "url": f"{SCHEDULE_CARD_PATH}?v=old", "type": "js"},
                {"id": "other", "url": "/local/other-card.js", "type": "module"},
            ]
        },
    }
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    resources = hass.data[LOVELACE_DATA].resources
    expected = [
        {"id": "schedule", "url": SCHEDULE_CARD_MODULE, "type": "module"},
        {"id": "other", "url": "/local/other-card.js", "type": "module"},
    ]
    assert resources.async_items() == expected
    await async_setup_dashboard(hass)
    assert resources.async_items() == expected


async def test_yaml_resources_use_extra_module_without_modifying_yaml(
    hass, config_entry, plc_client
):
    configured = [{"url": "/local/user-card.js", "type": "module"}]
    assert await async_setup_component(
        hass, "lovelace", {"lovelace": {"resource_mode": "yaml", "resources": configured}}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[LOVELACE_DATA].resources.async_items() == configured
    assert SCHEDULE_CARD_MODULE in hass.data[DATA_EXTRA_MODULE_URL].urls
