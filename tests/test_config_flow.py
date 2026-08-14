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
    flow = config_flow.S7PLCOptionsFlow(entry)
    # Add mock hass instance (needed for area_selector)
    flow.hass = HomeAssistant()
    return flow


def run_flow(coro):
    result = asyncio.run(coro)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return result


def test_add_step_shows_item_selector():
    flow = make_options_flow()

    result = run_flow(flow.async_step_add())

    assert result["type"] == "menu"
    assert result["kwargs"]["step_id"] == "add"
    assert result["kwargs"]["menu_options"] == list(config_flow.ADD_ENTITY_STEP_IDS)


def test_add_step_routes_to_selected_handler(monkeypatch):
    flow = make_options_flow()

    called: dict[str, bool] = {}

    async def fake_sensor_step(user_input=None):
        called["invoked"] = True
        called["user_input"] = user_input
        return {"type": "form", "step_id": "sensors"}

    monkeypatch.setattr(flow, "async_step_sensors", fake_sensor_step)

    result = run_flow(flow.async_step_add({"item_type": "sensors"}))

    assert called == {"invoked": True, "user_input": None}
    assert result["step_id"] == "sensors"


def test_sanitize_and_normalize_address():
    flow = make_options_flow()

    assert flow._sanitize_address("  DB1,X0.0  ") == "DB1,X0.0"
    assert flow._sanitize_address(123) == "123"
    assert flow._sanitize_address("   ") is None
    assert flow._sanitize_address(None) is None

    assert flow._normalized_address("db1,x0.0") == "DB1,X0.0"
    assert flow._normalized_address(None) is None


def test_has_duplicate_uses_normalized_addresses():
    options = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1,X0.0"}],
        const.CONF_SWITCHES: [
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.1",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.2",
            }
        ],
    }

    flow = make_options_flow(options)

    assert flow._has_duplicate(const.CONF_SENSORS, "db1,x0.0") is True
    assert flow._has_duplicate(const.CONF_SENSORS, "db1,x0.1") is False
    assert (
        flow._has_duplicate(
            const.CONF_SENSORS, "db1,x0.0", skip_idx=0
        )
        is False
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1,x0.1",
            keys=(const.CONF_STATE_ADDRESS, const.CONF_ADDRESS),
        )
        is True
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1,x0.2",
            keys=(const.CONF_STATE_ADDRESS, const.CONF_ADDRESS),
        )
        is False
    )
    assert (
        flow._has_duplicate(
            const.CONF_SWITCHES,
            "db1,x0.1",
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

        async def connect(self):
            return None

        async def disconnect(self):
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


def test_number_limits_clamped_on_add():
    flow = make_options_flow(options={const.CONF_NUMBERS: []})
    flow.hass = HomeAssistant()

    result = run_flow(
        flow.async_step_numbers(
            {
                const.CONF_ADDRESS: "DB1,I2",
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


def test_edit_sensor_scan_interval_can_be_cleared():
    options = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", const.CONF_SCAN_INTERVAL: 1.5}
        ]
    }

    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("s", 0)

    result = run_flow(
        flow.async_step_edit_sensor(
            {
                const.CONF_ADDRESS: "DB1,X0.0",
                CONF_NAME: "",
                const.CONF_SCAN_INTERVAL: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert const.CONF_SCAN_INTERVAL not in sensor


def test_add_sensor_assigns_uid():
    """A newly added item gets a permanent uid, independent of its address."""
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    result = run_flow(
        flow.async_step_sensors({const.CONF_ADDRESS: "DB1,X0.0"})
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert sensor[const.CONF_UID]


def test_edit_sensor_preserves_uid_when_address_changes():
    """Regression test: editing an item's address must not change its uid.

    Before the stable-uid fix, unique_id was derived straight from the
    address, so editing it orphaned the existing entity. Now the uid is
    assigned once at creation and must survive address edits unchanged.
    """
    options = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", const.CONF_UID: "original-uid"}
        ]
    }

    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("s", 0)

    result = run_flow(
        flow.async_step_edit_sensor(
            {
                const.CONF_ADDRESS: "DB2,X1.0",  # address changed
                CONF_NAME: "",
                const.CONF_SCAN_INTERVAL: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert sensor[const.CONF_ADDRESS] == "DB2,X1.0"
    assert sensor[const.CONF_UID] == "original-uid"


def test_add_sensor_with_value_multiplier():
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    result = run_flow(
        flow.async_step_sensors(
            {
                const.CONF_ADDRESS: "DB1,W0",
                const.CONF_VALUE_MULTIPLIER: "0.25",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert sensor[const.CONF_VALUE_MULTIPLIER] == pytest.approx(0.25)


def test_add_sensor_with_value_multiplier_comma_decimal():
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    result = run_flow(
        flow.async_step_sensors(
            {
                const.CONF_ADDRESS: "DB1,W0",
                const.CONF_VALUE_MULTIPLIER: "0,25",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert sensor[const.CONF_VALUE_MULTIPLIER] == pytest.approx(0.25)


def test_edit_sensor_value_multiplier_can_be_cleared():
    options = {
        const.CONF_SENSORS: [
            {
                const.CONF_ADDRESS: "DB1,W0",
                const.CONF_VALUE_MULTIPLIER: 2.0,
            }
        ]
    }

    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("s", 0)


    result = run_flow(
        flow.async_step_edit_sensor(
            {
                const.CONF_ADDRESS: "DB1,W0",
                CONF_NAME: "",
                const.CONF_VALUE_MULTIPLIER: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    sensor = flow._options[const.CONF_SENSORS][0]
    assert const.CONF_VALUE_MULTIPLIER not in sensor

    
def test_number_limits_clamped_on_edit():
    options = {
        const.CONF_NUMBERS: [
            {
                const.CONF_ADDRESS: "DB1,W0",
                const.CONF_MIN_VALUE: 0.0,
                const.CONF_MAX_VALUE: 100.0,
            }
        ]
    }
    flow = make_options_flow(options=options)
    flow.hass = HomeAssistant()
    flow._edit_target = ("nm", 0)

    result = run_flow(
        flow.async_step_edit_number(
            {
                const.CONF_ADDRESS: "DB1,W0",
                const.CONF_MIN_VALUE: -50,
                const.CONF_MAX_VALUE: 200,
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_NUMBERS][0]
    assert stored[const.CONF_MIN_VALUE] == 0.0 # clamped for WORD data type
    assert stored[const.CONF_MAX_VALUE] == 200.0
    assert flow._edit_target is None


def test_build_export_data_includes_all_keys():
    options = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1,X0.0", CONF_NAME: "A"}],
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

    assert payload[const.CONF_SENSORS][0][const.CONF_ADDRESS] == "DB1,X0.0"
    assert payload[const.CONF_SWITCHES][0][const.CONF_COMMAND_ADDRESS] == "Q0.1"


def test_import_step_replaces_configuration():
    original = {
        const.CONF_SENSORS: [{const.CONF_ADDRESS: "DB1,X0.0"}],
        const.CONF_BUTTONS: [{const.CONF_ADDRESS: "Q0.0"}],
    }

    flow = make_options_flow(options=original)

    new_payload = {
        const.CONF_SENSORS: [
            {
                const.CONF_ADDRESS: "DB10.DBW0",
                CONF_NAME: "New",
                const.CONF_AREA: "kitchen",
            }
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
    assert (
        flow._options[const.CONF_SENSORS][0][const.CONF_AREA]
        == "kitchen"
    )

def test_import_step_handles_invalid_json():
    flow = make_options_flow()

    result = asyncio.run(flow.async_step_import({"import_json": "not-json"}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "invalid_json"


def test_import_step_rejects_duplicate_sensor_addresses():
    """Test that import rejects duplicate addresses in sensors."""
    flow = make_options_flow()

    payload = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", CONF_NAME: "Sensor 1"},
            {const.CONF_ADDRESS: "DB1,X0.1", CONF_NAME: "Sensor 2"},
            {const.CONF_ADDRESS: "db1,x0.0", CONF_NAME: "Duplicate"},  # Duplicate (case-insensitive)
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "duplicate_addresses_in_import"


def test_import_step_rejects_duplicate_switch_addresses():
    """Test that import rejects duplicate addresses in switches."""
    flow = make_options_flow()

    payload = {
        const.CONF_SWITCHES: [
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.1",
                CONF_NAME: "Switch 1",
            },
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.2",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.3",
                CONF_NAME: "Switch 2",
            },
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",  # Duplicate
                const.CONF_COMMAND_ADDRESS: "DB1,X0.4",
                CONF_NAME: "Duplicate",
            },
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "duplicate_addresses_in_import"


def test_import_step_rejects_duplicate_light_addresses():
    """Test that import rejects duplicate addresses in lights."""
    flow = make_options_flow()

    payload = {
        const.CONF_LIGHTS: [
            {
                const.CONF_STATE_ADDRESS: "Q1.0",
                const.CONF_COMMAND_ADDRESS: "Q1.1",
            },
            {
                const.CONF_STATE_ADDRESS: "Q1.0",  # Duplicate
                const.CONF_COMMAND_ADDRESS: "Q1.2",
            },
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "duplicate_addresses_in_import"


def test_add_cover_traditional_requires_close_address():
    """close_command_address is required."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0"}
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "invalid_address"


def test_add_cover_traditional_requires_open_address():
    """open_command_address is still required."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1"}
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "invalid_address"


def test_add_cover_traditional_with_both_addresses_stores_both():
    """Normal two-button operation when both addresses are configured."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert stored[const.CONF_OPEN_COMMAND_ADDRESS] == "DB1,X0.0"
    assert stored[const.CONF_CLOSE_COMMAND_ADDRESS] == "DB1,X0.1"


def test_add_cover_toggle_mode_does_not_require_close_address():
    """toggle_mode covers use a single PLC pulse (open_command_address) -
    close_command_address has no meaning and must not be required."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_STATUS_ADDRESS: "DB1,INT0",
                const.CONF_COVER_STATUS_OPEN_VALUES: "0",
                const.CONF_COVER_STATUS_CLOSED_VALUES: "1",
                const.CONF_COVER_STATUS_OPENING_VALUES: "2",
                const.CONF_COVER_STATUS_CLOSING_VALUES: "3",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert stored[const.CONF_TOGGLE_MODE] is True
    assert const.CONF_CLOSE_COMMAND_ADDRESS not in stored


def test_add_cover_toggle_mode_ignores_a_supplied_close_address():
    """A cover is either two-address or toggle, never both - a supplied
    close_command_address is dropped when toggle_mode is on."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_STATUS_ADDRESS: "DB1,INT0",
                const.CONF_COVER_STATUS_OPEN_VALUES: "0",
                const.CONF_COVER_STATUS_CLOSED_VALUES: "1",
                const.CONF_COVER_STATUS_OPENING_VALUES: "2",
                const.CONF_COVER_STATUS_CLOSING_VALUES: "3",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert const.CONF_CLOSE_COMMAND_ADDRESS not in stored


def test_add_cover_toggle_mode_requires_movement_feedback():
    """toggle_mode's correctness depends on knowing the PLC's real state -
    with no feedback configured at all, it must be rejected up front
    rather than silently misbehaving at runtime."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "toggle_mode_requires_feedback"


def test_add_cover_toggle_mode_requires_settled_state_feedback():
    """Motion feedback alone (cover_opening_address/cover_closing_address)
    isn't enough - without a settled-state source, a closed gate could
    never be told apart from an open one. Locks in the is_closed fix."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_OPENING_ADDRESS: "DB1,X1.0",
                const.CONF_COVER_CLOSING_ADDRESS: "DB1,X1.1",
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "toggle_mode_requires_feedback"


def test_add_cover_toggle_mode_with_status_address_feedback_succeeds():
    """cover_status_address alone (with all 4 relevant values) satisfies
    both motion and settled-state feedback at once."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_STATUS_ADDRESS: "DB1,INT0",
                const.CONF_COVER_STATUS_OPEN_VALUES: "0",
                const.CONF_COVER_STATUS_CLOSED_VALUES: "1",
                const.CONF_COVER_STATUS_OPENING_VALUES: "2",
                const.CONF_COVER_STATUS_CLOSING_VALUES: "3",
            }
        )
    )

    assert result["type"] == "create_entry"


def test_add_cover_toggle_mode_with_boolean_and_state_topics_feedback_succeeds():
    """The alternative combination: boolean motion addresses plus
    use_state_topics + both end-stops for settled state."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_OPENING_ADDRESS: "DB1,X1.0",
                const.CONF_COVER_CLOSING_ADDRESS: "DB1,X1.1",
                const.CONF_USE_STATE_TOPICS: True,
                const.CONF_OPENING_STATE_ADDRESS: "DB1,X2.0",
                const.CONF_CLOSING_STATE_ADDRESS: "DB1,X2.1",
            }
        )
    )

    assert result["type"] == "create_entry"


def test_edit_cover_toggle_mode_does_not_require_close_address():
    """Same regression, via the edit path (_build_cover_item is shared
    between add and edit)."""
    options = {
        const.CONF_COVERS: [
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
                const.CONF_UID: "original-uid",
            }
        ]
    }
    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("cv", 0)

    result = run_flow(
        flow.async_step_edit_cover(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_TOGGLE_MODE: True,
                const.CONF_COVER_STATUS_ADDRESS: "DB1,INT0",
                const.CONF_COVER_STATUS_OPEN_VALUES: "0",
                const.CONF_COVER_STATUS_CLOSED_VALUES: "1",
                const.CONF_COVER_STATUS_OPENING_VALUES: "2",
                const.CONF_COVER_STATUS_CLOSING_VALUES: "3",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert stored[const.CONF_TOGGLE_MODE] is True
    assert const.CONF_CLOSE_COMMAND_ADDRESS not in stored


def test_add_cover_traditional_persists_movement_status_addresses():
    """Regression test: cover_opening_address/cover_closing_address/
    cover_stopped_address are exposed in the schema and consumed by
    cover.py, but _build_cover_item previously never copied them from
    user_input into the stored item - they were silently dropped on save."""
    flow = make_options_flow(options={const.CONF_COVERS: []})

    result = run_flow(
        flow.async_step_covers_traditional(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
                const.CONF_COVER_OPENING_ADDRESS: "DB1,X1.0",
                const.CONF_COVER_CLOSING_ADDRESS: "DB1,X1.1",
                const.CONF_COVER_STOPPED_ADDRESS: "DB1,X1.2",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert stored[const.CONF_COVER_OPENING_ADDRESS] == "DB1,X1.0"
    assert stored[const.CONF_COVER_CLOSING_ADDRESS] == "DB1,X1.1"
    assert stored[const.CONF_COVER_STOPPED_ADDRESS] == "DB1,X1.2"


def test_edit_cover_traditional_persists_movement_status_addresses():
    """Same regression, via the edit path (_build_cover_item is shared
    between add and edit)."""
    options = {
        const.CONF_COVERS: [
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
                const.CONF_UID: "original-uid",
            }
        ]
    }
    flow = make_options_flow(options=options)
    flow._action = "edit"
    flow._edit_target = ("cv", 0)

    result = run_flow(
        flow.async_step_edit_cover(
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "DB1,X0.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "DB1,X0.1",
                const.CONF_COVER_OPENING_ADDRESS: "DB1,X1.0",
                const.CONF_COVER_CLOSING_ADDRESS: "DB1,X1.1",
                const.CONF_COVER_STOPPED_ADDRESS: "DB1,X1.2",
            }
        )
    )

    assert result["type"] == "create_entry"
    stored = flow._options[const.CONF_COVERS][0]
    assert stored[const.CONF_COVER_OPENING_ADDRESS] == "DB1,X1.0"
    assert stored[const.CONF_COVER_CLOSING_ADDRESS] == "DB1,X1.1"
    assert stored[const.CONF_COVER_STOPPED_ADDRESS] == "DB1,X1.2"


def test_import_step_rejects_duplicate_cover_addresses():
    """Test that import rejects duplicate addresses in covers."""
    flow = make_options_flow()

    payload = {
        const.CONF_COVERS: [
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "Q2.0",
                const.CONF_CLOSE_COMMAND_ADDRESS: "Q2.1",
            },
            {
                const.CONF_OPEN_COMMAND_ADDRESS: "q2.0",  # Duplicate (case-insensitive)
                const.CONF_CLOSE_COMMAND_ADDRESS: "Q2.2",
            },
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "form"
    errors = result.get("errors") or result.get("kwargs", {}).get("errors")
    assert errors["base"] == "duplicate_addresses_in_import"


def test_import_step_accepts_unique_addresses():
    """Test that import accepts configuration with unique addresses."""
    flow = make_options_flow()

    payload = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", CONF_NAME: "Sensor 1"},
            {const.CONF_ADDRESS: "DB1,X0.1", CONF_NAME: "Sensor 2"},
        ],
        const.CONF_SWITCHES: [
            {
                const.CONF_STATE_ADDRESS: "DB2,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB2,X0.1",
            },
        ],
        const.CONF_BUTTONS: [
            {const.CONF_ADDRESS: "Q0.0"},
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "create_entry"
    assert len(flow._options[const.CONF_SENSORS]) == 2
    assert len(flow._options[const.CONF_SWITCHES]) == 1
    assert len(flow._options[const.CONF_BUTTONS]) == 1


def test_import_step_preserves_existing_uid():
    """A uid already present in the imported JSON (e.g. from this
    integration's own export) must survive untouched, so re-importing a
    backup doesn't orphan existing entities."""
    flow = make_options_flow()

    payload = {
        const.CONF_SENSORS: [
            {
                const.CONF_ADDRESS: "DB1,X0.0",
                CONF_NAME: "Sensor 1",
                const.CONF_UID: "preserved-uid",
            },
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "create_entry"
    assert flow._options[const.CONF_SENSORS][0][const.CONF_UID] == "preserved-uid"


def test_import_step_replaces_duplicate_uid(monkeypatch):
    """A duplicate imported uid is replaced without changing the first one."""
    flow = make_options_flow()
    monkeypatch.setattr(config_flow, "generate_uid", lambda: "replacement-uid")

    payload = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", const.CONF_UID: "duplicate-uid"},
            {const.CONF_ADDRESS: "DB1,X0.1", const.CONF_UID: "duplicate-uid"},
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "create_entry"
    assert flow._options[const.CONF_SENSORS][0][const.CONF_UID] == "duplicate-uid"
    assert flow._options[const.CONF_SENSORS][1][const.CONF_UID] == "replacement-uid"


def test_import_step_allows_same_address_across_entity_types():
    """Test that same address can be used in different entity types (e.g., sensor and button)."""
    flow = make_options_flow()

    # Same address used in different entity types should be allowed
    payload = {
        const.CONF_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0", CONF_NAME: "Sensor"},
        ],
        const.CONF_BUTTONS: [
            {const.CONF_ADDRESS: "DB1,X0.0"},  # Same as sensor - should be allowed
        ],
        const.CONF_BINARY_SENSORS: [
            {const.CONF_ADDRESS: "DB1,X0.0"},  # Same as sensor - should be allowed
        ],
    }

    result = run_flow(flow.async_step_import({"import_json": json.dumps(payload)}))

    assert result["type"] == "create_entry"
    assert len(flow._options[const.CONF_SENSORS]) == 1
    assert len(flow._options[const.CONF_BUTTONS]) == 1
    assert len(flow._options[const.CONF_BINARY_SENSORS]) == 1
    

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
    flow.hass = HomeAssistant()

    class FailingCoordinator:
        def __init__(self, hass, **kwargs):
            self.hass = hass

        async def connect(self):
            raise OSError("boom")

        async def disconnect(self):
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

        async def connect(self):
            return None

        async def disconnect(self):
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


def test_number_comma_decimal_normalization():
    """Test that comma decimals are normalized for min/max/step."""
    flow = make_options_flow(
        options={
            "sensors": [],
            "numbers": [],
        }
    )
    flow.hass = HomeAssistant()

    user_input = {
        const.CONF_ADDRESS: "DB1,REAL0",
        const.CONF_COMMAND_ADDRESS: "DB1,REAL4",
        const.CONF_MIN_VALUE: "0,5",
        const.CONF_MAX_VALUE: "100,75",
        const.CONF_STEP: "0,25",
    }

    result = run_flow(flow.async_step_numbers(user_input))

    # Should succeed and create entry
    assert result["type"] == "create_entry"
    numbers = flow._options[const.CONF_NUMBERS]
    assert len(numbers) == 1
    assert numbers[0][const.CONF_MIN_VALUE] == 0.5
    assert numbers[0][const.CONF_MAX_VALUE] == 100.75
    assert numbers[0][const.CONF_STEP] == 0.25


# ---------------------------------------------------------------------------
# add_another copies previous values as suggested_values
# ---------------------------------------------------------------------------


def _get_suggested_values(result):
    """Extract suggested values from the data_schema returned by async_show_form."""
    schema = result.get("kwargs", {}).get("data_schema") or result.get("data_schema")
    if schema is None:
        return {}
    suggested = {}
    for key in schema.schema:
        desc = getattr(key, "description", None)
        if desc and "suggested_value" in desc:
            suggested[key.schema] = desc["suggested_value"]
    return suggested


def test_add_another_sensor_copies_values():
    """When add_another is checked, the next sensor form should pre-fill previous values."""
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    result = run_flow(
        flow.async_step_sensors(
            {
                const.CONF_ADDRESS: "DB1,W0",
                "name": "Temperature",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "add_another": True,
            }
        )
    )

    assert result["type"] == "form"
    suggested = _get_suggested_values(result)
    assert suggested[const.CONF_ADDRESS] == "DB1,W0"
    assert suggested["name"] == "Temperature"
    assert suggested["device_class"] == "temperature"
    assert suggested["unit_of_measurement"] == "°C"
    assert "add_another" not in suggested
    assert len(flow._options[const.CONF_SENSORS]) == 1


def test_add_another_switch_copies_values():
    """When add_another is checked, the next switch form should pre-fill previous values."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.1",
                "name": "Pump",
                "sync_state": True,
                "add_another": True,
            }
        )
    )

    assert result["type"] == "form"
    suggested = _get_suggested_values(result)
    assert suggested[const.CONF_STATE_ADDRESS] == "DB1,X0.0"
    assert suggested[const.CONF_COMMAND_ADDRESS] == "DB1,X0.1"
    assert suggested["name"] == "Pump"
    assert suggested["sync_state"] is True
    assert "add_another" not in suggested
    assert len(flow._options[const.CONF_SWITCHES]) == 1


def test_add_another_binary_sensor_copies_values():
    """When add_another is checked, the next binary sensor form should pre-fill previous values."""
    flow = make_options_flow(options={const.CONF_BINARY_SENSORS: []})

    result = run_flow(
        flow.async_step_binary_sensors(
            {
                const.CONF_ADDRESS: "DB1,X1.0",
                "name": "Door",
                "device_class": "door",
                "invert_state": True,
                "add_another": True,
            }
        )
    )

    assert result["type"] == "form"
    suggested = _get_suggested_values(result)
    assert suggested[const.CONF_ADDRESS] == "DB1,X1.0"
    assert suggested["name"] == "Door"
    assert suggested["invert_state"] is True
    assert "add_another" not in suggested
    assert len(flow._options[const.CONF_BINARY_SENSORS]) == 1


def test_add_another_clears_suggested_after_use():
    """Suggested values should be cleared after the form is shown once."""
    flow = make_options_flow(options={const.CONF_SENSORS: []})

    # First: add_another with values — form shown with suggested values
    result1 = run_flow(
        flow.async_step_sensors(
            {
                const.CONF_ADDRESS: "DB1,W0",
                "name": "Temp",
                "add_another": True,
            }
        )
    )
    assert _get_suggested_values(result1) != {}
    assert flow._last_add_input is None  # cleared after showing form

    # Second call without user_input — no suggested values
    result2 = run_flow(flow.async_step_sensors())
    assert _get_suggested_values(result2) == {}


# ============================================================================
# sync_state / pulse_command mutual exclusion
# ============================================================================


def test_switch_sync_pulse_conflict():
    """Enabling both sync_state and pulse_command on a switch must fail."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                "sync_state": True,
                "pulse_command": True,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "sync_pulse_conflict"
    assert len(flow._options[const.CONF_SWITCHES]) == 0


def test_switch_sync_only_ok():
    """Switch with sync_state and different command address should succeed."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.1",
                "sync_state": True,
                "pulse_command": False,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert len(flow._options[const.CONF_SWITCHES]) == 1
    assert flow._options[const.CONF_SWITCHES][0]["sync_state"] is True
    assert flow._options[const.CONF_SWITCHES][0]["pulse_command"] is False


def test_switch_pulse_only_ok():
    """Switch with pulse_command only should succeed."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                "sync_state": False,
                "pulse_command": True,
                "pulse_duration": 0.5,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert len(flow._options[const.CONF_SWITCHES]) == 1
    assert flow._options[const.CONF_SWITCHES][0]["pulse_command"] is True


def test_switch_sync_same_address_conflict():
    """Sync state with same or missing command address must fail."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    # No command_address provided (defaults to state_address)
    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                "sync_state": True,
                "pulse_command": False,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "sync_same_address"


def test_switch_sync_explicit_same_address_conflict():
    """Sync state with explicitly same command address must fail."""
    flow = make_options_flow(options={const.CONF_SWITCHES: []})

    result = run_flow(
        flow.async_step_switches(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.0",
                "sync_state": True,
                "pulse_command": False,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "sync_same_address"


def test_light_sync_pulse_conflict():
    """Enabling both sync_state and pulse_command on a light must fail."""
    flow = make_options_flow(options={const.CONF_LIGHTS: []})

    result = run_flow(
        flow.async_step_lights(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                "sync_state": True,
                "pulse_command": True,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "sync_pulse_conflict"
    assert len(flow._options[const.CONF_LIGHTS]) == 0


def test_light_sync_only_ok():
    """Light with sync_state and different command address should succeed."""
    flow = make_options_flow(options={const.CONF_LIGHTS: []})

    result = run_flow(
        flow.async_step_lights(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                const.CONF_COMMAND_ADDRESS: "DB1,X0.1",
                "sync_state": True,
                "pulse_command": False,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert len(flow._options[const.CONF_LIGHTS]) == 1
    assert flow._options[const.CONF_LIGHTS][0]["sync_state"] is True


def test_light_sync_same_address_conflict():
    """Light sync state without separate command address must fail."""
    flow = make_options_flow(options={const.CONF_LIGHTS: []})

    result = run_flow(
        flow.async_step_lights(
            {
                const.CONF_STATE_ADDRESS: "DB1,X0.0",
                "sync_state": True,
                "pulse_command": False,
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "sync_same_address"


# ============================================================================
# Climate (setpoint control): review-driven validation
# ============================================================================


def test_add_climate_setpoint_rejects_non_integer_preset_value():
    """A decimal preset_mode_*_value is rejected, not silently truncated."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_PRESET_MODE_HEAT_VALUE: "2.7",
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "invalid_integer"


def test_add_climate_setpoint_rejects_duplicate_preset_value():
    """Two HVAC modes can't be mapped to the same PLC value."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_PRESET_MODE_HEAT_VALUE: "5",
                const.CONF_PRESET_MODE_COOL_VALUE: "5",
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "duplicate_preset_value"


def test_add_climate_setpoint_rejects_duplicate_status_value():
    """Two HVAC statuses can't share the same PLC status value."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_HVAC_STATUS_HEATING_VALUES: "2,3",
                const.CONF_HVAC_STATUS_COOLING_VALUES: "3",
            }
        )
    )

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "duplicate_status_value"


def test_add_climate_setpoint_stores_defrosting_and_bidirectional():
    """New fields (DEFROSTING status, opt-in bidirectional readback) are
    validated and stored like any other climate setpoint field."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_PRESET_MODE_ADDRESS: "DB1,INT0",
                const.CONF_PRESET_MODE_BIDIRECTIONAL: True,
                const.CONF_HVAC_STATUS_ADDRESS: "DB1,INT8",
                const.CONF_HVAC_STATUS_DEFROSTING_VALUES: "9",
            }
        )
    )

    assert result["type"] == "create_entry"
    item = flow._options[const.CONF_CLIMATES][0]
    assert item[const.CONF_PRESET_MODE_BIDIRECTIONAL] is True
    assert item[const.CONF_HVAC_STATUS_DEFROSTING_VALUES] == "9"


def test_add_climate_setpoint_disabled_mode_stored_as_none():
    """Leaving a disabled-by-default preset value blank stores None, not
    the retired -1 sentinel."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
            }
        )
    )

    assert result["type"] == "create_entry"
    item = flow._options[const.CONF_CLIMATES][0]
    assert item[const.CONF_PRESET_MODE_AUTO_VALUE] is None
    assert item[const.CONF_PRESET_MODE_DRY_VALUE] is None
    assert item[const.CONF_PRESET_MODE_FAN_ONLY_VALUE] is None


def test_add_climate_setpoint_explicitly_cleared_core_mode_stays_disabled():
    """Clearing a preset value for a core mode (OFF/HEAT/COOL/HEAT_COOL,
    which have non-empty defaults unlike AUTO/DRY/FAN_ONLY) must store None,
    not silently fall back to that mode's default value. Regression test
    for a bug where clearing e.g. preset_mode_heat_cool_value left the mode
    enabled anyway because the default (3) was re-applied on top of the
    user's explicit None."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_PRESET_MODE_HEAT_COOL_VALUE: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    item = flow._options[const.CONF_CLIMATES][0]
    assert item[const.CONF_PRESET_MODE_HEAT_COOL_VALUE] is None
    # Untouched core modes still get their sensible defaults.
    assert item[const.CONF_PRESET_MODE_OFF_VALUE] == const.DEFAULT_PRESET_MODE_OFF_VALUE
    assert item[const.CONF_PRESET_MODE_HEAT_VALUE] == const.DEFAULT_PRESET_MODE_HEAT_VALUE
    assert item[const.CONF_PRESET_MODE_COOL_VALUE] == const.DEFAULT_PRESET_MODE_COOL_VALUE


def test_add_climate_setpoint_explicitly_cleared_core_status_stays_disabled():
    """Same bug class as above, mirrored on the status-matching side:
    hvac_status_off/heating/cooling_values also have non-empty historical
    defaults ("0"/"1"/"2"), unlike idle/drying/fan/preheating/defrosting
    which default to "". Clearing e.g. hvac_status_cooling_values must
    store "" (disabled), not silently fall back to "2" - a status address
    reporting 2 would otherwise keep matching COOLING even though the
    field looked cleared in the config UI."""
    flow = make_options_flow(options={const.CONF_CLIMATES: []})

    result = run_flow(
        flow.async_step_climates_setpoint(
            {
                const.CONF_CURRENT_TEMPERATURE_ADDRESS: "DB1,REAL0",
                const.CONF_TARGET_TEMPERATURE_ADDRESS: "DB1,REAL4",
                const.CONF_HVAC_STATUS_ADDRESS: "DB1,INT8",
                const.CONF_HVAC_STATUS_COOLING_VALUES: "",
            }
        )
    )

    assert result["type"] == "create_entry"
    item = flow._options[const.CONF_CLIMATES][0]
    assert item[const.CONF_HVAC_STATUS_COOLING_VALUES] == ""
    # Untouched core statuses still get their sensible defaults.
    assert item[const.CONF_HVAC_STATUS_OFF_VALUES] == const.DEFAULT_HVAC_STATUS_OFF_VALUES
    assert (
        item[const.CONF_HVAC_STATUS_HEATING_VALUES]
        == const.DEFAULT_HVAC_STATUS_HEATING_VALUES
    )
