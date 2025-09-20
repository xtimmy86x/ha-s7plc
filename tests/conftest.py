"""Pytest configuration and stubs for Home Assistant dependencies."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Generic, TypeVar

# ---------------------------------------------------------------------------
# Stub minimal Home Assistant modules so the integration package can import.
# ---------------------------------------------------------------------------
if "homeassistant" not in sys.modules:
    homeassistant = ModuleType("homeassistant")
    sys.modules["homeassistant"] = homeassistant
else:
    homeassistant = sys.modules["homeassistant"]

# config_entries module
config_entries = ModuleType("homeassistant.config_entries")


class ConfigEntry:  # pragma: no cover - simple stub
    """Minimal stub used for type checking during imports."""

    def __init__(self, *args, **kwargs):
        self.data = {}
        self.entry_id = "test"

    async def async_on_unload(self, func):
        return func

    def add_update_listener(self, func):  # pragma: no cover - simple stub
        return func


config_entries.ConfigEntry = ConfigEntry
sys.modules["homeassistant.config_entries"] = config_entries
homeassistant.config_entries = config_entries

# const module
const = ModuleType("homeassistant.const")
const.CONF_HOST = "host"
const.CONF_NAME = "name"
const.CONF_PORT = "port"
const.CONF_SCAN_INTERVAL = "scan_interval"
sys.modules["homeassistant.const"] = const
homeassistant.const = const

# core module
core = ModuleType("homeassistant.core")


class HomeAssistant:  # pragma: no cover - simple stub
    """Minimal stand-in used for typing."""

    def __init__(self):
        self.data = {}
        self.config_entries = ModuleType("config_entries_api")

        async def async_forward_entry_setups(entry, platforms):
            return None

        async def async_unload_platforms(entry, platforms):
            return True

        async def async_reload(entry_id):
            return None

        async def async_add_executor_job(self, func, *args, **kwargs):
            return func(*args, **kwargs)

        self.config_entries.async_forward_entry_setups = async_forward_entry_setups
        self.config_entries.async_unload_platforms = async_unload_platforms
        self.config_entries.async_reload = async_reload
        self.async_add_executor_job = async_add_executor_job


core.HomeAssistant = HomeAssistant
sys.modules["homeassistant.core"] = core
homeassistant.core = core

# helpers package and submodules
helpers = ModuleType("homeassistant.helpers")
sys.modules["homeassistant.helpers"] = helpers
homeassistant.helpers = helpers

config_validation = ModuleType("homeassistant.helpers.config_validation")


def config_entry_only_config_schema(domain):  # pragma: no cover - stub
    return lambda config: config


config_validation.config_entry_only_config_schema = config_entry_only_config_schema
sys.modules["homeassistant.helpers.config_validation"] = config_validation
helpers.config_validation = config_validation

helpers_typing = ModuleType("homeassistant.helpers.typing")
helpers_typing.ConfigType = dict
sys.modules["homeassistant.helpers.typing"] = helpers_typing
helpers.typing = helpers_typing

update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

T = TypeVar("T")


class DataUpdateCoordinator(Generic[T]):  # pragma: no cover - simple stub
    def __init__(self, hass, logger, name=None, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

    async def async_config_entry_first_refresh(self):  # pragma: no cover - stub
        return None

    async def async_request_refresh(self):  # pragma: no cover - stub
        return None


update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
helpers.update_coordinator = update_coordinator

# util module
util = ModuleType("homeassistant.util")


def slugify(value):  # pragma: no cover - stub implementation
    return str(value).replace(" ", "_").lower()


util.slugify = slugify
sys.modules["homeassistant.util"] = util
homeassistant.util = util

# ---------------------------------------------------------------------------
# Ensure the repository root is importable for the tests.
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))