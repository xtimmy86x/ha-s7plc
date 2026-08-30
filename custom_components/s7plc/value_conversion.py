"""Central, side-effect free conversion pipeline for numeric PLC channels."""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping

from .address import DataType, get_numeric_limits, parse_tag

NUMERIC_DATA_TYPES = frozenset(
    value
    for name in (
        "BYTE",
        "SINT",
        "USINT",
        "WORD",
        "INT",
        "DWORD",
        "DINT",
        "REAL",
        "LREAL",
        "TIME",
    )
    if (value := getattr(DataType, name, None)) is not None
)
INTEGER_DATA_TYPES = frozenset(
    value
    for name in ("BYTE", "SINT", "USINT", "WORD", "INT", "DWORD", "DINT")
    if (value := getattr(DataType, name, None)) is not None
)

# Canonical logical-channel catalogue.  Address fields are strings on purpose:
# this module is also used by the configuration editor tests without importing
# Home Assistant's (large) const module.  Read and write addresses which model
# one HA value share one conversion and are validated independently.
VALUE_CHANNEL_SPECS: dict[str, dict[str, tuple[str | None, str | None]]] = {
    "sensors": {"value": ("address", None)},
    "numbers": {"value": ("address", "command_address")},
    "selects": {"value": ("address", "command_address")},
    "entity_sync": {"value": (None, "address")},
    "lights": {
        "brightness": ("brightness_state_address", "brightness_command_address")
    },
    "covers": {
        "position": ("position_state_address", "position_command_address"),
        "tilt": ("tilt_state_address", "tilt_command_address"),
        "status": ("cover_status_address", None),
    },
    "climates": {
        "current_temperature": ("current_temperature_address", None),
        # The same setpoint address is both read and written.
        "target_temperature": (
            "target_temperature_address",
            "target_temperature_address",
        ),
        # preset_mode is write-only unless preset_mode_bidirectional is enabled.
        "preset_mode": ("preset_mode_address", "preset_mode_address"),
        "hvac_status": ("hvac_status_address", None),
    },
}


def conversion_contexts(entity_type: str, entity: Mapping[str, Any], channel: str):
    """Return separate effective read/write contexts for a logical channel."""
    try:
        read_field, write_field = VALUE_CHANNEL_SPECS[entity_type][channel]
    except KeyError as err:
        raise ValueConversionError(
            f"unsupported conversion channel '{channel}'"
        ) from err
    read_address = entity.get(read_field) if read_field else None
    write_address = entity.get(write_field) if write_field else None
    if (
        entity_type == "climates"
        and channel == "preset_mode"
        and not entity.get("preset_mode_bidirectional")
    ):
        read_address = None
    # number/select command defaults to their state address at runtime.
    if entity_type in ("numbers", "selects") and not write_address:
        write_address = read_address
    contexts = []
    if read_address:
        contexts.append(ConversionContext.from_address(channel, read_address, "read"))
    if write_address:
        contexts.append(ConversionContext.from_address(channel, write_address, "write"))
    if not contexts:
        raise ValueConversionError(f"channel '{channel}' has no address")
    return contexts


class ValueConversionError(ValueError):
    """A conversion cannot be validated or performed."""


@dataclass(frozen=True)
class ConversionContext:
    """Metadata for one logical value channel."""

    channel: str
    data_type: Any
    direction: str = "bidirectional"  # read, write, bidirectional

    @classmethod
    def from_address(cls, channel: str, address: str, direction: str = "bidirectional"):
        return cls(channel, parse_tag(address).data_type, direction)

    @property
    def can_read(self) -> bool:
        return self.direction in ("read", "bidirectional")

    @property
    def can_write(self) -> bool:
        return self.direction in ("write", "bidirectional")


def supports_value_conversion(data_type: Any) -> bool:
    """Return the centralized numeric-conversion capability."""
    return data_type in NUMERIC_DATA_TYPES


def _finite(value: Any, field: str = "value") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise ValueConversionError(f"{field} must be numeric") from err
    if not math.isfinite(number):
        raise ValueConversionError(f"{field} must be finite")
    return number


def _round(value: float, mode: str) -> int:
    if mode == "floor":
        return math.floor(value)
    if mode == "ceil":
        return math.ceil(value)
    rounding = ROUND_HALF_UP if mode == "half_up" else ROUND_HALF_EVEN
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=rounding))


def _plc_result(
    value: Any, context: ConversionContext, config: Mapping[str, Any]
) -> Any:
    number = _finite(value)
    if context.data_type in INTEGER_DATA_TYPES:
        number = _round(number, str(config.get("rounding", "half_even")))
    limits = get_numeric_limits(context.data_type)
    if limits and not limits[0] <= number <= limits[1]:
        raise ValueConversionError(
            f"result {number} is outside PLC datatype limits {limits}"
        )
    return number


_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "round": round,
    "min": min,
    "max": max,
    "abs": abs,
    "int": int,
    "float": float,
    "clamp": lambda value, low, high: min(max(value, low), high),
}


def evaluate_expression(expression: str, value: Any) -> float:
    """Evaluate the documented arithmetic subset without eval/exec."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueConversionError("expression is required")
    if len(expression) > 256:
        raise ValueConversionError("expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as err:
        raise ValueConversionError("invalid expression syntax") from err
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueConversionError("expression is too complex")

    def visit(node: ast.AST, depth: int = 0) -> Any:
        if depth > 16:
            raise ValueConversionError("expression is too deeply nested")
        if isinstance(node, ast.Expression):
            return visit(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name) and node.id == "value":
            return _finite(value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if abs(left) > 1e100 or abs(right) > 1e100:
                raise ValueConversionError("expression operands are too large")
            try:
                return _BIN_OPS[type(node.op)](left, right)
            except (ArithmeticError, ValueError) as err:
                raise ValueConversionError(str(err)) from err
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](visit(node.operand, depth + 1))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
        ):
            return _FUNCTIONS[node.func.id](
                *(visit(arg, depth + 1) for arg in node.args)
            )
        raise ValueConversionError(
            f"expression contains forbidden element: {type(node).__name__}"
        )

    return _finite(visit(tree), "expression result")


def _logo_time(value: Any) -> int:
    if value is None:
        raise ValueConversionError("LOGO! time value is empty")
    text = str(value).strip()
    if text.lower() in ("", "unknown", "unavailable"):
        raise ValueConversionError("LOGO! time value is unavailable")
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not match:
        raise ValueConversionError("LOGO! time must use HH:MM or HH:MM:SS")
    hour, minute, second = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )
    if hour > 23 or minute > 59 or second > 59:
        raise ValueConversionError("LOGO! time is outside 00:00:00-23:59:59")
    return (
        ((hour // 10) << 12) | ((hour % 10) << 8) | ((minute // 10) << 4) | minute % 10
    )


def validate_value_conversion(
    config: Mapping[str, Any] | None, context: ConversionContext
) -> None:
    """Validate one serialized conversion against channel capabilities."""
    if not config:
        return
    if not supports_value_conversion(context.data_type):
        raise ValueConversionError("datatype is not numeric")
    kind = config.get("type")
    if kind == "multiplier":
        factor = _finite(config.get("factor"), "factor")
        if context.can_write and factor == 0:
            raise ValueConversionError("factor must not be zero for writes")
    elif kind == "linear_scale":
        values = [
            _finite(config.get(key), key)
            for key in ("plc_min", "plc_max", "ha_min", "ha_max")
        ]
        if values[0] == values[1] or (context.can_write and values[2] == values[3]):
            raise ValueConversionError("scale intervals must not be zero")
        if context.channel == "brightness" and (
            values[2] != 0 or values[3] != 255 or config.get("clamp") is not True
        ):
            raise ValueConversionError(
                "Home Assistant brightness requires ha_min 0, ha_max 255, "
                "and clamp true"
            )
    elif kind == "logo_time_bcd":
        if not context.can_write or context.data_type != getattr(
            DataType, "WORD", None
        ):
            raise ValueConversionError(
                "LOGO! time BCD requires a writable WORD channel"
            )
    elif kind == "expression":
        if context.can_read:
            evaluate_expression(str(config.get("read_expression", "")), 1)
        if context.can_write:
            evaluate_expression(str(config.get("write_expression", "")), 1)
    else:
        raise ValueConversionError(f"unknown conversion type: {kind}")


def normalize_value_conversion(
    entity: Mapping[str, Any], channel: str, context: ConversionContext | None = None
) -> dict[str, Any] | None:
    """Resolve new or legacy config, rejecting ambiguous double conversion."""
    conversions = entity.get("value_conversions") or {}
    configured = conversions.get(channel) if isinstance(conversions, Mapping) else None
    legacy: dict[str, Any] | None = None
    if channel == "brightness" and entity.get("brightness_scale") not in (None, ""):
        legacy = {
            "type": "linear_scale",
            "plc_min": 0,
            "plc_max": entity["brightness_scale"],
            "ha_min": 0,
            "ha_max": 255,
            "clamp": True,
            "rounding": "half_even",
        }
    elif channel == "value":
        scale = tuple(
            entity.get(k)
            for k in ("scale_raw_min", "scale_raw_max", "min_value", "max_value")
        )
        if all(v not in (None, "") for v in scale):
            legacy = {
                "type": "linear_scale",
                "plc_min": scale[0],
                "plc_max": scale[1],
                "ha_min": scale[2],
                "ha_max": scale[3],
            }
        elif entity.get("value_multiplier") not in (None, ""):
            legacy = {"type": "multiplier", "factor": entity["value_multiplier"]}
    if configured is not None and legacy is not None:
        raise ValueConversionError(
            f"new and legacy conversion conflict for channel '{channel}'"
        )
    result = dict(configured or legacy) if configured or legacy else None
    if result and context:
        validate_value_conversion(result, context)
    return result


def convert_from_plc(
    value: Any, config: Mapping[str, Any] | None, context: ConversionContext
) -> Any:
    if not config:
        return value
    validate_value_conversion(config, context)
    kind = config["type"]
    number = _finite(value)
    if kind == "multiplier":
        result = number * _finite(config["factor"], "factor")
    elif kind == "linear_scale":
        p0, p1, h0, h1 = (
            _finite(config[k], k) for k in ("plc_min", "plc_max", "ha_min", "ha_max")
        )
        if config.get("clamp"):
            number = min(max(number, min(p0, p1)), max(p0, p1))
        result = h0 + (number - p0) * (h1 - h0) / (p1 - p0)
    elif kind == "expression":
        result = evaluate_expression(config["read_expression"], number)
    else:
        raise ValueConversionError(f"{kind} does not support reading")
    return _finite(result, "conversion result")


def convert_to_plc(
    value: Any, config: Mapping[str, Any] | None, context: ConversionContext
) -> Any:
    if not config:
        return value
    validate_value_conversion(config, context)
    kind = config["type"]
    if kind == "logo_time_bcd":
        return _logo_time(value)
    number = _finite(value)
    if kind == "multiplier":
        result = number / _finite(config["factor"], "factor")
    elif kind == "linear_scale":
        p0, p1, h0, h1 = (
            _finite(config[k], k) for k in ("plc_min", "plc_max", "ha_min", "ha_max")
        )
        if config.get("clamp"):
            number = min(max(number, min(h0, h1)), max(h0, h1))
        result = p0 + (number - h0) * (p1 - p0) / (h1 - h0)
    elif kind == "expression":
        result = evaluate_expression(config["write_expression"], number)
    else:
        raise ValueConversionError(f"{kind} does not support writing")
    return _plc_result(result, context, config)


def describe_value_conversion(config: Mapping[str, Any] | None) -> str:
    if not config:
        return "None"
    if config.get("type") == "multiplier":
        return f"× {config.get('factor')}"
    if config.get("type") == "linear_scale":
        return (
            f"Scale {config.get('plc_min')}–{config.get('plc_max')} → "
            f"{config.get('ha_min')}–{config.get('ha_max')}"
        )
    if config.get("type") == "logo_time_bcd":
        return "LOGO! time (BCD)"
    return "Custom expression"
