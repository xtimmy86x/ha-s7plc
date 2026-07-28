"""Helpers for S7 address parsing."""

from __future__ import annotations

import re

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
    "parse_address_and_scale",
    "format_address_with_scale",
    "pyS7",
]

# Inline scaling suffix: "<address> Scale(raw_min,raw_max,scale_min,scale_max)".
# An alternative to filling in the separate raw/scale range fields. Numbers
# use "." for decimals (not ","), since "," already separates the four
# arguments.
_SCALE_SUFFIX_RE = re.compile(
    r"^(?P<address>.*\S)\s+[Ss]cale\(\s*"
    r"(?P<raw_min>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<raw_max>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<scale_min>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<scale_max>-?\d+(?:\.\d+)?)\s*"
    r"\)\s*$"
)


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


def parse_address_and_scale(
    raw: str | None,
) -> tuple[str | None, tuple[float, float, float, float] | None]:
    """Split an optional inline ``Scale(...)`` suffix off an address string.

    Lets scaling be configured directly in the address field, e.g.
    ``"DB6,B23 Scale(0,1,0,10)"``, as an alternative to the separate raw/
    scale range fields (raw 0..1 maps to engineering 0..10).

    Returns ``(address, None)`` unchanged when no ``Scale(...)`` suffix is
    present, so plain addresses behave exactly as before. Returns
    ``(address, (raw_min, raw_max, scale_min, scale_max))`` when a valid
    suffix is found. Raises ``ValueError`` if the input contains "scale("
    but doesn't match the expected four-number syntax.
    """
    if raw is None:
        return raw, None

    text = raw.strip()
    if "scale(" not in text.lower():
        return raw, None

    match = _SCALE_SUFFIX_RE.match(text)
    if not match:
        raise ValueError(
            "Invalid Scale(...) syntax: expected "
            "'<address> Scale(raw_min,raw_max,scale_min,scale_max)'"
        )

    address = match.group("address")
    scale = (
        float(match.group("raw_min")),
        float(match.group("raw_max")),
        float(match.group("scale_min")),
        float(match.group("scale_max")),
    )
    return address, scale


def _format_scale_number(value: float) -> str:
    """Format a scale number without a trailing ``.0`` when it's whole."""
    if value == int(value):
        return str(int(value))
    return repr(float(value))


def format_address_with_scale(
    address: str, scale: tuple[float, float, float, float]
) -> str:
    """Build an address string with an inline ``Scale(...)`` suffix.

    Inverse of :func:`parse_address_and_scale`:
    ``format_address_with_scale("DB6,B23", (0.0, 1.0, 0.0, 10.0))`` returns
    ``"DB6,B23 Scale(0,1,0,10)"``.
    """
    raw_min, raw_max, scale_min, scale_max = scale
    numbers = ",".join(
        _format_scale_number(v) for v in (raw_min, raw_max, scale_min, scale_max)
    )
    return f"{address} Scale({numbers})"


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
