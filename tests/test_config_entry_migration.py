"""Tests for general persisted config-entry migration helpers."""

from __future__ import annotations

from copy import deepcopy

import pytest

from custom_components.s7plc.config_entry_migration import (
    LegacySyncMigrationReport,
    canonicalize_legacy_sync_addresses,
)


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize(
    ("state_key", "state", "command"),
    [
        ("state_address", "DB1,X0.0", "DB1,X0.0"),
        ("state_address", "DB1,X0.0", "db1,x0.0"),
        ("state_address", " DB1,X0.0", "DB1,X0.0 "),
        ("address", "DB1,X0.0", "DB1,X0.0"),
        # pyS7 aliases map to the same canonical S7Tag.
        ("state_address", "DB1,W0", "DB1,WORD0"),
    ],
)
def test_canonicalizes_equivalent_parsed_addresses(
    entity_type, state_key, state, command
):
    entity = {
        "uid": "stable",
        state_key: state,
        "command_address": command,
        "sync_state": True,
        "unknown": {"nested": True},
    }
    original = deepcopy(entity)

    migrated, report = canonicalize_legacy_sync_addresses(entity_type, entity)

    assert entity == original
    assert migrated[state_key] == state
    assert migrated["uid"] == "stable"
    assert migrated["unknown"] == {"nested": True}
    assert migrated["sync_state"] is False
    assert "command_address" not in migrated
    assert report == LegacySyncMigrationReport(True, True)
    again, second_report = canonicalize_legacy_sync_addresses(entity_type, migrated)
    assert again == migrated
    assert second_report == LegacySyncMigrationReport()


@pytest.mark.parametrize("entity_type", ["switches", "lights"])
@pytest.mark.parametrize("command", [None, "", "   "])
def test_canonicalizes_absent_command_without_adding_one(entity_type, command):
    entity = {"state_address": "DB1,X0.0", "sync_state": True}
    if command is not None:
        entity["command_address"] = command

    migrated, report = canonicalize_legacy_sync_addresses(entity_type, entity)

    assert migrated["sync_state"] is False
    assert "command_address" not in migrated
    assert report == LegacySyncMigrationReport(True, command is not None)


@pytest.mark.parametrize(
    ("entity_type", "updates"),
    [
        ("switches", {"sync_state": False}),
        ("lights", {"command_address": "DB1,X0.1"}),
        ("numbers", {}),
        ("selects", {}),
        ("texts", {}),
        ("covers", {}),
        ("climates", {}),
        ("entity_sync", {}),
        ("switches", {"state_address": "invalid", "command_address": "invalid"}),
        ("switches", {"pulse_command": True}),
    ],
)
def test_unsafe_or_out_of_scope_configuration_is_unchanged(entity_type, updates):
    entity = {
        "uid": "stable",
        "state_address": "DB1,X0.0",
        "command_address": "DB1,X0.0",
        "sync_state": True,
        **updates,
    }

    migrated, report = canonicalize_legacy_sync_addresses(entity_type, entity)

    assert migrated == entity
    assert migrated is not entity
    assert not report.changed
    assert not report.sync_state_disabled
    assert not report.command_address_removed
