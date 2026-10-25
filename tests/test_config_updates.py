"""Regressions for restore safety and side-effect-free live config publication."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.s7plc.config_updates import (
    async_apply_live_options,
    prepare_live_options,
    preview_options_update,
)
from custom_components.s7plc.entity import S7SyncEntity
from custom_components.s7plc.helpers import RuntimeEntryData
from custom_components.s7plc.sensor import S7Sensor


@pytest.mark.asyncio
async def test_conversion_discards_restored_sample_but_keeps_live_data(
    mock_coordinator,
):
    item = {"uid": "temperature", "address": "DB1,INT0", "availability_mode": "always"}
    entity = S7Sensor(
        mock_coordinator,
        "Temperature",
        "temperature",
        {},
        "sensor:DB1,INT0",
        "DB1,INT0",
        None,
    )
    await entity.async_configure_availability(item)
    await entity.async_added_to_hass()
    old_signature = entity._restore_config
    entity._restored_values = {"sensor:DB1,INT0": 15}
    assert entity.native_value == 15
    entry = SimpleNamespace(data={}, options={"sensors": [item]})
    runtime = RuntimeEntryData(
        mock_coordinator,
        "PLC",
        "host",
        "id",
        applied_data={},
        applied_options=deepcopy(entry.options),
    )
    entry.options = {
        "sensors": [
            {
                **item,
                "value_conversions": {
                    "value": {"type": "multiplier", "factor": 2},
                },
            }
        ]
    }
    assert await async_apply_live_options(entry, runtime)
    assert entity.native_value is None
    assert entity._restore_config != old_signature
    mock_coordinator.data = {"sensor:DB1,INT0": 21}
    assert entity.native_value == 42
    assert entity.extra_restore_state_data.as_dict()["config"] == entity._restore_config


def test_area_publication_does_not_run_command_sync(mock_coordinator, monkeypatch):
    entity = S7SyncEntity(mock_coordinator, unique_id="switch", device_info={})
    sync_write = Mock()
    monkeypatch.setattr(S7SyncEntity, "async_write_ha_state", sync_write)
    attributes = entity.prepare_live_config({"uid": "switch", "area": "room"}, {"area"})
    entity.apply_live_config(attributes, conversion_changed=False)
    sync_write.assert_not_called()
    assert entity._ha_state_calls == 1


@pytest.mark.asyncio
async def test_unsupported_late_edit_does_not_partially_apply(mock_coordinator):
    entity = S7Sensor(
        mock_coordinator,
        "Temperature",
        "temperature",
        {},
        "sensor:DB1,INT0",
        "DB1,INT0",
        None,
    )
    await entity.async_added_to_hass()
    item = {"uid": "temperature", "address": "DB1,INT0"}
    original = {"sensors": [item]}
    runtime = RuntimeEntryData(
        mock_coordinator,
        "PLC",
        "host",
        "id",
        applied_data={},
        applied_options=deepcopy(original),
    )
    entry = SimpleNamespace(
        data={},
        options={
            "sensors": [
                {
                    **item,
                    "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
                }
            ],
            "numbers": [{"uid": "new", "address": "DB1,INT2"}],
        },
    )
    assert not await async_apply_live_options(entry, runtime)
    assert entity._value_conversion is None
    assert runtime.applied_options == original
    assert entity._ha_state_calls == 0


@pytest.mark.parametrize(
    "case,reason",
    [
        ("no_runtime", "runtime_unavailable"),
        ("no_snapshot", "runtime_unavailable"),
        ("connection", "connection_changed"),
        ("options", "options_changed"),
        ("entities", "entities_changed"),
        ("missing_uid", "entities_changed"),
        ("missing_entity", "entity_unavailable"),
        ("invalid_config", "invalid_live_config"),
    ],
)
def test_preflight_reports_reload_without_mutating_runtime(case, reason):
    item = {"uid": "sensor", "address": "DB1,INT0"}
    options = {"sensors": [item]}
    entity = Mock()
    coordinator = SimpleNamespace(config_entities={"sensor": entity})
    runtime = RuntimeEntryData(
        coordinator,
        "PLC",
        "host",
        "id",
        applied_data={},
        applied_options=deepcopy(options),
    )
    entry = SimpleNamespace(data={}, options=options, runtime_data=runtime)
    new = {"sensors": [{**item, "area": "room"}]}
    if case == "no_runtime":
        runtime = None
    elif case == "no_snapshot":
        runtime.applied_options = None
    elif case == "connection":
        entry.data = {"host": "new"}
    elif case == "options":
        new["other_option"] = True
    elif case == "entities":
        new["sensors"] = []
    elif case == "missing_uid":
        runtime.applied_options["sensors"][0].pop("uid")
        new["sensors"][0].pop("uid")
    elif case == "missing_entity":
        coordinator.config_entities.clear()
        new["sensors"][0]["scan_interval"] = 10
    else:
        entity.prepare_live_config.side_effect = ValueError("invalid")
    before = deepcopy(runtime.applied_options) if runtime else None
    plan = prepare_live_options(entry, runtime, new)
    assert plan.reload_reason["reason"] == reason
    entity.apply_live_config.assert_not_called()
    assert entry.options == options
    if runtime:
        assert runtime.applied_options == before


def test_preview_detects_a_queued_update_before_listener_takes_lock():
    runtime = RuntimeEntryData(
        SimpleNamespace(), "PLC", "host", "id", applied_data={}, applied_options={}
    )
    entry = SimpleNamespace(
        data={}, options={"sensors": [{"uid": "pending"}]}, runtime_data=runtime
    )
    assert preview_options_update(
        entry, entry.options, has_changes=True, has_errors=False
    ) == {"mode": "pending"}
