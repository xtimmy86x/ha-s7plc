"""Atomic patch preparation preserves options outside the requested fields."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from custom_components.s7plc.bulk_edit import prepare_bulk_edit


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
