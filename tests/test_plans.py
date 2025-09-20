"""Tests for plan helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.s7plc import plans


class DummyTag:
    """Simple stand-in for ``S7Tag`` used in tests."""

    def __init__(self, data_type, db_number=1, start=0, length=1):
        self.data_type = data_type
        self.db_number = db_number
        self.start = start
        self.length = length


def test_build_plans_splits_scalar_and_strings(monkeypatch):
    """``build_plans`` should separate scalar and string reads."""

    data_type = SimpleNamespace(CHAR="char", INT="int", REAL="real")
    monkeypatch.setattr(plans, "DataType", data_type)

    char_tag = DummyTag(data_type.CHAR, db_number=2, start=4, length=12)
    int_tag = DummyTag(data_type.INT, db_number=3, start=0)

    def fake_parse(address: str) -> DummyTag:
        if address == "STRING_ADDR":
            return char_tag
        if address == "INT_ADDR":
            return int_tag
        raise ValueError(f"Unknown address: {address}")

    monkeypatch.setattr(plans, "parse_tag", fake_parse)

    items = {
        "topic/string": "STRING_ADDR",
        "topic/int": "INT_ADDR",
        "topic/bad": "BAD_ADDR",
    }

    batch_plans, string_plans = plans.build_plans(items)

    assert string_plans == [plans.StringPlan("topic/string", 2, 4)]
    assert len(batch_plans) == 1
    assert batch_plans[0].topic == "topic/int"
    assert batch_plans[0].tag is int_tag


def test_apply_postprocess_rounds_real_values(monkeypatch):
    """REAL values should be rounded to a single decimal place."""

    data_type = SimpleNamespace(CHAR="char", INT="int", REAL="real")
    monkeypatch.setattr(plans, "DataType", data_type)

    real_tag = DummyTag(data_type.REAL)

    def fake_parse(address: str) -> DummyTag:
        if address != "REAL_ADDR":
            raise ValueError("unexpected address")
        return real_tag

    monkeypatch.setattr(plans, "parse_tag", fake_parse)

    batch_plans, string_plans = plans.build_plans({"topic/real": "REAL_ADDR"})

    assert string_plans == []
    assert len(batch_plans) == 1
    postprocess = batch_plans[0].postprocess
    assert postprocess is not None
    assert postprocess(3.14159) == pytest.approx(3.1)
    assert postprocess(2) == pytest.approx(2.0)