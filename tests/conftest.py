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
        self.options = {}
        self.entry_id = "test"

    async def async_on_unload(self, func):
        return func

    def add_update_listener(self, func):  # pragma: no cover - simple stub
        return func


class ConfigFlow:  # pragma: no cover - simple stub
    """Barebones replacement providing helpers used in tests."""

    def __init_subclass__(cls, **kwargs):  # pragma: no cover - accept kwargs
        return super().__init_subclass__()

    async def async_show_form(self, *args, **kwargs):
        return {"type": "form", "args": args, "kwargs": kwargs}

    async def async_show_menu(self, *args, **kwargs):
        return {"type": "menu", "args": args, "kwargs": kwargs}

    async def async_create_entry(self, *args, **kwargs):
        return {"type": "create_entry", "args": args, "kwargs": kwargs}

    async def async_set_unique_id(self, *args, **kwargs):
        return None

    def _abort_if_unique_id_configured(self):  # pragma: no cover - stub
        return None


class OptionsFlow:  # pragma: no cover - simple stub
    async def async_create_entry(self, *args, **kwargs):
        return {"type": "create_entry", "args": args, "kwargs": kwargs}


config_entries.ConfigEntry = ConfigEntry
config_entries.ConfigFlow = ConfigFlow
config_entries.OptionsFlow = OptionsFlow
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


def callback(func):  # pragma: no cover - simple passthrough decorator
    return func


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
core.callback = callback
sys.modules["homeassistant.core"] = core
homeassistant.core = core

# exceptions module
exceptions = ModuleType("homeassistant.exceptions")


class HomeAssistantError(Exception):  # pragma: no cover - simple stub
    pass


exceptions.HomeAssistantError = HomeAssistantError


sys.modules["homeassistant.exceptions"] = exceptions
homeassistant.exceptions = exceptions

# helpers package and submodules
helpers = ModuleType("homeassistant.helpers")
sys.modules["homeassistant.helpers"] = helpers
homeassistant.helpers = helpers

config_validation = ModuleType("homeassistant.helpers.config_validation")


def config_entry_only_config_schema(domain):  # pragma: no cover - stub
    return lambda config: config


config_validation.config_entry_only_config_schema = config_entry_only_config_schema
config_validation.multi_select = lambda options: (lambda values: values)
sys.modules["homeassistant.helpers.config_validation"] = config_validation
helpers.config_validation = config_validation

helpers_typing = ModuleType("homeassistant.helpers.typing")
helpers_typing.ConfigType = dict
sys.modules["homeassistant.helpers.typing"] = helpers_typing
helpers.typing = helpers_typing

update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

T = TypeVar("T")


class UpdateFailed(exceptions.HomeAssistantError):  # pragma: no cover - simple stub
    """Raised when a data update fails."""


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


class CoordinatorEntity:  # pragma: no cover - simple stub
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = getattr(coordinator, "hass", None)
        self._ha_state_calls = 0

    def async_write_ha_state(self):
        self._ha_state_calls += 1


update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
update_coordinator.CoordinatorEntity = CoordinatorEntity
update_coordinator.UpdateFailed = UpdateFailed
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
helpers.update_coordinator = update_coordinator

# helpers.entity module
helpers_entity = ModuleType("homeassistant.helpers.entity")


class DeviceInfo(dict):  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


helpers_entity.DeviceInfo = DeviceInfo
sys.modules["homeassistant.helpers.entity"] = helpers_entity
helpers.entity = helpers_entity

# helpers.selector module
selector = ModuleType("homeassistant.helpers.selector")


class SelectOptionDict(dict):  # pragma: no cover - simple stub
    def __init__(self, *, value, label):
        super().__init__(value=value, label=label)


class SelectSelectorConfig:  # pragma: no cover - simple stub
    def __init__(self, options=None, custom_value=False, mode=None):
        self.options = options or []
        self.custom_value = custom_value
        self.mode = mode


class SelectSelector:  # pragma: no cover - simple stub
    def __init__(self, config):
        self.config = config


class SelectSelectorMode:  # pragma: no cover - simple stub
    DROPDOWN = "dropdown"


class TextSelector:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class BooleanSelector:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


selector.SelectOptionDict = SelectOptionDict
selector.SelectSelector = SelectSelector
selector.SelectSelectorConfig = SelectSelectorConfig
selector.SelectSelectorMode = SelectSelectorMode
selector.TextSelector = TextSelector
selector.BooleanSelector = BooleanSelector
sys.modules["homeassistant.helpers.selector"] = selector
helpers.selector = selector

# util module
util = ModuleType("homeassistant.util")


def slugify(value):  # pragma: no cover - stub implementation
    return str(value).replace(" ", "_").lower()


util.slugify = slugify
sys.modules["homeassistant.util"] = util
homeassistant.util = util

# components package
components = ModuleType("homeassistant.components")
sys.modules["homeassistant.components"] = components
homeassistant.components = components

network = ModuleType("homeassistant.components.network")


async def async_get_adapters(hass):  # pragma: no cover - stub
    return []


network.async_get_adapters = async_get_adapters
sys.modules["homeassistant.components.network"] = network
components.network = network

from enum import Enum


class BinarySensorDeviceClass(Enum):  # pragma: no cover - simple stub
    DOOR = "door"


binary_sensor = ModuleType("homeassistant.components.binary_sensor")
binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
sys.modules["homeassistant.components.binary_sensor"] = binary_sensor
components.binary_sensor = binary_sensor


class ButtonEntity:  # pragma: no cover - simple stub
    async def async_press(self):
        return None


button = ModuleType("homeassistant.components.button")
button.ButtonEntity = ButtonEntity
sys.modules["homeassistant.components.button"] = button
components.button = button


class SensorDeviceClass(Enum):  # pragma: no cover - simple stub
    TEMPERATURE = "temperature"


sensor = ModuleType("homeassistant.components.sensor")
sensor.SensorDeviceClass = SensorDeviceClass
sys.modules["homeassistant.components.sensor"] = sensor
components.sensor = sensor

# voluptuous stub
voluptuous = ModuleType("voluptuous")


class _Schema:  # pragma: no cover - simple stub
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, value):
        return value


def _optional_factory(base_cls):
    class _Option(base_cls):  # pragma: no cover - simple stub
        def __new__(cls, key, default=None):
            obj = base_cls.__new__(cls, key)
            obj.default = default
            return obj

    return _Option


voluptuous.Schema = lambda schema: _Schema(schema)
voluptuous.Required = _optional_factory(str)
voluptuous.Optional = _optional_factory(str)
sys.modules["voluptuous"] = voluptuous


def pytest_configure(config):  # pragma: no cover - register custom marks
    config.addinivalue_line("markers", "asyncio: mark test as using asyncio")

# ---------------------------------------------------------------------------
# Ensure the repository root is importable for the tests.
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))