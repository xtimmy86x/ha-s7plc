"""LOGO clock Number configuration, PLC feedback and write regressions."""

from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.number import async_setup_entry
from custom_components.s7plc.sensor import S7EntitySync


@pytest.mark.parametrize("command_address", [None, "DB1,WORD6"])
@pytest.mark.asyncio
async def test_logo_number_setup_reads_and_writes_hhmm(
    mock_coordinator, fake_hass, monkeypatch, command_address
):
    config = {
        "address": "DB1,WORD4",
        "value_conversions": {"value": {"type": "logo_time_bcd"}},
    }
    if command_address:
        config["command_address"] = command_address
    item, errors = build_entity_item("numbers", config, options={})
    assert errors == {}
    assert item is not None
    item["uid"] = "logo-clock"
    monkeypatch.setattr(
        "custom_components.s7plc.number.get_coordinator_and_device_info",
        lambda entry: (mock_coordinator, {}, "logo"),
    )
    entities = []
    await async_setup_entry(
        fake_hass, SimpleNamespace(options={"numbers": [item]}), entities.extend
    )
    entity = entities[0]
    entity.hass = fake_hass
    assert entity.native_min_value == 0
    assert entity.native_max_value == 2359
    assert entity._attr_native_step == 1

    # Feedback always comes from the state address; reading must never write.
    topic = "number:DB1,WORD4"
    mock_coordinator.data = {topic: 0x0830}
    assert entity.native_value == 830
    mock_coordinator.data[topic] = 0x1245
    assert entity.native_value == 1245
    assert mock_coordinator.write_calls == []

    await entity.async_set_native_value(2359.0)
    assert mock_coordinator.write_calls == [
        ("write_batched", command_address or "DB1,WORD4", 0x2359)
    ]
    assert mock_coordinator.refresh_count == 2  # Setup and explicit HA command.

    for invalid in (860, 2399, 830.5):
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(invalid)
    assert len(mock_coordinator.write_calls) == 1

    mock_coordinator.data[topic] = 0x0A30
    assert entity.native_value is None
    mock_coordinator.data[topic] = 0x0400
    assert entity.native_value == 400
    assert len(mock_coordinator.write_calls) == 1


@pytest.mark.parametrize("field", ["address", "command_address"])
def test_logo_number_requires_word_on_both_addresses(field):
    item, errors = build_entity_item(
        "numbers",
        {
            "address": "DB1,WORD4",
            "command_address": "DB1,WORD6",
            field: "DB1,DWORD8",
            "value_conversions": {"value": {"type": "logo_time_bcd"}},
        },
        options={},
    )
    assert item is None
    assert "WORD" in errors["base"]


def test_logo_number_effective_default_limits_match_runtime():
    item, errors = build_entity_item(
        "numbers",
        {
            "address": "DB1,WORD4",
            "min_value": 2400,
            "value_conversions": {"value": {"type": "logo_time_bcd"}},
        },
        options={},
    )
    assert item is None
    assert errors == {"base": "invalid_range"}


@pytest.mark.asyncio
async def test_logo_entity_sync_keeps_clock_string_writes(mock_coordinator, fake_hass):
    """The existing input_datetime path still packs HH:MM, ignoring seconds."""
    entity = S7EntitySync(
        mock_coordinator,
        "Shift start",
        "shift-start",
        {},
        "DB1,WORD4",
        "input_datetime.shift_start",
        value_conversion={"type": "logo_time_bcd"},
    )
    entity.hass = fake_hass
    await entity._async_write_to_plc(SimpleNamespace(state="08:30:45"))
    assert mock_coordinator.write_calls == [("write_batched", "DB1,WORD4", 0x0830)]
