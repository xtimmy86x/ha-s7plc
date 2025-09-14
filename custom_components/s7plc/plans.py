"""Helpers for building read plans for the S7 PLC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from .address import DataType, S7Tag, parse_tag

_LOGGER = logging.getLogger(__name__)


@dataclass
class TagPlan:
    """Plan for a single scalar tag."""

    topic: str
    tag: S7Tag
    postprocess: Callable[[Any], Any] | None = None


@dataclass
class StringPlan:
    """Plan for reading an S7 string."""

    topic: str
    db: int
    start: int


def apply_postprocess(data_type, value):
    """Apply basic post-processing based on the tag data type."""

    return round(value, 1) if data_type == DataType.REAL else value


def build_plans(items: Dict[str, str]) -> Tuple[list[TagPlan], list[StringPlan]]:
    """Build read plans from a topic to address mapping."""

    plans_batch: list[TagPlan] = []
    plans_str: list[StringPlan] = []

    for topic, addr in items.items():
        try:
            tag = parse_tag(addr)
        except ValueError:
            _LOGGER.warning("Invalid address %s: %s", topic, addr)
            continue

        if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
            plans_str.append(StringPlan(topic, tag.db_number, tag.start))
            continue

        def _mk_post(dt):
            return lambda v: apply_postprocess(dt, v)

        plans_batch.append(TagPlan(topic, tag, _mk_post(tag.data_type)))

    return plans_batch, plans_str
