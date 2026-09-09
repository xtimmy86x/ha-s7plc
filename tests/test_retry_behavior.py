"""Retry policy and error cleanup contracts across coordinator entry points."""

import logging
import struct

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyS7.errors import S7CommunicationError, S7ConnectionError, S7ReadResponseError
from support.retry import assert_no_operations, invoke
from support.retry import rig as rig  # noqa: PLC0414 - expose the shared pytest fixture

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("error_type", "max_retries", "succeeds", "category"),
    [
        pytest.param(RuntimeError, 1, True, "runtime", id="sync-success"),
        pytest.param(RuntimeError, 1, False, "runtime", id="sync-exhausted"),
        pytest.param(struct.error, 0, False, "data_parsing", id="sync-struct-error"),
    ],
)
async def test_retry_supports_synchronous_callbacks(
    rig, error_type, max_retries, succeeds, category
):
    """Retain the synchronous callback contracts from test_coordinator.py."""
    rig.coord._max_retries = max_retries
    failure = error_type("failure")
    calls = 0

    def callback():
        nonlocal calls
        calls += 1
        rig.events.append("call")
        if succeeds and calls == 2:
            return "ok"
        raise failure

    if succeeds:
        assert await rig.coord._retry(callback) == "ok"
        assert rig.coord.error_count_by_category == {}
    else:
        with pytest.raises(RuntimeError) as caught:
            await rig.coord._retry(callback)
        assert caught.value.__cause__ is failure
        assert rig.coord.error_count_by_category == {category: 1}

    assert calls == max_retries + 1
    expected = ["call", "disconnect"]
    if max_retries:
        expected.extend([("sleep", 0.125), "connect", "call"])
        if not succeeds:
            expected.append("disconnect")
    assert rig.events == expected
    assert_no_operations(rig.coord)


@pytest.mark.parametrize(
    ("error_type", "category"),
    [
        (S7CommunicationError, "s7_communication"),
        (S7ConnectionError, "s7_communication"),
        (S7ReadResponseError, "s7_response"),
        (OSError, "network"),
        (struct.error, "data_parsing"),
        (IndexError, "unexpected_response"),
        (RuntimeError, "runtime"),
    ],
)
async def test_retry_exhaustion_preserves_category_cause_and_attempt_order(
    rig, error_type, category
):
    rig.coord._max_retries = 1
    last_error = error_type("final failure")
    rig.io_errors.extend([OSError("first failure"), last_error])

    with pytest.raises(RuntimeError) as caught:
        await rig.coord._retry(rig.client.read, ["tag"], optimize=True)

    assert str(caught.value) == (
        f"Operation failed after 2 attempts ({category}): final failure"
    )
    assert caught.value.__cause__ is last_error
    assert rig.events == [
        "read",
        "disconnect",
        ("sleep", 0.125),
        "connect",
        "read",
        "disconnect",
    ]
    assert rig.client.read.await_count == 2
    rig.client.read.assert_awaited_with(["tag"], optimize=True)
    assert rig.coord.last_error_category == category
    assert rig.coord.last_error_message == "final failure"
    assert rig.coord.error_count_by_category == {category: 1}
    assert_no_operations(rig.coord)


async def test_success_on_last_attempt_caps_backoff_and_skips_terminal_sleep(rig):
    rig.coord._max_retries = 4
    rig.io_errors.extend(OSError("transient") for _ in range(4))

    assert await rig.coord.write("DB1,W0", 7) is True

    expected = []
    for delay in (0.125, 0.25, 0.3, 0.3):
        expected.extend(["write", "disconnect", ("sleep", delay), "connect"])
    assert rig.events == [*expected, "write"]
    assert rig.coord.error_count_by_category == {}
    assert rig.coord.last_error_category is None
    assert_no_operations(rig.coord)


async def test_non_retryable_error_escapes_retry_unchanged(rig):
    failure = ValueError("invalid driver result")
    rig.io_errors.append(failure)
    rig.coord._max_retries = 3

    with pytest.raises(ValueError) as caught:
        await rig.coord._retry(rig.client.read, [])

    assert caught.value is failure
    assert rig.events == ["read"]
    assert rig.coord.error_count_by_category == {}
    assert_no_operations(rig.coord)


OPERATIONS = ["write", "write_multi", "read_one", "scalar_poll", "string_poll"]


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_initial_handshake_failure_is_outside_retry_budget(rig, operation):
    rig.coord._max_retries = 3
    rig.client.is_connected = False
    failure = OSError("offline")
    rig.connect_errors.append(failure)

    if operation in ("write", "write_multi"):
        result = await invoke(rig.coord, operation)
        assert result == (False if operation == "write" else {"DB1,W0": False})
    else:
        expected = RuntimeError if operation == "read_one" else UpdateFailed
        with pytest.raises(expected) as caught:
            await invoke(rig.coord, operation)
        assert caught.value.__cause__.__cause__ is failure

    # The handshake already closed this failed session successfully.
    assert rig.events == ["connect", "disconnect"]
    assert rig.coord.last_error_category is None
    assert rig.coord.error_count_by_category == {}
    assert_no_operations(rig.coord)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_exhausted_io_closes_the_failed_session_once(rig, operation):
    failure = OSError("offline")
    rig.io_errors.append(failure)

    if operation in ("write", "write_multi"):
        result = await invoke(rig.coord, operation)
        assert result == (False if operation == "write" else {"DB1,W0": False})
    else:
        expected = RuntimeError if operation == "read_one" else UpdateFailed
        with pytest.raises(expected) as caught:
            await invoke(rig.coord, operation)
        assert caught.value.__cause__.__cause__ is failure

    driver_call = "write" if operation in ("write", "write_multi") else "read"
    assert rig.events == [driver_call, "disconnect"]
    assert rig.coord.last_error_category == "network"
    assert rig.coord.error_count_by_category == {"network": 1}
    assert_no_operations(rig.coord)


async def test_reconnect_failure_within_retry_consumes_remaining_attempt(rig):
    rig.coord._max_retries = 1
    rig.io_errors.append(OSError("write failed"))
    rig.connect_errors.append(OSError("reconnect failed"))

    assert await rig.coord.write("DB1,W0", 7) is False

    assert rig.events == [
        "write",
        "disconnect",
        ("sleep", 0.125),
        "connect",
        "disconnect",
    ]
    rig.client.write.assert_awaited_once()
    assert rig.coord.last_error_category == "runtime"
    assert rig.coord.last_error_message == (
        "Connection to PLC plc.local failed: reconnect failed"
    )
    assert rig.coord.error_count_by_category == {"runtime": 1}
    assert_no_operations(rig.coord)


async def test_diagnostics_count_failed_operations_and_clear_only_after_poll(rig):
    for expected_count in (1, 2):
        rig.io_errors.append(OSError("offline"))
        assert await rig.coord.write("DB1,W0", 7) is False
        assert rig.coord.error_count_by_category == {"network": expected_count}

    assert await rig.coord.write("DB1,W0", 7) is True
    assert rig.coord.last_error_category == "network"
    assert rig.coord.last_error_message == "offline"
    assert await invoke(rig.coord, "scalar_poll") == {"value": 7}
    assert rig.coord.last_error_category is None
    assert rig.coord.last_error_message is None
    assert rig.coord.error_count_by_category == {"network": 2}
    assert_no_operations(rig.coord)


@pytest.mark.parametrize("during_connect", [False, True])
async def test_health_check_reports_failure_without_entering_retry(rig, during_connect):
    rig.coord._max_retries = 3
    if during_connect:
        rig.client.is_connected = False
        rig.connect_errors.append(OSError("offline"))
    else:
        rig.io_errors.append(OSError("offline"))

    result = await rig.coord.async_health_check()

    assert result["ok"] is False
    assert result["error"] == (
        "Connection to PLC plc.local failed: offline"
        if during_connect
        else "CPU info probe failed: offline"
    )
    assert rig.events == (["connect", "disconnect"] if during_connect else ["probe"])
    assert rig.coord.last_health_ok is False
    assert rig.coord.last_error_category is None
    assert rig.coord.error_count_by_category == {}
    assert_no_operations(rig.coord)


@pytest.mark.parametrize(
    ("failure", "level", "message", "with_traceback"),
    [
        (
            S7CommunicationError("offline"),
            logging.DEBUG,
            "S7 communication error on attempt 1/1: offline",
            False,
        ),
        (
            S7ConnectionError("offline"),
            logging.DEBUG,
            "S7 communication error on attempt 1/1: offline",
            False,
        ),
        (
            S7ReadResponseError("bad reply"),
            logging.DEBUG,
            "S7 response error on attempt 1/1: bad reply",
            False,
        ),
        (
            OSError(5, "offline"),
            logging.DEBUG,
            "Network error on attempt 1/1: [Errno 5] offline (errno: 5)",
            False,
        ),
        (
            struct.error("bad data"),
            logging.WARNING,
            "Data parsing error on attempt 1/1: bad data (check PLC data type)",
            False,
        ),
        (
            IndexError("missing data"),
            logging.WARNING,
            "Unexpected response size on attempt 1/1: missing data",
            True,
        ),
        (
            RuntimeError("failure"),
            logging.DEBUG,
            "Runtime error on attempt 1/1: failure",
            False,
        ),
    ],
)
async def test_retry_preserves_log_message_level_and_traceback(
    rig, caplog, failure, level, message, with_traceback
):
    """Consolidating retry handling must preserve troubleshooting details."""
    rig.io_errors.append(failure)
    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.s7plc.coordinator"),
        pytest.raises(RuntimeError),
    ):
        await rig.coord._retry(rig.client.read, [])

    records = [
        record
        for record in caplog.records
        if record.name == "custom_components.s7plc.coordinator"
    ]
    assert len(records) == 2
    attempt, exhausted = records
    assert attempt.getMessage() == message
    assert attempt.levelno == level
    if with_traceback:
        assert attempt.exc_info[1] is failure
    else:
        assert not attempt.exc_info
    assert exhausted.levelno == logging.ERROR
    assert exhausted.getMessage() == (
        f"Operation failed after 1 attempts (category: "
        f"{rig.coord.last_error_category}): {failure}"
    )
    assert_no_operations(rig.coord)
