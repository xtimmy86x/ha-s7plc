"""Tests for plan helpers."""

from __future__ import annotations

import pytest

from custom_components.s7plc.address import DataType
from custom_components.s7plc import plans


def test_build_plans_splits_scalar_and_strings(monkeypatch):
    """``build_plans`` should separate scalar and string reads."""

    items = {
        "topic/string": "DB2,S4.12",
        "topic/int": "DB3,W0",
        "topic/bad": "BAD_ADDR",
    }

    batch_plans, string_plans = plans.build_plans(items)

    assert string_plans == [plans.StringPlan("topic/string", 2, 4)]
    assert len(batch_plans) == 1
    assert batch_plans[0].topic == "topic/int"
    assert batch_plans[0].tag.data_type == DataType.WORD
    assert batch_plans[0].tag.db_number == 3
    assert batch_plans[0].tag.start == 0


def test_apply_postprocess_rounds_real_values(monkeypatch):
    """REAL values should be rounded to a single decimal place."""

    batch_plans, string_plans = plans.build_plans({"topic/real": "DB1,R2"})

    assert string_plans == []
    assert len(batch_plans) == 1
    assert batch_plans[0].tag.data_type == DataType.REAL
    postprocess = batch_plans[0].postprocess
    assert postprocess is not None
    assert postprocess(3.14159) == pytest.approx(3.1)
    assert postprocess(2) == pytest.approx(2.0)