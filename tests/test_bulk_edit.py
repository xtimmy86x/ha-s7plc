"""Atomic patch preparation preserves options outside the requested fields."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from custom_components.s7plc.bulk_edit import bulk_edit_fields, prepare_bulk_edit


@pytest.fixture
def entry():
    return SimpleNamespace(
        entry_id="plc",
        data={"scan_interval": 2},
        options={
            "sensors": [
                {
                    "uid": "a",
                    "address": "DB1,INT0",
                    "area": "old",
                    "scan_interval": 5,
                    "value_conversions": {"value": {"type": "multiplier", "factor": 2}},
                },
                {"uid": "keep", "address": "DB1,INT2", "legacy_option": "preserve"},
            ],
            "numbers": [{"uid": "b", "address": "DB1,INT4", "min_value": 0}],
            "other_option": {"nested": [1, 2]},
        },
    )


TARGETS = [
    {"entity_type": "sensors", "uid": "a"},
    {"entity_type": "numbers", "uid": "b"},
]


def test_preview_is_read_only_and_patches_only_selected_fields(entry):
    original = deepcopy(entry.options)
    options, preview = prepare_bulk_edit(
        entry, TARGETS, {"area": "new", "scan_interval": 0.25}
    )
    assert entry.options == original
    assert preview["changed_count"] == 2
    assert preview["rows"][0]["before"] == {"area": "old", "scan_interval": 5}
    assert preview["rows"][0]["after"] == {"area": "new", "scan_interval": 0.25}
    assert preview["default_scan_interval"] == 2
    assert options["sensors"][1] == original["sensors"][1]
    assert options["other_option"] == original["other_option"]
    assert (
        options["sensors"][0]["value_conversions"]
        == original["sensors"][0]["value_conversions"]
    )
    assert options["numbers"][0]["min_value"] == 0


def test_clearing_overrides_and_same_values_are_distinct(entry):
    options, preview = prepare_bulk_edit(
        entry, TARGETS, {"area": None, "scan_interval": None}
    )
    assert preview["changed_count"] == 1
    assert "area" not in options["sensors"][0]
    assert "scan_interval" not in options["sensors"][0]
    assert preview["rows"][1]["changed"] is False
    options, preview = prepare_bulk_edit(
        entry, TARGETS[:1], {"area": "old", "scan_interval": 5}
    )
    assert options == entry.options
    assert preview["changed_count"] == 0


@pytest.mark.parametrize(
    "value", [0, -1, 0.049, 3600.1, True, "1", float("nan"), float("inf")]
)
def test_invalid_scan_rejects_the_whole_patch(entry, value):
    original = deepcopy(entry.options)
    with pytest.raises(ValueError, match="invalid_bulk_scan_interval"):
        prepare_bulk_edit(entry, TARGETS, {"area": "new", "scan_interval": value})
    assert entry.options == original


@pytest.mark.parametrize("value", [0.05, 1.5, 3600])
def test_valid_scan_limits_are_preserved(entry, value):
    options, _ = prepare_bulk_edit(entry, TARGETS, {"scan_interval": value})
    assert options["sensors"][0]["scan_interval"] == value


@pytest.mark.parametrize(
    "targets",
    [
        [],
        TARGETS + TARGETS[:1],
        TARGETS + [{"entity_type": "sensors", "uid": "missing"}],
    ],
)
def test_invalid_selection_never_mutates_any_item(entry, targets):
    original = deepcopy(entry.options)
    with pytest.raises(ValueError, match="invalid_selection"):
        prepare_bulk_edit(entry, targets, {"area": "new"})
    assert entry.options == original


def test_ambiguous_uid_is_rejected(entry):
    entry.options["sensors"].append({"uid": "a", "address": "DB1,INT8"})
    with pytest.raises(ValueError, match="invalid_selection"):
        prepare_bulk_edit(entry, TARGETS, {"area": None})


@pytest.mark.parametrize("changes", [{}, {"name": "wrong"}, {"area": ""}, {"area": 1}])
def test_only_supported_bulk_fields_are_accepted(entry, changes):
    with pytest.raises(ValueError, match="invalid_bulk_"):
        prepare_bulk_edit(entry, TARGETS, changes)


@pytest.mark.parametrize("entity_type", ["buttons", "entity_sync"])
def test_event_driven_entities_skip_scan_but_accept_area(entry, entity_type):
    entry.options[entity_type] = [{"uid": "event", "address": "DB1,X0.0"}]
    targets = [{"entity_type": entity_type, "uid": "event"}]
    options, preview = prepare_bulk_edit(entry, targets, {"scan_interval": 0.5})
    assert options == entry.options
    assert preview["changed_count"] == 0
    assert preview["rows"][0]["scan_supported"] is False
    options, preview = prepare_bulk_edit(
        entry, targets, {"area": "new", "scan_interval": 0.5}
    )
    assert preview["changed_count"] == 1
    assert options[entity_type][0] == {
        "uid": "event",
        "address": "DB1,X0.0",
        "area": "new",
    }


def test_preview_token_binds_config_selection_and_requested_changes(entry):
    _, preview = prepare_bulk_edit(entry, TARGETS, {"scan_interval": 1})
    _, identical = prepare_bulk_edit(entry, TARGETS, {"scan_interval": 1.0})
    assert identical["preview_token"] == preview["preview_token"]
    for targets, changes in [
        (TARGETS[:1], {"scan_interval": 1}),
        (TARGETS, {"scan_interval": 2}),
    ]:
        assert (
            prepare_bulk_edit(entry, targets, changes)[1]["preview_token"]
            != preview["preview_token"]
        )
    entry.options["sensors"][1]["area"] = "changed_elsewhere"
    assert (
        prepare_bulk_edit(entry, TARGETS, {"scan_interval": 1})[1]["preview_token"]
        != preview["preview_token"]
    )


def test_numeric_and_metadata_changes_preserve_every_unrelated_option(entry):
    entry.options["sensors"][0]["address"] = "DB1,REAL0"
    entry.options["numbers"][0].update(address="DB1,LREAL8", max_value=100, step=0.1)
    original = deepcopy(entry.options)
    changes = {
        "value_multiplier": 0.5,
        "real_precision": 3,
        "device_class": "temperature",
        "unit_of_measurement": "°C",
        "state_class": "none",
    }
    options, preview = prepare_bulk_edit(entry, TARGETS, changes)
    assert entry.options == original
    assert preview["changed_count"] == 2
    assert preview["error_count"] == 0
    for kind in ("sensors", "numbers"):
        assert options[kind][0]["value_conversions"] == {
            "value": {"type": "multiplier", "factor": 0.5}
        }
        assert options[kind][0]["real_precision"] == 3
        assert options[kind][0]["device_class"] == "temperature"
        assert options[kind][0]["unit_of_measurement"] == "°C"
    assert options["sensors"][0]["state_class"] == "none"
    assert "state_class" not in options["numbers"][0]
    assert options["numbers"][0]["min_value"] == 0
    assert options["numbers"][0]["max_value"] == 100
    assert options["numbers"][0]["step"] == 0.1
    assert options["sensors"][1] == original["sensors"][1]
    assert preview["rows"][0]["before"]["value_multiplier"] == {
        "type": "multiplier",
        "factor": 2,
    }
    assert preview["rows"][0]["effective_after"]["state_class"] is None
    assert "state_class" not in preview["rows"][1]["supported_fields"]


@pytest.mark.parametrize(
    "conversion",
    [
        {"type": "expression", "read_expression": "x / 10"},
        {
            "type": "linear_scale",
            "plc_min": 0,
            "plc_max": 100,
            "ha_min": 0,
            "ha_max": 10,
        },
    ],
)
@pytest.mark.parametrize("factor", [0.1, None])
def test_existing_conversion_is_shown_before_replacement(entry, conversion, factor):
    item = entry.options["sensors"][0]
    item["value_conversions"] = {"value": conversion, "unrelated": {"type": "keep"}}
    item["legacy_option"] = "preserve"
    original = deepcopy(item)
    options, preview = prepare_bulk_edit(
        entry, TARGETS[:1], {"value_multiplier": factor}
    )
    row = preview["rows"][0]
    assert row["conversion_replaced"]
    assert row["before"]["value_multiplier"] == conversion
    assert row["after"]["value_multiplier"] == (
        None if factor is None else {"type": "multiplier", "factor": factor}
    )
    assert options["sensors"][0]["value_conversions"]["unrelated"] == {"type": "keep"}
    assert options["sensors"][0]["legacy_option"] == "preserve"
    assert item == original


def test_clearing_metadata_and_precision_restores_effective_defaults(entry):
    item = entry.options["sensors"][0]
    item.update(
        address="DB1,REAL0",
        device_class="energy",
        unit_of_measurement="Wh",
        state_class="none",
        real_precision=4,
    )
    options, preview = prepare_bulk_edit(
        entry,
        TARGETS[:1],
        {
            "real_precision": None,
            "unit_of_measurement": None,
            "state_class": None,
        },
    )
    new = options["sensors"][0]
    assert not {"real_precision", "unit_of_measurement", "state_class"} & new.keys()
    assert new["device_class"] == "energy"
    assert preview["error_count"] == 0
    assert preview["rows"][0]["effective_after"]["unit_of_measurement"] == "kWh"
    assert preview["rows"][0]["effective_after"]["state_class"] == "total_increasing"
    assert preview["default_real_precision"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("value_multiplier", True),
        ("value_multiplier", "0.5"),
        ("value_multiplier", float("nan")),
        ("value_multiplier", float("inf")),
        ("real_precision", True),
        ("real_precision", 2.5),
        ("real_precision", "2"),
        ("real_precision", -1),
        ("real_precision", 7),
        ("device_class", "missing"),
        ("unit_of_measurement", " "),
        ("state_class", "missing"),
    ],
)
def test_invalid_extended_values_reject_the_entire_request(entry, field, value):
    original = deepcopy(entry.options)
    with pytest.raises(ValueError, match="invalid_"):
        prepare_bulk_edit(entry, TARGETS, {"area": "new", field: value})
    assert entry.options == original


@pytest.mark.parametrize(
    "changes,error",
    [
        (
            {"device_class": "temperature", "unit_of_measurement": "bar"},
            "invalid_unit_of_measurement",
        ),
        (
            {"device_class": "temperature", "state_class": "total_increasing"},
            "invalid_state_class",
        ),
    ],
)
def test_metadata_conflicts_are_reported_per_entity_without_mutating(
    entry, changes, error
):
    original = deepcopy(entry.options)
    _, preview = prepare_bulk_edit(entry, TARGETS[:1], changes)
    assert preview["error_count"] == 1
    assert preview["rows"][0]["errors"] == [error]
    assert entry.options == original


def test_zero_multiplier_is_valid_for_reads_but_blocks_writable_numbers(entry):
    original = deepcopy(entry.options)
    _, preview = prepare_bulk_edit(entry, TARGETS, {"value_multiplier": 0})
    assert preview["error_count"] == 1
    assert preview["rows"][0]["errors"] == []
    assert preview["rows"][1]["errors"] == ["invalid_bulk_write_multiplier"]
    assert entry.options == original


@pytest.mark.parametrize(
    "kind,item,expected",
    [
        (
            "sensors",
            {"address": "DB1,INT0"},
            {"value_multiplier", "device_class", "unit_of_measurement", "state_class"},
        ),
        ("sensors", {"address": "DB1,S0.20"}, set()),
        (
            "sensors",
            {
                "address": "DB1,W0",
                "value_conversions": {
                    "value": {
                        "type": "enum_map",
                        "mappings": [{"value": 0, "label": "off"}],
                    }
                },
            },
            set(),
        ),
        (
            "numbers",
            {
                "address": "DB1,W0",
                "value_conversions": {"value": {"type": "logo_time_bcd"}},
            },
            {
                "device_class",
                "unit_of_measurement",
                "min_value",
                "max_value",
                "step",
                "mode",
            },
        ),
        (
            "numbers",
            {"address": "DB1,REAL0", "command_address": "DB1,X4.0"},
            {
                "real_precision",
                "device_class",
                "unit_of_measurement",
                "min_value",
                "max_value",
                "step",
                "mode",
            },
        ),
        ("binary_sensors", {"address": "DB1,X0.0"}, {"device_class"}),
        ("covers", {}, {"device_class"}),
        ("lights", {}, set()),
    ],
)
def test_capabilities_match_entity_type_datatype_and_conversion(kind, item, expected):
    assert bulk_edit_fields(kind, item) - {"area", "scan_interval"} == expected


def test_multiplier_noop_and_legacy_input_preview(entry):
    options, preview = prepare_bulk_edit(entry, TARGETS[:1], {"value_multiplier": 2})
    assert options == entry.options
    assert preview["changed_count"] == 0
    assert not preview["rows"][0]["conversion_replaced"]
    item = entry.options["sensors"][0]
    item.pop("value_conversions")
    item["value_multiplier"] = 3
    options, preview = prepare_bulk_edit(entry, TARGETS[:1], {"value_multiplier": None})
    assert preview["rows"][0]["before"]["value_multiplier"] == {
        "type": "multiplier",
        "factor": 3,
    }
    assert "value_conversions" not in options["sensors"][0]
    assert "value_multiplier" not in options["sensors"][0]


def test_number_settings_patch_final_range_and_preserve_mixed_selection(entry):
    item = entry.options["numbers"][0]
    item.update(max_value=10, step=1, mode="box", legacy_option="keep")
    original = deepcopy(entry.options)
    changes = {"min_value": 20, "max_value": 30, "step": 0.5, "mode": "slider"}
    options, preview = prepare_bulk_edit(entry, TARGETS, changes)
    assert entry.options == original
    assert options["sensors"] == original["sensors"]
    assert options["numbers"][0] == {**item, **changes}
    assert preview["changed_count"] == 1
    assert preview["error_count"] == 0
    assert not preview["rows"][0]["changed"]
    assert preview["rows"][1]["effective_after"] == changes
    assert preview["rows"][1]["before"]["max_value"] == 10


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"address": "DB1,B4"}, {"min_value": 0, "max_value": 255, "step": 1}),
        (
            {"address": "DB1,TIME4"},
            {"min_value": -2147483.648, "max_value": 2147483.647, "step": 0.001},
        ),
        (
            {
                "address": "DB1,W4",
                "value_conversions": {"value": {"type": "logo_time_bcd"}},
            },
            {"min_value": 0, "max_value": 2359, "step": 1},
        ),
        (
            {
                "address": "DB1,INT4",
                "value_conversions": {"value": {"type": "multiplier", "factor": -2}},
            },
            {"min_value": -32768, "max_value": 32767, "step": 1},
        ),
    ],
)
def test_number_clear_preview_resolves_runtime_defaults(entry, item, expected):
    item = {
        **item,
        "uid": "b",
        "min_value": 5,
        "max_value": 10,
        "step": 0.5,
        "mode": "box",
    }
    entry.options["numbers"] = [item]
    changes = dict.fromkeys(["min_value", "max_value", "step", "mode"])
    options, preview = prepare_bulk_edit(entry, TARGETS[1:], changes)
    assert not preview["error_count"]
    assert not options["numbers"][0].keys() & changes.keys()
    assert options["numbers"][0].get("value_conversions") == item.get(
        "value_conversions"
    )
    assert preview["rows"][0]["effective_after"] == {**expected, "mode": "auto"}


@pytest.mark.parametrize(
    "item,changes,error",
    [
        ({"max_value": 10}, {"min_value": 11}, "invalid_range"),
        ({"min_value": 5}, {"max_value": 4}, "invalid_range"),
        ({"address": "DB1,B4"}, {"min_value": 256}, "invalid_range"),
        ({"address": "DB1,B4", "max_value": -1}, {"min_value": None}, "invalid_range"),
        (
            {"address": "DB1,REAL4", "min_value": 0, "max_value": 100},
            {"min_value": None},
            "min_max_required_for_real",
        ),
        (
            {"address": "DB1,LREAL4", "min_value": 0, "max_value": 100},
            {"max_value": None},
            "min_max_required_for_real",
        ),
        (
            {
                "address": "DB1,W4",
                "value_conversions": {"value": {"type": "logo_time_bcd"}},
            },
            {"min_value": 2400},
            "invalid_range",
        ),
    ],
)
def test_number_preview_validates_retained_and_automatic_bounds(
    entry, item, changes, error
):
    entry.options["numbers"][0].update(item)
    original = deepcopy(entry.options)
    _, preview = prepare_bulk_edit(entry, TARGETS, changes)
    assert preview["error_count"] == 1
    assert preview["rows"][0]["errors"] == []
    assert preview["rows"][1]["errors"] == [error]
    assert entry.options == original


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"min_value": True}, "invalid_number"),
        ({"max_value": "100"}, "invalid_number"),
        ({"min_value": float("nan")}, "invalid_number"),
        ({"max_value": float("inf")}, "invalid_number"),
        ({"step": False}, "invalid_number"),
        ({"step": -0.1}, "invalid_number"),
        ({"step": 0}, "invalid_number"),
        ({"mode": "SLIDER"}, "invalid_number_mode"),
        ({"mode": ""}, "invalid_number_mode"),
        ({"mode": True}, "invalid_number_mode"),
    ],
)
def test_number_input_validation_also_applies_to_unsupported_targets(
    entry, changes, error
):
    with pytest.raises(ValueError, match=error):
        prepare_bulk_edit(entry, TARGETS[:1], changes)


def test_number_auto_mode_matches_clear_and_unchanged_values_do_not_save(entry):
    changes = {"min_value": 0, "mode": "auto"}
    options, preview = prepare_bulk_edit(entry, TARGETS, changes)
    assert options == entry.options
    assert preview["changed_count"] == 0
    _, cleared = prepare_bulk_edit(entry, TARGETS, {**changes, "mode": None})
    assert cleared["preview_token"] == preview["preview_token"]
