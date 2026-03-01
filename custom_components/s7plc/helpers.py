"""Helper utilities shared by the S7 PLC platforms."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_BINARY_SENSORS,
    CONF_BUTTONS,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COVERS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_ENTITY_SYNC,
    CONF_LIGHTS,
    CONF_NUMBERS,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_SENSORS,
    CONF_STATE_ADDRESS,
    CONF_SWITCHES,
    CONF_TEXTS,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
)

if TYPE_CHECKING:  # pragma: no cover - used for type checking only
    from .coordinator import S7Coordinator


# ---------------------------------------------------------------------------
# Centralised device-class → default-unit mapping
# ---------------------------------------------------------------------------

DEVICE_CLASS_DEFAULT_UNITS: dict[str, str | None] = {
    # Environmental
    "TEMPERATURE": UnitOfTemperature.CELSIUS,
    "TEMPERATURE_DELTA": UnitOfTemperature.CELSIUS,
    "HUMIDITY": PERCENTAGE,
    "MOISTURE": PERCENTAGE,
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
    "CO2": CONCENTRATION_PARTS_PER_MILLION,
    "CO": CONCENTRATION_PARTS_PER_MILLION,
    "OZONE": CONCENTRATION_PARTS_PER_BILLION,
    "NITROGEN_DIOXIDE": CONCENTRATION_PARTS_PER_BILLION,
    "NITROUS_OXIDE": CONCENTRATION_PARTS_PER_BILLION,
    "SULPHUR_DIOXIDE": CONCENTRATION_PARTS_PER_BILLION,
    "VOLATILE_ORGANIC_COMPOUNDS": CONCENTRATION_PARTS_PER_BILLION,
    "VOLATILE_ORGANIC_COMPOUNDS_PARTS": CONCENTRATION_PARTS_PER_MILLION,
    "PM1": "µg/m³",
    "PM25": "µg/m³",
    "PM4": "µg/m³",
    "PM10": "µg/m³",
    # Misc
    "BATTERY": PERCENTAGE,
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


def _iter_entity_unique_ids(
    device_id: str, options: Mapping[str, Any]
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(unique_id, config_item)`` for every configured entity.

    This is the single source of truth for the mapping
    *configuration item  →  entity unique_id*.
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


def build_expected_unique_ids(device_id: str, options: Mapping[str, Any]) -> set[str]:
    """Return the set of expected unique-ids for a config entry.

    Includes the connection binary sensor automatically.
    """
    ids = {uid for uid, _ in _iter_entity_unique_ids(device_id, options)}
    ids.add(f"{device_id}:connection")
    return ids


def build_entity_area_map(
    device_id: str, options: Mapping[str, Any]
) -> dict[str, str | None]:
    """Return a mapping ``unique_id → area_id`` for all configured entities."""
    return {
        uid: item.get(CONF_AREA)
        for uid, item in _iter_entity_unique_ids(device_id, options)
    }
