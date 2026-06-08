"""Introspect a rule set to discover which data fields it needs.

This answers "what does my payload have to contain to run these rules?" so a
non-technical author can see the required inputs without reading code.

Fields referenced inside an array quantifier are reported relative to the
array using ``[]`` notation, e.g. ``data.beneficiaries[].percentage``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from .models import RuleSet


def _new_str_set() -> set[str]:
    return set()


@dataclass
class FieldUsage:
    """A single data field referenced by one or more rules."""

    path: str
    rules: set[str] = field(default_factory=_new_str_set)
    operators: set[str] = field(default_factory=_new_str_set)
    # True when at least one referencing rule hard-requires the data
    # (severity escalate, or on_missing == "fail"/"escalate").
    always_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rules": sorted(self.rules),
            "operators": sorted(self.operators),
            "always_required": self.always_required,
        }


def collect_required_fields(ruleset: RuleSet) -> list[FieldUsage]:
    """Return every data field the rule set references, sorted by path."""
    usages: dict[str, FieldUsage] = {}

    for rule in ruleset.rules:
        hard = rule.on_missing in ("fail", "escalate")
        _walk(rule.check, prefix="", rule_id=rule.id, hard=hard, usages=usages)

    return [usages[key] for key in sorted(usages)]


def _record(
    usages: dict[str, FieldUsage],
    path: str,
    rule_id: str,
    op: str | None,
    hard: bool,
) -> None:
    usage = usages.get(path)
    if usage is None:
        usage = FieldUsage(path=path)
        usages[path] = usage
    usage.rules.add(rule_id)
    if op:
        usage.operators.add(op)
    if hard:
        usage.always_required = True


def _join(prefix: str, field_path: str) -> str:
    if not prefix:
        return field_path
    return f"{prefix}.{field_path}"


def _walk(
    node: Any,
    prefix: str,
    rule_id: str,
    hard: bool,
    usages: dict[str, FieldUsage],
) -> None:
    if not isinstance(node, (dict, str)):
        return

    # Expression-string form (bare string check or {expr: "..."} mapping)
    if isinstance(node, str):
        from .expressions import collect_expression_fields  # noqa: PLC0415
        for (path, op) in collect_expression_fields(node):
            _record(usages, _join(prefix, path), rule_id, op, hard)
        return

    node = cast(dict[str, Any], node)

    if "expr" in node:
        expr_text = node.get("expr", "")
        if isinstance(expr_text, str) and expr_text:
            from .expressions import collect_expression_fields  # noqa: PLC0415
            for (path, op) in collect_expression_fields(expr_text):
                _record(usages, _join(prefix, path), rule_id, op, hard)
        return

    if "all" in node or "any" in node:
        children: Any = node.get("all") or node.get("any") or []
        if isinstance(children, list):
            for child in cast(list[Any], children):
                _walk(child, prefix, rule_id, hard, usages)
        return

    if "not" in node:
        _walk(node["not"], prefix, rule_id, hard, usages)
        return

    if "if" in node:
        # The antecedent is needed to decide applicability; branches are
        # conditional, so they are not "always" required.
        _walk(node["if"], prefix, rule_id, hard, usages)
        _walk(node.get("then"), prefix, rule_id, False, usages)
        _walk(node.get("else"), prefix, rule_id, False, usages)
        return

    for quant in ("for_each", "any_of", "none_of", "count"):
        if quant in node:
            spec = node[quant]
            if not isinstance(spec, dict):
                return
            spec = cast(dict[str, Any], spec)
            array_path = _join(prefix, str(spec.get("field", "")))
            _record(usages, array_path, rule_id, quant, hard)
            match = spec.get("match", spec.get("where"))
            if match is not None:
                # 'any_of'/'count' don't require every element's fields; only
                # 'for_each' applies the inner condition to all elements.
                inner_hard = hard and quant == "for_each"
                _walk(match, f"{array_path}[]", rule_id, inner_hard, usages)
            return

    if "field" in node:
        op = node.get("op", "required")
        _record(usages, _join(prefix, str(node["field"])), rule_id, str(op), hard)
        if "field_value" in node:
            _record(
                usages, _join(prefix, str(node["field_value"])), rule_id, str(op), hard
            )
        return
