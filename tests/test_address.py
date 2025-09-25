"""Tests for S7 address helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.s7plc import address


class DummyTag:
    """Simple replacement for ``S7Tag`` supporting expected attributes."""

    def __init__(
        self,
        memory_area="DB",
        db_number=1,
        data_type=None,
        start=0,
        bit_offset=0,
        length=1,
    ):
        self.memory_area = memory_area
        self.db_number = db_number
        self.data_type = data_type
        self.start = start
        self.bit_offset = bit_offset
        self.length = length


def test_map_address_to_tag_discards_string_tags(monkeypatch):
    """``map_address_to_tag`` should skip string tags."""

    data_type = SimpleNamespace(BIT="bit", CHAR="char")
    monkeypatch.setattr(address, "DataType", data_type)

    def fake_parser(address_str):
        return DummyTag(data_type=data_type.CHAR, length=8)

    monkeypatch.setattr(address, "s7_address_parser", fake_parser)

    assert address.map_address_to_tag("DB1.DBB0") is None