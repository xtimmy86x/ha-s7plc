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
    CONF_ENTITY_SYNC,
)

CONF_ADDRESS = "address"
CONF_AREA = "area"
CONF_SOURCE_ENTITY = "source_entity"
CONF_DEVICE_CLASS = "device_class"
CONF_INVERT_STATE = "invert_state"
CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_OPEN_COMMAND_ADDRESS = "open_command_address"
CONF_CLOSE_COMMAND_ADDRESS = "close_command_address"
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
CONF_VALUE_MULTIPLIER = "value_multiplier"
CONF_UNIT_OF_MEASUREMENT = "unit_of_measurement"
CONF_STATE_CLASS = "state_class"
CONF_REAL_PRECISION = "real_precision"
CONF_OPENING_STATE_ADDRESS = "opening_state_address"
CONF_CLOSING_STATE_ADDRESS = "closing_state_address"
CONF_OPERATE_TIME = "operate_time"
CONF_USE_STATE_TOPICS = "use_state_topics"
CONF_POSITION_STATE_ADDRESS = "position_state_address"
CONF_POSITION_COMMAND_ADDRESS = "position_command_address"
CONF_INVERT_POSITION = "invert_position"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_PYS7_CONNECTION_TYPE = PYS7_CONNECTION_TYPE_PG  # PG as default
DEFAULT_SCAN_INTERVAL = 1  # seconds
DEFAULT_BUTTON_PULSE = 0.5  # seconds
DEFAULT_PULSE_DURATION = 0.5  # seconds
DEFAULT_OPERATE_TIME = 60  # seconds
DEFAULT_USE_STATE_TOPICS = False  # use operate_time by default
DEFAULT_REAL_PRECISION = 1

CONF_OP_TIMEOUT = "operation_timeout"
CONF_MAX_RETRIES = "max_retries"
CONF_BACKOFF_INITIAL = "retry_backoff_initial"
CONF_BACKOFF_MAX = "retry_backoff_max"
CONF_OPTIMIZE_READ = "optimize_read"
CONF_ENABLE_WRITE_BATCHING = "enable_write_batching"

DEFAULT_OP_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_INITIAL = 0.5  # seconds
DEFAULT_BACKOFF_MAX = 2.0  # seconds
DEFAULT_OPTIMIZE_READ = True  # enabled by default for better performance
DEFAULT_ENABLE_WRITE_BATCHING = True  # enabled by default for better performance
