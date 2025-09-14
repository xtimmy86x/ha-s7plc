DOMAIN = "s7plc"
PLATFORMS = ["binary_sensor", "sensor", "switch", "light", "button"]

CONF_RACK = "rack"
CONF_SLOT = "slot"

CONF_SENSORS = "sensors"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_SWITCHES = "switches"
CONF_LIGHTS = "lights"
CONF_BUTTONS = "buttons"

CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"
CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_SYNC_STATE = "sync_state"
CONF_BUTTON_PULSE = "button_pulse"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_SCAN_INTERVAL = 1  # seconds
DEFAULT_BUTTON_PULSE = 1  # seconds
