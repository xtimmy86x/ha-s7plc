"""Helper utilities shared by the S7 PLC platforms."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.cover import CoverDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)

try:
    from homeassistant.const import UnitOfRatio
except ImportError:
    # Compatibility with Home Assistant < 2026.7
    from homeassistant.const import (
        CONCENTRATION_PARTS_PER_BILLION,
        CONCENTRATION_PARTS_PER_MILLION,
        PERCENTAGE,
    )

    UNIT_PERCENTAGE = PERCENTAGE
    UNIT_PARTS_PER_MILLION = CONCENTRATION_PARTS_PER_MILLION
    UNIT_PARTS_PER_BILLION = CONCENTRATION_PARTS_PER_BILLION
else:
    UNIT_PERCENTAGE = UnitOfRatio.PERCENTAGE
    UNIT_PARTS_PER_MILLION = UnitOfRatio.PARTS_PER_MILLION
    UNIT_PARTS_PER_BILLION = UnitOfRatio.PARTS_PER_BILLION

from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_BINARY_SENSORS,
    CONF_BUTTONS,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_COVERS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_ENABLE_METRICS,
    CONF_ENTITY_SYNC,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_LIGHTS,
    CONF_NUMBERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SENSORS,
    CONF_SOURCE_ENTITY,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEXTS,
    CONF_UID,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_ENABLE_METRICS,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
    OPTION_KEYS,
)

if TYPE_CHECKING:  # pragma: no cover - used for type checking only
    from .coordinator import S7Coordinator


# ---------------------------------------------------------------------------
# Device/state class choices shared by the options flow and the panel editor
# ---------------------------------------------------------------------------

DEVICE_CLASS_ENUMS = {
    CONF_BINARY_SENSORS: BinarySensorDeviceClass,
    CONF_SENSORS: SensorDeviceClass,
    CONF_NUMBERS: NumberDeviceClass,
    CONF_COVERS: CoverDeviceClass,
}
STATE_CLASS_VALUES: tuple[str, ...] = ("measurement", "total", "total_increasing")


def device_class_values(entity_type: str) -> list[str]:
    """Return the sorted device class values valid for the given entity type."""

    try:
        enum_cls = DEVICE_CLASS_ENUMS[entity_type]
    except KeyError as err:
        raise ValueError(f"Unknown entity type: {entity_type}") from err
    return sorted(dc.value for dc in enum_cls)


# ---------------------------------------------------------------------------
# Centralised device-class → default-unit mapping
# ---------------------------------------------------------------------------

DEVICE_CLASS_DEFAULT_UNITS: dict[str, str | None] = {
    # Environmental
    "TEMPERATURE": UnitOfTemperature.CELSIUS,
    "TEMPERATURE_DELTA": UnitOfTemperature.CELSIUS,
    "HUMIDITY": UNIT_PERCENTAGE,
    "MOISTURE": UNIT_PERCENTAGE,
    "ILLUMINANCE": "lx",
    "IRRADIANCE": "W/m²",
    "ATMOSPHERIC_PRESSURE": UnitOfPressure.HPA,
    "PRESSURE": UnitOfPressure.HPA,
    "PRECIPITATION": "mm",
    "PRECIPITATION_INTENSITY": "mm/h",
    "WIND_SPEED": UnitOfSpeed.METERS_PER_SECOND,
    "SPEED": UnitOfSpeed.METERS_PER_SECOND,
    "WIND_DIRECTION": "°",
    # Electrical / energy
    "POWER": UnitOfPower.WATT,
    "APPARENT_POWER": "VA",
    "REACTIVE_POWER": "var",
    "POWER_FACTOR": None,
    "ENERGY": UnitOfEnergy.KILO_WATT_HOUR,
    "ENERGY_STORAGE": UnitOfEnergy.KILO_WATT_HOUR,
    "REACTIVE_ENERGY": "varh",
    "VOLTAGE": UnitOfElectricPotential.VOLT,
    "CURRENT": UnitOfElectricCurrent.AMPERE,
    "FREQUENCY": UnitOfFrequency.HERTZ,
    # Air quality
    "AQI": None,
    "CO2": UNIT_PARTS_PER_MILLION,
    "CO": UNIT_PARTS_PER_MILLION,
    "OZONE": UNIT_PARTS_PER_BILLION,
    "NITROGEN_DIOXIDE": UNIT_PARTS_PER_BILLION,
    "NITROUS_OXIDE": UNIT_PARTS_PER_BILLION,
    "SULPHUR_DIOXIDE": UNIT_PARTS_PER_BILLION,
    "VOLATILE_ORGANIC_COMPOUNDS": UNIT_PARTS_PER_BILLION,
    "VOLATILE_ORGANIC_COMPOUNDS_PARTS": UNIT_PARTS_PER_MILLION,
    "PM1": "µg/m³",
    "PM25": "µg/m³",
    "PM4": "µg/m³",
    "PM10": "µg/m³",
    # Misc
    "BATTERY": UNIT_PERCENTAGE,
    "SIGNAL_STRENGTH": "dBm",
    "SOUND_PRESSURE": "dB",
    "PH": None,
    "DURATION": "s",
    "DISTANCE": "m",
    "VOLUME": "m³",
    "VOLUME_STORAGE": "m³",
    "VOLUME_FLOW_RATE": "L/min",
    "WEIGHT": "kg",
    "WATER": "m³",
    "GAS": "m³",
    "DATA_RATE": "B/s",
    "DATA_SIZE": "B",
    # Non-numeric / special
    "DATE": None,
    "TIMESTAMP": None,
    "ENUM": None,
    "MONETARY": None,
}


@dataclass
class RuntimeEntryData:
    """Runtime data stored for each config entry."""

    coordinator: "S7Coordinator"
    name: str
    host: str
    device_id: str


def get_coordinator_and_device_info(
    entry: ConfigEntry,
) -> tuple["S7Coordinator", DeviceInfo, str]:
    """Return the coordinator, device info and identifier for a config entry."""

    data: RuntimeEntryData = entry.runtime_data
    coordinator = data.coordinator
    device_id = data.device_id
    device_name = data.name

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Siemens",
        model="S7 PLC",
    )

    return coordinator, device_info, device_id


def default_entity_name(address: str | None) -> str | None:
    """Return a default entity name using a humanized address.

    With has_entity_name=True, Home Assistant automatically prepends
    the device name to entity names. To avoid duplication (e.g., "My PLC My PLC DB1"),
    we only return the humanized address part.
    """

    if address:
        humanized = re.sub(r"[^0-9A-Za-z\.]+", " ", address)
        humanized = re.sub(r"\s+", " ", humanized).strip()
        return humanized.upper()

    return None


def scale_value(
    raw: float,
    raw_min: float,
    raw_max: float,
    scale_min: float,
    scale_max: float,
) -> float:
    """Map *raw* (in [raw_min, raw_max]) to [scale_min, scale_max] linearly.

    Formula: ``scaled = scale_min + (raw - raw_min) *
    (scale_max - scale_min) / (raw_max - raw_min)``

    If *raw_min == raw_max* the function returns *scale_min* to avoid division by zero.
    """
    if raw_max == raw_min:
        return scale_min
    return scale_min + (raw - raw_min) * (scale_max - scale_min) / (raw_max - raw_min)


def inverse_scale_value(
    scaled: float,
    raw_min: float,
    raw_max: float,
    scale_min: float,
    scale_max: float,
) -> float:
    """Inverse of :func:`scale_value`: map *scaled* back to the raw PLC range.

    Formula: ``raw = raw_min + (scaled - scale_min) *
    (raw_max - raw_min) / (scale_max - scale_min)``

    If *scale_min == scale_max* the function
    returns *raw_min* to avoid division by zero.
    """
    if scale_max == scale_min:
        return raw_min
    return raw_min + (scaled - scale_min) * (raw_max - raw_min) / (
        scale_max - scale_min
    )


def parse_pulse_duration(value: Any | None) -> float:
    """Parse and validate a pulse duration value.

    Returns *DEFAULT_PULSE_DURATION* when the value is ``None``, empty,
    non-numeric or outside the valid range (0.1 – 60 s).
    """
    if value in (None, ""):
        return DEFAULT_PULSE_DURATION
    try:
        pulse = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PULSE_DURATION
    if pulse < 0.1 or pulse > 60:
        return DEFAULT_PULSE_DURATION
    return round(pulse, 1)


# ---------------------------------------------------------------------------
# Centralised unique-id helpers
# ---------------------------------------------------------------------------


def make_unique_topic(seen_topics: set[str], base_topic: str) -> str:
    """Return a topic guaranteed not to collide with one already seen.

    Some entities may intentionally share the same source address (e.g.
    two climates reading the same temperature sensor while controlling
    different valves). The first entity to use a given base topic keeps
    it unchanged; every further one sharing it gets an incrementing suffix
    appended instead of colliding.

    Only used for the coordinator's internal polling key (``topic``) now,
    not for ``unique_id`` (which is uid-based and never collides on its
    own) -- two entities sharing a source address still need distinct
    coordinator topics so their per-item settings (e.g. scan_interval)
    don't overwrite each other.
    """
    topic = base_topic
    suffix = 2
    while topic in seen_topics:
        topic = f"{base_topic}:{suffix}"
        suffix += 1
    seen_topics.add(topic)
    return topic


def _iter_legacy_unique_ids(
    device_id: str, options: Mapping[str, Any]
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(unique_id, config_item)`` using the old, address-based formula.

    Frozen on purpose: this is no longer the live source of truth (see
    :func:`_iter_entity_unique_ids` below), but :func:`ensure_item_uids`
    needs it to know what unique_id an item *currently* has in the entity
    registry, so it can carry that exact value forward as the item's
    permanent ``uid`` instead of generating a new one and orphaning the
    existing entity.
    """

    # Sensors — device_id:sensor:address
    for item in options.get(CONF_SENSORS, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:sensor:{address}", item

    # Binary sensors — device_id:binary_sensor:address
    for item in options.get(CONF_BINARY_SENSORS, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:binary_sensor:{address}", item

    # Switches — device_id:switch:state_address
    for item in options.get(CONF_SWITCHES, []):
        state_addr = item.get(CONF_STATE_ADDRESS, "")
        if state_addr:
            yield f"{device_id}:switch:{state_addr}", item

    # Covers (position-based and traditional)
    for item in options.get(CONF_COVERS, []):
        position_state = item.get(CONF_POSITION_STATE_ADDRESS)
        if position_state:
            yield f"{device_id}:cover:position:{position_state}", item
        else:
            open_command = item.get(CONF_OPEN_COMMAND_ADDRESS, "")
            opened_state = item.get(CONF_OPENING_STATE_ADDRESS)
            closed_state = item.get(CONF_CLOSING_STATE_ADDRESS)

            if opened_state:
                yield f"{device_id}:cover:opened:{opened_state}", item
            elif closed_state:
                yield f"{device_id}:cover:closed:{closed_state}", item
            elif open_command:
                yield f"{device_id}:cover:command:{open_command}", item

    # Buttons — device_id:button:address
    for item in options.get(CONF_BUTTONS, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:button:{address}", item

    # Lights — always "light:" prefix (dimmer is an add-on, not a separate type)
    for item in options.get(CONF_LIGHTS, []):
        state_addr = item.get(CONF_STATE_ADDRESS) or item.get(CONF_ADDRESS, "")
        if state_addr:
            yield f"{device_id}:light:{state_addr}", item

    # Numbers — device_id:number:address
    for item in options.get(CONF_NUMBERS, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:number:{address}", item

    # Texts — device_id:text:address
    for item in options.get(CONF_TEXTS, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:text:{address}", item

    # Climates — device_id:climate_direct:… or device_id:climate_setpoint:…
    for item in options.get(CONF_CLIMATES, []):
        current_temp_address = item.get(CONF_CURRENT_TEMPERATURE_ADDRESS, "")
        control_mode = item.get(CONF_CLIMATE_CONTROL_MODE, CONTROL_MODE_SETPOINT)
        if current_temp_address:
            if control_mode == CONTROL_MODE_DIRECT:
                yield f"{device_id}:climate_direct:{current_temp_address}", item
            else:
                yield f"{device_id}:climate_setpoint:{current_temp_address}", item

    # Entity syncs — device_id:entity_sync:address
    for item in options.get(CONF_ENTITY_SYNC, []):
        address = item.get(CONF_ADDRESS, "")
        if address:
            yield f"{device_id}:entity_sync:{address}", item


def generate_uid() -> str:
    """Return a random identifier for a newly created config item."""
    return uuid.uuid4().hex


def _item_has_required_fields(option_key: str, item: Mapping[str, Any]) -> bool:
    """Return whether *item* has enough configured to produce a real entity.

    Mirrors the per-type conditions each platform's ``async_setup_entry``
    already checks before creating an entity, so the "expected" set below
    doesn't oversell items that won't actually be created.
    """
    if option_key in (
        CONF_SENSORS,
        CONF_BINARY_SENSORS,
        CONF_BUTTONS,
        CONF_NUMBERS,
        CONF_TEXTS,
    ):
        return bool(item.get(CONF_ADDRESS))
    if option_key == CONF_ENTITY_SYNC:
        return bool(item.get(CONF_ADDRESS) and item.get(CONF_SOURCE_ENTITY))
    if option_key == CONF_SWITCHES:
        return bool(item.get(CONF_STATE_ADDRESS))
    if option_key == CONF_LIGHTS:
        return bool(item.get(CONF_STATE_ADDRESS) or item.get(CONF_ADDRESS))
    if option_key == CONF_COVERS:
        if item.get(CONF_POSITION_STATE_ADDRESS):
            return True
        return bool(
            item.get(CONF_OPEN_COMMAND_ADDRESS) and item.get(CONF_CLOSE_COMMAND_ADDRESS)
        )
    if option_key == CONF_CLIMATES:
        if not item.get(CONF_CURRENT_TEMPERATURE_ADDRESS):
            return False
        control_mode = item.get(CONF_CLIMATE_CONTROL_MODE, CONTROL_MODE_SETPOINT)
        if control_mode == CONTROL_MODE_DIRECT:
            return bool(
                item.get(CONF_HEATING_OUTPUT_ADDRESS)
                or item.get(CONF_COOLING_OUTPUT_ADDRESS)
            )
        return bool(item.get(CONF_TARGET_TEMPERATURE_ADDRESS))
    return True


def ensure_item_uids(device_id: str, options: MutableMapping[str, Any]) -> bool:
    """Assign a permanent ``uid`` to every config item that doesn't have one.

    ``uid`` holds the item's *complete* unique_id, not a suffix combined with
    ``device_id`` at read time — so identity survives connection-parameter
    changes (host/rack/slot/TSAP), not just address edits. For an item that
    already corresponds to a registered entity (matched via the frozen,
    address-based :func:`_iter_legacy_unique_ids`), the *exact* string it
    already resolves to is reused verbatim as its ``uid`` — so the entity's
    unique_id/entity_id doesn't change at all. Items with no legacy match
    (e.g. missing a required field, so they never produced an entity) get a
    fresh random uid.

    Returns whether anything changed, so the caller knows whether to persist
    *options* back onto the config entry.
    """
    legacy_by_item_id = {
        id(item): legacy_id
        for legacy_id, item in _iter_legacy_unique_ids(device_id, options)
    }

    changed = False
    for option_key in OPTION_KEYS:
        for item in options.get(option_key, []):
            if CONF_UID in item:
                continue
            legacy_id = legacy_by_item_id.get(id(item))
            item[CONF_UID] = legacy_id if legacy_id else generate_uid()
            changed = True
    return changed


def _iter_entity_unique_ids(
    options: Mapping[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(unique_id, config_item)`` for every configured entity.

    This is the single source of truth for the mapping
    *configuration item → entity unique_id*, built entirely from each item's
    permanent :data:`CONF_UID` (no ``device_id`` involved, so identity is
    independent of connection settings too). Items are expected to already
    have a ``uid`` (assigned by :func:`ensure_item_uids` at setup time); one
    lacking it is skipped, not an error, since it would mean setup hasn't run
    the backfill yet.
    """
    for option_key in OPTION_KEYS:
        for item in options.get(option_key, []):
            uid = item.get(CONF_UID)
            if uid and _item_has_required_fields(option_key, item):
                yield uid, item


def build_expected_unique_ids(
    device_id: str,
    options: Mapping[str, Any],
    data: Mapping[str, Any] | None = None,
) -> set[str]:
    """Return the set of expected unique-ids for a config entry.

    Includes the connection binary sensor and metrics sensors automatically.
    *data* is the ``entry.data`` dict where ``enable_metrics`` is stored.
    """
    from .sensor import METRICS_DEFINITIONS

    ids = {uid for uid, _ in _iter_entity_unique_ids(options)}
    ids.add(f"{device_id}:connection")
    # enable_metrics lives in entry.data, not in entry.options
    source = data if data is not None else options
    if source.get(CONF_ENABLE_METRICS, DEFAULT_ENABLE_METRICS):
        for defn in METRICS_DEFINITIONS:
            ids.add(f"{device_id}:metrics:{defn.key}")
    return ids


def build_entity_area_map(
    device_id: str, options: Mapping[str, Any]
) -> dict[str, str | None]:
    """Return a mapping ``unique_id → area_id`` for all configured entities."""
    return {uid: item.get(CONF_AREA) for uid, item in _iter_entity_unique_ids(options)}
