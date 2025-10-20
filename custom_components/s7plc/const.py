DOMAIN = "s7plc"
PLATFORMS = ["binary_sensor", "sensor", "switch", "light", "button", "number"]

CONF_RACK = "rack"
CONF_SLOT = "slot"

CONF_SENSORS = "sensors"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_SWITCHES = "switches"
CONF_LIGHTS = "lights"
CONF_NUMBERS = "numbers"
CONF_BUTTONS = "buttons"

CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"
CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_SYNC_STATE = "sync_state"
CONF_BUTTON_PULSE = "button_pulse"
CONF_MIN_VALUE = "min_value"
CONF_MAX_VALUE = "max_value"
CONF_STEP = "step"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_SCAN_INTERVAL = 1  # seconds
DEFAULT_BUTTON_PULSE = 1  # seconds

CONF_OP_TIMEOUT = "operation_timeout"
CONF_MAX_RETRIES = "max_retries"
CONF_BACKOFF_INITIAL = "retry_backoff_initial"
CONF_BACKOFF_MAX = "retry_backoff_max"

DEFAULT_OP_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_INITIAL = 0.5  # seconds
DEFAULT_BACKOFF_MAX = 2.0  # seconds
