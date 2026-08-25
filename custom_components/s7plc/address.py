"""Helpers for S7 address parsing."""

from __future__ import annotations

import math
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import pyS7
from pyS7.address_parser import S7AddressError, map_address_to_tag
from pyS7.constants import DataType, MemoryArea
from pyS7.tag import S7Tag

__all__ = [
    "DataType",
    "MemoryArea",
    "S7Tag",
    "parse_tag",
    "get_numeric_limits",
    "is_time_data_type",
    "time_to_seconds",
    "seconds_to_time",
    "pyS7",
]

TIME_MIN_MILLISECONDS = -(2**31)
TIME_MAX_MILLISECONDS = 2**31 - 1
TIME_MIN_SECONDS = TIME_MIN_MILLISECONDS / 1000
TIME_MAX_SECONDS = TIME_MAX_MILLISECONDS / 1000


def is_time_data_type(data_type) -> bool:
    """Return whether *data_type* is the Siemens signed TIME type."""
    return data_type == getattr(DataType, "TIME", None)


def time_to_seconds(value: timedelta) -> float:
    """Convert the ``timedelta`` returned by pyS7 TIME reads to seconds."""
    if not isinstance(value, timedelta):
        raise TypeError(f"TIME value must be timedelta, got {type(value).__name__}")
    total_microseconds = (
        value.days * 86_400 + value.seconds
    ) * 1_000_000 + value.microseconds
    if total_microseconds % 1000:
        raise ValueError("TIME value does not have millisecond precision")
    milliseconds = total_microseconds // 1000
    if not TIME_MIN_MILLISECONDS <= milliseconds <= TIME_MAX_MILLISECONDS:
        raise ValueError("TIME value is outside the signed 32-bit range")
    return milliseconds / 1000


def seconds_to_time(value: float) -> timedelta:
    """Convert HA seconds to the millisecond-aligned type required by pyS7."""
    try:
        seconds = Decimal(str(value))
    except (InvalidOperation, ValueError) as err:
        raise ValueError("TIME value must be numeric") from err
    if not seconds.is_finite() or not math.isfinite(float(value)):
        raise ValueError("TIME value must be finite")
    milliseconds = int(
        (seconds * Decimal(1000)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    )
    if not TIME_MIN_MILLISECONDS <= milliseconds <= TIME_MAX_MILLISECONDS:
        raise ValueError("TIME value is outside the signed 32-bit range")
    return timedelta(milliseconds=milliseconds)


def parse_tag(address: str) -> S7Tag:
    """Parse an address into an ``S7Tag``.

    Raises ``ValueError`` if the address cannot be parsed. The returned tag
    always has the bit offset remapped when needed.
    """
    try:
        tag = map_address_to_tag(address)
    except S7AddressError as err:
        raise ValueError(f"Invalid address: {address}") from err

    return tag


def get_numeric_limits(data_type) -> tuple[float, float] | None:
    """Return the numeric limits for ``data_type`` when known.

    The limits correspond to the representable values for the main S7 numeric
    types. ``None`` is returned for types without explicit bounds (for example
    ``REAL``) or for unsupported data types.
    """

    byte = getattr(DataType, "BYTE", None)
    word = getattr(DataType, "WORD", None)
    dword = getattr(DataType, "DWORD", None)
    s_int = getattr(DataType, "INT", None)
    s_dint = getattr(DataType, "DINT", None)
    bit = getattr(DataType, "BIT", None)
    real = getattr(DataType, "REAL", None)
    lreal = getattr(DataType, "LREAL", None)
    usint = getattr(DataType, "USINT", None)
    sint = getattr(DataType, "SINT", None)
    time = getattr(DataType, "TIME", None)

    if data_type == byte:
        return (0.0, 255.0)
    if data_type == word:
        return (0.0, 65535.0)
    if data_type == dword:
        return (0.0, 4294967295.0)
    if data_type == s_int:
        return (-32768.0, 32767.0)
    if data_type == s_dint:
        return (-2147483648.0, 2147483647.0)
    if data_type == bit:
        return (0.0, 1.0)
    if data_type == usint:
        # ``USINT`` is an unsigned 8-bit integer: 0 … 255.
        return (0.0, 255.0)
    if data_type == sint:
        # ``SINT`` is a signed 8-bit integer: -128 … 127.
        return (-128.0, 127.0)
    if data_type == time:
        # Home Assistant represents TIME as seconds, not PLC milliseconds.
        return (TIME_MIN_SECONDS, TIME_MAX_SECONDS)
    if data_type == real:
        # ``REAL`` values are stored as 32-bit floating point numbers; we do not
        # impose an explicit limit so Home Assistant can expose any configured
        # range.
        return None
    if data_type == lreal:
        # ``LREAL`` values are stored as 64-bit floating point numbers; we do not
        # impose an explicit limit so Home Assistant can expose any configured
        # range.
        return None

    return None
