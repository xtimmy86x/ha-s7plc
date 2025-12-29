"""Helpers for S7 address parsing."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - fallback is for environments without pyS7
    import pyS7
    from pyS7.address_parser import S7AddressError
    from pyS7.address_parser import map_address_to_tag as s7_address_parser
    from pyS7.constants import DataType, MemoryArea
    from pyS7.tag import S7Tag
except ImportError as err:  # pragma: no cover
    _LOGGER.error("Unable to import pyS7: %s", err, exc_info=True)
    pyS7 = None
    DataType = SimpleNamespace(
        BIT=0,
        BYTE=1,
        WORD=2,
        DWORD=3,
        INT=4,
        DINT=5,
        REAL=6,
        CHAR=7,
        LREAL=0x1F,
    )
    MemoryArea = SimpleNamespace(DB=0, INPUT=1, OUTPUT=2, MERKER=3)
    S7Tag = Any
    s7_address_parser = None
    S7AddressError = Exception


__all__ = [
    "DataType",
    "MemoryArea",
    "S7Tag",
    "parse_tag",
    "map_address_to_tag",
    "get_numeric_limits",
    "pyS7",
]


def map_address_to_tag(address: str) -> Optional[S7Tag]:
    """Return an ``S7Tag`` for non-string addresses.

    ``None`` is returned for STRING addresses or when the parser is missing.
    The bit offset is remapped using :func:`_remap_bit_tag`.
    """

    if s7_address_parser is None:
        return None

    try:
        tag = s7_address_parser(address)
    except S7AddressError:
        return None

    if (
        getattr(tag, "data_type", None) == DataType.CHAR
        and getattr(tag, "length", 1) > 1
    ):
        return None

    return tag


def parse_tag(address: str) -> S7Tag:
    """Parse an address into an ``S7Tag``.

    Raises ``ValueError`` if the address cannot be parsed. The returned tag
    always has the bit offset remapped when needed.
    """

    if s7_address_parser is None:
        raise RuntimeError("S7 address parser not available")

    try:
        tag = s7_address_parser(address)
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
    if data_type == real:
        # ``REAL`` values are stored as 32-bit floating point numbers; we do not
        # impose an explicit limit so Home Assistant can expose any configured
        # range.
        return None

    return None
