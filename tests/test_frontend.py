"""Dashboard registration through the integration setup, without opening a panel."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.s7plc import async_setup
from custom_components.s7plc.const import DOMAIN
from custom_components.s7plc.frontend import (
    SCHEDULE_CARD_MODULE,
    SCHEDULE_CARD_PATH,
    async_setup_dashboard,
)


@pytest.fixture
def dashboard_hass(monkeypatch):
    frontend = ModuleType("homeassistant.components.frontend")
    frontend.add_extra_js_url = Mock()
    monkeypatch.setitem(sys.modules, frontend.__name__, frontend)
    http = ModuleType("homeassistant.components.http")
    http.StaticPathConfig = lambda url, path, **kwargs: SimpleNamespace(
        url=url, path=path, **kwargs
    )
    monkeypatch.setitem(sys.modules, http.__name__, http)
    hass = SimpleNamespace(
        data={}, http=SimpleNamespace(async_register_static_paths=AsyncMock())
    )
    return hass, frontend.add_extra_js_url


@pytest.mark.asyncio
async def test_setup_loads_card_independently_of_panel(dashboard_hass, monkeypatch):
    hass, add_module = dashboard_hass
    panel = AsyncMock()
    monkeypatch.setattr("custom_components.s7plc.panel.async_setup_panel", panel)

    assert await async_setup(hass, {})
    add_module.assert_called_once_with(hass, SCHEDULE_CARD_MODULE)
    asset = hass.http.async_register_static_paths.call_args.args[0][0]
    assert asset.url == SCHEDULE_CARD_PATH
    assert Path(asset.path).is_file()
    assert asset.cache_headers is False
    panel.assert_awaited_once_with(hass)
    # No dependency on Lovelace's storage collection or any configured PLC.
    assert list(hass.data) == [DOMAIN]


@pytest.mark.asyncio
async def test_dashboard_setup_is_idempotent(dashboard_hass):
    hass, add_module = dashboard_hass
    await async_setup_dashboard(hass)
    await async_setup_dashboard(hass)
    hass.http.async_register_static_paths.assert_awaited_once()
    add_module.assert_called_once_with(hass, SCHEDULE_CARD_MODULE)


@pytest.mark.asyncio
async def test_failed_static_registration_does_not_claim_success(dashboard_hass):
    hass, add_module = dashboard_hass
    hass.http.async_register_static_paths.side_effect = RuntimeError("HTTP not ready")
    with pytest.raises(RuntimeError, match="HTTP not ready"):
        await async_setup_dashboard(hass)
    add_module.assert_not_called()
    hass.http.async_register_static_paths.side_effect = None
    await async_setup_dashboard(hass)
    add_module.assert_called_once_with(hass, SCHEDULE_CARD_MODULE)
