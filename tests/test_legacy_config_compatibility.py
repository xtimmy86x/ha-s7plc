"""Regression coverage for configuration options persisted by ha-s7plc 6.5.1.

The fixture shapes come from tag ``6.5.1`` (commit 5108c9b): option keys and
field names are defined in ``custom_components/s7plc/const.py``; persisted
normalization is implemented by ``config_validation.py``; cover, climate,
light, and switch combinations are exercised by the matching platform tests
and by ``tests/test_panel.py`` at that tag.  In particular, the position cover
with stop and tilt follows ``_build_cover_position_item`` and the bidirectional
climate follows ``_build_climate_setpoint_item`` rather than today's editor
model.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.s7plc.config_validation import build_entity_item
from custom_components.s7plc.const import OPTION_KEYS
from custom_components.s7plc.helpers import _iter_entity_unique_ids
from custom_components.s7plc.panel import (
    _OPTION_DOMAINS,
    _configuration_from_yaml,
    _configuration_yaml,
    _entry_payload,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "configurations"
LEGACY_FIXTURES = tuple(sorted(FIXTURE_DIR.glob("6.5.1-*.json")))
ENTRY_ID = "legacy-entry"


def _load_fixture(path: Path) -> dict[str, list[dict]]:
    """Load a fixture through the standard-library JSON backend."""
    with path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _validate_configuration(
    configuration: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Run every persisted item through the current backend builder."""
    normalized = {key: [] for key in OPTION_KEYS}
    for entity_type in OPTION_KEYS:
        for entity in configuration.get(entity_type, []):
            item, errors = build_entity_item(
                entity_type, entity, options=normalized
            )
            assert errors == {}
            assert item is not None
            # The builder validates editable fields; both save handlers restore
            # the permanent identity after the builder returns.
            item["uid"] = entity["uid"]
            normalized[entity_type].append(item)
    return normalized


def _with_empty_option_lists(
    configuration: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    return {key: copy.deepcopy(configuration.get(key, [])) for key in OPTION_KEYS}


@pytest.mark.parametrize("fixture_path", LEGACY_FIXTURES, ids=lambda path: path.stem)
def test_651_persisted_configuration_loads_validates_without_data_loss(
    fixture_path: Path,
) -> None:
    """Current loading and normalization preserve valid 6.5.1 options exactly."""
    legacy = _load_fixture(fixture_path)
    original = copy.deepcopy(legacy)

    # Config entries are exposed to the panel through _entry_payload.  This is
    # the current backend load path and intentionally does not emulate a UI.
    entry = SimpleNamespace(
        entry_id=ENTRY_ID,
        title="Legacy test entry",
        data={},
        options=legacy,
        runtime_data=None,
    )
    loaded = _entry_payload(entry)["entities"]
    assert {key: value for key, value in loaded.items() if value} == legacy

    normalized = _validate_configuration(loaded)
    assert [
        item["uid"]
        for entity_type in OPTION_KEYS
        for item in normalized[entity_type]
    ] == [
        item["uid"]
        for entity_type in OPTION_KEYS
        for item in legacy.get(entity_type, [])
    ]
    for entity_type in OPTION_KEYS:
        for item in normalized[entity_type]:
            assert not {
                "value_multiplier",
                "scale_raw_min",
                "scale_raw_max",
                "brightness_scale",
            } & item.keys()
    assert legacy == original


@pytest.mark.parametrize("fixture_path", LEGACY_FIXTURES, ids=lambda path: path.stem)
def test_651_configuration_round_trip_preserves_semantics_and_uids(
    fixture_path: Path,
) -> None:
    """The real backend YAML backup cycle preserves same-entry identity."""
    legacy = _with_empty_option_lists(_load_fixture(fixture_path))
    normalized = _validate_configuration(legacy)
    serialized = _configuration_yaml(
        normalized, entry_id=ENTRY_ID, title="Legacy test entry"
    )

    # A same-entry backup is the backend's only save/load contract that is
    # explicitly allowed to retain UIDs.  An unversioned import deliberately
    # generates new UIDs and is therefore not an equivalent side-panel save.
    with patch(
        "custom_components.s7plc.panel.generate_uid",
        side_effect=AssertionError("a same-entry round trip generated a UID"),
    ):
        reloaded = _configuration_from_yaml(serialized, {}, ENTRY_ID)

    assert reloaded == normalized
    assert json.loads(json.dumps(reloaded, sort_keys=True)) == normalized


def test_651_representative_entity_identity_and_modes_remain_stable() -> None:
    """Permanent identity, platform, addresses, and legacy modes stay stable."""
    fixtures = [_load_fixture(path) for path in LEGACY_FIXTURES]
    configuration = {key: [] for key in OPTION_KEYS}
    for fixture in fixtures:
        for entity_type, items in fixture.items():
            configuration[entity_type].extend(copy.deepcopy(items))

    identities = {
        item["uid"]: (_OPTION_DOMAINS[entity_type], item)
        for entity_type in OPTION_KEYS
        for item in configuration[entity_type]
    }
    yielded = dict(_iter_entity_unique_ids(configuration))

    assert set(yielded) == set(identities)
    for uid, (platform, item) in identities.items():
        assert yielded[uid] is item
        assert item["uid"] == uid
        assert platform in {
            "sensor",
            "binary_sensor",
            "switch",
            "cover",
            "light",
            "button",
            "number",
            "text",
            "climate",
        }

    cover = configuration["covers"][0]
    assert "position_state_address" in cover  # position mode dispatch
    assert cover["stop_command_address"] == "DB2,X4.0"
    assert cover["tilt_state_address"] == "DB2,BYTE6"

    climate = configuration["climates"][0]
    assert climate["control_mode"] == "setpoint"
    assert climate["preset_mode_bidirectional"] is True

    light = configuration["lights"][0]
    assert light["brightness_state_address"] == "DB4,WORD2"
    assert light["brightness_command_address"] == "DB4,WORD4"
    assert light["brightness_scale"] == 1000

    pulse_switch = next(
        item for item in configuration["switches"] if item["pulse_command"]
    )
    assert pulse_switch["sync_state"] is False
    assert pulse_switch["pulse_duration"] == 0.8
