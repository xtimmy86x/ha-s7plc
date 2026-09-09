"""Real Home Assistant fixtures, isolated from tests/conftest.py's stubs."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.s7plc.const import (
    CONF_ADDRESS,
    CONF_MANUAL_CONNECTION_CONTROL,
    CONF_MAX_RETRIES,
    CONF_SENSORS,
    CONF_UID,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Load the repository integration through HA's normal loader."""


@pytest.fixture
def plc_client():
    """Mock only the external pyS7 transport, leaving HA and coordinator real."""
    client = Mock()
    client.is_connected = False
    client.metrics = None

    async def connect():
        client.is_connected = True

    async def disconnect():
        client.is_connected = False

    client.connect = AsyncMock(side_effect=connect)
    client.disconnect = AsyncMock(side_effect=disconnect)
    client.read = AsyncMock(side_effect=lambda tags, **kwargs: [21] * len(tags))
    client.write = AsyncMock()
    client.get_cpu_info = AsyncMock(return_value={})
    with patch(
        "custom_components.s7plc.plc.connection_manager.pyS7.AsyncS7Client",
        return_value=client,
    ):
        yield client


@pytest.fixture
def config_entry(hass):
    """One persisted PLC entry with a data sensor and connection control."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test PLC",
        version=3,
        data={
            CONF_HOST: "192.0.2.10",
            CONF_NAME: "Test PLC",
            CONF_SCAN_INTERVAL: 3600,
            CONF_MAX_RETRIES: 0,
            CONF_MANUAL_CONNECTION_CONTROL: True,
        },
        options={
            CONF_SENSORS: [
                {
                    CONF_NAME: "Temperature",
                    CONF_ADDRESS: "DB1,INT0",
                    CONF_UID: "temperature",
                }
            ]
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded_entry(hass, config_entry, plc_client):
    """Wait for a data refresh after the concurrently loaded platforms add tags."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    return config_entry
