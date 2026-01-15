"""Pytest configuration and stubs for Home Assistant dependencies."""

from __future__ import annotations

import asyncio
import sys
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
    def async_show_form(self, *args, **kwargs):
        return {"type": "form", "args": args, "kwargs": kwargs}

    def async_show_menu(self, *args, **kwargs):
        return {"type": "menu", "args": args, "kwargs": kwargs}
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

        self.config_entries.async_forward_entry_setups = async_forward_entry_setups
        self.config_entries.async_unload_platforms = async_unload_platforms
        self.config_entries.async_reload = async_reload
        self.config_entries.async_update_entry = async_update_entry
        self.config_entries.async_entries = async_entries
        self.config_entries._entries = []
        self.async_add_executor_job = async_add_executor_job


core.HomeAssistant = HomeAssistant
core.callback = callback
core.State = State
core.Event = Event
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


selector.SelectOptionDict = SelectOptionDict
selector.SelectSelector = SelectSelector
selector.SelectSelectorConfig = SelectSelectorConfig
selector.SelectSelectorMode = SelectSelectorMode
selector.TextSelector = TextSelector
selector.BooleanSelector = BooleanSelector
selector.NumberSelector = NumberSelector
selector.NumberSelectorConfig = NumberSelectorConfig
selector.NumberSelectorMode = NumberSelectorMode
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


cover = ModuleType("homeassistant.components.cover")
cover.CoverEntityFeature = CoverEntityFeature
cover.CoverEntity = CoverEntity
sys.modules["homeassistant.components.cover"] = cover
components.cover = cover


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


def _optional_factory(base_cls):
    class _Option(base_cls):  # pragma: no cover - simple stub
        def __new__(cls, key, default=None):
            obj = base_cls.__new__(cls, key)
            obj.default = default
            return obj

    return _Option

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
    """Shared coordinator mock for all tests."""

    def __init__(self, *args, **kwargs):
        self._connected = kwargs.pop("connected", True)
        self.connection_type = kwargs.pop("connection_type", "rack_slot")
        self.pys7_connection_type = kwargs.pop("pys7_connection_type", "pg")
        self._pys7_connection_type_str = self.pys7_connection_type
        # Pop all other coordinator parameters that might be passed
        kwargs.pop("host", None)
        kwargs.pop("rack", None)
        kwargs.pop("slot", None)
        kwargs.pop("local_tsap", None)
        kwargs.pop("remote_tsap", None)
        kwargs.pop("port", None)
        kwargs.pop("scan_interval", None)
        kwargs.pop("op_timeout", None)
        kwargs.pop("max_retries", None)
        kwargs.pop("backoff_initial", None)
        kwargs.pop("backoff_max", None)
        kwargs.pop("optimize_read", None)
        self.data = {}
        self.write_calls: list[tuple[str, object]] = []
        self.refresh_called = False
        self._write_queue: list[bool] = []
        self._default_write_result = True
        self._item_scan_intervals = {}
        self._default_scan_interval = 10
        self._item_real_precisions = {}

    def is_connected(self):
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def add_item(self, *args, **kwargs):
        return None

    def write_bool(self, address: str, value: bool) -> bool:
        self.write_calls.append(("write_bool", address, bool(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def write_number(self, address: str, value: float) -> bool:
        self.write_calls.append(("write_number", address, float(value)))
        if self._write_queue:
            return self._write_queue.pop(0)
        return self._default_write_result

    def set_write_queue(self, *results: bool) -> None:
        self._write_queue = list(results)

    def set_default_write_result(self, value: bool) -> None:
        self._default_write_result = value

    async def async_request_refresh(self):
        self.refresh_called = True


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
    """Provide a fake hass instance for tests."""
    return FakeHass()


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