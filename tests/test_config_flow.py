from __future__ import annotations

from types import SimpleNamespace

from custom_components.s7plc import config_flow
from custom_components.s7plc import const


def make_options_flow(options=None):
    entry = SimpleNamespace(options=options or {})
    return config_flow.S7PLCOptionsFlow(entry)


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