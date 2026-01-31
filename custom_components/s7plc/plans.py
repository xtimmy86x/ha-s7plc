"""Helpers for building read plans for the S7 PLC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from .address import DataType, S7Tag, parse_tag
from .const import DEFAULT_REAL_PRECISION

_LOGGER = logging.getLogger(__name__)


@dataclass
class TagPlan:
    """Plan for a single scalar tag."""

    topic: str
    tag: S7Tag
    postprocess: Callable[[Any], Any] | None = None


@dataclass
class StringPlan:
    """Plan for an S7 string."""

    topic: str
    db: int
    start: int
    length: int
    is_wstring: bool = False


def apply_postprocess(
    data_type, value, *, precision: int | None = DEFAULT_REAL_PRECISION
):
    """Apply basic post-processing based on the tag data type."""

    if data_type not in (DataType.REAL, getattr(DataType, "LREAL", None)):
        return value
    if precision is None:
        return value
    return round(value, precision)


def build_plans(
    items: Dict[str, str],
    *,
    precisions: Dict[str, int | None] | None = None,
    tag_cache: Dict[str, S7Tag] | None = None,
) -> Tuple[list[TagPlan], list[StringPlan]]:
    """Build read plans from a topic to address mapping.

    Args:
        items: Mapping of topic names to PLC addresses
        precisions: Optional precision settings for REAL values
        tag_cache: Optional cache for parsed tags (improves performance on rebuilds)
    """

    plans_batch: list[TagPlan] = []
    plans_str: list[StringPlan] = []

    for topic, addr in items.items():
        try:
            # Use cache if provided to avoid reparsing tags
            if tag_cache is not None:
                tag = tag_cache.get(addr)
                if tag is None:
                    tag = parse_tag(addr)
                    tag_cache[addr] = tag
            else:
                tag = parse_tag(addr)
        except ValueError:
            _LOGGER.warning("Invalid address %s: %s", topic, addr)
            continue

        if tag.data_type == DataType.CHAR and getattr(tag, "length", 1) > 1:
            plans_str.append(
                StringPlan(
                    topic, tag.db_number, tag.start, tag.length, is_wstring=False
                )
            )
            continue

        if tag.data_type == DataType.STRING:
            plans_str.append(
                StringPlan(
                    topic, tag.db_number, tag.start, tag.length, is_wstring=False
                )
            )
            continue

        if tag.data_type == DataType.WSTRING:
            plans_str.append(
                StringPlan(topic, tag.db_number, tag.start, tag.length, is_wstring=True)
            )
            continue

        def _mk_post(dt, precision):
            return lambda v: apply_postprocess(dt, v, precision=precision)

        precision = DEFAULT_REAL_PRECISION
        if precisions is not None and topic in precisions:
            precision = precisions[topic]
        plans_batch.append(TagPlan(topic, tag, _mk_post(tag.data_type, precision)))

    return plans_batch, plans_str
