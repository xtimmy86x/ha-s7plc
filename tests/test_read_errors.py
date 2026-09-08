"""Preserve the HA error contract at the read executor/adapter boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyS7.errors import S7CommunicationError, S7ConnectionError, S7ReadResponseError

from custom_components.s7plc.coordinator import S7Coordinator
from custom_components.s7plc.plans import StringPlan
from custom_components.s7plc.read_executor import S7ReadError, S7ReadExecutor

pytestmark = pytest.mark.asyncio


@pytest.fixture
def reader(fake_hass):
    coord = S7Coordinator(fake_hass, "plc.local", op_timeout=0.5)
    coord._connection.client = SimpleNamespace(
        is_connected=True, disconnect=AsyncMock()
    )
    return coord


@pytest.mark.parametrize("address", ["DB1,S0.12", "DB1,WS0.12"])
@pytest.mark.parametrize(
    ("error_type", "prefix"),
    [
        (OSError, "Error"),
        (RuntimeError, "Error"),
        (S7CommunicationError, "S7 error"),
        (S7ConnectionError, "S7 error"),
        (S7ReadResponseError, "S7 error"),
    ],
)
async def test_string_poll_preserves_error_message_cause_and_cache(
    reader, address, error_type, prefix
):
    """A reader failure must not enter the generic error/disconnect fallback."""
    await reader.add_item("label", address)
    reader._data_cache = {"label": "previous"}
    due = dict(reader._item_next_read)
    failure = error_type("PLC reply failed")
    # The transport/retry layer is covered elsewhere. Supply its final failure
    # here to exercise each reader error branch and the real HA poll adapter.
    reader._read_executor._read_tags = AsyncMock(side_effect=failure)

    with pytest.raises(UpdateFailed) as caught:
        await reader._async_update_data()

    assert type(caught.value) is UpdateFailed
    assert str(caught.value) == f"{prefix} reading string label: PLC reply failed"
    assert caught.value.__cause__ is failure
    assert reader._data_cache == {"label": "previous"}
    assert reader._item_next_read == due
    assert reader.get_topic_read_revision("label") == 0
    assert reader.last_health_ok is False
    reader._read_executor._read_tags.assert_awaited_once()
    reader._connection.client.disconnect.assert_not_awaited()
    assert not reader._connection._io_tasks


@pytest.mark.parametrize(
    ("error_type", "prefix"),
    [
        (OSError, "Error"),
        (RuntimeError, "Error"),
        (S7CommunicationError, "S7 error"),
        (S7ConnectionError, "S7 error"),
        (S7ReadResponseError, "S7 error"),
    ],
)
async def test_executor_exposes_domain_error_with_original_cause(error_type, prefix):
    failure = error_type("PLC reply failed")
    executor = S7ReadExecutor(
        read_tags=AsyncMock(side_effect=failure),
        optimize_read=True,
        op_timeout=0.5,
        monotonic=lambda: 0.0,
    )

    with pytest.raises(S7ReadError) as caught:
        await executor.read_strings([StringPlan("label", 1, 0, 12)], deadline=0.5)

    assert type(caught.value) is S7ReadError
    assert str(caught.value) == f"{prefix} reading string label: PLC reply failed"
    assert caught.value.__cause__ is failure


async def test_executor_deadline_uses_domain_error_without_driver_call():
    read_tags = AsyncMock()
    executor = S7ReadExecutor(
        read_tags=read_tags,
        optimize_read=True,
        op_timeout=0.5,
        monotonic=lambda: 1.0,
    )

    with pytest.raises(S7ReadError) as caught:
        await executor.read_strings([StringPlan("label", 1, 0, 12)], deadline=0.5)

    assert str(caught.value) == "String read timeout reached (0.50s)"
    assert caught.value.__cause__ is None
    read_tags.assert_not_awaited()


@pytest.mark.parametrize("address", ["DB1,S0.12", "DB1,WS0.12"])
async def test_string_deadline_preserves_public_error_without_io(reader, address):
    await reader.add_item("label", address)
    reader._data_cache = {"label": "previous"}
    reader._read_executor._monotonic = lambda: float("inf")
    reader._read_executor._read_tags = AsyncMock()

    with pytest.raises(UpdateFailed) as caught:
        await reader._async_update_data()

    assert str(caught.value) == "String read timeout reached (0.50s)"
    assert caught.value.__cause__ is None
    assert reader._data_cache == {"label": "previous"}
    assert reader.get_topic_read_revision("label") == 0
    assert reader.last_health_ok is False
    reader._read_executor._read_tags.assert_not_awaited()
    reader._connection.client.disconnect.assert_not_awaited()
