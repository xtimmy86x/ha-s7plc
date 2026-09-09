"""Driver-controlled retry fixture and shared coordinator entry points."""

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest_asyncio

from custom_components.s7plc.coordinator import S7Coordinator


@pytest_asyncio.fixture
async def rig(fake_hass):
    """Keep managed I/O and reconnect real; control only the driver and delays."""
    coord = S7Coordinator(
        fake_hass,
        "plc.local",
        max_retries=0,
        backoff_initial=0.125,
        backoff_max=0.3,
    )
    events = []
    io_errors = deque()
    connect_errors = deque()
    client = SimpleNamespace(is_connected=True)

    async def connect():
        events.append("connect")
        if connect_errors:
            raise connect_errors.popleft()
        client.is_connected = True

    async def disconnect():
        events.append("disconnect")
        client.is_connected = False

    async def io(operation):
        assert client.is_connected, "I/O must follow a completed handshake"
        events.append(operation)
        if io_errors:
            raise io_errors.popleft()

    async def read(*args, **kwargs):
        await io("read")
        return [7]

    async def write(*args, **kwargs):
        await io("write")

    async def probe():
        await io("probe")
        return {}

    async def sleep(seconds):
        events.append(("sleep", seconds))

    client.connect = AsyncMock(side_effect=connect)
    client.disconnect = AsyncMock(side_effect=disconnect)
    client.read = AsyncMock(side_effect=read)
    client.write = AsyncMock(side_effect=write)
    client.get_cpu_info = AsyncMock(side_effect=probe)
    coord._connection.client = client
    coord._connection.sleep = sleep
    try:
        yield SimpleNamespace(
            coord=coord,
            client=client,
            events=events,
            io_errors=io_errors,
            connect_errors=connect_errors,
        )
    finally:
        await coord.async_shutdown()


def assert_no_operations(coord):
    """Each attempted operation must release its managed ownership scope."""
    assert not coord._connection._io_tasks
    assert not coord._connection._io_completions
    assert coord._connection._connect_task is None


async def invoke(coord, operation):
    """Exercise entry points through the real executor and retry layer."""
    if operation == "write":
        return await coord.write("DB1,W0", 7)
    if operation == "write_multi":
        return await coord.write_multi([("DB1,W0", 7)])
    if operation == "read_one":
        return await coord._read_one("DB1,W0")
    address = "DB1,S0.12" if operation == "string_poll" else "DB1,W0"
    await coord.add_item("value", address)
    return await coord._async_update_data()
