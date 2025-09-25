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
    )
    MemoryArea = SimpleNamespace(DB=0)
    S7Tag = Any
    s7_address_parser = None
    S7AddressError = Exception


__all__ = [
    "DataType",
    "MemoryArea",
    "S7Tag",
    "parse_tag",
    "map_address_to_tag",
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
