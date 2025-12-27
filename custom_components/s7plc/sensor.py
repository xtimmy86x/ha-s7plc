from __future__ import annotations

import logging
import numbers

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_NAME,
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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_REAL_PRECISION,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_VALUE_MULTIPLIER,
)
from .entity import S7BaseEntity
from .helpers import get_coordinator_and_device_info

_LOGGER = logging.getLogger(__name__)


_CANDIDATE_UNITS: dict[str, str] = {
    "TEMPERATURE": UnitOfTemperature.CELSIUS,
    "HUMIDITY": PERCENTAGE,
    "BATTERY": PERCENTAGE,
    "PRESSURE": UnitOfPressure.HPA,
    "POWER": UnitOfPower.WATT,
    "ENERGY": UnitOfEnergy.KILO_WATT_HOUR,
    "ENERGY_STORAGE": UnitOfEnergy.KILO_WATT_HOUR,
    "CURRENT": UnitOfElectricCurrent.AMPERE,
    "VOLTAGE": UnitOfElectricPotential.VOLT,
    "FREQUENCY": UnitOfFrequency.HERTZ,
    "SPEED": UnitOfSpeed.METERS_PER_SECOND,
    "CO2": CONCENTRATION_PARTS_PER_MILLION,
    "NITROGEN_DIOXIDE": CONCENTRATION_PARTS_PER_BILLION,
    "OZONE": CONCENTRATION_PARTS_PER_BILLION,
    "PM1": "µg/m³",
    "PM10": "µg/m³",
    "PM25": "µg/m³",
    "ILLUMINANCE": "lx",
}

DEVICE_CLASS_UNITS: dict[SensorDeviceClass, str] = {
    getattr(SensorDeviceClass, name): unit
    for name, unit in _CANDIDATE_UNITS.items()
    if hasattr(SensorDeviceClass, name)
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    coord, device_info, device_id = get_coordinator_and_device_info(hass, entry)

    entities = []
    for item in entry.options.get(CONF_SENSORS, []):
        address = item.get(CONF_ADDRESS)
        if not address:
            continue
        name = item.get(CONF_NAME, "S7 Sensor")
        topic = f"sensor:{address}"
        unique_id = f"{device_id}:{topic}"
        device_class = item.get(CONF_DEVICE_CLASS)
        value_multiplier = item.get(CONF_VALUE_MULTIPLIER)
        real_precision = item.get(CONF_REAL_PRECISION)
        scan_interval = item.get(CONF_SCAN_INTERVAL)
        await hass.async_add_executor_job(
            coord.add_item, topic, address, scan_interval, real_precision
        )
        entities.append(
            S7Sensor(
                coord,
                name,
                unique_id,
                device_info,
                topic,
                address,
                device_class,
                value_multiplier,
            )
        )

    if entities:
        async_add_entities(entities)
        await coord.async_request_refresh()


class S7Sensor(S7BaseEntity, SensorEntity):
    def __init__(
        self,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        topic: str,
        address: str,
        device_class: str | None,
        value_multiplier: float | None,
    ):
        super().__init__(
            coordinator,
            name=name,
            unique_id=unique_id,
            device_info=device_info,
            topic=topic,
            address=address,
        )
        self._value_multiplier = (
            float(value_multiplier) if value_multiplier not in (None, "") else None
        )
        if device_class:
            try:
                sensor_device_class = SensorDeviceClass(device_class)
            except ValueError:
                _LOGGER.warning("Invalid device class %s", device_class)
            else:
                self._attr_device_class = sensor_device_class
                unit = DEVICE_CLASS_UNITS.get(sensor_device_class)
                if unit is not None:
                    self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self._topic)
        if self._value_multiplier is None or value is None:
            return value
        if isinstance(value, bool):
            return value
        if isinstance(value, numbers.Number):
            return value * self._value_multiplier
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Cannot apply multiplier to non-numeric value for %s: %s",
                self._topic,
                value,
            )
            return value
        return numeric_value * self._value_multiplier

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._value_multiplier is not None:
            attrs["value_multiplier"] = self._value_multiplier
        return attrs
