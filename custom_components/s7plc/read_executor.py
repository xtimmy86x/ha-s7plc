"""Execute read plans through the coordinator's managed transport."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pyS7.errors import S7CommunicationError, S7ConnectionError, S7ReadResponseError

from .address import DataType, MemoryArea, S7Tag
from .plans import StringPlan, TagPlan, apply_postprocess

_LOGGER = logging.getLogger(__name__)


class S7ReadError(Exception):
    """A planned string read failed or its cooperative deadline expired."""


class S7ReadExecutor:
    """Execute scalar and string reads for one PLC without owning its client.

    The supplied read callback owns retry and resolves the current client on
    each attempt. Calls run within the connection manager's operation scope;
    this executor creates no tasks, connections, caches or lifecycle barriers.
    The coordinator supplies the cycle deadline and its monotonic clock, and
    translates S7ReadError into its framework's update error. This executor
    does not handle lifecycle errors or cancellations.
    """

    def __init__(
        self,
        *,
        read_tags: Callable[[list[S7Tag]], Awaitable[list[Any]]],
        optimize_read: bool,
        op_timeout: float,
        monotonic: Callable[[], float],
    ) -> None:
        self._read_tags = read_tags
        self._optimize_read = optimize_read
        self._op_timeout = op_timeout
        self._monotonic = monotonic

    async def read_s7_string(
        self, db: int, start: int, length: int, is_wstring: bool = False
    ) -> str:
        """Read S7 STRING or WSTRING from PLC memory.

        Handles both STRING (Latin-1, max 254 chars)
        and WSTRING (UTF-16, max 16382 chars).

        Note:
            pyS7 handles all string parsing, decoding, and chunking automatically.

        Args:
            db: Data block number
            start: Starting byte address in the data block
            length: Maximum length of the string as declared in PLC
            is_wstring: True for WSTRING (UTF-16), False for STRING (Latin-1)

        Returns:
            Decoded string content
        """
        data_type = DataType.WSTRING if is_wstring else DataType.STRING
        # Use the length declared in the tag (e.g., S308.50 -> length=50)
        tag = S7Tag(MemoryArea.DB, db, data_type, start, 0, length)

        # pyS7 handles header parsing, data reading, and decoding
        result = await self._read_tags([tag])
        value = result[0]

        _LOGGER.debug(
            "Read S7 %s DB%d.%d value=%s optimize=%s",
            "WSTRING" if is_wstring else "STRING",
            db,
            start,
            repr(value[:50] if len(value) > 50 else value) if value else value,
            self._optimize_read,
        )

        return value if isinstance(value, str) else str(value)

    def _tag_key(self, tag: S7Tag) -> tuple[Any, ...]:
        """Generate a unique key for tag deduplication.

        Args:
            tag: S7Tag instance to generate key for

        Returns:
            Tuple of tag attributes that uniquely identify it
        """
        return (
            tag.memory_area,
            tag.db_number,
            tag.data_type,
            tag.start,
            tag.bit_offset,
            tag.length,
        )

    async def read_batch(self, plans_batch: list[TagPlan]) -> dict[str, Any]:
        """Read scalar tags in batch handling deduplication and post-processing.

        Args:
            plans_batch: List of TagPlan objects for scalar reads

        Returns:
            Dictionary mapping topic names to their read values

        Raises:
            OSError, RuntimeError, S7 errors: On communication failures
        """
        results: dict[str, Any] = {}
        if not plans_batch:
            return results

        groups: dict[tuple, list[TagPlan]] = {}
        order: list[tuple] = []
        for plan in plans_batch:
            k = self._tag_key(plan.tag)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(plan)

        try:
            tags = [groups[k][0].tag for k in order]
            # Changed in pyS7 1.5.0 optimized=True by default
            values = await self._read_tags(tags)
            _LOGGER.debug(
                "Batch read %d tags optimize=%s", len(tags), self._optimize_read
            )
            for k, v in zip(order, values):
                for plan in groups[k]:
                    results[plan.topic] = plan.postprocess(v) if plan.postprocess else v
        except (OSError, RuntimeError) as err:
            _LOGGER.error("Batch read failed for %d tags: %s", len(plans_batch), err)
            raise
        except (
            S7CommunicationError,
            S7ConnectionError,
            S7ReadResponseError,
        ) as err:
            _LOGGER.error(
                "S7 communication error during batch read of %d tags: %s",
                len(plans_batch),
                err,
            )
            raise
        return results

    async def read_strings(
        self, plans_str: list[StringPlan], deadline: float
    ) -> dict[str, Any]:
        """Read strings respecting an absolute deadline.

        Args:
            plans_str: List of StringPlan objects for string reads
            deadline: Absolute monotonic timestamp to stop reading

        Returns:
            Dictionary mapping topic names to their string values

        Raises:
            S7ReadError: On timeout or communication failures
        """
        results: dict[str, Any] = {}
        for plan in plans_str:
            if self._monotonic() > deadline:
                _LOGGER.warning("String read timeout reached (%.2fs)", self._op_timeout)
                raise S7ReadError(
                    f"String read timeout reached ({self._op_timeout:.2f}s)"
                )
            try:
                results[plan.topic] = await self.read_s7_string(
                    plan.db, plan.start, plan.length, plan.is_wstring
                )
            except (
                S7CommunicationError,
                S7ConnectionError,
                S7ReadResponseError,
            ) as err:
                _LOGGER.error(
                    "String read error: "
                    "S7 communication error reading %s (DB%d.%d): %s",
                    plan.topic,
                    plan.db,
                    plan.start,
                    err,
                )
                raise S7ReadError(
                    f"S7 error reading string {plan.topic}: {err}"
                ) from err
            except (OSError, RuntimeError) as err:
                _LOGGER.error(
                    "String read error: Network/runtime error reading %s (DB%d.%d): %s",
                    plan.topic,
                    plan.db,
                    plan.start,
                    err,
                )
                raise S7ReadError(f"Error reading string {plan.topic}: {err}") from err
        return results

    async def read_one(self, tag: S7Tag, address: str) -> Any:
        """Read an already parsed tag using the existing datatype normalization."""
        # Handle STRING types (CHAR array, STRING, WSTRING)
        if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
            return await self.read_s7_string(
                tag.db_number, tag.start, tag.length, is_wstring=False
            )
        elif tag.data_type == DataType.STRING:
            return await self.read_s7_string(
                tag.db_number, tag.start, tag.length, is_wstring=False
            )
        elif tag.data_type == DataType.WSTRING:
            return await self.read_s7_string(
                tag.db_number, tag.start, tag.length, is_wstring=True
            )

        # Changed in pyS7 1.5.0 optimized=True by default
        value = (await self._read_tags([tag]))[0]
        _LOGGER.debug("Read single tag %s optimize=%s", address, self._optimize_read)
        # Normalize BIT to bool
        if tag.data_type == DataType.BIT:
            return bool(value)
        return apply_postprocess(tag.data_type, value)
