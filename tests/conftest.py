"""Pytest configuration and stubs for Home Assistant dependencies.

Testing Approach:
-----------------
This test suite uses a stub-based approach with custom mocks instead of the
official pytest-homeassistant-custom-component package. This choice provides:

- Fast test execution: ~5 seconds for 254 tests
- Full control over mock behavior
- No version compatibility issues between HA versions
- Lightweight fixtures focused on integration logic

The official pytest-homeassistant-custom-component package was evaluated but
rejected due to:
- Version sensitivity requiring exact HA API alignment
- Slower test execution (30-60s vs 5s)
- Heavy auto-mocking that can obscure integration-specific issues
- Additional maintenance burden tracking HA core changes

All mocks are centralized in this file for consistency. Individual test files
should import fixtures from here rather than defining local duplicates.
"""

from __future__ import annotations

import asyncio
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Generic, TypeVar
import pytest

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
        self.data = kwargs.get("data", {})
        self.options = kwargs.get("options", {})
        self.entry_id = kwargs.get("entry_id", "test")
        self.title = kwargs.get("title", "Test Entry")
        self.runtime_data = None  # Will be set by async_setup_entry

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
    def async_show_form(self, *args, **kwargs):
        return {"type": "form", "args": args, "kwargs": kwargs}

    def async_show_menu(self, *args, **kwargs):
        return {"type": "menu", "args": args, "kwargs": kwargs}
    
    async def async_create_entry(self, *args, **kwargs):
        return {"type": "create_entry", "args": args, "kwargs": kwargs}

    def add_suggested_values_to_schema(self, data_schema, suggested_values):
        """Populate schema markers with suggested values (stub)."""
        import copy
        import voluptuous as vol

        if suggested_values is None:
            return data_schema
        schema = {}
        for key, val in data_schema.schema.items():
            new_key = key
            if key in suggested_values and isinstance(key, vol.Marker):
                new_key = copy.copy(key)
                new_key.description = {"suggested_value": suggested_values[key.schema]}
            schema[new_key] = val
        return vol.Schema(schema)


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
const.CONCENTRATION_PARTS_PER_BILLION = "ppb"
const.CONCENTRATION_PARTS_PER_MILLION = "ppm"
const.PERCENTAGE = "%"


class _UnitEnum:
    """Base class for unit enums."""
    pass


class UnitOfElectricCurrent(_UnitEnum):
    AMPERE = "A"


class UnitOfElectricPotential(_UnitEnum):
    VOLT = "V"


class UnitOfEnergy(_UnitEnum):
    KILO_WATT_HOUR = "kWh"


class UnitOfFrequency(_UnitEnum):
    HERTZ = "Hz"


class UnitOfPower(_UnitEnum):
    WATT = "W"


class UnitOfPressure(_UnitEnum):
    HPA = "hPa"


class UnitOfSpeed(_UnitEnum):
    METERS_PER_SECOND = "m/s"


class UnitOfTemperature(_UnitEnum):
    CELSIUS = "°C"


const.UnitOfElectricCurrent = UnitOfElectricCurrent
const.UnitOfElectricPotential = UnitOfElectricPotential
const.UnitOfEnergy = UnitOfEnergy
const.UnitOfFrequency = UnitOfFrequency
const.UnitOfPower = UnitOfPower
const.UnitOfPressure = UnitOfPressure
const.UnitOfSpeed = UnitOfSpeed
const.UnitOfTemperature = UnitOfTemperature
sys.modules["homeassistant.const"] = const
homeassistant.const = const

# core module
core = ModuleType("homeassistant.core")


def callback(func):  # pragma: no cover - simple passthrough decorator
    return func


class State:  # pragma: no cover - simple stub
    """Minimal State stub for testing."""

    def __init__(self, entity_id: str, state: str, attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        from datetime import datetime
        self.last_updated = datetime.now()


class Event:  # pragma: no cover - simple stub
    """Minimal Event stub for testing."""

    def __init__(self, event_type: str, data=None):
        self.event_type = event_type
        self.data = data or {}


class HomeAssistant:  # pragma: no cover - simple stub
    """Minimal stand-in used for typing."""

    def __init__(self):
        self.data = {}
        self.config_entries = ModuleType("config_entries_api")
        self.services = ModuleType("services_api")
        
        # Track registered services
        self._services_registry = {}
        
        # Mock services.async_call
        async def async_call(domain, service, service_data=None, blocking=True, **kwargs):
            return None
        
        self.services.async_call = async_call
        
        # Mock services.async_register
        def async_register(domain, service, handler, schema=None):
            key = f"{domain}.{service}"
            self._services_registry[key] = {
                "handler": handler,
                "schema": schema
            }
        
        self.services.async_register = async_register
        
        # Mock services.async_remove
        def async_remove(domain, service):
            key = f"{domain}.{service}"
            self._services_registry.pop(key, None)
        
        self.services.async_remove = async_remove
        
        # Mock services.has_service
        def has_service(domain, service):
            key = f"{domain}.{service}"
            return key in self._services_registry
        
        self.services.has_service = has_service
        
        # Mock event loop with call_later
        import asyncio
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            # If no loop is running, create a minimal mock
            class MockLoop:
                def call_later(self, delay, callback):
                    # Execute immediately in tests
                    callback()
                    return None
            self.loop = MockLoop()

        async def async_forward_entry_setups(entry, platforms):
            return None

        async def async_unload_platforms(entry, platforms):
            return True

        async def async_reload(entry_id):
            return None

        async def async_update_entry(entry, *, title=None, data=None, unique_id=None):
            if title is not None:
                entry.title = title
            if data is not None:
                entry.data = data
            if unique_id is not None:
                entry.unique_id = unique_id
            return None

        def async_entries(domain=None):
            entries = list(self.config_entries._entries)
            if domain is None:
                return entries
            return [
                entry
                for entry in entries
                if getattr(entry, "domain", None) == domain
            ]

        async def async_add_executor_job(func, *args, **kwargs):
            return func(*args, **kwargs)
        
        def async_create_task(coro):
            """Mock for hass.async_create_task - executes immediately in tests."""
            import asyncio
            return asyncio.create_task(coro)
        
        def async_create_background_task(coro, name=None):
            """Mock for hass.async_create_background_task - executes immediately in tests."""
            import asyncio
            return asyncio.create_task(coro)

        def async_get_entry(entry_id):
            """Get config entry by id."""
            for entry in self.config_entries._entries:
                if entry.entry_id == entry_id:
                    return entry
            return None

        self.config_entries.async_forward_entry_setups = async_forward_entry_setups
        self.config_entries.async_unload_platforms = async_unload_platforms
        self.config_entries.async_reload = async_reload
        self.config_entries.async_update_entry = async_update_entry
        self.config_entries.async_entries = async_entries
        self.config_entries.async_get_entry = async_get_entry
        self.config_entries._entries = []
        self.async_add_executor_job = async_add_executor_job
        self.async_create_task = async_create_task
        self.async_create_background_task = async_create_background_task


core.HomeAssistant = HomeAssistant
core.callback = callback
core.State = State
core.Event = Event
sys.modules["homeassistant.core"] = core
homeassistant.core = core

# data_entry_flow module
data_entry_flow = ModuleType("homeassistant.data_entry_flow")


class FlowResult(dict):  # pragma: no cover - simple stub
    pass


data_entry_flow.FlowResult = FlowResult
sys.modules["homeassistant.data_entry_flow"] = data_entry_flow
homeassistant.data_entry_flow = data_entry_flow

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

    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Called when entity is added to hass."""
        pass


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


class EntityCategory:  # pragma: no cover - simple stub
    """Stub for EntityCategory enum."""
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


helpers_entity.DeviceInfo = DeviceInfo
helpers_entity.EntityCategory = EntityCategory
sys.modules["homeassistant.helpers.entity"] = helpers_entity
helpers.entity = helpers_entity

# helpers.event module
helpers_event = ModuleType("homeassistant.helpers.event")


def async_track_state_change_event(hass, entity_ids, action):  # pragma: no cover - stub
    """Mock for async_track_state_change_event."""
    return lambda: None


def async_call_later(hass, delay, action):  # pragma: no cover - stub
    """Mock for async_call_later."""
    return lambda: None


helpers_event.async_track_state_change_event = async_track_state_change_event
helpers_event.async_call_later = async_call_later
sys.modules["homeassistant.helpers.event"] = helpers_event
helpers.event = helpers_event

# helpers.entity_registry module
entity_registry = ModuleType("homeassistant.helpers.entity_registry")


class MockEntityRegistryEntry:  # pragma: no cover - stub implementation
    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id
        self.area_id = None


class MockEntityRegistry:  # pragma: no cover - stub implementation
    def __init__(self):
        self.entities = {}

    def async_remove(self, entity_id: str):
        """Remove entity from registry."""
        self.entities.pop(entity_id, None)

    def async_get_entity_id(self, platform: str, domain: str, unique_id: str):
        """Get entity_id from platform, domain, and unique_id."""
        # In the tests, we don't have entities registered
        # Return None to simulate no matching entity
        return None

    def async_update_entity(self, entity_id: str, **kwargs):
        """Update entity in registry."""
        # Stub implementation - accepts area_id parameter
        pass


_mock_entity_registry = MockEntityRegistry()


def async_get(hass):  # pragma: no cover - stub implementation
    """Get entity registry."""
    return _mock_entity_registry


def async_entries_for_config_entry(registry, entry_id: str):  # pragma: no cover - stub implementation
    """Return entities for a config entry."""
    return [e for e in registry.entities.values() if e.config_entry_id == entry_id]


entity_registry.async_get = async_get
entity_registry.async_entries_for_config_entry = async_entries_for_config_entry
entity_registry.MockEntityRegistry = MockEntityRegistry
entity_registry.MockEntityRegistryEntry = MockEntityRegistryEntry
sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
helpers.entity_registry = entity_registry

# helpers.area_registry module
area_registry = ModuleType("homeassistant.helpers.area_registry")


class MockAreaEntry:  # pragma: no cover - stub implementation
    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name


class MockAreaRegistry:  # pragma: no cover - stub implementation
    def __init__(self):
        self.areas = []

    def async_list_areas(self):
        """Return all areas."""
        return self.areas


_mock_area_registry = MockAreaRegistry()


def async_get_area_registry(hass):  # pragma: no cover - stub implementation
    """Get area registry."""
    return _mock_area_registry


area_registry.async_get = async_get_area_registry
area_registry.MockAreaRegistry = MockAreaRegistry
area_registry.MockAreaEntry = MockAreaEntry
sys.modules["homeassistant.helpers.area_registry"] = area_registry
helpers.area_registry = area_registry

# helpers.restore_state module
restore_state = ModuleType("homeassistant.helpers.restore_state")


class RestoreEntity:  # pragma: no cover - stub implementation
    """Mock RestoreEntity for testing."""
    
    async def async_get_last_state(self):
        """Return None for last state in tests (no restored state)."""
        return None


restore_state.RestoreEntity = RestoreEntity
sys.modules["homeassistant.helpers.restore_state"] = restore_state
helpers.restore_state = restore_state

# helpers.issue_registry module
issue_registry = ModuleType("homeassistant.helpers.issue_registry")


class IssueSeverity:  # pragma: no cover - stub implementation
    WARNING = "warning"
    ERROR = "error"


def async_create_issue(hass, domain, issue_id, **kwargs):  # pragma: no cover - stub implementation
    """Create an issue."""
    pass


def async_delete_issue(hass, domain, issue_id):  # pragma: no cover - stub implementation
    """Delete an issue."""
    pass


issue_registry.IssueSeverity = IssueSeverity
issue_registry.async_create_issue = async_create_issue
issue_registry.async_delete_issue = async_delete_issue
sys.modules["homeassistant.helpers.issue_registry"] = issue_registry
helpers.issue_registry = issue_registry

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


class NumberSelectorConfig:  # pragma: no cover - simple stub
    def __init__(self, *, mode=None, min=None, max=None, step=None):
        self.mode = mode
        self.min = min
        self.max = max
        self.step = step

class NumberSelector:  # pragma: no cover - simple stub
    def __init__(self, config):
        self.config = config


class NumberSelectorMode:  # pragma: no cover - simple stub
    BOX = "box"


class AreaSelectorConfig:  # pragma: no cover - simple stub
    def __init__(self, **kwargs):
        pass


class AreaSelector:  # pragma: no cover - simple stub
    def __init__(self, config):
        self.config = config


selector.SelectOptionDict = SelectOptionDict
selector.SelectSelector = SelectSelector
selector.SelectSelectorConfig = SelectSelectorConfig
selector.SelectSelectorMode = SelectSelectorMode
selector.TextSelector = TextSelector
selector.BooleanSelector = BooleanSelector
selector.NumberSelector = NumberSelector
selector.NumberSelectorConfig = NumberSelectorConfig
selector.NumberSelectorMode = NumberSelectorMode
selector.AreaSelector = AreaSelector
selector.AreaSelectorConfig = AreaSelectorConfig
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

# repairs component
repairs = ModuleType("homeassistant.components.repairs")


class RepairsFlow:  # pragma: no cover - stub
    """Stub for RepairsFlow."""
    pass


repairs.RepairsFlow = RepairsFlow
sys.modules["homeassistant.components.repairs"] = repairs
components.repairs = repairs


class BinarySensorDeviceClass(Enum):  # pragma: no cover - simple stub
    DOOR = "door"
    CONNECTIVITY = "connectivity"


class BinarySensorEntity:  # pragma: no cover - simple stub
    """Stub for BinarySensorEntity."""
    pass


binary_sensor = ModuleType("homeassistant.components.binary_sensor")
binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
binary_sensor.BinarySensorEntity = BinarySensorEntity
sys.modules["homeassistant.components.binary_sensor"] = binary_sensor
components.binary_sensor = binary_sensor


class ButtonEntity:  # pragma: no cover - simple stub
    async def async_press(self):
        return None


button = ModuleType("homeassistant.components.button")
button.ButtonEntity = ButtonEntity
sys.modules["homeassistant.components.button"] = button
components.button = button


class NumberEntity:  # pragma: no cover - simple stub
    @property
    def native_min_value(self):
        return getattr(self, "_attr_native_min_value", None)

    @property
    def native_max_value(self):
        return getattr(self, "_attr_native_max_value", None)


class _NumberDeviceClassMeta(type):
    """Metaclass to make NumberDeviceClass iterable."""
    def __iter__(cls):
        return iter([
            cls.APPARENT_POWER, cls.AQI, cls.ATMOSPHERIC_PRESSURE, cls.BATTERY,
            cls.CURRENT, cls.DATA_RATE, cls.DATA_SIZE, cls.DISTANCE, cls.DURATION,
            cls.ENERGY, cls.ENERGY_STORAGE, cls.FREQUENCY, cls.GAS, cls.HUMIDITY,
            cls.ILLUMINANCE, cls.IRRADIANCE, cls.MOISTURE, cls.MONETARY,
            cls.NITROGEN_DIOXIDE, cls.NITROUS_OXIDE, cls.OZONE, cls.PH,
            cls.PM1, cls.PM10, cls.PM25, cls.POWER, cls.POWER_FACTOR,
            cls.PRECIPITATION, cls.PRECIPITATION_INTENSITY, cls.PRESSURE,
            cls.REACTIVE_POWER, cls.SIGNAL_STRENGTH, cls.SOUND_PRESSURE,
            cls.SPEED, cls.SULPHUR_DIOXIDE, cls.TEMPERATURE,
            cls.VOLATILE_ORGANIC_COMPOUNDS, cls.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
            cls.VOLTAGE, cls.VOLUME, cls.VOLUME_FLOW_RATE, cls.VOLUME_STORAGE,
            cls.WATER, cls.WEIGHT, cls.WIND_SPEED
        ])


class NumberDeviceClass(metaclass=_NumberDeviceClassMeta):  # pragma: no cover - stub for device classes
    """Enum-like class for number device classes."""
    
    class _DeviceClass:
        def __init__(self, value):
            self.value = value
    
    APPARENT_POWER = _DeviceClass("apparent_power")
    AQI = _DeviceClass("aqi")
    ATMOSPHERIC_PRESSURE = _DeviceClass("atmospheric_pressure")
    BATTERY = _DeviceClass("battery")
    CURRENT = _DeviceClass("current")
    DATA_RATE = _DeviceClass("data_rate")
    DATA_SIZE = _DeviceClass("data_size")
    DISTANCE = _DeviceClass("distance")
    DURATION = _DeviceClass("duration")
    ENERGY = _DeviceClass("energy")
    ENERGY_STORAGE = _DeviceClass("energy_storage")
    FREQUENCY = _DeviceClass("frequency")
    GAS = _DeviceClass("gas")
    HUMIDITY = _DeviceClass("humidity")
    ILLUMINANCE = _DeviceClass("illuminance")
    IRRADIANCE = _DeviceClass("irradiance")
    MOISTURE = _DeviceClass("moisture")
    MONETARY = _DeviceClass("monetary")
    NITROGEN_DIOXIDE = _DeviceClass("nitrogen_dioxide")
    NITROUS_OXIDE = _DeviceClass("nitrous_oxide")
    OZONE = _DeviceClass("ozone")
    PH = _DeviceClass("ph")
    PM1 = _DeviceClass("pm1")
    PM10 = _DeviceClass("pm10")
    PM25 = _DeviceClass("pm25")
    POWER = _DeviceClass("power")
    POWER_FACTOR = _DeviceClass("power_factor")
    PRECIPITATION = _DeviceClass("precipitation")
    PRECIPITATION_INTENSITY = _DeviceClass("precipitation_intensity")
    PRESSURE = _DeviceClass("pressure")
    REACTIVE_POWER = _DeviceClass("reactive_power")
    SIGNAL_STRENGTH = _DeviceClass("signal_strength")
    SOUND_PRESSURE = _DeviceClass("sound_pressure")
    SPEED = _DeviceClass("speed")
    SULPHUR_DIOXIDE = _DeviceClass("sulphur_dioxide")
    TEMPERATURE = _DeviceClass("temperature")
    VOLATILE_ORGANIC_COMPOUNDS = _DeviceClass("volatile_organic_compounds")
    VOLATILE_ORGANIC_COMPOUNDS_PARTS = _DeviceClass("volatile_organic_compounds_parts")
    VOLTAGE = _DeviceClass("voltage")
    VOLUME = _DeviceClass("volume")
    VOLUME_FLOW_RATE = _DeviceClass("volume_flow_rate")
    VOLUME_STORAGE = _DeviceClass("volume_storage")
    WATER = _DeviceClass("water")
    WEIGHT = _DeviceClass("weight")
    WIND_SPEED = _DeviceClass("wind_speed")
    WEIGHT = _DeviceClass("weight")
    WIND_SPEED = _DeviceClass("wind_speed")


number = ModuleType("homeassistant.components.number")
number.NumberEntity = NumberEntity
number.NumberDeviceClass = NumberDeviceClass
sys.modules["homeassistant.components.number"] = number
components.number = number


class TextEntity:  # pragma: no cover - simple stub
    """Minimal TextEntity stub."""
    pass


text = ModuleType("homeassistant.components.text")
text.TextEntity = TextEntity
sys.modules["homeassistant.components.text"] = text
components.text = text


class SwitchEntity:  # pragma: no cover - simple stub
    """Minimal SwitchEntity stub."""
    pass


switch = ModuleType("homeassistant.components.switch")
switch.SwitchEntity = SwitchEntity
sys.modules["homeassistant.components.switch"] = switch
components.switch = switch


class ColorMode:  # pragma: no cover - simple stub
    """Minimal ColorMode stub."""
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"


class LightEntity:  # pragma: no cover - simple stub
    """Minimal LightEntity stub."""
    pass


light = ModuleType("homeassistant.components.light")
light.ColorMode = ColorMode
light.LightEntity = LightEntity
sys.modules["homeassistant.components.light"] = light
components.light = light


class CoverEntityFeature:  # pragma: no cover - simple stub
    """Minimal CoverEntityFeature stub."""
    OPEN = 1
    CLOSE = 2
    SET_POSITION = 4
    STOP = 8
    OPEN_TILT = 16
    CLOSE_TILT = 32
    STOP_TILT = 64
    SET_TILT_POSITION = 128


class CoverEntity:  # pragma: no cover - simple stub
    """Minimal CoverEntity stub."""
    pass


class CoverDeviceClass(Enum):  # pragma: no cover - simple stub
    """Cover device classes."""
    AWNING = "awning"
    BLIND = "blind"
    CURTAIN = "curtain"
    DAMPER = "damper"
    DOOR = "door"
    GARAGE = "garage"
    GATE = "gate"
    SHADE = "shade"
    SHUTTER = "shutter"
    WINDOW = "window"


cover = ModuleType("homeassistant.components.cover")
cover.CoverEntityFeature = CoverEntityFeature
cover.CoverEntity = CoverEntity
cover.CoverDeviceClass = CoverDeviceClass
sys.modules["homeassistant.components.cover"] = cover
components.cover = cover


class ClimateEntityFeature:  # pragma: no cover - simple stub
    """Minimal ClimateEntityFeature stub."""
    TARGET_TEMPERATURE = 1
    TARGET_TEMPERATURE_RANGE = 2
    TARGET_HUMIDITY = 4
    FAN_MODE = 8
    PRESET_MODE = 16
    SWING_MODE = 32
    AUX_HEAT = 64


class HVACMode(Enum):  # pragma: no cover - simple stub
    """HVAC modes."""
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"


class HVACAction(Enum):  # pragma: no cover - simple stub
    """HVAC actions."""
    OFF = "off"
    HEATING = "heating"
    COOLING = "cooling"
    DRYING = "drying"
    IDLE = "idle"
    FAN = "fan"


class ClimateEntity:  # pragma: no cover - simple stub
    """Minimal ClimateEntity stub."""
    pass


climate = ModuleType("homeassistant.components.climate")
climate.ATTR_HVAC_MODE = "hvac_mode"
climate.ATTR_TEMPERATURE = "temperature"
climate.ClimateEntity = ClimateEntity
climate.ClimateEntityFeature = ClimateEntityFeature
climate.HVACMode = HVACMode
climate.HVACAction = HVACAction
sys.modules["homeassistant.components.climate"] = climate
components.climate = climate


class SensorDeviceClass(Enum):  # pragma: no cover - simple stub
    TEMPERATURE = "temperature"
    ENERGY = "energy"
    ENERGY_STORAGE = "energy_storage"
    GAS = "gas"
    WATER = "water"
    VOLUME = "volume"


class SensorEntity:  # pragma: no cover - simple stub
    """Minimal SensorEntity stub."""
    pass


class SensorStateClass:  # pragma: no cover - simple stub
    """Minimal SensorStateClass stub."""
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


sensor = ModuleType("homeassistant.components.sensor")
sensor.SensorDeviceClass = SensorDeviceClass
sensor.SensorEntity = SensorEntity
sensor.SensorStateClass = SensorStateClass
sys.modules["homeassistant.components.sensor"] = sensor
components.sensor = sensor

# voluptuous stub
voluptuous = ModuleType("voluptuous")


class _Schema:  # pragma: no cover - simple stub
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, value):
        return value


class _Marker(str):  # pragma: no cover - base class matching voluptuous.Marker
    """Minimal Marker stub for schema key introspection."""
    def __new__(cls, key, default=None, description=None):
        obj = str.__new__(cls, key)
        obj.schema = key  # real voluptuous stores the key name here
        obj.default = default
        obj.description = description
        return obj

    def __hash__(self):
        return str.__hash__(self)

    def __eq__(self, other):
        if isinstance(other, str):
            return str.__eq__(self, other)
        return NotImplemented


def _optional_factory(base_cls):
    class _Option(_Marker):  # pragma: no cover - simple stub
        pass

    return _Option


voluptuous.Marker = _Marker

def _all_factory(*validators):
    def _validator(value):  # pragma: no cover - simple stub
        result = value
        for validator in validators:
            result = validator(result)
        return result

    return _validator


def _coerce_factory(target_type):
    def _coerce(value):  # pragma: no cover - simple stub
        return target_type(value)

    return _coerce


def _range_factory(min=None, max=None):
    def _range(value):  # pragma: no cover - simple stub
        if min is not None and value < min:
            raise ValueError("value below minimum")
        if max is not None and value > max:
            raise ValueError("value above maximum")
        return value

    return _range

voluptuous.Schema = lambda schema: _Schema(schema)
voluptuous.Required = _optional_factory(str)
voluptuous.Optional = _optional_factory(str)
voluptuous.All = _all_factory
voluptuous.Coerce = _coerce_factory
voluptuous.Range = _range_factory
sys.modules["voluptuous"] = voluptuous


def pytest_configure(config):  # pragma: no cover - register custom marks
    config.addinivalue_line("markers", "asyncio: mark test as using asyncio")

# ---------------------------------------------------------------------------
# Ensure the repository root is importable for the tests.
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ============================================================================
# Shared Mock Classes for Tests
# ============================================================================


class DummyCoordinator:
    """Shared coordinator mock for all tests.
    
    Extended to support all optional attributes used in various test scenarios:
    - Connection attributes (host, rack, slot, tsap)
    - Health/error tracking (last_health_ok, last_error_category, error_count_by_category)
    - Plan tracking (_plans_str, _plans_batch) for sensor tests
    """

    def __init__(self, *args, **kwargs):
        self._connected = kwargs.pop("connected", True)
        self.connection_type = kwargs.pop("connection_type", "rack_slot")
        self.pys7_connection_type = kwargs.pop("pys7_connection_type", "pg")
        self.pys7_connection_type_str = self.pys7_connection_type
        
        # Store or pop all other coordinator parameters
        self.hass = kwargs.pop("hass", None) or (args[0] if args else None)
        self.host = kwargs.pop("host", "192.168.1.100")
        self.rack = kwargs.pop("rack", 0)
        self.slot = kwargs.pop("slot", 1)
        self.local_tsap = kwargs.pop("local_tsap", None)
        self.remote_tsap = kwargs.pop("remote_tsap", None)
        self.port = kwargs.pop("port", None)
        self.scan_interval = kwargs.pop("scan_interval", None)
        self.op_timeout = kwargs.pop("op_timeout", None)
        self.max_retries = kwargs.pop("max_retries", None)
        self.backoff_initial = kwargs.pop("backoff_initial", None)
        self.backoff_max = kwargs.pop("backoff_max", None)
        self.optimize_read = kwargs.pop("optimize_read", None)
        self.enable_write_batching = kwargs.pop("enable_write_batching", None)
        
        # Core data structures
        self.data = {}
        self.write_calls: list[tuple[str, object]] = []
        self.add_item_calls: list[tuple] = []  # Track add_item calls
        self.refresh_called = False
        self.refresh_count = 0  # Track how many times refresh was called
        self._write_queue: list[bool] = []
        self._default_write_result = True
        self._item_scan_intervals = {}
        self._default_scan_interval = 10
        self._item_real_precisions = {}
        self.connected = False
        self.disconnected = False
        
        # Health/error tracking attributes (for binary_sensor connection tests)
        self.last_health_ok = kwargs.pop("last_health_ok", None)
        self.last_health_latency = kwargs.pop("last_health_latency", None)
        self.last_error_category = kwargs.pop("last_error_category", None)
        self.last_error_message = kwargs.pop("last_error_message", None)
        self.error_count_by_category = kwargs.pop("error_count_by_category", {})
        
        # Plan tracking (for sensor tests)
        self._plans_str = kwargs.pop("_plans_str", {})
        self._plans_batch = kwargs.pop("_plans_batch", {})

    def get_scan_interval(self, topic: str) -> float:
        return self._item_scan_intervals.get(topic, self._default_scan_interval)

    def get_real_precision(self, topic: str):
        return self._item_real_precisions.get(topic)

    def is_string_plan(self, topic: str) -> bool:
        return topic in self._plans_str

    def get_batch_plan(self, topic: str):
        return self._plans_batch.get(topic)

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    async def add_item(self, *args, **kwargs):
        """Track add_item calls for test verification."""
        self.add_item_calls.append((args, kwargs))
        return None

    def write(self, address: str, value: bool | int | float | str) -> bool:
        self.write_calls.append(("write", address, value))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    async def write_batched(self, address: str, value: bool | int | float | str) -> None:
        """Mock batched write - behaves like regular write for testing."""
        self.write_calls.append(("write_batched", address, value))
        # Batched writes are fire-and-forget, so no return value

    def set_write_queue(self, *results: bool) -> None:
        self._write_queue = list(results)

    def set_default_write_result(self, value: bool) -> None:
        self._default_write_result = value

    async def async_request_refresh(self):
        """Track async_request_refresh calls."""
        self.refresh_called = True
        self.refresh_count += 1

    async def async_config_entry_first_refresh(self):
        """Mock for coordinator first refresh."""
        self.refresh_called = True
        self.refresh_count += 1

    def connect(self):
        """Mock connect method."""
        self.connected = True
        self._connected = True

    def disconnect(self):
        """Mock disconnect method."""
        self.disconnected = True
        self._connected = False


class _ImmediateAwaitable:
    """Awaitable that immediately returns a value (no event loop needed)."""

    def __init__(self, value: Any = None, exc: Exception | None = None):
        self._value = value
        self._exc = exc

    def __await__(self):
        if self._exc is not None:
            raise self._exc
        if False:
            yield  # pragma: no cover
        return self._value


class FakeHass:
    """Fake hass compatible with both async and sync tests."""

    def __init__(self):
        from unittest.mock import MagicMock
        self.calls = []
        self.data = {}
        self.states = MagicMock()

    def async_create_task(self, coro):
        """Mock for hass.async_create_task - executes immediately in tests."""
        import asyncio
        return asyncio.create_task(coro)
    
    def async_create_background_task(self, coro, name=None):
        """Mock for hass.async_create_background_task - executes immediately in tests."""
        import asyncio
        return asyncio.create_task(coro)

    def async_add_executor_job(self, func: Callable, *args, **kwargs):
        self.calls.append((func.__name__, args))
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return _ImmediateAwaitable(exc=exc)
            fut = loop.create_future()
            fut.set_exception(exc)
            return fut

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return _ImmediateAwaitable(result)
        fut = loop.create_future()
        fut.set_result(result)
        return fut

    def create_task(self, coro):
        """Mock create_task."""
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            from unittest.mock import MagicMock
            return MagicMock()


class DummyEntry:
    """Shared entry mock for tests."""

    def __init__(self, options):
        self.options = options
        self.data = {}
        self.entry_id = "test_entry"
        self._on_unload = []

    def add_update_listener(self, listener):
        """Mock add_update_listener."""
        return listener

    def async_on_unload(self, callback):
        """Mock async_on_unload - returns None like the real implementation."""
        self._on_unload.append(callback)
        return None


class DummyCoordinatorClient:
    """Shared coordinator client mock for tests."""

    def __init__(self, values):
        self._values = values
        self.calls = []

    def read(self, tags, optimize=True):
        self.calls.append((list(tags), optimize))
        result = self._values.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class DummyTag:
    """Shared tag mock for tests."""

    def __init__(
        self,
        memory_area="DB",
        db_number=1,
        data_type=None,
        start=0,
        bit_offset=0,
        length=1,
    ):
        self.memory_area = memory_area
        self.db_number = db_number
        self.data_type = data_type
        self.start = start
        self.bit_offset = bit_offset
        self.length = length


# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def mock_coordinator():
    """Provide a connected mock coordinator for tests."""
    return DummyCoordinator()


@pytest.fixture
def mock_coordinator_disconnected():
    """Provide a disconnected mock coordinator for tests."""
    return DummyCoordinator(connected=False)


@pytest.fixture
def mock_coordinator_failing():
    """Provide a mock coordinator that fails writes."""
    coord = DummyCoordinator()
    coord.set_default_write_result(False)
    return coord


@pytest.fixture
def fake_hass():
    """Provide a fake hass instance for entity tests (MagicMock-based)."""
    from unittest.mock import MagicMock, AsyncMock
    import asyncio
    
    hass = MagicMock()
    hass.calls = []  # For compatibility with test_entity.py
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    
    # Make async_create_task actually execute the coroutine
    def create_task_impl(coro):
        try:
            return asyncio.create_task(coro)
        except RuntimeError:
            # If no event loop is running, return a mock
            return MagicMock()
    
    # Make async_create_background_task work the same way
    def create_background_task_impl(coro, name=None):
        try:
            return asyncio.create_task(coro)
        except RuntimeError:
            # If no event loop is running, return a mock
            return MagicMock()
    
    hass.async_create_task = create_task_impl
    hass.async_create_background_task = create_background_task_impl
    hass.create_task = MagicMock()
    return hass


@pytest.fixture
def dummy_entry():
    """Provide a dummy entry factory."""
    def _create_entry(options):
        return DummyEntry(options)
    return _create_entry


@pytest.fixture
def dummy_tag():
    """Factory fixture for creating dummy tags."""
    def _create_tag(**kwargs):
        return DummyTag(**kwargs)
    return _create_tag


@pytest.fixture
def dummy_client():
    """Factory fixture for creating dummy clients."""
    def _create_client(values):
        return DummyCoordinatorClient(values)
    return _create_client