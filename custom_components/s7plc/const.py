DOMAIN = "s7plc"
PLATFORMS = [
    "binary_sensor",
    "sensor",
    "switch",
    "cover",
    "light",
    "button",
    "number",
]

CONF_RACK = "rack"
CONF_SLOT = "slot"
CONF_CONNECTION_TYPE = "connection_type"
CONF_LOCAL_TSAP = "local_tsap"
CONF_REMOTE_TSAP = "remote_tsap"

CONNECTION_TYPE_RACK_SLOT = "rack_slot"
CONNECTION_TYPE_TSAP = "tsap"

CONF_SENSORS = "sensors"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_SWITCHES = "switches"
CONF_COVERS = "covers"
CONF_LIGHTS = "lights"
CONF_NUMBERS = "numbers"
CONF_BUTTONS = "buttons"
CONF_WRITERS = "writers"

OPTION_KEYS = (
    CONF_SENSORS,
    CONF_BINARY_SENSORS,
    CONF_SWITCHES,
    CONF_COVERS,
    CONF_LIGHTS,
    CONF_BUTTONS,
    CONF_NUMBERS,
    CONF_WRITERS,
)

CONF_ADDRESS = "address"
CONF_SOURCE_ENTITY = "source_entity"
CONF_DEVICE_CLASS = "device_class"
CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_OPEN_COMMAND_ADDRESS = "open_command_address"
CONF_CLOSE_COMMAND_ADDRESS = "close_command_address"
CONF_SYNC_STATE = "sync_state"
CONF_BUTTON_PULSE = "button_pulse"
CONF_MIN_VALUE = "min_value"
CONF_MAX_VALUE = "max_value"
CONF_STEP = "step"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_VALUE_MULTIPLIER = "value_multiplier"
CONF_UNIT_OF_MEASUREMENT = "unit_of_measurement"
CONF_STATE_CLASS = "state_class"
CONF_REAL_PRECISION = "real_precision"
CONF_OPENING_STATE_ADDRESS = "opening_state_address"
CONF_CLOSING_STATE_ADDRESS = "closing_state_address"
CONF_OPERATE_TIME = "operate_time"
CONF_USE_STATE_TOPICS = "use_state_topics"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_SCAN_INTERVAL = 1  # seconds
DEFAULT_BUTTON_PULSE = 1  # seconds
DEFAULT_OPERATE_TIME = 60  # seconds
DEFAULT_USE_STATE_TOPICS = False  # use operate_time by default
DEFAULT_REAL_PRECISION = 1

CONF_OP_TIMEOUT = "operation_timeout"
CONF_MAX_RETRIES = "max_retries"
CONF_BACKOFF_INITIAL = "retry_backoff_initial"
CONF_BACKOFF_MAX = "retry_backoff_max"
CONF_OPTIMIZE_READ = "optimize_read"

DEFAULT_OP_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_INITIAL = 0.5  # seconds
DEFAULT_BACKOFF_MAX = 2.0  # seconds
DEFAULT_OPTIMIZE_READ = True  # enabled by default for better performance
