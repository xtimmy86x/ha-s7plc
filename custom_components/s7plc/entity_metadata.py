"""Resolve and validate HA metadata consistently for setup and live edits."""

from homeassistant.components import number, sensor
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from .helpers import DEVICE_CLASS_DEFAULT_UNITS, STATE_CLASS_VALUES, device_class_values
from .plc.address import DataType, is_time_data_type, parse_tag

METADATA_FIELDS = frozenset({"device_class", "unit_of_measurement", "state_class"})
TEXT_TYPES = {DataType.CHAR, DataType.STRING, DataType.WSTRING}
TOTAL_INCREASING_CLASSES = {
    SensorDeviceClass.ENERGY,
    getattr(SensorDeviceClass, "REACTIVE_ENERGY", None),
}
NO_MEASUREMENT_CLASSES = {
    SensorDeviceClass.GAS,
    SensorDeviceClass.WATER,
    SensorDeviceClass.VOLUME,
    getattr(SensorDeviceClass, "VOLUME_STORAGE", None),
    getattr(SensorDeviceClass, "MONETARY", None),
}


def number_metadata(device_class, unit, *, is_time=False):
    """Include explicit None values so removing options clears cached metadata."""
    if is_time:
        device_class, unit = "duration", "s"
    elif not unit and device_class:
        unit = DEVICE_CLASS_DEFAULT_UNITS.get(device_class.upper())
    return {
        "_attr_device_class": device_class or None,
        "_attr_native_unit_of_measurement": unit or None,
    }


def sensor_metadata(
    device_class, unit, state_class, *, is_time=False, is_text=False, is_enum=False
):
    """Resolve automatic defaults separately from an explicit 'none' state class."""
    attributes = {
        "_attr_device_class": None,
        "_attr_native_unit_of_measurement": None,
        "_attr_state_class": None,
    }
    if is_enum:
        attributes["_attr_device_class"] = SensorDeviceClass.ENUM
        return attributes
    if is_text:
        return attributes
    attributes.update(number_metadata(device_class, unit, is_time=is_time))
    try:
        device_class = SensorDeviceClass(attributes["_attr_device_class"])
    except (ValueError, TypeError):
        device_class = None
    attributes["_attr_device_class"] = device_class
    if state_class == "none":
        return attributes
    if state_class:
        attributes["_attr_state_class"] = state_class
    elif device_class and device_class in TOTAL_INCREASING_CLASSES:
        attributes["_attr_state_class"] = SensorStateClass.TOTAL_INCREASING
    elif (
        device_class
        and device_class not in NO_MEASUREMENT_CLASSES
        and SensorStateClass.MEASUREMENT
        in sensor.DEVICE_CLASS_STATE_CLASSES.get(device_class, set())
    ):
        attributes["_attr_state_class"] = SensorStateClass.MEASUREMENT
    return attributes


def metadata_error(entity_type: str, item: dict) -> str | None:
    """Reject incompatible new settings before saving any configuration."""
    if entity_type not in {"sensors", "numbers", "binary_sensors", "covers"}:
        return None
    device_class = item.get("device_class")
    if device_class and device_class not in device_class_values(entity_type):
        return "invalid_device_class"
    if entity_type not in {"sensors", "numbers"}:
        return None
    unit = item.get("unit_of_measurement")
    state_class = item.get("state_class")
    data_type = parse_tag(item["address"]).data_type
    is_time = is_time_data_type(data_type)
    if is_time:
        if device_class and device_class != "duration":
            return "invalid_device_class"
        if unit and unit != "s":
            return "invalid_unit_of_measurement"
    if entity_type == "sensors":
        is_enum = (
            item.get("value_conversions", {}).get("value", {}).get("type") == "enum_map"
        )
        if device_class in {"date", "timestamp", "uptime"} or (
            device_class == "enum" and not is_enum
        ):
            # PLC values do not provide HA date/datetime objects or enum options.
            return "invalid_device_class"
        if data_type in TEXT_TYPES:
            if device_class:
                return "invalid_device_class"
            if unit:
                return "invalid_unit_of_measurement"
            if state_class and state_class != "none":
                return "invalid_state_class"
        if state_class and state_class not in (*STATE_CLASS_VALUES, "none"):
            return "invalid_state_class"
        attributes = sensor_metadata(
            device_class,
            unit,
            state_class,
            is_time=is_time,
            is_text=data_type in TEXT_TYPES,
            is_enum=is_enum,
        )
        device_class = attributes["_attr_device_class"]
        state_class = attributes["_attr_state_class"]
        if state_class and device_class:
            allowed = sensor.DEVICE_CLASS_STATE_CLASSES.get(device_class)
            if allowed is not None and SensorStateClass(state_class) not in allowed:
                return "invalid_state_class"
        units = sensor.DEVICE_CLASS_UNITS
    else:
        attributes = number_metadata(device_class, unit, is_time=is_time)
        device_class = attributes["_attr_device_class"]
        units = number.DEVICE_CLASS_UNITS
    allowed_units = units.get(device_class)
    if (
        allowed_units is not None
        and attributes["_attr_native_unit_of_measurement"] not in allowed_units
    ):
        return "invalid_unit_of_measurement"
    return None
