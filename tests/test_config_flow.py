from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest
import voluptuous as vol
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from custom_components.s7plc import config_flow, const


def make_config_entry(
    *,
    options=None,
    data=None,
    title="S7 PLC",
    unique_id="plc.local-0-1",
    entry_id="entry",
    domain=const.DOMAIN,
):
    return SimpleNamespace(
        options=options if options is not None else {},
        data=data or {},
        title=title,
        unique_id=unique_id,
        entry_id=entry_id,
        domain=domain,
    )


def run_flow(coro):
    result = asyncio.run(coro)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return result


def connection_data(**overrides):
    data = {
        CONF_NAME: "PLC",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT,
        const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        const.CONF_PYS7_CONNECTION_TYPE: const.DEFAULT_PYS7_CONNECTION_TYPE,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        const.CONF_OPTIMIZE_READ: const.DEFAULT_OPTIMIZE_READ,
        const.CONF_ENABLE_WRITE_BATCHING: const.DEFAULT_ENABLE_WRITE_BATCHING,
        const.CONF_ENABLE_METRICS: const.DEFAULT_ENABLE_METRICS,
    }
    data.update(overrides)
    return data


def install_connection_success(monkeypatch):
    async def ok(*args, **kwargs):
        return None

    monkeypatch.setattr(config_flow, "_test_plc_connection", ok)


def test_options_init_opens_connection_form_directly():
    flow = config_flow.S7PLCOptionsFlow(make_config_entry(data=connection_data()))
    flow.hass = HomeAssistant()
    result = run_flow(flow.async_step_init())
    assert result["type"] == "form"
    assert result["kwargs"]["step_id"] == "connection"


@pytest.mark.parametrize(
    "connection_type,step_id",
    [
        (const.CONNECTION_TYPE_RACK_SLOT, "rack_slot"),
        (const.CONNECTION_TYPE_TSAP, "tsap"),
    ],
)
def test_initial_config_flow_creates_connection(monkeypatch, connection_type, step_id):
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []
    install_connection_success(monkeypatch)
    first = run_flow(
        flow.async_step_user({const.CONF_CONNECTION_TYPE: connection_type})
    )
    assert first["kwargs"]["step_id"] == step_id
    user_input = connection_data()
    if connection_type == const.CONNECTION_TYPE_TSAP:
        user_input.pop(const.CONF_RACK)
        user_input.pop(const.CONF_SLOT)
        user_input[const.CONF_LOCAL_TSAP] = "01.00"
        user_input[const.CONF_REMOTE_TSAP] = "01.01"
    result = run_flow(getattr(flow, f"async_step_{step_id}")(user_input))
    assert result["type"] == "create_entry"
    assert result["kwargs"]["title"] == "PLC"
    assert result["kwargs"]["data"][const.CONF_CONNECTION_TYPE] == connection_type
    assert result["kwargs"]["data"][const.CONF_MANUAL_CONNECTION_CONTROL] is False


def test_initial_config_flow_enables_manual_connection_control(monkeypatch):
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []
    install_connection_success(monkeypatch)
    run_flow(
        flow.async_step_user(
            {const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT}
        )
    )

    result = run_flow(
        flow.async_step_rack_slot(
            connection_data(**{const.CONF_MANUAL_CONNECTION_CONTROL: True})
        )
    )

    assert result["type"] == "create_entry"
    assert result["kwargs"]["data"][const.CONF_MANUAL_CONNECTION_CONTROL] is True


def test_initial_config_flow_persists_logo_family_and_uses_verified_defaults():
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []
    result = run_flow(
        flow.async_step_user(
            {
                const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT,
                const.CONF_PLC_FAMILY: const.PLC_FAMILY_LOGO_0BA8,
            }
        )
    )
    assert result["kwargs"]["step_id"] == "rack_slot"
    defaults = result["kwargs"]["data_schema"]({CONF_HOST: "plc.local"})
    assert defaults[const.CONF_RACK] == 0
    assert defaults[const.CONF_SLOT] == 2


def test_initial_logo_0ba7_tsap_defaults_are_verified_values():
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []
    result = run_flow(
        flow.async_step_user(
            {
                const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_TSAP,
                const.CONF_PLC_FAMILY: const.PLC_FAMILY_LOGO_0BA7,
            }
        )
    )
    defaults = result["kwargs"]["data_schema"]({CONF_HOST: "plc.local"})
    assert defaults[const.CONF_LOCAL_TSAP] == "10.00"
    assert defaults[const.CONF_REMOTE_TSAP] == "10.01"


def test_initial_flow_rejects_logo_0ba7_rack_slot_combination():
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    result = run_flow(
        flow.async_step_user(
            {
                const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT,
                const.CONF_PLC_FAMILY: const.PLC_FAMILY_LOGO_0BA7,
            }
        )
    )
    assert result["kwargs"]["step_id"] == "user"
    assert result["kwargs"]["errors"] == {"base": "incompatible_family_connection"}


def test_options_family_fallback_and_connection_compatible_choices():
    legacy = config_flow.S7PLCOptionsFlow(make_config_entry(data=connection_data()))
    legacy.hass = HomeAssistant()
    result = run_flow(legacy.async_step_connection())
    schema = result["kwargs"]["data_schema"].schema
    family_marker = next(key for key in schema if key.schema == const.CONF_PLC_FAMILY)
    defaults = result["kwargs"]["data_schema"]({})
    assert defaults[const.CONF_PLC_FAMILY] == const.PLC_FAMILY_S7
    choices = schema[family_marker].config.options
    assert const.PLC_FAMILY_LOGO_0BA7 not in {choice["value"] for choice in choices}


def test_initial_config_flow_connection_error(monkeypatch):
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []

    async def fail(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(config_flow, "_test_plc_connection", fail)
    run_flow(
        flow.async_step_user(
            {const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_RACK_SLOT}
        )
    )
    result = run_flow(flow.async_step_rack_slot(connection_data()))
    assert (
        result["type"] == "form"
        and result["kwargs"]["errors"]["base"] == "cannot_connect"
    )


def test_options_connection_preserves_all_650_options_and_unknown_key(monkeypatch):
    options = {
        const.CONF_SENSORS: [{"name": "sensor"}],
        const.CONF_BINARY_SENSORS: [{"name": "binary"}],
        const.CONF_SWITCHES: [{"name": "switch"}],
        const.CONF_COVERS: [{"name": "cover"}],
        const.CONF_BUTTONS: [{"name": "button"}],
        const.CONF_LIGHTS: [{"name": "light"}],
        const.CONF_NUMBERS: [{"name": "number"}],
        const.CONF_TEXTS: [{"name": "text"}],
        const.CONF_CLIMATES: [{"name": "climate"}],
        const.CONF_ENTITY_SYNC: [{"name": "sync"}],
        "future_unknown_key": {"nested": [1, 2, 3]},
    }
    original = dict(options)
    entry = make_config_entry(
        options=options, data=connection_data(), unique_id="plc.local-0-1"
    )
    hass = HomeAssistant()
    hass.config_entries._entries.append(entry)
    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = hass
    install_connection_success(monkeypatch)
    updated = connection_data(
        **{CONF_NAME: "Updated", CONF_HOST: "new.local", const.CONF_SLOT: 2}
    )
    result = run_flow(flow.async_step_connection(updated))
    assert result["type"] == "create_entry"
    assert entry.options == original
    assert result["kwargs"]["data"] == original
    assert entry.title == "Updated"
    assert entry.unique_id == "new.local-0-2"


def test_legacy_entity_steps_are_not_reachable():
    legacy = (
        "setup_connection",
        "setup_entities",
        "manage_configuration",
        "add",
        "edit",
        "remove",
        "import",
        "export",
        "sensors",
        "binary_sensors",
        "switches",
        "covers",
        "covers_traditional",
        "covers_position",
        "buttons",
        "lights",
        "numbers",
        "texts",
        "climates",
        "climates_direct",
        "climates_setpoint",
        "entity_sync",
    )
    for step in legacy:
        assert not hasattr(config_flow.S7PLCOptionsFlow, f"async_step_{step}")


def test_config_flow_version_is_three():
    assert config_flow.S7PLCConfigFlow.VERSION == 3


def test_options_connection_handles_connection_failure(monkeypatch):
    entry = make_config_entry(
        data={
            CONF_NAME: "PLC Old",
            CONF_HOST: "old.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        options={},
        unique_id="old.local-0-1",
    )

    hass = HomeAssistant()
    hass.config_entries._entries.append(entry)

    flow = config_flow.S7PLCOptionsFlow(entry)
    flow.hass = HomeAssistant()

    class FailingCoordinator:
        def __init__(self, hass, **kwargs):
            self.hass = hass

        async def connect(self):
            raise OSError("boom")

        async def async_shutdown(self):
            return None

    monkeypatch.setattr(config_flow, "S7Coordinator", FailingCoordinator)

    user_input = {
        CONF_NAME: "PLC Updated",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
    }

    result = asyncio.run(flow.async_step_connection(user_input))

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "cannot_connect"
    assert entry.data[CONF_HOST] == "old.local"


def test_options_connection_detects_duplicate_unique_id(monkeypatch):
    primary = make_config_entry(
        data={
            CONF_NAME: "Primary",
            CONF_HOST: "old.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        entry_id="primary",
        unique_id="old.local-0-1",
    )
    other = make_config_entry(
        data={
            CONF_NAME: "Other",
            CONF_HOST: "plc.local",
            CONF_PORT: const.DEFAULT_PORT,
            const.CONF_RACK: const.DEFAULT_RACK,
            const.CONF_SLOT: const.DEFAULT_SLOT,
            CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
            const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
            const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
            const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
            const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
        },
        unique_id="plc.local-0-1",
        entry_id="other",
    )

    hass = HomeAssistant()
    hass.config_entries._entries.extend([primary, other])

    flow = config_flow.S7PLCOptionsFlow(primary)
    flow.hass = hass

    class FakeCoordinator:
        def __init__(self, hass, **kwargs):
            self.hass = hass

        async def connect(self):
            return None

        async def async_shutdown(self):
            return None

    monkeypatch.setattr(config_flow, "S7Coordinator", FakeCoordinator)

    user_input = {
        CONF_NAME: "Primary",
        CONF_HOST: "plc.local",
        CONF_PORT: const.DEFAULT_PORT,
        const.CONF_RACK: const.DEFAULT_RACK,
        const.CONF_SLOT: const.DEFAULT_SLOT,
        CONF_SCAN_INTERVAL: const.DEFAULT_SCAN_INTERVAL,
        const.CONF_OP_TIMEOUT: const.DEFAULT_OP_TIMEOUT,
        const.CONF_MAX_RETRIES: const.DEFAULT_MAX_RETRIES,
        const.CONF_BACKOFF_INITIAL: const.DEFAULT_BACKOFF_INITIAL,
        const.CONF_BACKOFF_MAX: const.DEFAULT_BACKOFF_MAX,
    }

    result = asyncio.run(flow.async_step_connection(user_input))

    assert result["type"] == "form"
    assert result["kwargs"]["errors"]["base"] == "already_configured"


@pytest.fixture(
    params=["initial-rack_slot", "initial-tsap", "options-rack_slot", "options-tsap"]
)
def connection_schema(request):
    """Return the actual schema shown by each supported connection form."""
    stage, connection_type = request.param.split("-", 1)
    if stage == "initial":
        flow = config_flow.S7PLCConfigFlow()
        flow.hass = HomeAssistant()
        flow._discovered_hosts = []
        result = run_flow(
            flow.async_step_user({const.CONF_CONNECTION_TYPE: connection_type})
        )
    else:
        flow = config_flow.S7PLCOptionsFlow(
            make_config_entry(
                data=connection_data(**{const.CONF_CONNECTION_TYPE: connection_type})
            )
        )
        flow.hass = HomeAssistant()
        result = run_flow(flow.async_step_connection())
    return result["kwargs"]["data_schema"]


# These rules belong to voluptuous, not the pass-through HA selector doubles.
_CONNECTION_SCHEMA_RANGES = [
    (CONF_SCAN_INTERVAL, 0.05, 3600, float),
    (const.CONF_OP_TIMEOUT, 0.5, 120, float),
    (const.CONF_MAX_RETRIES, 0, 10, int),
    (const.CONF_BACKOFF_INITIAL, 0.1, 30, float),
    (const.CONF_BACKOFF_MAX, 0.1, 120, float),
]


def test_connection_schema_applies_defaults_and_coerces_boundaries(connection_schema):
    submitted = {CONF_HOST: "plc.local"}
    validated = connection_schema(submitted)
    assert submitted == {CONF_HOST: "plc.local"}
    assert validated[CONF_PORT] == const.DEFAULT_PORT
    assert validated[const.CONF_OP_TIMEOUT] == const.DEFAULT_OP_TIMEOUT
    assert (
        validated[const.CONF_ENABLE_WRITE_BATCHING]
        is const.DEFAULT_ENABLE_WRITE_BATCHING
    )
    for field, minimum, maximum, value_type in _CONNECTION_SCHEMA_RANGES:
        for boundary in (minimum, maximum):
            validated = connection_schema({**submitted, field: str(boundary)})
            assert validated[field] == boundary, (field, boundary)
            assert type(validated[field]) is value_type, (field, boundary)


def test_connection_schema_rejects_invalid_fields(connection_schema):
    invalid_fields = [
        (CONF_NAME, 123),
        (CONF_PORT, "102"),  # This field uses int, not Coerce(int).
        (const.CONF_ENABLE_WRITE_BATCHING, "false"),
        ("unexpected_field", True),
    ]
    for field, minimum, maximum, _ in _CONNECTION_SCHEMA_RANGES:
        invalid_fields.extend(
            (field, value) for value in (minimum - 1, maximum + 1, "invalid")
        )
    for field, value in invalid_fields:
        with pytest.raises(vol.Invalid) as exc:
            connection_schema({CONF_HOST: "plc.local", field: value})
        assert exc.value.path == [field], (field, value)


@pytest.mark.parametrize("step", ["rack_slot", "tsap"])
def test_initial_connection_schema_requires_host(step):
    flow = config_flow.S7PLCConfigFlow()
    flow.hass = HomeAssistant()
    flow._discovered_hosts = []
    result = run_flow(getattr(flow, f"async_step_{step}")())
    with pytest.raises(vol.Invalid) as exc:
        result["kwargs"]["data_schema"]({})
    assert exc.value.path == [CONF_HOST]
