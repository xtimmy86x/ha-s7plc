DOMAIN = "s7plc"
PLATFORMS = [
    "binary_sensor",
    "sensor",
    "switch",
    "cover",
    "light",
    "button",
    "number",
    "text",
    "climate",
]

CONF_RACK = "rack"
CONF_SLOT = "slot"
CONF_CONNECTION_TYPE = "connection_type"
CONF_PYS7_CONNECTION_TYPE = "pys7_connection_type"
CONF_LOCAL_TSAP = "local_tsap"
CONF_REMOTE_TSAP = "remote_tsap"

CONNECTION_TYPE_RACK_SLOT = "rack_slot"
CONNECTION_TYPE_TSAP = "tsap"

# pyS7 ConnectionType values
PYS7_CONNECTION_TYPE_PG = "pg"
PYS7_CONNECTION_TYPE_OP = "op"
PYS7_CONNECTION_TYPE_S7BASIC = "s7basic"

CONF_SENSORS = "sensors"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_SWITCHES = "switches"
CONF_COVERS = "covers"
CONF_LIGHTS = "lights"
CONF_NUMBERS = "numbers"
CONF_BUTTONS = "buttons"
CONF_TEXTS = "texts"
CONF_CLIMATES = "climates"
CONF_ENTITY_SYNC = "entity_sync"

OPTION_KEYS = (
    CONF_SENSORS,
    CONF_BINARY_SENSORS,
    CONF_SWITCHES,
    CONF_COVERS,
    CONF_LIGHTS,
    CONF_BUTTONS,
    CONF_NUMBERS,
    CONF_TEXTS,
    CONF_CLIMATES,
    CONF_ENTITY_SYNC,
)

CONF_ADDRESS = "address"
CONF_AREA = "area"
# Permanent per-item identity, assigned once at creation and never derived
# from any editable field. unique_id is built from this, not from addresses,
# so editing an item's address only changes its behavior, never its identity.
CONF_UID = "uid"
# Internal marker (not user-facing): set once the one-time migration that
# upgrades pre-existing "uid" values to include the device_id prefix has
# run for this config entry. See helpers.migrate_legacy_uid_device_prefix.
CONF_UID_DEVICE_PREFIX_MIGRATED = "_uid_device_prefix_migrated"
CONF_SOURCE_ENTITY = "source_entity"
CONF_DEVICE_CLASS = "device_class"
CONF_INVERT_STATE = "invert_state"
CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_SYNC_STATE = "sync_state"
CONF_BUTTON_PULSE = "button_pulse"
CONF_PULSE_COMMAND = "pulse_command"
CONF_PULSE_DURATION = "pulse_duration"
CONF_MIN_VALUE = "min_value"
CONF_MAX_VALUE = "max_value"
CONF_STEP = "step"
CONF_MIN_LENGTH = "min_length"
CONF_MAX_LENGTH = "max_length"
CONF_PATTERN = "pattern"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_BRIGHTNESS_STATE_ADDRESS = "brightness_state_address"
CONF_BRIGHTNESS_COMMAND_ADDRESS = "brightness_command_address"
CONF_BRIGHTNESS_SCALE = "brightness_scale"
CONF_VALUE_MULTIPLIER = "value_multiplier"
CONF_SCALE_RAW_MIN = "scale_raw_min"
CONF_SCALE_RAW_MAX = "scale_raw_max"
CONF_UNIT_OF_MEASUREMENT = "unit_of_measurement"
CONF_STATE_CLASS = "state_class"
CONF_REAL_PRECISION = "real_precision"

# Cover entity configuration
CONF_OPEN_COMMAND_ADDRESS = "open_command_address"
CONF_CLOSE_COMMAND_ADDRESS = "close_command_address"
CONF_OPENING_STATE_ADDRESS = "opening_state_address"
CONF_CLOSING_STATE_ADDRESS = "closing_state_address"
CONF_OPERATE_TIME = "operate_time"
CONF_USE_STATE_TOPICS = "use_state_topics"
CONF_POSITION_STATE_ADDRESS = "position_state_address"
CONF_POSITION_COMMAND_ADDRESS = "position_command_address"
CONF_INVERT_POSITION = "invert_position"
CONF_STOP_COMMAND_ADDRESS = "stop_command_address"
CONF_STOP_PULSE_DURATION = "stop_pulse_duration"

# Climate entity configuration
CONF_CLIMATE_CONTROL_MODE = "control_mode"
CONF_CURRENT_TEMPERATURE_ADDRESS = "current_temperature_address"
CONF_TARGET_TEMPERATURE_ADDRESS = "target_temperature_address"
CONF_HEATING_OUTPUT_ADDRESS = "heating_output_address"
CONF_COOLING_OUTPUT_ADDRESS = "cooling_output_address"
CONF_HEATING_ACTION_ADDRESS = "heating_action_address"
CONF_COOLING_ACTION_ADDRESS = "cooling_action_address"
CONF_PRESET_MODE_ADDRESS = "preset_mode_address"
# Optional boolean PLC address for thermostats that have no OFF mode of
# their own and are instead switched on/off by a separate output: writes
# False/0 when the target mode is set to OFF, True/1 for any other mode.
CONF_ON_OFF_ADDRESS = "on_off_address"
CONF_HVAC_STATUS_ADDRESS = "hvac_status_address"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TEMP_STEP = "temp_step"

# Climate HVAC mode <-> PLC value mapping (setpoint control mode).
# Current (read) and target (write) are configured independently since the
# PLC may use different codes for reporting status vs. accepting a command.

# Sentinel: -1 disables/skips this mode.
# - In a target (preset_mode_*_value) field, it removes that HVAC mode from
#   the thermostat's selectable mode list entirely.
# - In a current (hvac_status_*_values) field, it is dropped from the parsed
#   value list, so that status is never matched (skipped).
MODE_VALUE_DISABLED = -1

# Current status: value(s) read from hvac_status_address that are recognized
# as each mode. Each field accepts one or more comma-separated integers,
# e.g. "2,3", so several PLC codes can be treated as the same mode.
CONF_HVAC_STATUS_OFF_VALUES = "hvac_status_off_values"
CONF_HVAC_STATUS_HEATING_VALUES = "hvac_status_heating_values"
CONF_HVAC_STATUS_COOLING_VALUES = "hvac_status_cooling_values"
CONF_HVAC_STATUS_IDLE_VALUES = "hvac_status_idle_values"
CONF_HVAC_STATUS_DRYING_VALUES = "hvac_status_drying_values"
CONF_HVAC_STATUS_FAN_VALUES = "hvac_status_fan_values"
CONF_HVAC_STATUS_PREHEATING_VALUES = "hvac_status_preheating_values"

DEFAULT_HVAC_STATUS_OFF_VALUES = "0"
DEFAULT_HVAC_STATUS_HEATING_VALUES = "1"
DEFAULT_HVAC_STATUS_COOLING_VALUES = "2"
# Disabled (-1) by default: these statuses were added after the original
# off/heating/cooling trio and are uncommon for a PLC-driven thermostat, so
# they stay unmatched until explicitly assigned a value. Any status value
# not matched by any field already falls back to IDLE regardless, so this
# has no effect unless a real code is explicitly assigned.
DEFAULT_HVAC_STATUS_IDLE_VALUES = str(MODE_VALUE_DISABLED)
DEFAULT_HVAC_STATUS_DRYING_VALUES = str(MODE_VALUE_DISABLED)
DEFAULT_HVAC_STATUS_FAN_VALUES = str(MODE_VALUE_DISABLED)
DEFAULT_HVAC_STATUS_PREHEATING_VALUES = str(MODE_VALUE_DISABLED)

# Target mode: single value written to preset_mode_address when that mode
# is selected.
CONF_PRESET_MODE_OFF_VALUE = "preset_mode_off_value"
CONF_PRESET_MODE_HEAT_VALUE = "preset_mode_heat_value"
CONF_PRESET_MODE_COOL_VALUE = "preset_mode_cool_value"
CONF_PRESET_MODE_HEAT_COOL_VALUE = "preset_mode_heat_cool_value"
CONF_PRESET_MODE_AUTO_VALUE = "preset_mode_auto_value"
CONF_PRESET_MODE_DRY_VALUE = "preset_mode_dry_value"
CONF_PRESET_MODE_FAN_ONLY_VALUE = "preset_mode_fan_only_value"

DEFAULT_PRESET_MODE_OFF_VALUE = 0
DEFAULT_PRESET_MODE_HEAT_VALUE = 1
DEFAULT_PRESET_MODE_COOL_VALUE = 2
DEFAULT_PRESET_MODE_HEAT_COOL_VALUE = 3
# Disabled by default: these modes are uncommon for a PLC-driven thermostat
# (auto is redundant with heat_cool; dry/fan_only rarely apply), so they stay
# hidden from the thermostat's mode list unless explicitly assigned a value.
DEFAULT_PRESET_MODE_AUTO_VALUE = MODE_VALUE_DISABLED
DEFAULT_PRESET_MODE_DRY_VALUE = MODE_VALUE_DISABLED
DEFAULT_PRESET_MODE_FAN_ONLY_VALUE = MODE_VALUE_DISABLED

# Climate control modes
CONTROL_MODE_DIRECT = "direct"
CONTROL_MODE_SETPOINT = "setpoint"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_PYS7_CONNECTION_TYPE = PYS7_CONNECTION_TYPE_PG  # PG as default
DEFAULT_SCAN_INTERVAL = 1  # seconds
DEFAULT_PULSE_DURATION = 0.5  # seconds
DEFAULT_OPERATE_TIME = 60  # seconds
DEFAULT_USE_STATE_TOPICS = False  # use operate_time by default
DEFAULT_REAL_PRECISION = 1
DEFAULT_MIN_TEMP = 7.0  # °C
DEFAULT_MAX_TEMP = 35.0  # °C
DEFAULT_TEMP_STEP = 0.5  # °C

CONF_OP_TIMEOUT = "operation_timeout"
CONF_MAX_RETRIES = "max_retries"
CONF_BACKOFF_INITIAL = "retry_backoff_initial"
CONF_BACKOFF_MAX = "retry_backoff_max"
CONF_OPTIMIZE_READ = "optimize_read"
CONF_ENABLE_WRITE_BATCHING = "enable_write_batching"
CONF_ENABLE_METRICS = "enable_metrics"

DEFAULT_OP_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_INITIAL = 0.5  # seconds
DEFAULT_BACKOFF_MAX = 2.0  # seconds
DEFAULT_OPTIMIZE_READ = True  # enabled by default for better performance
DEFAULT_ENABLE_WRITE_BATCHING = True  # enabled by default for better performance
DEFAULT_ENABLE_METRICS = False  # disabled by default to avoid overhead
