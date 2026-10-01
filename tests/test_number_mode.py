"""Number display modes survive configuration without changing PLC values."""

import pytest
from homeassistant.components.number import NumberMode

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.export import build_export_payload
from custom_components.s7plc.number import async_setup_entry
from custom_components.s7plc.panel import _configuration_from_yaml, _configuration_yaml


@pytest.mark.parametrize("mode", [None, "", " ", "auto", "box", "slider", " box "])
def test_number_mode_validation_and_yaml_round_trip(mode):
    source = {
        "address": "DB1,R0",
        "min_value": 0,
        "max_value": 20,
        "step": 0.1,
        "mode": mode,
    }
    item, errors = build_entity_item("numbers", source, options={})
    assert not errors
    expected = mode.strip() if mode else "auto"
    if expected in ("box", "slider"):
        assert item["mode"] == expected
    else:
        assert "mode" not in item
    options = {"numbers": [item]}
    assert build_export_payload(options)["numbers"] == [item]
    restored = _configuration_from_yaml(_configuration_yaml(options), {})["numbers"][0]
    for key in ("mode", "min_value", "max_value", "step"):
        assert restored.get(key) == item.get(key)


@pytest.mark.parametrize("mode", ["invalid", "BOX", 0, False, [], {}])
def test_number_mode_rejects_invalid_values(mode):
    item, errors = build_entity_item(
        "numbers", {"address": "DB1,W0", "mode": mode}, options={}
    )
    assert item is None
    assert errors == {"base": "invalid_number_mode"}


def test_display_mode_is_only_a_number_option():
    with pytest.raises(ValueError, match="mode"):
        build_entity_item("sensors", {"address": "DB1,W0", "mode": "box"}, options={})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (None, NumberMode.AUTO),
        ("auto", NumberMode.AUTO),
        ("box", NumberMode.BOX),
        ("slider", NumberMode.SLIDER),
        ("invalid", NumberMode.AUTO),
    ],
)
async def test_number_setup_applies_mode(
    mode, expected, mock_coordinator, fake_hass, dummy_entry, monkeypatch
):
    monkeypatch.setattr(
        "custom_components.s7plc.number.get_coordinator_and_device_info",
        lambda entry: (mock_coordinator, {}, "device"),
    )
    item = {
        "address": "DB1,W0",
        "uid": "number-mode",
        "min_value": 0,
        "max_value": 20,
        "step": 0.1,
    }
    if mode is not None:
        item["mode"] = mode
    added = []
    await async_setup_entry(
        fake_hass, dummy_entry(options={"numbers": [item]}), added.extend
    )
    assert len(added) == 1
    entity = added[0]
    assert entity.mode == expected
    assert entity.native_min_value == 0
    assert entity.native_max_value == 20
    assert entity._attr_native_step == 0.1
