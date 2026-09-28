"""Regression tests for display-only restoration of PLC readings."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.s7plc.climate import S7ClimateDirectControl
from custom_components.s7plc.entity import S7BaseEntity, S7BoolSyncEntity
from custom_components.s7plc.restore import S7StoredData, decode_values, encode_values
from custom_components.s7plc.sensor import S7EntitySync


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["always", "connection", "bit"])
async def test_snapshot_policy_and_live_readings(mock_coordinator, mode):
    """Only always-available entities restore; live zero/false/None win."""
    entity = S7BaseEntity(
        mock_coordinator, unique_id="uid", device_info={}, topic="value"
    )
    await entity.async_configure_availability({"availability_mode": mode})
    mock_coordinator.data = {"value": 12}
    snapshot = entity.extra_restore_state_data
    if mode != "always":
        assert snapshot is None
        return
    entity.async_get_last_extra_data = AsyncMock(return_value=snapshot)
    mock_coordinator.data = {}
    await entity.async_added_to_hass()
    assert entity._state_data == {"value": 12}
    assert mock_coordinator.data == {}
    assert mock_coordinator.get_topic_read_revision("value") == 0
    with pytest.raises(HomeAssistantError, match="fresh PLC feedback"):
        await entity._ensure_connected()
    for value in (0, False, None, 42):
        mock_coordinator.data = {"value": value}
        assert entity._state_data["value"] is value
        assert not entity._has_restored_feedback


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["address", "uid", "version", "type"])
async def test_incompatible_snapshots_are_ignored(mock_coordinator, change):
    """Renamed/reconfigured entities must not reuse another channel's data."""
    entity = S7BaseEntity(
        mock_coordinator, unique_id="uid", device_info={}, topic="value"
    )
    item = {"availability_mode": "always", "address": "DB1,INT0"}
    await entity.async_configure_availability(item)
    mock_coordinator.data = {"value": 12}
    snapshot = entity.extra_restore_state_data.as_dict()
    if change == "address":
        await entity.async_configure_availability({**item, "address": "DB1,INT2"})
    elif change == "uid":
        snapshot["unique_id"] = "different"
    elif change == "version":
        snapshot["version"] = 999
    else:
        snapshot["config"] = "different-entity-type"
    entity.async_get_last_extra_data = AsyncMock(return_value=S7StoredData(snapshot))
    mock_coordinator.data = {}
    await entity.async_added_to_hass()
    assert entity._state_data == {}


@pytest.mark.asyncio
async def test_restored_switch_does_not_enter_sync_feedback(mock_coordinator):
    """No PLC write or initial sync baseline comes from a saved ON value."""
    entity = S7BoolSyncEntity(
        mock_coordinator,
        unique_id="uid",
        device_info={},
        topic="value",
        state_address="DB1,X0.0",
        command_address="DB1,X0.1",
        sync_state=True,
    )
    await entity.async_configure_availability({"availability_mode": "always"})
    mock_coordinator.data = {"value": True}
    entity.async_get_last_extra_data = AsyncMock(
        return_value=entity.extra_restore_state_data
    )
    mock_coordinator.data = {}
    await entity.async_added_to_hass()
    entity.async_write_ha_state()
    assert entity.is_on is True
    assert entity._sync_value() is None
    assert entity._last_state is None
    assert not mock_coordinator.write_calls
    # First real feedback initializes sync, without writing the saved ON back.
    mock_coordinator.data = {"value": False}
    mock_coordinator.advance_topic_read_revision("value")
    entity.async_write_ha_state()
    assert entity.is_on is False
    assert entity._last_state is False
    assert not mock_coordinator.write_calls


def test_json_roundtrip_preserves_time_zero_false_and_empty_text():
    values = {
        "time": timedelta(milliseconds=-1500),
        "zero": 0,
        "off": False,
        "text": "",
    }
    assert decode_values(json.loads(json.dumps(encode_values(values)))) == values
    assert encode_values({"none": None, "nan": float("nan"), "inf": float("inf")}) == {}
    assert (
        decode_values({"bad": {"timedelta_seconds": "abc"}, "nan": float("nan")}) == {}
    )
    assert decode_values([]) == {}


@pytest.mark.asyncio
async def test_entity_sync_restores_display_but_still_requires_resync(mock_coordinator):
    entity = S7EntitySync(
        mock_coordinator,
        name="Sync",
        unique_id="sync",
        device_info={},
        address="DB1,REAL0",
        source_entity="sensor.source",
    )
    await entity.async_configure_availability({"availability_mode": "always"})
    entity._last_written_value = 12.5
    entity.async_get_last_extra_data = AsyncMock(
        return_value=entity.extra_restore_state_data
    )
    entity._last_written_value = None
    await S7BaseEntity.async_added_to_hass(entity)
    assert entity.native_value == 12.5
    assert entity._resync_required
    assert not entity._initial_write_pending
    assert not mock_coordinator.write_calls


@pytest.mark.asyncio
async def test_no_snapshot_does_not_invent_a_value(mock_coordinator):
    entity = S7BaseEntity(
        mock_coordinator, unique_id="uid", device_info={}, topic="value"
    )
    await entity.async_configure_availability({"availability_mode": "always"})
    await entity.async_added_to_hass()
    assert entity.available
    assert entity._state_data.get("value") is None


@pytest.mark.asyncio
async def test_climate_control_waits_for_real_temperature(mock_coordinator):
    """A saved low temperature must not turn heating on after restart."""
    entity = S7ClimateDirectControl(
        mock_coordinator,
        name="Climate",
        unique_id="climate",
        device_info={},
        topic="climate",
        current_temp_address="DB1,REAL0",
        heating_output_address="DB1,X4.0",
        cooling_output_address=None,
        heating_action_address=None,
        cooling_action_address=None,
        min_temp=7,
        max_temp=35,
        temp_step=0.5,
    )
    await entity.async_configure_availability({"availability_mode": "always"})
    mock_coordinator.data = {"climate:current_temp": 10}
    entity.async_get_last_extra_data = AsyncMock(
        return_value=entity.extra_restore_state_data
    )
    mock_coordinator.data = {}
    await entity.async_added_to_hass()
    entity._hvac_mode = HVACMode.HEAT
    entity._target_temperature = 20
    assert entity.current_temperature == 10
    await entity._update_outputs()
    assert not mock_coordinator.write_calls
    mock_coordinator.data = {"climate:current_temp": 25}
    await entity._update_outputs()
    assert mock_coordinator.write_calls == [("write_batched", "DB1,X4.0", False)]
