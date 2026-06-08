"""Comparison operators for leaf conditions.

Each operator is a callable ``(left, right) -> bool`` where ``left`` is the
resolved field value and ``right`` is the literal/expected operand. Operators
that do not take an operand (``exists``, ``required`` ...) are handled in
:mod:`checks.conditions`, not here.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# Operators that compare a field against an operand value.
BINARY_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {}

# Operators that test only the field itself (no operand).
UNARY_OPERATORS = {"exists", "not_exists", "required", "empty"}


def operator(
    *names: str,
) -> Callable[[Callable[[Any, Any], bool]], Callable[[Any, Any], bool]]:
    def register(func: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
        for name in names:
            BINARY_OPERATORS[name] = func
        return func

    return register


def _as_number(value: Any) -> float | None:
    """Coerce numeric-looking values to float; return None if not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _compare(left: Any, right: Any) -> int | None:
    """Return -1/0/1 comparing left vs right, or None if incomparable."""
    ln, rn = _as_number(left), _as_number(right)
    if ln is not None and rn is not None:
        return (ln > rn) - (ln < rn)
    try:
        if left == right:
            return 0
        return 1 if left > right else -1  # type: ignore[operator]
    except TypeError:
        return None


@operator("eq", "equals", "==")
def op_eq(left: Any, right: Any) -> bool:
    cmp = _compare(left, right)
    if cmp is not None:
        return cmp == 0
    return left == right


@operator("ne", "not_equals", "!=")
def op_ne(left: Any, right: Any) -> bool:
    return not op_eq(left, right)


@operator("gt", ">")
def op_gt(left: Any, right: Any) -> bool:
    cmp = _compare(left, right)
    return cmp is not None and cmp > 0


@operator("gte", "ge", ">=")
def op_gte(left: Any, right: Any) -> bool:
    cmp = _compare(left, right)
    return cmp is not None and cmp >= 0


@operator("lt", "<")
def op_lt(left: Any, right: Any) -> bool:
    cmp = _compare(left, right)
    return cmp is not None and cmp < 0


@operator("lte", "le", "<=")
def op_lte(left: Any, right: Any) -> bool:
    cmp = _compare(left, right)
    return cmp is not None and cmp <= 0


@operator("in")
def op_in(left: Any, right: Any) -> bool:
    if isinstance(right, (list, tuple, set, str)):
        return left in right
    return False


@operator("not_in")
def op_not_in(left: Any, right: Any) -> bool:
    return not op_in(left, right)


@operator("contains")
def op_contains(left: Any, right: Any) -> bool:
    if isinstance(left, (list, tuple, set, str)):
        return right in left
    return False


@operator("not_contains")
def op_not_contains(left: Any, right: Any) -> bool:
    return not op_contains(left, right)


@operator("regex", "matches")
def op_regex(left: Any, right: Any) -> bool:
    try:
        return re.search(str(right), str(left)) is not None
    except re.error:
        return False


@operator("starts_with")
def op_starts_with(left: Any, right: Any) -> bool:
    return isinstance(left, str) and left.startswith(str(right))


@operator("ends_with")
def op_ends_with(left: Any, right: Any) -> bool:
    return isinstance(left, str) and left.endswith(str(right))


@operator("between")
def op_between(left: Any, right: Any) -> bool:
    """``right`` is a two-item ``[low, high]`` range, inclusive."""
    if not isinstance(right, (list, tuple)) or len(right) != 2:
        return False
    return op_gte(left, right[0]) and op_lte(left, right[1])


@operator("len_eq")
def op_len_eq(left: Any, right: Any) -> bool:
    return _length(left) == _as_number(right)


@operator("len_gt")
def op_len_gt(left: Any, right: Any) -> bool:
    length = _length(left)
    rn = _as_number(right)
    return length is not None and rn is not None and length > rn


@operator("len_lt")
def op_len_lt(left: Any, right: Any) -> bool:
    length = _length(left)
    rn = _as_number(right)
    return length is not None and rn is not None and length < rn


def _length(value: Any) -> float | None:
    try:
        return float(len(value))
    except TypeError:
        return None
