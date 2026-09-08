"""Validate Python values for pyS7 writes without entity-level conversions."""

from __future__ import annotations

from datetime import timedelta

from .address import DataType, S7Tag


def prepare_payload(
    tag: S7Tag,
    value: bool | int | float | str | timedelta,
    address: str = "",
) -> bool | int | float | str | timedelta:
    """Validate and convert a Python value to the appropriate PLC payload.

    Args:
        tag: Parsed S7Tag describing the target data type.
        value: Value to convert.
        address: PLC address (used only in error messages).

    Returns:
        Converted payload ready for the pyS7 write call.

    Raises:
        ValueError: If value type doesn't match the tag data type.
    """
    if tag.data_type == DataType.BIT:
        if not isinstance(value, bool):
            raise ValueError(
                f"BIT address {address} requires bool value, "
                f"got {type(value).__name__}"
            )
        return bool(value)

    if tag.data_type == getattr(DataType, "TIME", None):
        if not isinstance(value, timedelta):
            raise ValueError(
                f"TIME address {address} requires timedelta value, "
                f"got {type(value).__name__}"
            )
        return value

    if tag.data_type in (DataType.STRING, DataType.WSTRING):
        if not isinstance(value, str):
            raise ValueError(
                f"STRING/WSTRING address {address} requires str value, "
                f"got {type(value).__name__}"
            )
        return str(value)

    if tag.data_type in (DataType.REAL, DataType.LREAL):
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{tag.data_type.name} address {address} requires numeric value, "
                f"got {type(value).__name__}"
            )
        return float(value)

    if tag.data_type in (
        DataType.BYTE,
        DataType.WORD,
        DataType.DWORD,
        DataType.INT,
        DataType.DINT,
        DataType.USINT,
        DataType.SINT,
    ):
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{tag.data_type.name} address {address} requires "
                f"numeric value, got {type(value).__name__}"
            )
        return int(round(float(value)))

    if tag.data_type == DataType.CHAR:
        raise ValueError(
            f"CHAR arrays not supported for write at {address}, use STRING instead"
        )

    raise ValueError(f"Unsupported data type for write at {address}: {tag.data_type}")
