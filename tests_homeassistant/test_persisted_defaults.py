"""Stored defaults are dropped by the real config-entry migration."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.s7plc.const import (
    CONF_MANUAL_CONNECTION_CONTROL,
    CONF_MAX_RETRIES,
    CONFIG_ENTRY_MINOR_VERSION,
    DOMAIN,
)


async def test_minor_migration_drops_stored_defaults(hass, plc_client):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test PLC",
        version=3,
        minor_version=1,
        data={
            CONF_HOST: "192.0.2.10",
            CONF_NAME: "Test PLC",
            CONF_SCAN_INTERVAL: 3600,
            CONF_MAX_RETRIES: 0,
            CONF_MANUAL_CONNECTION_CONTROL: True,
        },
        options={
            "buttons": [
                {"uid": "reset", "address": "DB1,X0.0", "button_pulse": 0.5},
                {"uid": "long", "address": "DB1,X0.1", "button_pulse": 2.0},
            ]
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 3
    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    assert entry.options["buttons"] == [
        {"uid": "reset", "address": "DB1,X0.0"},
        {"uid": "long", "address": "DB1,X0.1", "button_pulse": 2.0},
    ]


def test_panel_defaults_match_home_assistant_metadata(hass):
    from custom_components.s7plc.panel import _entry_payload

    entry = MockConfigEntry(domain=DOMAIN, version=3, data={}, options={})
    defaults = _entry_payload(entry)["defaults"]

    assert defaults["units"]["sensors"]["temperature"] == "°C"
    assert defaults["units"]["sensors"]["power"] == "W"
    assert defaults["units"]["numbers"]["temperature"] == "°C"
    assert defaults["state_classes"]["temperature"] == "measurement"
    assert defaults["state_classes"]["energy"] == "total_increasing"
    assert "gas" not in defaults["state_classes"]
