from __future__ import annotations

import asyncio
import json
import inspect
from types import SimpleNamespace

import pytest

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from custom_components.s7plc import config_flow
from custom_components.s7plc import const


def make_config_entry(
    *,
    options: dict | None = None,
    data: dict | None = None,
    title: str = "S7 PLC",
    unique_id: str = "plc.local-0-1",
    entry_id: str = "entry",
    domain: str = const.DOMAIN,
):
    return SimpleNamespace(
        options=options or {},
        data=data or {},
        title=title,
        unique_id=unique_id,
        entry_id=entry_id,
        domain=domain,
    )


def make_options_flow(options=None, *, data=None, **kwargs):
    entry = make_config_entry(options=options, data=data, **kwargs)
    return config_flow.S7PLCOptionsFlow(entry)


def run_flow(coro):
    result = asyncio.run(coro)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return result


def test_sanitize_and_normalize_address():
    flow = make_options_flow()

    assert flow._sanitize_address("  DB1.DBX0.0  ") == "DB1.DBX0.0"
    assert flow._sanitize_address(123) == "123"
    assert flow._sanitize_address("   ") is None
    assert flow._sanitize_address(None) is None

    assert flow._normalized_address("db1.dbx0.0") == "DB1.DBX0.0"
    assert flow._normalized_address(None) is None


def test_has_duplicate_uses_normalized_addresses():
    options = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1.DBX0.0"}],
        const.CONF_SWITCHES: [
            {
                const.CONF_STATE_ADDRESS: "DB1.DBX0.1",
                const.CONF_COMMAND_ADDRESS: "DB1.DBX0.2",
            }
        ],
    }

    flow = make_options_flow(options)

    assert flow._has_duplicate(const.CONF_SENSORS, "db1.dbx0.0") is True
    assert flow._has_duplicate(const.CONF_SENSORS, "db1.dbx0.1") is False
    assert (
        flow._has_duplicate(
            const.CONF_SENSORS, "db1.dbx0.0", skip_idx=0
        )
        is False
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1.dbx0.1",
            keys=(const.CONF_STATE_ADDRESS, const.CONF_ADDRESS),
        )
        is True
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1.dbx0.2",
            keys=(const.CONF_STATE_ADDRESS, const.CONF_ADDRESS),
        )
        is False
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1.dbx0.1",
            keys=(const.CONF_STATE_ADDRESS, const.CONF_ADDRESS),
            skip_idx=0,
        )
        is False
    )


def test_options_connection_updates_entry(monkeypatch):
    entry = make_config_entry(
        data={
            CONF_NAME: "PLC Old",
            CONF_HOST: "old.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        options={},
        unique_id="old.local-0-1",
    )

    hass = HomeAssistant()
    hass.config_entries._entries.append(entry)

    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass

    captured_kwargs: dict[str, float | int | str] = {}

    class FakeCoordinator:
        def __init__(self, hass, **kwargs):
            captured_kwargs.update(kwargs)
            self.hass = hass

        def connect(self):
            return None

        def disconnect(self):
            return None

    monkeypatch.setattr(config_flow, "S7Coordinator", FakeCoordinator)

    user_input = {
        CONF_NAME: "PLC Updated",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT + 1,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT + 1,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL + 1,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT + 1.5,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES + 1,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL + 0.2,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX + 1.0,
    }

    result = run_flow(flow.async_step_connection(user_input))

    assert result["type"] == "create_entry"
    assert entry.data[CONF_HOST] == "plc.local"
    assert entry.data[const.CONF_SLOT] == const.DEFAULT_SLOT + 1
    assert entry.data[const.CONF_BACKOFF_INITIAL] == pytest.approx(
        const.DEFAULT_BACKOFF_INITIAL + 0.2
    )
    assert entry.data[const.CONF_BACKOFF_MAX] == pytest.approx(
        const.DEFAULT_BACKOFF_MAX + 1.0
    )
    assert entry.title == "PLC Updated"
    assert entry.unique_id == "old.local-0-1"
    assert captured_kwargs["host"] == "plc.local"
    assert captured_kwargs["scan_interval"] == const.DEFAULT_SCAN_INTERVAL + 1
    assert captured_kwargs["op_timeout"] == pytest.approx(
        const.DEFAULT_OP_TIMEOUT + 1.5
    )


def test_number_limits_clamped_on_add(monkeypatch):
    flow = make_options_flow(options={const.CONF_NUMBERS: []})
    flow.hass = HomeAssistant()

    tag = SimpleNamespace(data_type="INT")
    monkeypatch.setattr(config_flow, "parse_tag", lambda addr: tag)
    monkeypatch.setattr(
        config_flow, "get_numeric_limits", lambda data_type: (-32768.0, 32767.0)
    )

    result = run_flow(
        flow.async_step_numbers(
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                const.CONF_MIN_VALUE: -99999,
                const.CONF_MAX_VALUE: 99999,
                const.CONF_STEP: 1,
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_NUMBERS][0]
    assert stored[const.CONF_MIN_VALUE] == -32768.0
    assert stored[const.CONF_MAX_VALUE] == 32767.0


def test_edit_sensor_scan_interval_can_be_cleared(monkeypatch):
    options = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1.DBX0.0", const.CONF_SCAN_INTERVAL: 1.5}
        ]
    }

    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("s", 0)

    monkeypatch.setattr(config_flow, "parse_tag", lambda addr: None)

    result = run_flow(
        flow.async_step_edit_sensor(
            {
                const.CONF_ADDRESS: "DB1.DBX0.0",
                CONF_NAME: "",
                const.CONF_SCAN_INTERVAL: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert const.CONF_SCAN_INTERVAL not in sensor
    

def test_add_sensor_with_value_multiplier(monkeypatch):
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    monkeypatch.setattr(config_flow, "parse_tag", lambda addr: None)

    result = run_flow(
        flow.async_step_sensors(
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                const.CONF_VALUE_MULTIPLIER: "0.25",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert sensor[const.CONF_VALUE_MULTIPLIER] == pytest.approx(0.25)


def test_edit_sensor_value_multiplier_can_be_cleared(monkeypatch):
    options = {
        const.CONF_SENSORS: [
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                const.CONF_VALUE_MULTIPLIER: 2.0,
            }
        ]
    }

    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("s", 0)

    monkeypatch.setattr(config_flow, "parse_tag", lambda addr: None)

    result = run_flow(
        flow.async_step_edit_sensor(
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                CONF_NAME: "",
                const.CONF_VALUE_MULTIPLIER: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert const.CONF_VALUE_MULTIPLIER not in sensor

    
def test_number_limits_clamped_on_edit(monkeypatch):
    options = {
        const.CONF_NUMBERS: [
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                const.CONF_MIN_VALUE: -100.0,
                const.CONF_MAX_VALUE: 100.0,
            }
        ]
    }
    flow = make_options_flow(options=options)
    flow.hass = HomeAssistant()
    flow._edit_target = ("nm", 0)

    tag = SimpleNamespace(data_type="INT")
    monkeypatch.setattr(config_flow, "parse_tag", lambda addr: tag)
    monkeypatch.setattr(config_flow, "get_numeric_limits", lambda data_type: (0.0, 100.0))

    result = run_flow(
        flow.async_step_edit_number(
            {
                const.CONF_ADDRESS: "DB1.DBW0",
                const.CONF_MIN_VALUE: -50,
                const.CONF_MAX_VALUE: 200,
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_NUMBERS][0]
    assert stored[const.CONF_MIN_VALUE] == 0.0
    assert stored[const.CONF_MAX_VALUE] == 100.0
    assert flow._edit_target is None


def test_build_export_data_includes_all_keys():
    options = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1.DBX0.0", CONF_NAME: "A"}],
        const.CONF_SWITCHES: [
            {
                const.CONF_STATE_ADDRESS: "Q0.0",
                const.CONF_COMMAND_ADDRESS: "Q0.1",
            }
        ],
    }

    flow = make_options_flow(options=options)

    export_json = flow._build_export_data()
    payload = json.loads(export_json)

    for key in config_flow.OPTION_KEYS:
        assert key in payload

    assert payload[const.CONF_SENSORS][0][const.CONF_ADDRESS] == "DB1.DBX0.0"
    assert payload[const.CONF_SWITCHES][0][const.CONF_COMMAND_ADDRESS] == "Q0.1"


def test_import_step_replaces_configuration():
    original = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1.DBX0.0"}],
        const.CONF_BUTTONS: [{const.CONF_ADDRESS: "Q0.0"}],
    }

    flow = make_options_flow(options=original)

    new_payload = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB10.DBW0", CONF_NAME: "New"}
        ],
        const.CONF_LIGHTS: [
            {
                const.CONF_STATE_ADDRESS: "Q1.0",
                const.CONF_COMMAND_ADDRESS: "Q1.1",
            }
        ],
    }

    result = run_flow(
        flow.async_step_import({"import_json": json.dumps(new_payload)})
    )

    assert result["type"] == "create_entry"
    assert flow._options[const.CONF_SENSORS][0][const.CONF_ADDRESS] == "DB10.DBW0"
    assert flow._options[const.CONF_LIGHTS][0][const.CONF_COMMAND_ADDRESS] == "Q1.1"
    assert flow._options[const.CONF_BUTTONS] == []


def test_import_step_handles_invalid_json():
    flow = make_options_flow()

    result = asyncio.run(flow.async_step_import({"import_json": "not-json"}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "invalid_json"
    

def test_options_connection_handles_connection_failure(monkeypatch):
    entry = make_config_entry(
        data={
            CONF_NAME: "PLC Old",
            CONF_HOST: "old.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        options={},
        unique_id="old.local-0-1",
    )

    hass = HomeAssistant()
    hass.config_entries._entries.append(entry)

    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass

    class FailingCoordinator:
        def __init__(self, hass, **kwargs):
            self.hass = hass

        def connect(self):
            raise OSError("boom")

        def disconnect(self):
            return None

    monkeypatch.setattr(config_flow, "S7Coordinator", FailingCoordinator)

    user_input = {
        CONF_NAME: "PLC Updated",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
    }

    result = asyncio.run(flow.async_step_connection(user_input))

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "cannot_connect"
    assert entry.data[CONF_HOST] == "old.local"


def test_options_connection_detects_duplicate_unique_id(monkeypatch):
    primary = make_config_entry(
        data={
            CONF_NAME: "Primary",
            CONF_HOST: "old.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        entry_id="primary",
        unique_id="old.local-0-1",
    )
    other = make_config_entry(
        data={
            CONF_NAME: "Other",
            CONF_HOST: "plc.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        unique_id="plc.local-0-1",
        entry_id="other",
    )

    hass = HomeAssistant()
    hass.config_entries._entries.extend([primary, other])

    flow = config_flow.S7PLCOptionsFlow(primary)
    flow.hass = hass

    class FakeCoordinator:
        def __init__(self, hass, **kwargs):
            self.hass = hass

        def connect(self):
            return None

        def disconnect(self):
            return None

    monkeypatch.setattr(config_flow, "S7Coordinator", FakeCoordinator)

    user_input = {
        CONF_NAME: "Primary",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
    }

    result = asyncio.run(flow.async_step_connection(user_input))

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "already_configured"