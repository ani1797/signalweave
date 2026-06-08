"""Recursive evaluation of the condition tree used inside a rule's ``check``.

A condition node is one of:

* **Leaf** — tests a single ``field`` with an ``op``:
    ``{field: data.amount, op: lte, value: 1000}``
    Compare to another field instead of a literal with ``field_value``:
    ``{field: data.a, op: eq, field_value: data.b}``
    Presence ops take no operand: ``exists``, ``not_exists``, ``required``, ``empty``.
* **Logical** — ``{all: [...]}``, ``{any: [...]}``, ``{not: {...}}``.
* **Conditional** — ``{if: {...}, then: {...}, else: {...}}`` (``else`` optional).

Evaluation returns a :class:`ConditionResult`. ``missing`` means the condition
could not be decided because required data was absent (distinct from a clean
FALSE), so the engine can apply the rule's ``on_missing`` policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from .operators import BINARY_OPERATORS, UNARY_OPERATORS
from .paths import MISSING, is_empty, resolve_path


@dataclass
class ConditionResult:
    passed: bool
    reason: str
    missing: bool = False


class RuleFormatError(ValueError):
    """Raised when a condition node is malformed."""


def evaluate_condition(node: Any, data: Any) -> ConditionResult:
    """Evaluate a condition ``node`` against ``data``.

    Accepts three forms:
    * A **dict** — the original structured condition tree.
    * A **str** — a bare expression string, e.g. ``"data.amount <= 1000"``.
    * A **dict with an ``expr`` key** — ``{expr: "..."}`` — so an expression
      can be nested inside a structured ``all`` / ``any`` / ``if`` node.
    """
    # Expression-string form (bare string or {expr: ...} mapping)
    if isinstance(node, str):
        from .expressions import evaluate_expression  # noqa: PLC0415
        return evaluate_expression(node, data)

    if not isinstance(node, dict):
        raise RuleFormatError(f"Condition must be a mapping or string, got: {node!r}")
    node = cast(dict[str, Any], node)

    if "expr" in node:
        expr_text = node["expr"]
        if not isinstance(expr_text, str):
            raise RuleFormatError(
                f"'expr' value must be a string, got: {expr_text!r}"
            )
        from .expressions import evaluate_expression  # noqa: PLC0415
        return evaluate_expression(str(expr_text), data)

    if "all" in node:
        return _eval_all(node["all"], data)
    if "any" in node:
        return _eval_any(node["any"], data)
    if "not" in node:
        return _eval_not(node["not"], data)
    if "if" in node:
        return _eval_if(node, data)
    # Array quantifiers carry a `field` (the array path) plus a `match`
    # condition applied to each element, so test them before the leaf case.
    if "for_each" in node:
        return _eval_quantifier("for_each", node["for_each"], data)
    if "any_of" in node:
        return _eval_quantifier("any_of", node["any_of"], data)
    if "none_of" in node:
        return _eval_quantifier("none_of", node["none_of"], data)
    if "count" in node:
        return _eval_count(node["count"], data)
    if "field" in node:
        return _eval_leaf(node, data)

    raise RuleFormatError(
        "Condition must contain one of "
        f"field/all/any/not/if/for_each/any_of/none_of/count; got keys {list(node)}"
    )


def _eval_all(children: Any, data: Any) -> ConditionResult:
    _require_list("all", children)
    any_missing = False
    for child in children:
        res = evaluate_condition(child, data)
        if not res.passed and not res.missing:
            return ConditionResult(False, res.reason)
        any_missing = any_missing or res.missing
    if any_missing:
        return ConditionResult(
            False, "one or more conditions could not be evaluated", missing=True
        )
    return ConditionResult(True, "all conditions satisfied")


def _eval_any(children: Any, data: Any) -> ConditionResult:
    _require_list("any", children)
    any_missing = False
    reasons: list[str] = []
    for child in children:
        res = evaluate_condition(child, data)
        if res.passed and not res.missing:
            return ConditionResult(True, res.reason)
        any_missing = any_missing or res.missing
        reasons.append(res.reason)
    if any_missing:
        return ConditionResult(
            False, "no condition satisfied and data was missing", missing=True
        )
    return ConditionResult(False, "no condition satisfied: " + "; ".join(reasons))


def _eval_not(child: Any, data: Any) -> ConditionResult:
    res = evaluate_condition(child, data)
    if res.missing:
        return ConditionResult(False, res.reason, missing=True)
    return ConditionResult(not res.passed, f"NOT ({res.reason})")


def _eval_if(node: dict[str, Any], data: Any) -> ConditionResult:
    cond = evaluate_condition(node["if"], data)
    if cond.missing:
        return ConditionResult(
            False, f"condition could not be evaluated: {cond.reason}", missing=True
        )
    if cond.passed:
        if "then" not in node:
            raise RuleFormatError("'if' condition requires a 'then' branch")
        return evaluate_condition(node["then"], data)
    if "else" in node:
        return evaluate_condition(node["else"], data)
    # No else branch and the antecedent is false -> rule is vacuously satisfied.
    return ConditionResult(True, "precondition not met; rule not applicable")


def _resolve_array(
    spec: Any, data: Any
) -> tuple[str, list[Any] | None, ConditionResult | None]:
    """Resolve the array a quantifier targets.

    Returns ``(field_path, elements, error)``. ``error`` is non-None when the
    array could not be resolved (missing or not a list), in which case
    ``elements`` is None.
    """
    if not isinstance(spec, dict) or "field" not in spec:
        raise RuleFormatError("Array quantifier requires a 'field' (the array path)")
    spec = cast(dict[str, Any], spec)
    field_path = str(spec["field"])
    value = resolve_path(data, field_path)
    if value is MISSING:
        return (
            field_path,
            None,
            ConditionResult(False, f"array '{field_path}' is missing", missing=True),
        )
    if not isinstance(value, list):
        return (
            field_path,
            None,
            ConditionResult(
                False, f"field '{field_path}' is not an array", missing=True
            ),
        )
    return field_path, cast(list[Any], value), None


def _element_condition(spec: dict[str, Any]) -> dict[str, Any]:
    match = spec.get("match", spec.get("where"))
    if not isinstance(match, dict):
        raise RuleFormatError("Array quantifier requires a 'match' condition mapping")
    return cast(dict[str, Any], match)


def _eval_quantifier(kind: str, spec: Any, data: Any) -> ConditionResult:
    """Evaluate ``for_each`` / ``any_of`` / ``none_of`` over an array.

    The ``match`` condition is evaluated with each element as its own root, so
    inner ``field`` paths are relative to the element (e.g. ``name``,
    ``address.line1``). This is how a check targets several fields per element.
    """
    field_path, elements, error = _resolve_array(spec, data)
    if error is not None:
        return error
    assert elements is not None
    match = _element_condition(spec)

    matched = 0
    any_missing = False
    failing_reason = ""
    for index, element in enumerate(elements):
        res = evaluate_condition(match, element)
        if res.missing:
            any_missing = True
        elif res.passed:
            matched += 1
        elif not failing_reason:
            failing_reason = f"element {index} {res.reason}"

    total = len(elements)
    if kind == "for_each":
        if any_missing:
            return ConditionResult(
                False, f"'{field_path}' has elements with missing data", missing=True
            )
        if matched == total:
            return ConditionResult(
                True, f"all {total} elements of '{field_path}' satisfy the condition"
            )
        return ConditionResult(False, f"'{field_path}': {failing_reason}")
    if kind == "any_of":
        if matched > 0:
            return ConditionResult(
                True, f"{matched} element(s) of '{field_path}' satisfy the condition"
            )
        if any_missing:
            return ConditionResult(
                False,
                f"no element of '{field_path}' matched and some had missing data",
                missing=True,
            )
        return ConditionResult(
            False, f"no element of '{field_path}' satisfies the condition"
        )
    if kind == "none_of":
        if matched > 0:
            return ConditionResult(
                False,
                f"{matched} element(s) of '{field_path}' unexpectedly satisfy the condition",
            )
        if any_missing:
            return ConditionResult(
                False, f"'{field_path}' had elements with missing data", missing=True
            )
        return ConditionResult(
            True, f"no element of '{field_path}' satisfies the condition"
        )
    raise RuleFormatError(f"Unknown quantifier '{kind}'")


def _eval_count(spec: Any, data: Any) -> ConditionResult:
    """Constrain how many array elements match: ``count`` + ``op`` + ``value``.

    With no ``match`` condition, counts all elements (array length).
    """
    field_path, elements, error = _resolve_array(spec, data)
    if error is not None:
        return error
    assert elements is not None

    spec = cast(dict[str, Any], spec)
    op = spec.get("op")
    if op not in BINARY_OPERATORS:
        raise RuleFormatError(f"'count' requires a comparison 'op'; got {op!r}")
    if "value" not in spec:
        raise RuleFormatError("'count' requires a 'value' to compare against")

    match = spec.get("match", spec.get("where"))
    if match is None:
        matched = len(elements)
    else:
        if not isinstance(match, dict):
            raise RuleFormatError("'count' match must be a condition mapping")
        matched = 0
        for element in elements:
            res = evaluate_condition(cast(dict[str, Any], match), element)
            if res.passed and not res.missing:
                matched += 1

    expected = spec["value"]
    passed = BINARY_OPERATORS[op](matched, expected)
    verb = "satisfies" if passed else "does not satisfy"
    return ConditionResult(
        passed,
        f"count of matching elements in '{field_path}' ({matched}) {verb} {op} {expected}",
    )


def _eval_leaf(node: dict[str, Any], data: Any) -> ConditionResult:
    field_path = node["field"]
    op = node.get("op", "required")
    value = resolve_path(data, field_path)
    present = value is not MISSING

    # Presence / emptiness operators decide on the field's existence itself.
    if op in UNARY_OPERATORS:
        return _eval_unary(op, field_path, value, present)

    if op not in BINARY_OPERATORS:
        raise RuleFormatError(f"Unknown operator '{op}' on field '{field_path}'")

    if not present:
        return ConditionResult(False, f"field '{field_path}' is missing", missing=True)

    # Resolve the right-hand operand: a literal `value` or another `field_value`.
    if "field_value" in node:
        other_path = node["field_value"]
        operand = resolve_path(data, other_path)
        if operand is MISSING:
            return ConditionResult(
                False, f"comparison field '{other_path}' is missing", missing=True
            )
        operand_label = f"{other_path} ({_fmt(operand)})"
    elif "value" in node:
        operand = node["value"]
        operand_label = _fmt(operand)
    else:
        raise RuleFormatError(
            f"Operator '{op}' on field '{field_path}' needs 'value' or 'field_value'"
        )

    passed = BINARY_OPERATORS[op](value, operand)
    verb = "satisfies" if passed else "does not satisfy"
    reason = f"{field_path} ({_fmt(value)}) {verb} {op} {operand_label}"
    return ConditionResult(passed, reason)


def _eval_unary(op: str, field_path: str, value: Any, present: bool) -> ConditionResult:
    if op == "exists":
        return ConditionResult(
            present, f"field '{field_path}' " + ("exists" if present else "is missing")
        )
    if op == "not_exists":
        return ConditionResult(
            not present,
            f"field '{field_path}' " + ("is absent" if not present else "exists"),
        )
    if op == "required":
        empty = is_empty(value)
        return ConditionResult(
            not empty,
            f"field '{field_path}' "
            + ("is present and non-empty" if not empty else "is missing or empty"),
        )
    if op == "empty":
        empty = is_empty(value)
        return ConditionResult(
            empty, f"field '{field_path}' " + ("is empty" if empty else "is non-empty")
        )
    raise RuleFormatError(f"Unhandled unary operator '{op}'")


def _require_list(key: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise RuleFormatError(f"'{key}' must be a non-empty list of conditions")


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)
