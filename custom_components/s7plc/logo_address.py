"""Pure Siemens LOGO! VM address conversion helpers.

Only fixed mappings published in the Siemens ``Parameter VM Mapping`` tables
are represented here.  User-configured block-parameter mappings deliberately
remain manual DB1 addresses.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .address import parse_tag
from .const import PLC_FAMILY_LOGO_0BA7, PLC_FAMILY_LOGO_0BA8, PLC_FAMILY_LOGO_9


@dataclass(frozen=True, slots=True)
class LogoArea:
    """One contiguous, non-reserved portion of the Siemens mapping table."""

    name: str
    first: int
    last: int
    vm_offset: int
    data_type: str
    writable: bool | None


@dataclass(frozen=True, slots=True)
class LogoProfile:
    """Addressing capabilities for one LOGO! hardware generation."""

    family: str
    vm_last_byte: int
    areas: tuple[LogoArea, ...]
    documented: bool = True


# Analog LOGO values are signed 16-bit values (including negative values), so
# fixed AI/AQ/AM/NAI/NAQ mappings use pyS7 INT rather than unsigned WORD.
_0BA7 = (
    LogoArea("I", 1, 24, 923, "X", None),
    LogoArea("AI", 1, 8, 926, "INT", None),
    LogoArea("Q", 1, 16, 942, "X", None),
    LogoArea("AQ", 1, 2, 944, "INT", None),
    LogoArea("M", 1, 27, 948, "X", None),
    LogoArea("AM", 1, 16, 952, "INT", None),
)

_0BA8 = (
    LogoArea("I", 1, 64, 1024, "X", None),
    LogoArea("AI", 1, 16, 1032, "INT", None),
    LogoArea("Q", 1, 64, 1064, "X", None),
    LogoArea("AQ", 1, 16, 1072, "INT", None),
    LogoArea("M", 1, 112, 1104, "X", None),
    LogoArea("AM", 1, 64, 1118, "INT", None),
    LogoArea("NI", 1, 128, 1246, "X", None),
    LogoArea("NAI", 1, 64, 1262, "INT", None),
    LogoArea("NQ", 1, 128, 1390, "X", None),
    LogoArea("NAQ", 1, 32, 1406, "INT", None),
)

# LOGO! 9 keeps each numbered area continuous while its official VM table
# places the additional elements in a second, non-contiguous VM segment.
_LOGO_9 = (
    LogoArea("I", 1, 64, 1024, "X", None),
    LogoArea("I", 65, 128, 6024, "X", None),
    LogoArea("AI", 1, 16, 1032, "INT", None),
    LogoArea("AI", 17, 32, 6040, "INT", None),
    LogoArea("Q", 1, 64, 1064, "X", None),
    # Siemens prints "6104 ... 6110.5" but labels the range "7.5 bytes".
    # Those statements disagree; expose only the 54 bits named by the endpoints.
    LogoArea("Q", 65, 118, 6104, "X", None),
    LogoArea("AQ", 1, 16, 1072, "INT", None),
    LogoArea("AQ", 17, 32, 6120, "INT", None),
    LogoArea("M", 1, 112, 1104, "X", None),
    LogoArea("M", 113, 240, 6184, "X", None),
    LogoArea("AM", 1, 64, 1118, "INT", None),
    LogoArea("AM", 65, 192, 6216, "INT", None),
    LogoArea("FAM", 1, 32, 6728, "REAL", None),
    LogoArea("NI", 1, 128, 1246, "X", None),
    LogoArea("NI", 129, 640, 6984, "X", None),
    LogoArea("NAI", 1, 64, 1262, "INT", None),
    LogoArea("NAI", 65, 192, 7112, "INT", None),
    LogoArea("NQ", 1, 128, 1390, "X", None),
    LogoArea("NQ", 129, 608, 7624, "X", None),
    LogoArea("NAQ", 1, 32, 1406, "INT", None),
    LogoArea("NAQ", 33, 160, 7752, "INT", None),
    LogoArea("NFAI", 1, 32, 8264, "INT", None),
    LogoArea("NFAQ", 1, 32, 8392, "INT", None),
)

_PROFILES = {
    PLC_FAMILY_LOGO_0BA7: LogoProfile(PLC_FAMILY_LOGO_0BA7, 850, _0BA7),
    PLC_FAMILY_LOGO_0BA8: LogoProfile(PLC_FAMILY_LOGO_0BA8, 850, _0BA8),
    PLC_FAMILY_LOGO_9: LogoProfile(PLC_FAMILY_LOGO_9, 850, _LOGO_9),
}

_LOGO_RE = re.compile(r"^(NFAI|NFAQ|NAI|NAQ|FAM|AI|AQ|AM|NI|NQ|I|Q|M)([1-9]\d*)$", re.I)
_VM_RE = re.compile(r"^(V|VB|VW|VD)(\d+)(?:\.([0-7]))?$", re.I)


def get_logo_profile(family: str) -> LogoProfile:
    """Return the immutable profile for *family*."""
    try:
        return _PROFILES[family]
    except KeyError as err:
        raise ValueError(f"Unsupported LOGO! family: {family}") from err


def logo_profile_payload(family: str) -> dict[str, Any]:
    """Return the authoritative browser-safe representation of a profile."""
    return asdict(get_logo_profile(family))


def parse_logo_address(address: str, family: str) -> tuple[str, int]:
    """Parse and validate a symbolic fixed-mapping LOGO! address."""
    match = _LOGO_RE.fullmatch(address.strip())
    if not match:
        raise ValueError("invalid_logo_address")
    area_name, number_text = match.groups()
    area_name = area_name.upper()
    number = int(number_text)
    named_areas = [
        item for item in get_logo_profile(family).areas if item.name == area_name
    ]
    if not named_areas:
        raise ValueError("address_not_convertible")
    if not any(area.first <= number <= area.last for area in named_areas):
        raise ValueError("address_out_of_range")
    return area_name, number


def logo_to_s7_address(address: str, family: str) -> str:
    """Convert a validated LOGO! address to canonical pyS7 syntax."""
    stripped = address.strip()
    vm_match = _VM_RE.fullmatch(stripped)
    if vm_match:
        kind, offset_text, bit_text = vm_match.groups()
        kind = kind.upper()
        offset = int(offset_text)
        profile = get_logo_profile(family)
        width = {"V": 1, "VB": 1, "VW": 2, "VD": 4}[kind]
        if offset + width - 1 > profile.vm_last_byte:
            raise ValueError("address_out_of_range")
        if kind == "V":
            if bit_text is None:
                raise ValueError("invalid_logo_address")
            result = f"DB1,X{offset}.{bit_text}"
        else:
            if bit_text is not None:
                raise ValueError("invalid_logo_address")
            s7_type = {"VB": "BYTE", "VW": "WORD", "VD": "DWORD"}[kind]
            result = f"DB1,{s7_type}{offset}"
        parse_tag(result)
        return result

    area_name, number = parse_logo_address(stripped, family)
    area = next(
        item
        for item in get_logo_profile(family).areas
        if item.name == area_name and item.first <= number <= item.last
    )
    index = number - area.first
    if area.data_type == "X":
        result = f"DB1,X{area.vm_offset + index // 8}.{index % 8}"
    else:
        byte_width = 4 if area.data_type == "REAL" else 2
        result = f"DB1,{area.data_type}{area.vm_offset + index * byte_width}"
    parse_tag(result)
    return result


def s7_to_logo_address(address: str, family: str) -> str | None:
    """Reverse only exact fixed-table elements; never reserved/manual bytes."""
    normalized = address.strip().upper()
    try:
        parse_tag(normalized)
    except ValueError:
        return None
    for area in get_logo_profile(family).areas:
        for number in range(area.first, area.last + 1):
            if logo_to_s7_address(f"{area.name}{number}", family).upper() == normalized:
                return f"{area.name}{number}"
    return None
