"""Load the configuration panel through Home Assistant's actual WebSocket API."""

from homeassistant.const import UnitOfArea


async def test_panel_list_serializes_real_unit_catalogs(
    hass, loaded_entry, hass_ws_client
):
    """Real sensor/number catalogs mix unit enums with unitless None values."""
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "s7plc/config/list"})
    response = await ws.receive_json()

    assert response["success"], response
    entry = next(
        item for item in response["result"] if item["entry_id"] == loaded_entry.entry_id
    )
    assert entry["entities"]["sensors"][0]["uid"] == "temperature"
    selectors = entry["selector_options"]
    units = selectors["units"]
    assert {UnitOfArea.SQUARE_METERS.value, "°C", "kWh"} <= set(units)
    assert all(type(unit) is str for unit in units)
    assert units == sorted(set(units))
    assert "None" not in units
    assert "temperature" in selectors["device_classes"]["sensors"]
    assert selectors["state_classes"] == ["measurement", "total", "total_increasing"]
