DOMAIN = "s7plc"
PLATFORMS = ["binary_sensor", "sensor", "switch", "light"]

CONF_NAME = "name"
CONF_HOST = "host"
CONF_RACK = "rack"
CONF_SLOT = "slot"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"

CONF_SENSORS = "sensors"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_SWITCHES = "switches"
CONF_LIGHTS = "lights"

CONF_STATE_ADDRESS = "state_address"
CONF_COMMAND_ADDRESS = "command_address"
CONF_SYNC_STATE = "sync_state"

DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 1
DEFAULT_SCAN_INTERVAL = 1  # seconds