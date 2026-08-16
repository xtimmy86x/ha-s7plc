from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from dataclasses import dataclass
from ipaddress import ip_interface, ip_network
from typing import Any, Callable, Dict, List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

# Import S7-specific exceptions if available
try:
    from pyS7.errors import S7CommunicationError, S7ConnectionError
except (ImportError, AttributeError):

    class S7ConnectionError(RuntimeError):
        """Fallback S7 connection error."""

    class S7CommunicationError(RuntimeError):
        """Fallback S7 communication error."""


from .config_validation import EntityConfigBuilder
from .const import (
    CONF_ADDRESS,
    CONF_AREA,
    CONF_BACKOFF_INITIAL,
    CONF_BACKOFF_MAX,
    CONF_BINARY_SENSORS,
    CONF_BRIGHTNESS_COMMAND_ADDRESS,
    CONF_BRIGHTNESS_SCALE,
    CONF_BRIGHTNESS_STATE_ADDRESS,
    CONF_BUTTON_PULSE,
    CONF_BUTTONS,
    CONF_CLIMATE_CONTROL_MODE,
    CONF_CLIMATES,
    CONF_CLOSE_COMMAND_ADDRESS,
    CONF_CLOSING_STATE_ADDRESS,
    CONF_COMMAND_ADDRESS,
    CONF_CONNECTION_TYPE,
    CONF_COOLING_ACTION_ADDRESS,
    CONF_COOLING_OUTPUT_ADDRESS,
    CONF_COVER_CLOSING_ADDRESS,
    CONF_COVER_OPENING_ADDRESS,
    CONF_COVER_STATUS_ADDRESS,
    CONF_COVER_STATUS_CLOSED_VALUES,
    CONF_COVER_STATUS_CLOSING_VALUES,
    CONF_COVER_STATUS_OPEN_VALUES,
    CONF_COVER_STATUS_OPENING_VALUES,
    CONF_COVER_STATUS_STOPPED_VALUES,
    CONF_COVER_STOPPED_ADDRESS,
    CONF_COVERS,
    CONF_CURRENT_TEMPERATURE_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_ENABLE_METRICS,
    CONF_ENABLE_WRITE_BATCHING,
    CONF_ENTITY_SYNC,
    CONF_HEATING_ACTION_ADDRESS,
    CONF_HEATING_OUTPUT_ADDRESS,
    CONF_HVAC_STATUS_ADDRESS,
    CONF_HVAC_STATUS_COOLING_VALUES,
    CONF_HVAC_STATUS_DEFROSTING_VALUES,
    CONF_HVAC_STATUS_DRYING_VALUES,
    CONF_HVAC_STATUS_FAN_VALUES,
    CONF_HVAC_STATUS_HEATING_VALUES,
    CONF_HVAC_STATUS_IDLE_VALUES,
    CONF_HVAC_STATUS_OFF_VALUES,
    CONF_HVAC_STATUS_PREHEATING_VALUES,
    CONF_INVERT_POSITION,
    CONF_INVERT_STATE,
    CONF_INVERT_TILT,
    CONF_LIGHTS,
    CONF_LOCAL_TSAP,
    CONF_MAX_RETRIES,
    CONF_MAX_TEMP,
    CONF_MAX_VALUE,
    CONF_MIN_TEMP,
    CONF_MIN_VALUE,
    CONF_NUMBERS,
    CONF_ON_OFF_ADDRESS,
    CONF_OP_TIMEOUT,
    CONF_OPEN_COMMAND_ADDRESS,
    CONF_OPENING_STATE_ADDRESS,
    CONF_OPERATE_TIME,
    CONF_OPTIMIZE_READ,
    CONF_PATTERN,
    CONF_POSITION_COMMAND_ADDRESS,
    CONF_POSITION_STATE_ADDRESS,
    CONF_PRESET_MODE_ADDRESS,
    CONF_PRESET_MODE_AUTO_VALUE,
    CONF_PRESET_MODE_BIDIRECTIONAL,
    CONF_PRESET_MODE_COOL_VALUE,
    CONF_PRESET_MODE_DRY_VALUE,
    CONF_PRESET_MODE_FAN_ONLY_VALUE,
    CONF_PRESET_MODE_HEAT_COOL_VALUE,
    CONF_PRESET_MODE_HEAT_VALUE,
    CONF_PRESET_MODE_OFF_VALUE,
    CONF_PULSE_COMMAND,
    CONF_PULSE_DURATION,
    CONF_PYS7_CONNECTION_TYPE,
    CONF_RACK,
    CONF_REAL_PRECISION,
    CONF_REMOTE_TSAP,
    CONF_SCALE_RAW_MAX,
    CONF_SCALE_RAW_MIN,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_SLOT,
    CONF_SOURCE_ENTITY,
    CONF_STATE_ADDRESS,
    CONF_STATE_CLASS,
    CONF_STEP,
    CONF_STOP_COMMAND_ADDRESS,
    CONF_STOP_PULSE_DURATION,
    CONF_SWITCHES,
    CONF_SYNC_STATE,
    CONF_TARGET_TEMPERATURE_ADDRESS,
    CONF_TEMP_STEP,
    CONF_TEXTS,
    CONF_TILT_COMMAND_ADDRESS,
    CONF_TILT_STATE_ADDRESS,
    CONF_UID,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USE_STATE_TOPICS,
    CONF_VALUE_MULTIPLIER,
    CONNECTION_TYPE_RACK_SLOT,
    CONNECTION_TYPE_TSAP,
    CONTROL_MODE_DIRECT,
    CONTROL_MODE_SETPOINT,
    DEFAULT_BACKOFF_INITIAL,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_COVER_STATUS_CLOSED_VALUES,
    DEFAULT_COVER_STATUS_CLOSING_VALUES,
    DEFAULT_COVER_STATUS_OPEN_VALUES,
    DEFAULT_COVER_STATUS_OPENING_VALUES,
    DEFAULT_COVER_STATUS_STOPPED_VALUES,
    DEFAULT_ENABLE_METRICS,
    DEFAULT_ENABLE_WRITE_BATCHING,
    DEFAULT_HVAC_STATUS_COOLING_VALUES,
    DEFAULT_HVAC_STATUS_DEFROSTING_VALUES,
    DEFAULT_HVAC_STATUS_DRYING_VALUES,
    DEFAULT_HVAC_STATUS_FAN_VALUES,
    DEFAULT_HVAC_STATUS_HEATING_VALUES,
    DEFAULT_HVAC_STATUS_IDLE_VALUES,
    DEFAULT_HVAC_STATUS_OFF_VALUES,
    DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_OP_TIMEOUT,
    DEFAULT_OPERATE_TIME,
    DEFAULT_OPTIMIZE_READ,
    DEFAULT_PORT,
    DEFAULT_PRESET_MODE_AUTO_VALUE,
    DEFAULT_PRESET_MODE_BIDIRECTIONAL,
    DEFAULT_PRESET_MODE_COOL_VALUE,
    DEFAULT_PRESET_MODE_DRY_VALUE,
    DEFAULT_PRESET_MODE_FAN_ONLY_VALUE,
    DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
    DEFAULT_PRESET_MODE_HEAT_VALUE,
    DEFAULT_PRESET_MODE_OFF_VALUE,
    DEFAULT_PULSE_DURATION,
    DEFAULT_PYS7_CONNECTION_TYPE,
    DEFAULT_RACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOT,
    DEFAULT_TEMP_STEP,
    DEFAULT_USE_STATE_TOPICS,
    DOMAIN,
    OPTION_KEYS,
    PYS7_CONNECTION_TYPE_OP,
    PYS7_CONNECTION_TYPE_PG,
    PYS7_CONNECTION_TYPE_S7BASIC,
)
from .coordinator import S7Coordinator
from .export import build_export_json, build_export_payload, register_export_download
from .helpers import STATE_CLASS_VALUES, device_class_values, generate_uid

_LOGGER = logging.getLogger(__name__)

NONE_OPTION = selector.SelectOptionDict(value="__none__", label="No device class")


def _device_selector_by_type(entity_type: str) -> selector.SelectSelector:
    """Return the appropriate device class selector for the given entity type."""

    options = [NONE_OPTION] + [
        selector.SelectOptionDict(
            value=value,
            label=value.replace("_", " ").title(),
        )
        for value in device_class_values(entity_type)
    ]
    options = [NONE_OPTION] + [
        selector.SelectOptionDict(
            value=value,
            label=value.replace("_", " ").title(),
        )
        for value in device_class_values(entity_type)
    ]

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def num_sel(
    *,
    min: float | None = None,
    max: float | None = None,
    step: float | str | None = None,
    mode: selector.NumberSelectorMode = selector.NumberSelectorMode.BOX,
):
    # Crea solo i campi valorizzati (così non ripeti sempre tutto)
    cfg = {"mode": mode}
    if min is not None:
        cfg["min"] = min
    if max is not None:
        cfg["max"] = max
    if step is not None:
        cfg["step"] = step

    return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))


scan_interval_selector = num_sel(min=0.1, max=3600, step=0.1)
real_precision_selector = num_sel(min=0, max=6, step=1)
operate_time_selector = num_sel(min=0, max=3600, step=1)

value_multiplier_selector = num_sel(min=-1000, max=1000, step=0.05)
scale_value_selector = num_sel(step=0.001)

pulse_duration_selector = num_sel(min=0.1, max=60, step=0.1)

number_value_selector = num_sel(step=0.01)
positive_number_selector = num_sel(min=0, step=0.01)


# Area options builder (needs to be called at runtime with hass)
def _get_area_options(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Get area options for selector including 'No area' option."""
    from homeassistant.helpers import area_registry as ar

    area_reg = ar.async_get(hass)
    areas = area_reg.async_list_areas()

    options = [
        selector.SelectOptionDict(value="__none__", label="No area"),
    ]
    for area in sorted(areas, key=lambda a: a.name):
        options.append(selector.SelectOptionDict(value=area.id, label=area.name))
    return options


# State class options (reused in sensors)
state_class_selector = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[selector.SelectOptionDict(value="none", label="none")]
        + [
            selector.SelectOptionDict(value=value, label=value)
            for value in STATE_CLASS_VALUES
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

ADD_ENTITY_STEP_IDS: tuple[str, ...] = (
    "sensors",
    "binary_sensors",
    "switches",
    "covers",
    "buttons",
    "lights",
    "numbers",
    "texts",
    "climates",
    "entity_sync",
)


# ---------------------------------------------------------------------------
# Entity-type registry: unifies add / edit flows
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntityTypeInfo:
    """Descriptor for one entity type used by the generic add / edit flows."""

    option_key: str  # e.g. CONF_SENSORS
    prefix: str  # e.g. "s"
    add_step_id: str  # e.g. "sensors"
    edit_step_id: str  # e.g. "edit_sensor"
    build_add_schema: Callable  # (flow) -> vol.Schema
    build_edit_schema: Callable  # (flow, item) -> vol.Schema
    item_builder_name: str  # e.g. "_build_sensor_item"


# --- schema builders (add) ------------------------------------------------


def _add_schema_sensor(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_DEVICE_CLASS): _device_selector_by_type(CONF_SENSORS),
            vol.Optional(CONF_UNIT_OF_MEASUREMENT): selector.TextSelector(),
            vol.Optional(CONF_VALUE_MULTIPLIER): value_multiplier_selector,
            vol.Optional(CONF_MIN_VALUE): number_value_selector,
            vol.Optional(CONF_MAX_VALUE): number_value_selector,
            vol.Optional(CONF_SCALE_RAW_MIN): scale_value_selector,
            vol.Optional(CONF_SCALE_RAW_MAX): scale_value_selector,
            vol.Optional(CONF_STATE_CLASS): state_class_selector,
            vol.Optional(CONF_REAL_PRECISION): real_precision_selector,
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_binary_sensor(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_DEVICE_CLASS): _device_selector_by_type(
                CONF_BINARY_SENSORS
            ),
            vol.Optional(CONF_INVERT_STATE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_switch(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_SYNC_STATE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_PULSE_COMMAND, default=False): selector.BooleanSelector(),
            vol.Optional(
                CONF_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
            ): pulse_duration_selector,
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_cover(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_OPEN_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Required(CONF_CLOSE_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_OPENING_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_CLOSING_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COVER_OPENING_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COVER_CLOSING_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COVER_STOPPED_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COVER_STATUS_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_OPEN_VALUES,
                default=DEFAULT_COVER_STATUS_OPEN_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_CLOSED_VALUES,
                default=DEFAULT_COVER_STATUS_CLOSED_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_OPENING_VALUES,
                default=DEFAULT_COVER_STATUS_OPENING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_CLOSING_VALUES,
                default=DEFAULT_COVER_STATUS_CLOSING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_STOPPED_VALUES,
                default=DEFAULT_COVER_STATUS_STOPPED_VALUES,
            ): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_DEVICE_CLASS): _device_selector_by_type(CONF_COVERS),
            vol.Optional(
                CONF_OPERATE_TIME, default=DEFAULT_OPERATE_TIME
            ): operate_time_selector,
            vol.Optional(
                CONF_USE_STATE_TOPICS, default=False
            ): selector.BooleanSelector(),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_cover_position(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_POSITION_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_POSITION_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_STOP_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_STOP_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
            ): pulse_duration_selector,
            vol.Optional(CONF_TILT_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_TILT_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_INVERT_TILT, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_COVER_STATUS_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_OPEN_VALUES,
                default=DEFAULT_COVER_STATUS_OPEN_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_CLOSED_VALUES,
                default=DEFAULT_COVER_STATUS_CLOSED_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_OPENING_VALUES,
                default=DEFAULT_COVER_STATUS_OPENING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_CLOSING_VALUES,
                default=DEFAULT_COVER_STATUS_CLOSING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_COVER_STATUS_STOPPED_VALUES,
                default=DEFAULT_COVER_STATUS_STOPPED_VALUES,
            ): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_DEVICE_CLASS): _device_selector_by_type(CONF_COVERS),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional(
                CONF_INVERT_POSITION, default=False
            ): selector.BooleanSelector(),
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_button(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(
                CONF_BUTTON_PULSE, default=DEFAULT_PULSE_DURATION
            ): pulse_duration_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_light(flow) -> vol.Schema:
    _brightness_scale_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1, max=65535, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )
    return vol.Schema(
        {
            vol.Required(CONF_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_SYNC_STATE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_PULSE_COMMAND, default=False): selector.BooleanSelector(),
            vol.Optional(
                CONF_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
            ): pulse_duration_selector,
            vol.Optional(CONF_BRIGHTNESS_STATE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_BRIGHTNESS_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_BRIGHTNESS_SCALE): _brightness_scale_sel,
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_number(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_DEVICE_CLASS): _device_selector_by_type(CONF_NUMBERS),
            vol.Optional(CONF_UNIT_OF_MEASUREMENT): selector.TextSelector(),
            vol.Optional(CONF_STEP): positive_number_selector,
            vol.Optional(CONF_VALUE_MULTIPLIER): value_multiplier_selector,
            vol.Optional(CONF_MIN_VALUE): number_value_selector,
            vol.Optional(CONF_MAX_VALUE): number_value_selector,
            vol.Optional(CONF_SCALE_RAW_MIN): scale_value_selector,
            vol.Optional(CONF_SCALE_RAW_MAX): scale_value_selector,
            vol.Optional(CONF_REAL_PRECISION): real_precision_selector,
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_text(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COMMAND_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_PATTERN): selector.TextSelector(),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_climate_direct(flow) -> vol.Schema:
    _temp_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-50, max=100, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _step_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.1, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    return vol.Schema(
        {
            vol.Required(CONF_CURRENT_TEMPERATURE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_HEATING_OUTPUT_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COOLING_OUTPUT_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_HEATING_ACTION_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_COOLING_ACTION_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): _temp_sel,
            vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): _temp_sel,
            vol.Optional(CONF_TEMP_STEP, default=DEFAULT_TEMP_STEP): _step_sel,
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_climate_setpoint(flow) -> vol.Schema:
    _temp_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-50, max=100, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _step_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.1, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _int_sel = num_sel(step=1)
    return vol.Schema(
        {
            vol.Required(CONF_CURRENT_TEMPERATURE_ADDRESS): selector.TextSelector(),
            vol.Required(CONF_TARGET_TEMPERATURE_ADDRESS): selector.TextSelector(),
            vol.Optional(CONF_PRESET_MODE_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_PRESET_MODE_BIDIRECTIONAL,
                default=DEFAULT_PRESET_MODE_BIDIRECTIONAL,
            ): selector.BooleanSelector(),
            vol.Optional(CONF_ON_OFF_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_PRESET_MODE_OFF_VALUE, default=DEFAULT_PRESET_MODE_OFF_VALUE
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_HEAT_VALUE, default=DEFAULT_PRESET_MODE_HEAT_VALUE
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_COOL_VALUE, default=DEFAULT_PRESET_MODE_COOL_VALUE
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_HEAT_COOL_VALUE,
                default=DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_AUTO_VALUE, default=DEFAULT_PRESET_MODE_AUTO_VALUE
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_DRY_VALUE, default=DEFAULT_PRESET_MODE_DRY_VALUE
            ): _int_sel,
            vol.Optional(
                CONF_PRESET_MODE_FAN_ONLY_VALUE,
                default=DEFAULT_PRESET_MODE_FAN_ONLY_VALUE,
            ): _int_sel,
            vol.Optional(CONF_HVAC_STATUS_ADDRESS): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_OFF_VALUES, default=DEFAULT_HVAC_STATUS_OFF_VALUES
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_HEATING_VALUES,
                default=DEFAULT_HVAC_STATUS_HEATING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_COOLING_VALUES,
                default=DEFAULT_HVAC_STATUS_COOLING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_IDLE_VALUES, default=DEFAULT_HVAC_STATUS_IDLE_VALUES
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_DRYING_VALUES,
                default=DEFAULT_HVAC_STATUS_DRYING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_FAN_VALUES, default=DEFAULT_HVAC_STATUS_FAN_VALUES
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_PREHEATING_VALUES,
                default=DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(
                CONF_HVAC_STATUS_DEFROSTING_VALUES,
                default=DEFAULT_HVAC_STATUS_DEFROSTING_VALUES,
            ): selector.TextSelector(),
            vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): _temp_sel,
            vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): _temp_sel,
            vol.Optional(CONF_TEMP_STEP, default=DEFAULT_TEMP_STEP): _step_sel,
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional(CONF_SCAN_INTERVAL): scan_interval_selector,
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


def _add_schema_writer(flow) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ADDRESS): selector.TextSelector(),
            vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(),
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_AREA): flow._get_area_selector(),
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        }
    )


# --- schema builders (edit) -----------------------------------------------


def _edit_schema_sensor(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    for key, sel in [
        (CONF_DEVICE_CLASS, _device_selector_by_type(CONF_SENSORS)),
        (CONF_UNIT_OF_MEASUREMENT, selector.TextSelector()),
        (CONF_VALUE_MULTIPLIER, value_multiplier_selector),
        (CONF_MIN_VALUE, number_value_selector),
        (CONF_MAX_VALUE, number_value_selector),
        (CONF_SCALE_RAW_MIN, scale_value_selector),
        (CONF_SCALE_RAW_MAX, scale_value_selector),
        (CONF_STATE_CLASS, state_class_selector),
        (CONF_REAL_PRECISION, real_precision_selector),
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_binary_sensor(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(
        CONF_DEVICE_CLASS, item, _device_selector_by_type(CONF_BINARY_SENSORS)
    )
    d[k] = v
    d[vol.Optional(CONF_INVERT_STATE, default=item.get(CONF_INVERT_STATE, False))] = (
        selector.BooleanSelector()
    )
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_switch(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_STATE_ADDRESS, default=item.get(CONF_STATE_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COMMAND_ADDRESS, default=item.get(CONF_COMMAND_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_SYNC_STATE, default=bool(item.get(CONF_SYNC_STATE, False))
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_PULSE_COMMAND, default=bool(item.get(CONF_PULSE_COMMAND, False))
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_PULSE_DURATION,
            default=float(item.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)),
        ): pulse_duration_selector,
    }
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_cover(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_OPEN_COMMAND_ADDRESS,
            default=item.get(CONF_OPEN_COMMAND_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Required(
            CONF_CLOSE_COMMAND_ADDRESS,
            default=item.get(CONF_CLOSE_COMMAND_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_OPENING_STATE_ADDRESS,
            default=item.get(CONF_OPENING_STATE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_CLOSING_STATE_ADDRESS,
            default=item.get(CONF_CLOSING_STATE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_OPENING_ADDRESS,
            default=item.get(CONF_COVER_OPENING_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_CLOSING_ADDRESS,
            default=item.get(CONF_COVER_CLOSING_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STOPPED_ADDRESS,
            default=item.get(CONF_COVER_STOPPED_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_ADDRESS,
            default=item.get(CONF_COVER_STATUS_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_OPEN_VALUES,
            default=item.get(
                CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_CLOSED_VALUES,
            default=item.get(
                CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_OPENING_VALUES,
            default=item.get(
                CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_CLOSING_VALUES,
            default=item.get(
                CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_STOPPED_VALUES,
            default=item.get(
                CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(
        CONF_DEVICE_CLASS, item, _device_selector_by_type(CONF_COVERS)
    )
    d[k] = v
    d[
        vol.Optional(
            CONF_OPERATE_TIME,
            default=float(item.get(CONF_OPERATE_TIME, DEFAULT_OPERATE_TIME)),
        )
    ] = operate_time_selector
    d[
        vol.Optional(
            CONF_USE_STATE_TOPICS,
            default=item.get(CONF_USE_STATE_TOPICS, DEFAULT_USE_STATE_TOPICS),
        )
    ] = selector.BooleanSelector()
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_cover_position(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_POSITION_STATE_ADDRESS,
            default=item.get(CONF_POSITION_STATE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_POSITION_COMMAND_ADDRESS,
            default=item.get(CONF_POSITION_COMMAND_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_STOP_COMMAND_ADDRESS,
            default=item.get(CONF_STOP_COMMAND_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_STOP_PULSE_DURATION,
            default=float(item.get(CONF_STOP_PULSE_DURATION, DEFAULT_PULSE_DURATION)),
        ): pulse_duration_selector,
        vol.Optional(
            CONF_TILT_STATE_ADDRESS,
            default=item.get(CONF_TILT_STATE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_TILT_COMMAND_ADDRESS,
            default=item.get(CONF_TILT_COMMAND_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_INVERT_TILT, default=item.get(CONF_INVERT_TILT, False)
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_COVER_STATUS_ADDRESS,
            default=item.get(CONF_COVER_STATUS_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_OPEN_VALUES,
            default=item.get(
                CONF_COVER_STATUS_OPEN_VALUES, DEFAULT_COVER_STATUS_OPEN_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_CLOSED_VALUES,
            default=item.get(
                CONF_COVER_STATUS_CLOSED_VALUES, DEFAULT_COVER_STATUS_CLOSED_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_OPENING_VALUES,
            default=item.get(
                CONF_COVER_STATUS_OPENING_VALUES, DEFAULT_COVER_STATUS_OPENING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_CLOSING_VALUES,
            default=item.get(
                CONF_COVER_STATUS_CLOSING_VALUES, DEFAULT_COVER_STATUS_CLOSING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COVER_STATUS_STOPPED_VALUES,
            default=item.get(
                CONF_COVER_STATUS_STOPPED_VALUES, DEFAULT_COVER_STATUS_STOPPED_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(
        CONF_DEVICE_CLASS, item, _device_selector_by_type(CONF_COVERS)
    )
    d[k] = v
    k, v = flow._optional_field(CONF_SCAN_INTERVAL, item, scan_interval_selector)
    d[k] = v
    d[
        vol.Optional(
            CONF_INVERT_POSITION, default=item.get(CONF_INVERT_POSITION, False)
        )
    ] = selector.BooleanSelector()
    k, v = flow._optional_field(CONF_AREA, item, flow._get_area_selector())
    d[k] = v
    return vol.Schema(d)


def _edit_schema_button(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_BUTTON_PULSE,
            default=float(item.get(CONF_BUTTON_PULSE, DEFAULT_PULSE_DURATION)),
        ): pulse_duration_selector,
    }
    k, v = flow._optional_field(CONF_AREA, item, flow._get_area_selector())
    d[k] = v
    return vol.Schema(d)


def _edit_schema_light(flow, item: dict[str, Any]) -> vol.Schema:
    _brightness_scale_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1, max=65535, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )
    d: dict[Any, Any] = {
        vol.Required(
            CONF_STATE_ADDRESS, default=item.get(CONF_STATE_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COMMAND_ADDRESS, default=item.get(CONF_COMMAND_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_SYNC_STATE, default=bool(item.get(CONF_SYNC_STATE, False))
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_PULSE_COMMAND, default=bool(item.get(CONF_PULSE_COMMAND, False))
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_PULSE_DURATION,
            default=item.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
        ): pulse_duration_selector,
    }
    for key, sel in [
        (CONF_BRIGHTNESS_STATE_ADDRESS, selector.TextSelector()),
        (CONF_BRIGHTNESS_COMMAND_ADDRESS, selector.TextSelector()),
        (CONF_BRIGHTNESS_SCALE, _brightness_scale_sel),
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_number(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COMMAND_ADDRESS, default=item.get(CONF_COMMAND_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(
        CONF_DEVICE_CLASS, item, _device_selector_by_type(CONF_NUMBERS)
    )
    d[k] = v
    k, v = flow._optional_field(CONF_UNIT_OF_MEASUREMENT, item, selector.TextSelector())
    d[k] = v
    k, v = flow._optional_field(CONF_MIN_VALUE, item, number_value_selector)
    d[k] = v
    k, v = flow._optional_field(CONF_MAX_VALUE, item, number_value_selector)
    d[k] = v
    for key, sel in [
        (CONF_STEP, positive_number_selector),
        (CONF_VALUE_MULTIPLIER, value_multiplier_selector),
        (CONF_SCALE_RAW_MIN, scale_value_selector),
        (CONF_SCALE_RAW_MAX, scale_value_selector),
        (CONF_REAL_PRECISION, real_precision_selector),
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_text(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COMMAND_ADDRESS, default=item.get(CONF_COMMAND_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    for key, sel in [
        (CONF_PATTERN, selector.TextSelector()),
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_climate_direct(flow, item: dict[str, Any]) -> vol.Schema:
    _temp_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-50, max=100, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _step_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.1, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    d: dict[Any, Any] = {
        vol.Required(
            CONF_CURRENT_TEMPERATURE_ADDRESS,
            default=item.get(CONF_CURRENT_TEMPERATURE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HEATING_OUTPUT_ADDRESS,
            default=item.get(CONF_HEATING_OUTPUT_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COOLING_OUTPUT_ADDRESS,
            default=item.get(CONF_COOLING_OUTPUT_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HEATING_ACTION_ADDRESS,
            default=item.get(CONF_HEATING_ACTION_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_COOLING_ACTION_ADDRESS,
            default=item.get(CONF_COOLING_ACTION_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_MIN_TEMP,
            default=float(item.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)),
        ): _temp_sel,
        vol.Optional(
            CONF_MAX_TEMP,
            default=float(item.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)),
        ): _temp_sel,
        vol.Optional(
            CONF_TEMP_STEP,
            default=float(item.get(CONF_TEMP_STEP, DEFAULT_TEMP_STEP)),
        ): _step_sel,
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_climate_setpoint(flow, item: dict[str, Any]) -> vol.Schema:
    _temp_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-50, max=100, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _step_sel = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.1, max=10, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    _int_sel = num_sel(step=1)
    d: dict[Any, Any] = {
        vol.Required(
            CONF_CURRENT_TEMPERATURE_ADDRESS,
            default=item.get(CONF_CURRENT_TEMPERATURE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Required(
            CONF_TARGET_TEMPERATURE_ADDRESS,
            default=item.get(CONF_TARGET_TEMPERATURE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_PRESET_MODE_ADDRESS,
            default=item.get(CONF_PRESET_MODE_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_PRESET_MODE_BIDIRECTIONAL,
            default=item.get(
                CONF_PRESET_MODE_BIDIRECTIONAL, DEFAULT_PRESET_MODE_BIDIRECTIONAL
            ),
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_ON_OFF_ADDRESS,
            default=item.get(CONF_ON_OFF_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_PRESET_MODE_OFF_VALUE,
            default=item.get(CONF_PRESET_MODE_OFF_VALUE, DEFAULT_PRESET_MODE_OFF_VALUE),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_HEAT_VALUE,
            default=item.get(
                CONF_PRESET_MODE_HEAT_VALUE, DEFAULT_PRESET_MODE_HEAT_VALUE
            ),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_COOL_VALUE,
            default=item.get(
                CONF_PRESET_MODE_COOL_VALUE, DEFAULT_PRESET_MODE_COOL_VALUE
            ),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_HEAT_COOL_VALUE,
            default=item.get(
                CONF_PRESET_MODE_HEAT_COOL_VALUE,
                DEFAULT_PRESET_MODE_HEAT_COOL_VALUE,
            ),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_AUTO_VALUE,
            default=item.get(
                CONF_PRESET_MODE_AUTO_VALUE, DEFAULT_PRESET_MODE_AUTO_VALUE
            ),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_DRY_VALUE,
            default=item.get(CONF_PRESET_MODE_DRY_VALUE, DEFAULT_PRESET_MODE_DRY_VALUE),
        ): _int_sel,
        vol.Optional(
            CONF_PRESET_MODE_FAN_ONLY_VALUE,
            default=item.get(
                CONF_PRESET_MODE_FAN_ONLY_VALUE, DEFAULT_PRESET_MODE_FAN_ONLY_VALUE
            ),
        ): _int_sel,
        vol.Optional(
            CONF_HVAC_STATUS_ADDRESS,
            default=item.get(CONF_HVAC_STATUS_ADDRESS, ""),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_OFF_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_OFF_VALUES, DEFAULT_HVAC_STATUS_OFF_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_HEATING_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_HEATING_VALUES, DEFAULT_HVAC_STATUS_HEATING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_COOLING_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_COOLING_VALUES, DEFAULT_HVAC_STATUS_COOLING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_IDLE_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_IDLE_VALUES, DEFAULT_HVAC_STATUS_IDLE_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_DRYING_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_DRYING_VALUES, DEFAULT_HVAC_STATUS_DRYING_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_FAN_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_FAN_VALUES, DEFAULT_HVAC_STATUS_FAN_VALUES
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_PREHEATING_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_PREHEATING_VALUES,
                DEFAULT_HVAC_STATUS_PREHEATING_VALUES,
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_HVAC_STATUS_DEFROSTING_VALUES,
            default=item.get(
                CONF_HVAC_STATUS_DEFROSTING_VALUES,
                DEFAULT_HVAC_STATUS_DEFROSTING_VALUES,
            ),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_MIN_TEMP,
            default=float(item.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)),
        ): _temp_sel,
        vol.Optional(
            CONF_MAX_TEMP,
            default=float(item.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)),
        ): _temp_sel,
        vol.Optional(
            CONF_TEMP_STEP,
            default=float(item.get(CONF_TEMP_STEP, DEFAULT_TEMP_STEP)),
        ): _step_sel,
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    return vol.Schema(d)


def _edit_schema_writer(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Required(
            CONF_SOURCE_ENTITY, default=item.get(CONF_SOURCE_ENTITY, "")
        ): selector.EntitySelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(CONF_AREA, item, flow._get_area_selector())
    d[k] = v
    return vol.Schema(d)


# --- registry --------------------------------------------------------------

ENTITY_TYPE_REGISTRY: dict[str, EntityTypeInfo] = {}


def _reg(info: EntityTypeInfo) -> None:
    ENTITY_TYPE_REGISTRY[info.prefix] = info


_reg(
    EntityTypeInfo(
        CONF_SENSORS,
        "s",
        "sensors",
        "edit_sensor",
        _add_schema_sensor,
        _edit_schema_sensor,
        "_build_sensor_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_BINARY_SENSORS,
        "bs",
        "binary_sensors",
        "edit_binary_sensor",
        _add_schema_binary_sensor,
        _edit_schema_binary_sensor,
        "_build_binary_sensor_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_SWITCHES,
        "sw",
        "switches",
        "edit_switch",
        _add_schema_switch,
        _edit_schema_switch,
        "_build_switch_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_COVERS,
        "cv",
        "covers_traditional",
        "edit_cover",
        _add_schema_cover,
        _edit_schema_cover,
        "_build_cover_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_COVERS,
        "cvp",
        "covers_position",
        "edit_cover_position",
        _add_schema_cover_position,
        _edit_schema_cover_position,
        "_build_cover_position_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_BUTTONS,
        "bt",
        "buttons",
        "edit_button",
        _add_schema_button,
        _edit_schema_button,
        "_build_button_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_LIGHTS,
        "lt",
        "lights",
        "edit_light",
        _add_schema_light,
        _edit_schema_light,
        "_build_light_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_NUMBERS,
        "nm",
        "numbers",
        "edit_number",
        _add_schema_number,
        _edit_schema_number,
        "_build_number_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_TEXTS,
        "tx",
        "texts",
        "edit_text",
        _add_schema_text,
        _edit_schema_text,
        "_build_text_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_CLIMATES,
        "cl_d",
        "climates_direct",
        "edit_climate_direct",
        _add_schema_climate_direct,
        _edit_schema_climate_direct,
        "_build_climate_direct_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_CLIMATES,
        "cl_s",
        "climates_setpoint",
        "edit_climate_setpoint",
        _add_schema_climate_setpoint,
        _edit_schema_climate_setpoint,
        "_build_climate_setpoint_item",
    )
)
_reg(
    EntityTypeInfo(
        CONF_ENTITY_SYNC,
        "wr",
        "entity_sync",
        "edit_writer",
        _add_schema_writer,
        _edit_schema_writer,
        "_build_writer_item",
    )
)

# Derived: add_step_id -> prefix
_ADD_STEP_TO_PREFIX: dict[str, str] = {
    info.add_step_id: prefix for prefix, info in ENTITY_TYPE_REGISTRY.items()
}

del _reg  # cleanup namespace


def _get_connection_description(
    connection_type: str,
    local_tsap: str | None = None,
    remote_tsap: str | None = None,
    rack: int | None = None,
    slot: int | None = None,
) -> str:
    """Return human-readable connection description."""
    if connection_type == CONNECTION_TYPE_TSAP:
        return f"TSAP {local_tsap}/{remote_tsap}"
    return f"rack {rack} slot {slot}"


def _handle_connection_error(
    flow_instance,
    err: Exception,
    host: str,
    port: int,
    connection_type: str,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
    step_id: str,
    data_schema: vol.Schema,
    errors: dict[str, str],
    description_placeholders: dict[str, str] | None = None,
):
    """Handle connection test errors with logging."""
    connection_desc = _get_connection_description(
        connection_type, local_tsap, remote_tsap, rack, slot
    )

    if isinstance(err, S7ConnectionError):
        _LOGGER.error(
            "S7 connection error to PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, S7CommunicationError):
        _LOGGER.error(
            "S7 communication error with PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, OSError):
        _LOGGER.error(
            "Network error connecting to S7 PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    elif isinstance(err, RuntimeError):
        _LOGGER.error(
            "Runtime error with S7 PLC at %s:%s (%s): %s",
            host,
            port,
            connection_desc,
            err,
        )
    else:
        _LOGGER.exception(
            "Unexpected error connecting to S7 PLC at %s:%s (%s)",
            host,
            port,
            connection_desc,
        )

    errors["base"] = "cannot_connect"

    if description_placeholders:
        return flow_instance.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
    return flow_instance.async_show_form(
        step_id=step_id,
        data_schema=data_schema,
        errors=errors,
    )


def _sanitize_connection_params(
    scan_s: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
) -> tuple[float, float, int, float, float]:
    """Sanitize connection parameters to valid defaults."""
    if scan_s <= 0:
        scan_s = DEFAULT_SCAN_INTERVAL
    if op_timeout <= 0:
        op_timeout = DEFAULT_OP_TIMEOUT
    if max_retries < 0:
        max_retries = DEFAULT_MAX_RETRIES
    if backoff_initial <= 0:
        backoff_initial = DEFAULT_BACKOFF_INITIAL
    if backoff_max < backoff_initial:
        backoff_max = max(backoff_initial, backoff_max)
    return scan_s, op_timeout, max_retries, backoff_initial, backoff_max


def _build_connection_parse_defaults(
    connection_type: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build parsing defaults for connection parameters."""
    source = data or {}

    defaults: dict[str, Any] = {
        CONF_PORT: int(source.get(CONF_PORT, DEFAULT_PORT)),
        CONF_PYS7_CONNECTION_TYPE: source.get(
            CONF_PYS7_CONNECTION_TYPE, DEFAULT_PYS7_CONNECTION_TYPE
        ),
        CONF_SCAN_INTERVAL: float(
            source.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        CONF_OP_TIMEOUT: float(source.get(CONF_OP_TIMEOUT, DEFAULT_OP_TIMEOUT)),
        CONF_MAX_RETRIES: int(source.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)),
        CONF_BACKOFF_INITIAL: float(
            source.get(CONF_BACKOFF_INITIAL, DEFAULT_BACKOFF_INITIAL)
        ),
        CONF_BACKOFF_MAX: float(source.get(CONF_BACKOFF_MAX, DEFAULT_BACKOFF_MAX)),
        CONF_OPTIMIZE_READ: bool(source.get(CONF_OPTIMIZE_READ, DEFAULT_OPTIMIZE_READ)),
        CONF_ENABLE_WRITE_BATCHING: bool(
            source.get(CONF_ENABLE_WRITE_BATCHING, DEFAULT_ENABLE_WRITE_BATCHING)
        ),
        CONF_ENABLE_METRICS: bool(
            source.get(CONF_ENABLE_METRICS, DEFAULT_ENABLE_METRICS)
        ),
    }

    if connection_type == CONNECTION_TYPE_TSAP:
        defaults[CONF_LOCAL_TSAP] = source.get(CONF_LOCAL_TSAP, "01.00")
        defaults[CONF_REMOTE_TSAP] = source.get(CONF_REMOTE_TSAP, "01.01")
    else:
        defaults[CONF_RACK] = int(source.get(CONF_RACK, DEFAULT_RACK))
        defaults[CONF_SLOT] = int(source.get(CONF_SLOT, DEFAULT_SLOT))

    return defaults


@dataclass(frozen=True, slots=True)
class ParsedConnectionParams:
    """Parsed and sanitized connection-related parameters."""

    port: int
    pys7_connection_type: str
    scan_interval: float
    op_timeout: float
    max_retries: int
    backoff_initial: float
    backoff_max: float
    optimize_read: bool
    enable_write_batching: bool
    enable_metrics: bool
    rack: int | None
    slot: int | None
    local_tsap: str | None
    remote_tsap: str | None


def _parse_connection_params(
    user_input: dict[str, Any],
    *,
    connection_type: str,
    defaults: dict[str, Any],
) -> ParsedConnectionParams:
    """Parse and sanitize shared connection parameters from user input."""
    port = int(user_input.get(CONF_PORT, defaults[CONF_PORT]))
    pys7_connection_type = user_input.get(
        CONF_PYS7_CONNECTION_TYPE, defaults[CONF_PYS7_CONNECTION_TYPE]
    )
    scan_interval = float(
        user_input.get(CONF_SCAN_INTERVAL, defaults[CONF_SCAN_INTERVAL])
    )
    op_timeout = float(user_input.get(CONF_OP_TIMEOUT, defaults[CONF_OP_TIMEOUT]))
    max_retries = int(user_input.get(CONF_MAX_RETRIES, defaults[CONF_MAX_RETRIES]))
    backoff_initial = float(
        user_input.get(CONF_BACKOFF_INITIAL, defaults[CONF_BACKOFF_INITIAL])
    )
    backoff_max = float(user_input.get(CONF_BACKOFF_MAX, defaults[CONF_BACKOFF_MAX]))
    optimize_read = bool(
        user_input.get(CONF_OPTIMIZE_READ, defaults[CONF_OPTIMIZE_READ])
    )
    enable_write_batching = bool(
        user_input.get(CONF_ENABLE_WRITE_BATCHING, defaults[CONF_ENABLE_WRITE_BATCHING])
    )
    enable_metrics = bool(
        user_input.get(CONF_ENABLE_METRICS, defaults[CONF_ENABLE_METRICS])
    )

    if connection_type == CONNECTION_TYPE_TSAP:
        local_tsap = user_input.get(CONF_LOCAL_TSAP, defaults[CONF_LOCAL_TSAP])
        remote_tsap = user_input.get(CONF_REMOTE_TSAP, defaults[CONF_REMOTE_TSAP])
        rack = None
        slot = None
    else:
        rack = int(user_input.get(CONF_RACK, defaults[CONF_RACK]))
        slot = int(user_input.get(CONF_SLOT, defaults[CONF_SLOT]))
        local_tsap = None
        remote_tsap = None

    scan_interval, op_timeout, max_retries, backoff_initial, backoff_max = (
        _sanitize_connection_params(
            scan_interval,
            op_timeout,
            max_retries,
            backoff_initial,
            backoff_max,
        )
    )

    return ParsedConnectionParams(
        port=port,
        pys7_connection_type=pys7_connection_type,
        scan_interval=scan_interval,
        op_timeout=op_timeout,
        max_retries=max_retries,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
        optimize_read=optimize_read,
        enable_write_batching=enable_write_batching,
        rack=rack,
        slot=slot,
        local_tsap=local_tsap,
        remote_tsap=remote_tsap,
        enable_metrics=enable_metrics,
    )


def _generate_connection_unique_id(
    host: str,
    connection_type: str,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
) -> str:
    """Generate unique ID based on connection type."""
    if connection_type == CONNECTION_TYPE_TSAP:
        return f"{host}-tsap-{local_tsap}-{remote_tsap}"
    return f"{host}-{rack}-{slot}"


async def _test_plc_connection(
    hass,
    *,
    host: str,
    connection_type: str,
    rack: int | None,
    slot: int | None,
    local_tsap: str | None,
    remote_tsap: str | None,
    pys7_connection_type: str,
    port: int,
    scan_interval: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
    optimize_read: bool,
    enable_write_batching: bool,
    enable_metrics: bool,
) -> None:
    """Test PLC connection. Raises on failure."""
    coordinator = S7Coordinator(
        hass,
        host=host,
        connection_type=connection_type,
        rack=rack,
        slot=slot,
        local_tsap=local_tsap,
        remote_tsap=remote_tsap,
        pys7_connection_type=pys7_connection_type,
        port=port,
        scan_interval=scan_interval,
        op_timeout=op_timeout,
        max_retries=max_retries,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
        optimize_read=optimize_read,
        enable_write_batching=enable_write_batching,
        enable_metrics=enable_metrics,
    )
    await coordinator.connect()
    await coordinator.disconnect()


def _build_connection_entry_data(
    *,
    name: str,
    host: str,
    port: int,
    connection_type: str,
    pys7_connection_type: str,
    scan_interval: float,
    op_timeout: float,
    max_retries: int,
    backoff_initial: float,
    backoff_max: float,
    optimize_read: bool,
    enable_write_batching: bool,
    enable_metrics: bool,
    local_tsap: str | None,
    remote_tsap: str | None,
    rack: int | None,
    slot: int | None,
) -> dict[str, Any]:
    """Build connection entry data dict."""
    data = {
        CONF_NAME: name,
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_CONNECTION_TYPE: connection_type,
        CONF_PYS7_CONNECTION_TYPE: pys7_connection_type,
        CONF_SCAN_INTERVAL: scan_interval,
        CONF_OP_TIMEOUT: op_timeout,
        CONF_MAX_RETRIES: max_retries,
        CONF_BACKOFF_INITIAL: backoff_initial,
        CONF_BACKOFF_MAX: backoff_max,
        CONF_OPTIMIZE_READ: optimize_read,
        CONF_ENABLE_WRITE_BATCHING: enable_write_batching,
        CONF_ENABLE_METRICS: enable_metrics,
    }
    if connection_type == CONNECTION_TYPE_TSAP:
        data[CONF_LOCAL_TSAP] = local_tsap
        data[CONF_REMOTE_TSAP] = remote_tsap
    else:
        data[CONF_RACK] = rack
        data[CONF_SLOT] = slot
    return data


class S7PLCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for S7 PLC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""

        self._discovered_hosts: list[str] | None = None
        self._connection_data: dict[str, Any] = {}

    def _get_area_selector(self) -> selector.SelectSelector:
        """Get area selector with dynamic area list."""
        options = _get_area_options(self.hass)
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step - choose connection type."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_RACK_SLOT
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    selector.SelectOptionDict(
                                        value=CONNECTION_TYPE_RACK_SLOT,
                                        label="Rack/Slot",
                                    ),
                                    selector.SelectOptionDict(
                                        value=CONNECTION_TYPE_TSAP,
                                        label="TSAP",
                                    ),
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        )
                    }
                ),
            )

        self._connection_data[CONF_CONNECTION_TYPE] = user_input[CONF_CONNECTION_TYPE]

        if user_input[CONF_CONNECTION_TYPE] == CONNECTION_TYPE_RACK_SLOT:
            return await self.async_step_rack_slot()
        else:
            return await self.async_step_tsap()

    async def async_step_rack_slot(self, user_input: dict[str, Any] | None = None):
        """Handle rack/slot connection configuration."""
        errors: dict[str, str] = {}

        discovered_hosts = await self._async_get_discovered_hosts()

        host_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=host, label=host)
                    for host in discovered_hosts
                ],
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): host_selector,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_RACK, default=DEFAULT_RACK): int,
                vol.Optional(CONF_SLOT, default=DEFAULT_SLOT): int,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE, default=DEFAULT_PYS7_CONNECTION_TYPE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG (Programming Console)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP (Operator Panel)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=3600)),
                vol.Optional(CONF_OP_TIMEOUT, default=DEFAULT_OP_TIMEOUT): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=120)
                ),
                vol.Optional(CONF_MAX_RETRIES, default=DEFAULT_MAX_RETRIES): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10)
                ),
                vol.Optional(
                    CONF_BACKOFF_INITIAL, default=DEFAULT_BACKOFF_INITIAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=30)),
                vol.Optional(CONF_BACKOFF_MAX, default=DEFAULT_BACKOFF_MAX): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=120)
                ),
                vol.Optional(CONF_OPTIMIZE_READ, default=DEFAULT_OPTIMIZE_READ): bool,
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING, default=DEFAULT_ENABLE_WRITE_BATCHING
                ): bool,
                vol.Optional(CONF_ENABLE_METRICS, default=DEFAULT_ENABLE_METRICS): bool,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="rack_slot",
                data_schema=data_schema,
                description_placeholders={
                    "default_port": str(DEFAULT_PORT),
                    "default_rack": str(DEFAULT_RACK),
                    "default_slot": str(DEFAULT_SLOT),
                    "default_scan": str(DEFAULT_SCAN_INTERVAL),
                    "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
                    "default_retries": str(DEFAULT_MAX_RETRIES),
                    "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
                    "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
                },
                errors=errors,
            )

        return await self._async_validate_and_create(user_input, errors, data_schema)

    async def async_step_tsap(self, user_input: dict[str, Any] | None = None):
        """Handle TSAP connection configuration."""
        errors: dict[str, str] = {}

        discovered_hosts = await self._async_get_discovered_hosts()

        host_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=host, label=host)
                    for host in discovered_hosts
                ],
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="S7 PLC"): str,
                vol.Required(CONF_HOST): host_selector,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_LOCAL_TSAP, default="01.00"): str,
                vol.Required(CONF_REMOTE_TSAP, default="01.01"): str,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE, default=DEFAULT_PYS7_CONNECTION_TYPE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG (Programming Console)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP (Operator Panel)",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=3600)),
                vol.Optional(CONF_OP_TIMEOUT, default=DEFAULT_OP_TIMEOUT): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=120)
                ),
                vol.Optional(CONF_MAX_RETRIES, default=DEFAULT_MAX_RETRIES): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=10)
                ),
                vol.Optional(
                    CONF_BACKOFF_INITIAL, default=DEFAULT_BACKOFF_INITIAL
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=30)),
                vol.Optional(CONF_BACKOFF_MAX, default=DEFAULT_BACKOFF_MAX): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=120)
                ),
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING, default=DEFAULT_ENABLE_WRITE_BATCHING
                ): bool,
                vol.Optional(CONF_OPTIMIZE_READ, default=DEFAULT_OPTIMIZE_READ): bool,
                vol.Optional(CONF_ENABLE_METRICS, default=DEFAULT_ENABLE_METRICS): bool,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="tsap",
                data_schema=data_schema,
                description_placeholders={
                    "default_port": str(DEFAULT_PORT),
                    "default_scan": str(DEFAULT_SCAN_INTERVAL),
                    "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
                    "default_retries": str(DEFAULT_MAX_RETRIES),
                    "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
                    "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
                },
                errors=errors,
            )

        return await self._async_validate_and_create(user_input, errors, data_schema)

    async def _async_validate_and_create(
        self, user_input: dict[str, Any], errors: dict[str, str], data_schema
    ):
        """Validate connection and create entry."""

        connection_type = self._connection_data.get(
            CONF_CONNECTION_TYPE, CONNECTION_TYPE_RACK_SLOT
        )
        parse_defaults = _build_connection_parse_defaults(connection_type)

        try:
            host = user_input[CONF_HOST]
            params = _parse_connection_params(
                user_input,
                connection_type=connection_type,
                defaults=parse_defaults,
            )
            name = user_input.get(CONF_NAME, "S7 PLC")

        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            step_id = (
                "tsap"
                if self._connection_data.get(CONF_CONNECTION_TYPE)
                == CONNECTION_TYPE_TSAP
                else "rack_slot"
            )
            return self.async_show_form(
                step_id=step_id, data_schema=data_schema, errors=errors
            )

        unique_id = _generate_connection_unique_id(
            host,
            connection_type,
            params.local_tsap,
            params.remote_tsap,
            params.rack,
            params.slot,
        )
        await self.async_set_unique_id(unique_id, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        try:
            await _test_plc_connection(
                self.hass,
                host=host,
                connection_type=connection_type,
                rack=params.rack,
                slot=params.slot,
                local_tsap=params.local_tsap,
                remote_tsap=params.remote_tsap,
                pys7_connection_type=params.pys7_connection_type,
                port=params.port,
                scan_interval=params.scan_interval,
                op_timeout=params.op_timeout,
                max_retries=params.max_retries,
                backoff_initial=params.backoff_initial,
                backoff_max=params.backoff_max,
                optimize_read=params.optimize_read,
                enable_write_batching=params.enable_write_batching,
                enable_metrics=params.enable_metrics,
            )
        except Exception as err:
            # Catch all connection errors (OSError, S7 errors, RuntimeError, etc.)
            # and present them to the user through the config flow UI
            step_id = "tsap" if connection_type == CONNECTION_TYPE_TSAP else "rack_slot"
            return _handle_connection_error(
                self,
                err,
                host,
                params.port,
                connection_type,
                params.local_tsap,
                params.remote_tsap,
                params.rack,
                params.slot,
                step_id,
                data_schema,
                errors,
            )

        entry_data = _build_connection_entry_data(
            name=name,
            host=host,
            port=params.port,
            connection_type=connection_type,
            pys7_connection_type=params.pys7_connection_type,
            scan_interval=params.scan_interval,
            op_timeout=params.op_timeout,
            max_retries=params.max_retries,
            backoff_initial=params.backoff_initial,
            backoff_max=params.backoff_max,
            optimize_read=params.optimize_read,
            enable_write_batching=params.enable_write_batching,
            local_tsap=params.local_tsap,
            remote_tsap=params.remote_tsap,
            rack=params.rack,
            slot=params.slot,
            enable_metrics=params.enable_metrics,
        )

        return self.async_create_entry(title=name, data=entry_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return S7PLCOptionsFlow(config_entry)

    async def _async_get_discovered_hosts(self) -> list[str]:
        """Return cached or freshly discovered PLC hosts on the local network."""

        if self._discovered_hosts is not None:
            return self._discovered_hosts

        hosts_to_scan: list[str] = []
        hosts_seen: set[str] = set()
        adapters = await network.async_get_adapters(self.hass)

        for adapter in adapters:
            if not adapter.get("enabled", False):
                continue

            for ip_info in adapter.get("ipv4", []):
                address = ip_info.get("address")
                prefix = ip_info.get("network_prefix")

                if not address or prefix is None:
                    continue

                try:
                    interface = ip_interface(f"{address}/{prefix}")
                except ValueError:
                    continue

                if interface.ip.is_loopback:
                    continue

                network_obj = interface.network

                # Avoid scanning excessively large networks; narrow to /24 when needed.
                if network_obj.num_addresses > 1024:
                    try:
                        network_obj = ip_network(f"{interface.ip}/24", strict=False)
                    except ValueError:
                        continue

                for host in network_obj.hosts():
                    if host == interface.ip:
                        continue

                    host_str = str(host)
                    if host_str in hosts_seen:
                        continue
                    hosts_seen.add(host_str)
                    hosts_to_scan.append(host_str)

                    if len(hosts_to_scan) >= 256:
                        break

                if len(hosts_to_scan) >= 256:
                    break

            if len(hosts_to_scan) >= 256:
                break

        discovered: list[str] = []
        semaphore = asyncio.Semaphore(32)

        async def _probe(host: str) -> None:
            try:
                async with semaphore:
                    _reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, DEFAULT_PORT),
                        timeout=0.5,
                    )
            except (asyncio.TimeoutError, OSError):
                return
            except asyncio.CancelledError:
                raise
            else:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                discovered.append(host)

        await asyncio.gather(*(_probe(host) for host in hosts_to_scan))

        # Filter out already configured hosts
        configured_hosts = {
            entry.data.get(CONF_HOST)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_HOST)
        }
        discovered = [host for host in discovered if host not in configured_hosts]

        discovered.sort()
        self._discovered_hosts = discovered
        if discovered:
            _LOGGER.debug("Discovered potential S7 PLC hosts: %s", discovered)

        return discovered


class S7PLCOptionsFlow(config_entries.OptionsFlow):
    """Handle options for S7 PLC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._options = {
            CONF_SENSORS: list(config_entry.options.get(CONF_SENSORS, [])),
            CONF_BINARY_SENSORS: list(
                config_entry.options.get(CONF_BINARY_SENSORS, [])
            ),
            CONF_SWITCHES: list(config_entry.options.get(CONF_SWITCHES, [])),
            CONF_COVERS: list(config_entry.options.get(CONF_COVERS, [])),
            CONF_LIGHTS: list(config_entry.options.get(CONF_LIGHTS, [])),
            CONF_BUTTONS: list(config_entry.options.get(CONF_BUTTONS, [])),
            CONF_NUMBERS: list(config_entry.options.get(CONF_NUMBERS, [])),
            CONF_TEXTS: list(config_entry.options.get(CONF_TEXTS, [])),
            CONF_CLIMATES: list(config_entry.options.get(CONF_CLIMATES, [])),
            CONF_ENTITY_SYNC: list(config_entry.options.get(CONF_ENTITY_SYNC, [])),
        }
        self._entity_config_builder = EntityConfigBuilder(self._options)
        self._action: str | None = None  # "add" | "remove" | "edit"
        self._edit_target: tuple[str, int] | None = None
        self._last_add_input: dict[str, Any] | None = None

    def _sanitize_address(self, address: Any | None) -> str | None:
        """Delegate address sanitization to the shared entity builder."""
        return self._entity_config_builder._sanitize_address(address)

    def _normalized_address(self, address: Any | None) -> str | None:
        """Delegate address normalization to the shared entity builder."""
        return self._entity_config_builder._normalized_address(address)

    def _has_duplicate(
        self,
        option_key: str,
        address: str,
        *,
        keys: tuple[str, ...] = (CONF_ADDRESS,),
        skip_idx: int | None = None,
    ) -> bool:
        """Delegate duplicate checks to the shared entity builder."""
        return self._entity_config_builder._has_duplicate(
            option_key, address, keys=keys, skip_idx=skip_idx
        )

    def _get_area_selector(self) -> selector.SelectSelector:
        """Get area selector with dynamic area list."""
        options = _get_area_options(self.hass)
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    def _optional_field(
        self,
        key: str,
        item: dict[str, Any],
        selector_obj: Any,
    ) -> tuple[Any, Any]:
        """Return (vol.Optional, selector) with or without default."""
        if key in item and item[key] is not None and item[key] != "":
            return vol.Optional(key, default=item[key]), selector_obj
        return vol.Optional(key), selector_obj

    async def _edit_entity(
        self,
        *,
        option_key: str,
        prefix: str,
        build_schema,
        process_input,
        step_id: str,
        user_input: dict[str, Any] | None,
    ):
        """Generic helper to edit an entity type."""
        lookup = self._get_edit_item(option_key, prefix)
        if lookup is None:
            self._clear_edit_state()
            return await self.async_step_edit()

        idx, item = lookup
        errors: dict[str, str] = {}
        data_schema = build_schema(item)

        if user_input is not None:
            new_item, errors = process_input(item, idx, user_input)
            if not errors and new_item is not None:
                # Carry the item's permanent identity forward: the builder
                # only sees user_input, never the old item, so it can't
                # preserve this itself. Without this, editing any field
                # would assign a fresh uid and orphan the existing entity.
                new_item[CONF_UID] = item.get(CONF_UID) or generate_uid()
                self._options[option_key][idx] = new_item
                self._clear_edit_state()
                return self.async_create_entry(title="", data=self._options)
            if errors:
                data_schema = self.add_suggested_values_to_schema(
                    data_schema, user_input
                )

        return self.async_show_form(
            step_id=step_id, data_schema=data_schema, errors=errors
        )

    # ====== GENERIC ADD / EDIT via ENTITY_TYPE_REGISTRY ======

    async def _add_entity(self, step_id: str, user_input: dict[str, Any] | None = None):
        """Generic handler for *all* entity-add steps."""
        info = ENTITY_TYPE_REGISTRY[_ADD_STEP_TO_PREFIX[step_id]]
        data_schema = info.build_add_schema(self)

        if user_input is not None:
            builder = getattr(self._entity_config_builder, info.item_builder_name)
            item, errors = builder(user_input, skip_idx=None)

            if errors:
                data_schema = self.add_suggested_values_to_schema(
                    data_schema, user_input
                )
                return self.async_show_form(
                    step_id=step_id, data_schema=data_schema, errors=errors
                )

            if item is not None:
                item[CONF_UID] = generate_uid()
                self._options[info.option_key].append(item)

            if user_input.get("add_another"):
                self._last_add_input = {
                    k: v for k, v in user_input.items() if k != "add_another"
                }
                return await self._add_entity(step_id)

            return self.async_create_entry(title="", data=self._options)

        if self._last_add_input is not None:
            data_schema = self.add_suggested_values_to_schema(
                data_schema, self._last_add_input
            )
            self._last_add_input = None
        return self.async_show_form(step_id=step_id, data_schema=data_schema)

    async def _edit_entity_by_prefix(
        self, prefix: str, user_input: dict[str, Any] | None = None
    ):
        """Generic handler for *all* entity-edit steps."""
        info = ENTITY_TYPE_REGISTRY[prefix]

        def _build(item: dict[str, Any]) -> vol.Schema:
            return info.build_edit_schema(self, item)

        def _process(old_item: dict[str, Any], idx: int, inp: dict[str, Any]):
            return getattr(self._entity_config_builder, info.item_builder_name)(
                inp, skip_idx=idx
            )

        return await self._edit_entity(
            option_key=info.option_key,
            prefix=prefix,
            build_schema=_build,
            process_input=_process,
            step_id=info.edit_step_id,
            user_input=user_input,
        )

    @staticmethod
    def _labelize(prefix: str, item: dict[str, Any]) -> str:
        name = item.get(CONF_NAME)
        address = item.get(CONF_ADDRESS) or item.get(CONF_STATE_ADDRESS) or "?"
        type_label = {
            "s": "Sensor",
            "bs": "Binary",
            "sw": "Switch",
            "cv": "Cover",
            "cvp": "Cover (Position)",
            "bt": "Button",
            "lt": "Light",
            "nm": "Number",
            "tx": "Text",
            "cl_d": "Climate (Direct)",
            "cl_s": "Climate (Setpoint)",
            "wr": "Entity Sync",
        }[prefix]
        base = name or address
        return f"{type_label} • {base} [{address}]"

    def _build_items_map(self) -> Dict[str, str]:
        items: Dict[str, str] = {}

        # Helper function to get sort key (name or address)
        def get_sort_key(item: dict[str, Any]) -> str:
            name = item.get(CONF_NAME, "")
            if name:
                return name.lower()
            address = (
                item.get(CONF_ADDRESS)
                or item.get(CONF_STATE_ADDRESS)
                or item.get(CONF_OPEN_COMMAND_ADDRESS)
                or ""
            )
            return address.lower()

        # Sensors - sorted alphabetically
        sensors = self._options.get(CONF_SENSORS, [])
        sorted_sensors = sorted(enumerate(sensors), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_sensors:
            items[f"s:{orig_idx}"] = self._labelize("s", it)

        # Binary Sensors - sorted alphabetically
        binary_sensors = self._options.get(CONF_BINARY_SENSORS, [])
        sorted_binary = sorted(
            enumerate(binary_sensors), key=lambda x: get_sort_key(x[1])
        )
        for orig_idx, it in sorted_binary:
            items[f"bs:{orig_idx}"] = self._labelize("bs", it)

        # Switches - sorted alphabetically
        switches = self._options.get(CONF_SWITCHES, [])
        sorted_switches = sorted(enumerate(switches), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_switches:
            switch_item = {**it}
            switch_item.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"sw:{orig_idx}"] = self._labelize("sw", switch_item)

        # Covers - sorted alphabetically (distinguish position-based covers)
        covers = self._options.get(CONF_COVERS, [])
        sorted_covers = sorted(enumerate(covers), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_covers:
            cover_item = {**it}
            # Check if this is a position-based cover
            if CONF_POSITION_STATE_ADDRESS in it:
                cover_item.setdefault(CONF_ADDRESS, it.get(CONF_POSITION_STATE_ADDRESS))
                items[f"cvp:{orig_idx}"] = self._labelize("cvp", cover_item)
            else:
                cover_item.setdefault(CONF_ADDRESS, it.get(CONF_OPEN_COMMAND_ADDRESS))
                items[f"cv:{orig_idx}"] = self._labelize("cv", cover_item)

        # Buttons - sorted alphabetically
        buttons = self._options.get(CONF_BUTTONS, [])
        sorted_buttons = sorted(enumerate(buttons), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_buttons:
            items[f"bt:{orig_idx}"] = self._labelize("bt", it)

        # Lights - sorted alphabetically (distinguish dimmer lights)
        lights = self._options.get(CONF_LIGHTS, [])
        sorted_lights = sorted(enumerate(lights), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_lights:
            light_item = {**it}
            light_item.setdefault(CONF_ADDRESS, it.get(CONF_STATE_ADDRESS))
            items[f"lt:{orig_idx}"] = self._labelize("lt", light_item)

        # Numbers - sorted alphabetically
        numbers = self._options.get(CONF_NUMBERS, [])
        sorted_numbers = sorted(enumerate(numbers), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_numbers:
            items[f"nm:{orig_idx}"] = self._labelize("nm", it)

        # Texts - sorted alphabetically
        texts = self._options.get(CONF_TEXTS, [])
        sorted_texts = sorted(enumerate(texts), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_texts:
            items[f"tx:{orig_idx}"] = self._labelize("tx", it)

        # Climates - sorted alphabetically
        climates = self._options.get(CONF_CLIMATES, [])
        sorted_climates = sorted(enumerate(climates), key=lambda x: get_sort_key(x[1]))
        for orig_idx, it in sorted_climates:
            control_mode = it.get(CONF_CLIMATE_CONTROL_MODE, CONTROL_MODE_SETPOINT)
            prefix = "cl_d" if control_mode == CONTROL_MODE_DIRECT else "cl_s"
            # Override address for labelize
            climate_item = dict(it)
            climate_item.setdefault(
                CONF_ADDRESS, it.get(CONF_CURRENT_TEMPERATURE_ADDRESS)
            )
            items[f"{prefix}:{orig_idx}"] = self._labelize(prefix, climate_item)

        # Entity Syncs - sorted alphabetically
        entity_syncs = self._options.get(CONF_ENTITY_SYNC, [])
        sorted_entity_syncs = sorted(
            enumerate(entity_syncs), key=lambda x: get_sort_key(x[1])
        )
        for orig_idx, it in sorted_entity_syncs:
            items[f"wr:{orig_idx}"] = self._labelize("wr", it)

        return items

    def _exportable_options(self) -> dict[str, list[dict[str, Any]]]:
        return build_export_payload(self._options)

    def _build_export_data(self) -> str:
        return build_export_json(self._options)

    def _sanitize_import_payload(
        self, payload: Any
    ) -> tuple[dict[str, list[dict[str, Any]]] | None, str | None]:
        """Sanitize import payload.

        Returns:
            Tuple of (sanitized_data, error_key). If successful, error_key is None.
            If failed, sanitized_data is None and
            error_key contains the error message key.
        """
        if not isinstance(payload, dict):
            return None, "invalid_json"

        sanitized: dict[str, list[dict[str, Any]]] = {}
        for key in OPTION_KEYS:
            raw_items = payload.get(key, [])
            if raw_items is None:
                raw_items = []
            if not isinstance(raw_items, list):
                return None, "invalid_json"
            sanitized[key] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    return None, "invalid_json"
                sanitized[key].append(dict(item))

            # Log imported items for each key
            if sanitized[key]:
                _LOGGER.info("Import: %s = %d items", key, len(sanitized[key]))

        seen_uids: set[str] = set()
        for key in OPTION_KEYS:
            for item in sanitized[key]:
                uid = item.get(CONF_UID)
                if not isinstance(uid, str) or not uid:
                    continue
                if uid in seen_uids:
                    replacement_uid = generate_uid()
                    while replacement_uid in seen_uids:
                        replacement_uid = generate_uid()
                    item[CONF_UID] = replacement_uid
                    uid = replacement_uid
                seen_uids.add(uid)

        # Validate for duplicate addresses within each entity type
        if not self._validate_import_duplicates(sanitized):
            _LOGGER.warning("Import failed: duplicate addresses found")
            return None, "duplicate_addresses_in_import"

        _LOGGER.info(
            "Import validation successful, total climate items: %d",
            len(sanitized.get(CONF_CLIMATES, [])),
        )

        # Preserve any other option keys currently in use to avoid losing data.
        for key, value in self._options.items():
            if key not in sanitized:
                if isinstance(value, list):
                    sanitized[key] = [
                        dict(item) if isinstance(item, dict) else item for item in value
                    ]
                else:
                    sanitized[key] = value

        return sanitized, None

    def _validate_import_duplicates(
        self, sanitized: dict[str, list[dict[str, Any]]]
    ) -> bool:
        """Validate that imported data doesn't contain duplicate addresses.

        Returns False if duplicates are found, True otherwise.
        """
        # Define which address keys to check for each entity type
        address_keys_map = {
            CONF_SENSORS: (CONF_ADDRESS,),
            CONF_BINARY_SENSORS: (CONF_ADDRESS,),
            CONF_SWITCHES: (CONF_STATE_ADDRESS, CONF_ADDRESS),
            CONF_COVERS: (CONF_OPEN_COMMAND_ADDRESS, CONF_POSITION_STATE_ADDRESS),
            CONF_LIGHTS: (CONF_STATE_ADDRESS, CONF_ADDRESS),
            CONF_BUTTONS: (CONF_ADDRESS,),
            CONF_NUMBERS: (CONF_ADDRESS,),
            CONF_TEXTS: (CONF_ADDRESS,),
            CONF_CLIMATES: (
                CONF_TARGET_TEMPERATURE_ADDRESS,
                CONF_HEATING_OUTPUT_ADDRESS,
                CONF_COOLING_OUTPUT_ADDRESS,
            ),
            CONF_ENTITY_SYNC: (CONF_ADDRESS,),
        }

        for entity_type, address_keys in address_keys_map.items():
            items = sanitized.get(entity_type, [])
            seen_addresses: set[str] = set()

            for item in items:
                # Check all relevant address keys for this entity type
                for key in address_keys:
                    address = item.get(key)
                    if address:
                        normalized = self._normalized_address(address)
                        if normalized:
                            if normalized in seen_addresses:
                                # Duplicate found
                                return False
                            seen_addresses.add(normalized)

        return True

    def _clear_edit_state(self) -> None:
        self._action = None
        self._edit_target = None

    async def async_step_connection(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        data = self._config_entry.data

        # Determine connection type from existing data
        connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_RACK_SLOT)
        is_tsap = connection_type == CONNECTION_TYPE_TSAP
        parse_defaults = _build_connection_parse_defaults(connection_type, data)

        defaults = {
            CONF_NAME: data.get(CONF_NAME) or self._config_entry.title or "S7 PLC",
            CONF_HOST: data.get(CONF_HOST, ""),
            **parse_defaults,
        }

        # Build schema based on connection type
        schema_fields = {
            vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
            vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
            vol.Optional(CONF_PORT, default=defaults[CONF_PORT]): int,
        }

        if is_tsap:
            schema_fields[
                vol.Required(CONF_LOCAL_TSAP, default=defaults[CONF_LOCAL_TSAP])
            ] = str
            schema_fields[
                vol.Required(CONF_REMOTE_TSAP, default=defaults[CONF_REMOTE_TSAP])
            ] = str
        else:
            schema_fields[vol.Optional(CONF_RACK, default=defaults[CONF_RACK])] = int
            schema_fields[vol.Optional(CONF_SLOT, default=defaults[CONF_SLOT])] = int

        schema_fields.update(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=3600)),
                vol.Optional(
                    CONF_OP_TIMEOUT, default=defaults[CONF_OP_TIMEOUT]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=120)),
                vol.Optional(
                    CONF_MAX_RETRIES, default=defaults[CONF_MAX_RETRIES]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Optional(
                    CONF_BACKOFF_INITIAL, default=defaults[CONF_BACKOFF_INITIAL]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=30)),
                vol.Optional(
                    CONF_BACKOFF_MAX, default=defaults[CONF_BACKOFF_MAX]
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=120)),
                vol.Optional(
                    CONF_OPTIMIZE_READ, default=defaults[CONF_OPTIMIZE_READ]
                ): bool,
                vol.Optional(
                    CONF_ENABLE_WRITE_BATCHING,
                    default=defaults[CONF_ENABLE_WRITE_BATCHING],
                ): bool,
                vol.Optional(
                    CONF_ENABLE_METRICS, default=defaults[CONF_ENABLE_METRICS]
                ): bool,
                vol.Optional(
                    CONF_PYS7_CONNECTION_TYPE,
                    default=defaults[CONF_PYS7_CONNECTION_TYPE],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_PG,
                                label="PG",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_OP,
                                label="OP",
                            ),
                            selector.SelectOptionDict(
                                value=PYS7_CONNECTION_TYPE_S7BASIC,
                                label="S7 Basic",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        data_schema = vol.Schema(schema_fields)

        description_placeholders = {
            "default_port": str(DEFAULT_PORT),
            "default_scan": str(DEFAULT_SCAN_INTERVAL),
            "default_timeout": f"{DEFAULT_OP_TIMEOUT:.1f}",
            "default_retries": str(DEFAULT_MAX_RETRIES),
            "default_backoff_initial": f"{DEFAULT_BACKOFF_INITIAL:.2f}",
            "default_backoff_max": f"{DEFAULT_BACKOFF_MAX:.1f}",
        }

        if not is_tsap:
            description_placeholders["default_rack"] = str(DEFAULT_RACK)
            description_placeholders["default_slot"] = str(DEFAULT_SLOT)

        if user_input is None:
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                description_placeholders=description_placeholders,
            )

        try:
            host = str(user_input[CONF_HOST]).strip()
            params = _parse_connection_params(
                user_input,
                connection_type=(
                    CONNECTION_TYPE_TSAP if is_tsap else CONNECTION_TYPE_RACK_SLOT
                ),
                defaults=parse_defaults,
            )
            name = (
                user_input.get(CONF_NAME) or defaults[CONF_NAME]
            ).strip() or "S7 PLC"

        except (KeyError, ValueError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors=errors,
                description_placeholders=description_placeholders,
            )

        connection_type = CONNECTION_TYPE_TSAP if is_tsap else CONNECTION_TYPE_RACK_SLOT
        new_unique_id = _generate_connection_unique_id(
            host,
            connection_type,
            params.local_tsap,
            params.remote_tsap,
            params.rack,
            params.slot,
        )

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == self._config_entry.entry_id:
                continue
            if entry.unique_id == new_unique_id:
                errors["base"] = "already_configured"
                break

        if errors:
            return self.async_show_form(
                step_id="connection",
                data_schema=data_schema,
                errors=errors,
                description_placeholders=description_placeholders,
            )

        try:
            await _test_plc_connection(
                self.hass,
                host=host,
                connection_type=connection_type,
                rack=params.rack,
                slot=params.slot,
                local_tsap=params.local_tsap,
                remote_tsap=params.remote_tsap,
                pys7_connection_type=params.pys7_connection_type,
                port=params.port,
                scan_interval=params.scan_interval,
                op_timeout=params.op_timeout,
                max_retries=params.max_retries,
                backoff_initial=params.backoff_initial,
                backoff_max=params.backoff_max,
                optimize_read=params.optimize_read,
                enable_write_batching=params.enable_write_batching,
                enable_metrics=params.enable_metrics,
            )
        except Exception as err:
            # Catch all connection errors during options flow connection test
            # to provide user-friendly error messages in the UI
            return _handle_connection_error(
                self,
                err,
                host,
                params.port,
                connection_type,
                params.local_tsap,
                params.remote_tsap,
                params.rack,
                params.slot,
                "connection",
                data_schema,
                errors,
                description_placeholders,
            )

        new_data = _build_connection_entry_data(
            name=name,
            host=host,
            port=params.port,
            connection_type=connection_type,
            pys7_connection_type=params.pys7_connection_type,
            scan_interval=params.scan_interval,
            op_timeout=params.op_timeout,
            max_retries=params.max_retries,
            backoff_initial=params.backoff_initial,
            backoff_max=params.backoff_max,
            optimize_read=params.optimize_read,
            enable_write_batching=params.enable_write_batching,
            enable_metrics=params.enable_metrics,
            local_tsap=params.local_tsap,
            remote_tsap=params.remote_tsap,
            rack=params.rack,
            slot=params.slot,
        )

        update_result = self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=new_data,
            title=name,
        )

        if inspect.isawaitable(update_result):
            await update_result

        return self.async_create_entry(title="", data=self._options)

    # ====== STEP 0: choose action (main menu) ======
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Show a simplified main menu with 3 main options
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "setup_connection",  # modify connection parameters
                "setup_entities",  # add or edit entities
                "manage_configuration",  # remove, export or import configuration
            ],
        )

    # ====== STEP: setup connection (redirect) ======
    async def async_step_setup_connection(
        self, user_input: dict[str, Any] | None = None
    ):
        """Redirect to connection step."""
        return await self.async_step_connection(user_input)

    # ====== STEP: setup entities (submenu) ======
    async def async_step_setup_entities(self, user_input: dict[str, Any] | None = None):
        """Show submenu for entity operations."""
        return self.async_show_menu(
            step_id="setup_entities",
            menu_options=[
                "add",  # add new entities
                "edit",  # edit existing entities
                "remove",  # remove existing entities
            ],
        )

    # ====== STEP: manage configuration (submenu) ======
    async def async_step_manage_configuration(
        self, user_input: dict[str, Any] | None = None
    ):
        """Show submenu for configuration management."""
        return self.async_show_menu(
            step_id="manage_configuration",
            menu_options=[
                "export",  # export configuration
                "import",  # import configuration
            ],
        )

    async def async_step_add(self, user_input: dict[str, Any] | None = None):
        _LOGGER.debug(f"async_step_add called with user_input={user_input}")
        if user_input is None:
            _LOGGER.debug("Showing add menu")
            return self.async_show_menu(
                step_id="add",
                menu_options=list(ADD_ENTITY_STEP_IDS),
            )

        selection = user_input.get("menu_option") or user_input.get("item_type") or ""
        _LOGGER.debug(f"User selected from add menu: '{selection}'")

        if selection not in ADD_ENTITY_STEP_IDS:
            _LOGGER.warning(f"Invalid selection '{selection}', returning to add menu")
            return await self.async_step_add()

        _LOGGER.debug(f"Calling handler async_step_{selection}")
        handler = getattr(self, f"async_step_{selection}")
        return await handler()

    # ====== ADD: sensors ======
    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("sensors", user_input)

    # ====== ADD: binary_sensors ======
    async def async_step_binary_sensors(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("binary_sensors", user_input)

    # ====== ADD: switches ======
    async def async_step_switches(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("switches", user_input)

    # ====== ADD: covers (menu to choose type) ======
    async def async_step_covers(self, user_input: dict[str, Any] | None = None):
        """Show menu to choose between traditional or position cover."""
        _LOGGER.debug(f"async_step_covers called with user_input={user_input}")
        if user_input is None:
            _LOGGER.debug("Showing covers type selection menu")
            return self.async_show_menu(
                step_id="covers",
                menu_options=["covers_traditional", "covers_position"],
            )

        selection = user_input.get("menu_option") or ""
        _LOGGER.debug(f"User selected cover type: {selection}")

        if selection == "covers_traditional":
            return await self.async_step_covers_traditional()
        elif selection == "covers_position":
            return await self.async_step_covers_position()

        _LOGGER.warning(f"Invalid cover type selection: {selection}")
        return await self.async_step_covers()

    # ====== ADD: covers_traditional ======
    async def async_step_covers_traditional(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._add_entity("covers_traditional", user_input)

    # ====== ADD: covers_position ======
    async def async_step_covers_position(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._add_entity("covers_position", user_input)

    # ====== ADD: buttons ======
    async def async_step_buttons(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("buttons", user_input)

    # ====== ADD: lights ======
    async def async_step_lights(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("lights", user_input)

    # ====== ADD: numbers ======
    async def async_step_numbers(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("numbers", user_input)

    # ====== ADD: texts ======
    async def async_step_texts(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("texts", user_input)

    # ====== ADD: climates ======
    async def async_step_climates(self, user_input: dict[str, Any] | None = None):
        """Show menu to choose between direct or setpoint climate control."""
        _LOGGER.debug(f"async_step_climates called with user_input={user_input}")
        if user_input is None:
            _LOGGER.debug("Showing climates type selection menu")
            return self.async_show_menu(
                step_id="climates",
                menu_options=["climates_direct", "climates_setpoint"],
            )

        selection = user_input.get("menu_option") or ""
        _LOGGER.debug(f"User selected climate type: {selection}")

        if selection == "climates_direct":
            return await self.async_step_climates_direct()
        elif selection == "climates_setpoint":
            return await self.async_step_climates_setpoint()

        _LOGGER.warning(f"Invalid climate type selection: {selection}")
        return await self.async_step_climates()

    # ====== ADD: climates_direct ======
    async def async_step_climates_direct(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._add_entity("climates_direct", user_input)

    # ====== ADD: climates_setpoint ======
    async def async_step_climates_setpoint(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._add_entity("climates_setpoint", user_input)

    # ====== ADD: entity_sync ======
    async def async_step_entity_sync(self, user_input: dict[str, Any] | None = None):
        return await self._add_entity("entity_sync", user_input)

    # ====== EXPORT ======
    async def async_step_export(self, user_input: dict[str, Any] | None = None):
        export_text = self._build_export_data()

        data_schema = vol.Schema(
            {vol.Required("export_json", default=export_text): str}
        )

        if user_input is None:
            item_count = sum(len(self._options.get(key, [])) for key in OPTION_KEYS)
            download_link = register_export_download(
                self.hass,
                self._config_entry.title,
                self._config_entry.data.get(CONF_NAME),
                export_text,
            )
            return self.async_show_form(
                step_id="export",
                data_schema=data_schema,
                description_placeholders={
                    "item_count": str(item_count),
                    "download_filename": download_link.filename,
                    "download_link_start": (
                        f'<a href="{download_link.url}" '
                        f'download="{download_link.filename}" '
                        'target="_blank" rel="noopener">'
                    ),
                    "download_link_end": "</a>",
                },
            )

        return self.async_create_entry(title="", data=self._options)

    # ====== IMPORT ======
    async def async_step_import(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current_text = ""

        if user_input is not None:
            raw_value = user_input.get("import_json")
            if raw_value is None:
                errors["base"] = "invalid_json"
            else:
                current_text = str(raw_value)
                raw_text = current_text.strip()
                if not raw_text:
                    errors["base"] = "invalid_json"
                else:
                    try:
                        payload = json.loads(raw_text)
                    except ValueError:
                        errors["base"] = "invalid_json"
                    else:
                        sanitized, error_key = self._sanitize_import_payload(payload)
                        if sanitized is None:
                            errors["base"] = error_key or "invalid_json"
                        else:
                            self._options = sanitized
                            return self.async_create_entry(title="", data=self._options)

        data_schema = vol.Schema(
            {vol.Required("import_json", default=current_text): str}
        )

        item_count = sum(len(self._options.get(key, [])) for key in OPTION_KEYS)
        return self.async_show_form(
            step_id="import",
            data_schema=data_schema,
            description_placeholders={"item_count": str(item_count)},
            errors=errors if errors else None,
        )

    # ====== STEP B: remove ======
    def _parse_item_key(self, key: str) -> tuple[str, int] | None:
        """Safely parse an item key like 's:0' into (prefix, index).

        Returns None if the key is malformed.
        """
        try:
            parts = key.split(":", 1)
            if len(parts) != 2:
                return None
            prefix, idx_str = parts
            return (prefix, int(idx_str))
        except (ValueError, AttributeError):
            return None

    async def async_step_remove(self, user_input: dict[str, Any] | None = None):
        # Build a key->label map for all configured items
        # Unique key: type prefix + index, e.g. "s:0", "bs:1", "sw:2", "lt:0"
        items: Dict[str, str] = self._build_items_map()

        if user_input is not None:
            to_remove: List[str] = user_input.get("remove_items", [])
            # filter each list removing the selected indices
            if to_remove:
                # Map prefix -> (config_key, set of indices to remove)
                prefix_map = {
                    "s": CONF_SENSORS,
                    "bs": CONF_BINARY_SENSORS,
                    "sw": CONF_SWITCHES,
                    "cv": CONF_COVERS,
                    "cvp": CONF_COVERS,  # Position-based covers
                    "bt": CONF_BUTTONS,
                    "lt": CONF_LIGHTS,
                    "nm": CONF_NUMBERS,
                    "tx": CONF_TEXTS,
                    "cl_d": CONF_CLIMATES,  # Direct control climate
                    "cl_s": CONF_CLIMATES,  # Setpoint control climate
                    "wr": CONF_ENTITY_SYNC,
                }

                # Build set of indices to remove for each prefix (safe parsing)
                remove_indices = {prefix: set() for prefix in prefix_map}
                for key in to_remove:
                    parsed = self._parse_item_key(key)
                    if parsed and parsed[0] in prefix_map:
                        remove_indices[parsed[0]].add(parsed[1])

                # Filter each list
                for prefix, conf_key in prefix_map.items():
                    indices_to_remove = remove_indices[prefix]
                    self._options[conf_key] = [
                        v
                        for idx, v in enumerate(self._options.get(conf_key, []))
                        if idx not in indices_to_remove
                    ]

            # Save and close: __init__.py will reload the entry
            # and the entities will disappear
            return self.async_create_entry(title="", data=self._options)

        # Preselect nothing: the user chooses what to remove
        data_schema = vol.Schema(
            {vol.Optional("remove_items", default=[]): cv.multi_select(items)}
        )
        # Title/description from translations: options.step.remove.*
        return self.async_show_form(step_id="remove", data_schema=data_schema)

    # ====== STEP C: edit ======
    async def async_step_edit(self, user_input: dict[str, Any] | None = None):
        items = self._build_items_map()

        if not items:
            return self.async_show_form(
                step_id="edit",
                data_schema=vol.Schema({}),
                errors={"base": "no_items"},
            )

        select_options = [
            selector.SelectOptionDict(value=f"{key} | {label}", label=label)
            for key, label in items.items()
        ]
        data_schema = vol.Schema(
            {
                vol.Required("edit_item"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=select_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="edit", data_schema=data_schema)

        raw_selection = user_input.get("edit_item", "")
        # Extract the key (e.g. "s:0") from "s:0 | Label text"
        selection = raw_selection.split(" | ", 1)[0]
        if selection not in items:
            return await self.async_step_edit()

        prefix, _, idx_str = selection.partition(":")
        try:
            idx = int(idx_str)
        except ValueError:
            return await self.async_step_edit()

        self._action = "edit"
        self._edit_target = (prefix, idx)

        if prefix in ENTITY_TYPE_REGISTRY:
            return await self._edit_entity_by_prefix(prefix)

        return await self.async_step_edit()

    def _get_edit_item(
        self, option_key: str, prefix: str
    ) -> tuple[int, dict[str, Any]] | None:
        if self._edit_target is None:
            return None
        target_prefix, index = self._edit_target
        if target_prefix != prefix:
            return None
        items = self._options.get(option_key, [])
        if not 0 <= index < len(items):
            return None
        return index, items[index]

    # ====== EDIT: entity steps (all delegated via registry) ======
    async def async_step_edit_sensor(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("s", user_input)

    async def async_step_edit_binary_sensor(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._edit_entity_by_prefix("bs", user_input)

    async def async_step_edit_switch(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("sw", user_input)

    async def async_step_edit_cover(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("cv", user_input)

    async def async_step_edit_cover_position(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._edit_entity_by_prefix("cvp", user_input)

    async def async_step_edit_button(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("bt", user_input)

    async def async_step_edit_light(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("lt", user_input)

    async def async_step_edit_number(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("nm", user_input)

    async def async_step_edit_text(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("tx", user_input)

    async def async_step_edit_climate_direct(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._edit_entity_by_prefix("cl_d", user_input)

    async def async_step_edit_climate_setpoint(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self._edit_entity_by_prefix("cl_s", user_input)

    async def async_step_edit_writer(self, user_input: dict[str, Any] | None = None):
        return await self._edit_entity_by_prefix("wr", user_input)
