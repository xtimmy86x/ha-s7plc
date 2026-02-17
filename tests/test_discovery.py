"""Tests for host discovery in config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.const import CONF_HOST

from custom_components.s7plc import config_flow


@pytest.fixture
def mock_network_adapters():
    """Mock network adapters."""
    return [
        {
            "enabled": True,
            "ipv4": [
                {
                    "address": "192.168.1.100",
                    "network_prefix": 24,
                }
            ],
        }
    ]


@pytest.fixture
def mock_open_connection():
    """Mock asyncio.open_connection."""
    async def _mock_connection(host, port):
        # Simulate successful connection for .10, .20, .30
        if host in ["192.168.1.10", "192.168.1.20", "192.168.1.30"]:
            reader = MagicMock()
            writer = MagicMock()
            writer.close = MagicMock()
            writer.wait_closed = AsyncMock()
            return reader, writer
        raise OSError("Connection refused")
    
    return _mock_connection


@pytest.mark.asyncio
async def test_discovery_finds_hosts(
    fake_hass,
    mock_network_adapters,
    mock_open_connection,
):
    """Test that discovery finds PLC hosts."""
    
    # Setup config_entries mock
    fake_hass.config_entries = MagicMock()
    fake_hass.config_entries.async_entries = MagicMock(return_value=[])
    
    with patch("homeassistant.components.network.async_get_adapters", return_value=mock_network_adapters):
        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            flow = config_flow.S7PLCConfigFlow()
            flow.hass = fake_hass
            
            discovered = await flow._async_get_discovered_hosts()
            
            # Should find the three hosts that responded
            assert len(discovered) == 3
            assert "192.168.1.10" in discovered
            assert "192.168.1.20" in discovered
            assert "192.168.1.30" in discovered


@pytest.mark.asyncio
async def test_discovery_filters_configured_hosts(
    fake_hass,
    mock_network_adapters,
    mock_open_connection,
):
    """Test that discovery filters out already configured hosts."""
    
    # Create a mock config entry for 192.168.1.10
    mock_entry = MagicMock()
    mock_entry.data = {CONF_HOST: "192.168.1.10"}
    
    # Setup config_entries mock
    fake_hass.config_entries = MagicMock()
    fake_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    
    with patch("homeassistant.components.network.async_get_adapters", return_value=mock_network_adapters):
        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            flow = config_flow.S7PLCConfigFlow()
            flow.hass = fake_hass
            
            discovered = await flow._async_get_discovered_hosts()
            
            # Should find only two hosts (10 is already configured)
            assert len(discovered) == 2
            assert "192.168.1.10" not in discovered
            assert "192.168.1.20" in discovered
            assert "192.168.1.30" in discovered


@pytest.mark.asyncio
async def test_discovery_handles_no_hosts(
    fake_hass,
    mock_network_adapters,
):
    """Test that discovery handles case when no hosts respond."""
    
    async def _no_hosts(host, port):
        raise OSError("Connection refused")
    
    # Setup config_entries mock
    fake_hass.config_entries = MagicMock()
    fake_hass.config_entries.async_entries = MagicMock(return_value=[])
    
    with patch("homeassistant.components.network.async_get_adapters", return_value=mock_network_adapters):
        with patch("asyncio.open_connection", side_effect=_no_hosts):
            flow = config_flow.S7PLCConfigFlow()
            flow.hass = fake_hass
            
            discovered = await flow._async_get_discovered_hosts()
            
            # Should return empty list
            assert len(discovered) == 0


@pytest.mark.asyncio
async def test_discovery_caches_results(
    fake_hass,
    mock_network_adapters,
    mock_open_connection,
):
    """Test that discovery caches results."""
    
    # Setup config_entries mock
    fake_hass.config_entries = MagicMock()
    fake_hass.config_entries.async_entries = MagicMock(return_value=[])
    
    with patch("homeassistant.components.network.async_get_adapters", return_value=mock_network_adapters) as mock_adapters:
        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            flow = config_flow.S7PLCConfigFlow()
            flow.hass = fake_hass
            
            # First call
            discovered1 = await flow._async_get_discovered_hosts()
            
            # Second call should use cache
            discovered2 = await flow._async_get_discovered_hosts()
            
            # Should be the same
            assert discovered1 == discovered2
            
            # Network should only be queried once
            assert mock_adapters.call_count == 1
