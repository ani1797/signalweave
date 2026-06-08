"""Integrity validation for rule files.

Designed for non-technical rule authors: it loads a rules file and reports
*every* structural problem it can find in plain language, instead of stopping
at the first error. Use :func:`validate_file` from code or ``python -m signalweave.checks
--validate`` from the terminal.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from .models import VALID_ON_MISSING, VALID_SEVERITIES, Verdict
from .operators import BINARY_OPERATORS, UNARY_OPERATORS

ALL_OPERATORS = sorted(set(BINARY_OPERATORS) | set(UNARY_OPERATORS))

# Keys allowed at each kind of condition node.
_LEAF_KEYS = {"field", "op", "value", "field_value"}
_QUANTIFIER_KEYS = {"field", "match", "where", "op", "value"}
_EXPR_KEYS = {"expr"}


def _new_issue_list() -> list["ValidationIssue"]:
    return []


@dataclass
class ValidationIssue:
    level: str  # "error" or "warning"
    location: str
    message: str
    hint: str = ""

    def __str__(self) -> str:
        line = f"{self.level.upper():7} {self.location}: {self.message}"
        if self.hint:
            line += f"\n          hint: {self.hint}"
        return line


@dataclass
class ValidationReport:
    source: str
    issues: list[ValidationIssue] = field(default_factory=_new_issue_list)
    rule_count: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add_error(self, location: str, message: str, hint: str = "") -> None:
        self.issues.append(ValidationIssue("error", location, message, hint))

    def add_warning(self, location: str, message: str, hint: str = "") -> None:
        self.issues.append(ValidationIssue("warning", location, message, hint))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "valid": self.is_valid,
            "rule_count": self.rule_count,
            "errors": [i.message for i in self.errors],
            "warnings": [i.message for i in self.warnings],
            "issues": [
                {
                    "level": i.level,
                    "location": i.location,
                    "message": i.message,
                    "hint": i.hint,
                }
                for i in self.issues
            ],
        }

    def to_summary(self) -> str:
        if self.is_valid and not self.warnings:
            return f"OK — '{self.source}' is valid ({self.rule_count} rules, no problems found)."
        header_state = "valid with warnings" if self.is_valid else "INVALID"
        counts = f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        lines = [
            f"{header_state} — '{self.source}' ({self.rule_count} rules, {counts}):",
            "",
        ]
        lines.extend(str(issue) for issue in self.issues)
        return "\n".join(lines)


def validate_file(path: str | Path) -> ValidationReport:
    """Validate a rules file for structural integrity."""
    path = Path(path)
    report = ValidationReport(source=str(path))

    if not path.exists():
        report.add_error("file", f"rules file not found: {path}")
        return report

    text = path.read_text(encoding="utf-8")
    try:
        raw = (
            json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
        )
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        report.add_error(
            "file",
            f"the file is not valid {path.suffix.lstrip('.') or 'YAML'}: {exc}",
            hint="Check indentation and that every '-' list item lines up.",
        )
        return report

    _validate_document(raw, report)
    return report


def _validate_document(raw: Any, report: ValidationReport) -> None:
    if raw is None:
        report.add_error("file", "the file is empty.")
        return
    if not isinstance(raw, dict):
        report.add_error(
            "file", "the top level must be a mapping with a 'rules:' list."
        )
        return

    doc = cast(dict[str, Any], raw)
    rules = doc.get("rules")
    if rules is None:
        report.add_error("file", "missing the top-level 'rules:' list.")
        return
    if not isinstance(rules, list) or not rules:
        report.add_error("rules", "'rules' must be a non-empty list.")
        return

    rule_items = cast(list[Any], rules)
    seen_ids: dict[str, int] = {}
    report.rule_count = len(rule_items)
    for index, rule in enumerate(rule_items):
        _validate_rule(rule, index, seen_ids, report)


def _validate_rule(
    rule: Any, index: int, seen_ids: dict[str, int], report: ValidationReport
) -> None:
    label = f"rule #{index + 1}"
    if not isinstance(rule, dict):
        report.add_error(label, "each rule must be a mapping with 'name' and 'check'.")
        return

    rule = cast(dict[str, Any], rule)
    rule_id = rule.get("id")
    if rule_id is not None:
        rid = str(rule_id)
        label = f"rule {rid}"
        if rid in seen_ids:
            report.add_error(
                label, f"duplicate id '{rid}' (also used by rule #{seen_ids[rid] + 1})."
            )
        else:
            seen_ids[rid] = index

    name = rule.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        report.add_error(label, "missing a non-empty 'name'.")

    if "description" in rule and not isinstance(rule["description"], str):
        report.add_warning(label, "'description' should be text.")

    severity = rule.get("severity", "fail")
    if not _is_valid_enum(severity, VALID_SEVERITIES):
        report.add_error(
            label,
            f"'severity' must be 'fail' or 'escalate' (got {severity!r}).",
        )
    on_missing = rule.get("on_missing", "escalate")
    if not isinstance(on_missing, str) or on_missing.lower() not in VALID_ON_MISSING:
        report.add_error(
            label,
            f"'on_missing' must be one of {sorted(VALID_ON_MISSING)} (got {on_missing!r}).",
        )

    if str(severity).upper() == Verdict.ESCALATE.value and not rule.get("authority"):
        report.add_warning(
            label,
            "severity is 'escalate' but no 'authority' is set; escalations will use a default.",
        )

    check = rule.get("check")
    if check is None:
        report.add_error(label, "missing the 'check:' condition.")
    elif isinstance(check, str):
        _validate_expression_str(check, f"{label} → check", report)
    else:
        _validate_condition(check, f"{label} → check", report)


def _validate_condition(node: Any, loc: str, report: ValidationReport) -> None:
    if not isinstance(node, dict):
        report.add_error(loc, "a condition must be a mapping or an expression string.")
        return
    node = cast(dict[str, Any], node)

    if not node:
        report.add_error(loc, "the condition is empty.")
        return

    # Expression form: {expr: "..."}  — validate the string and stop
    if "expr" in node:
        expr_val = node["expr"]
        if not isinstance(expr_val, str):
            report.add_error(loc, "'expr' must be a string expression.")
            return
        extra = [k for k in node if k not in _EXPR_KEYS]
        if extra:
            report.add_warning(loc, f"unexpected key(s) {extra} alongside 'expr' will be ignored.")
        _validate_expression_str(str(expr_val), loc, report)
        return

    if "all" in node or "any" in node:
        _validate_logical_list(node, loc, report)
        return
    if "not" in node:
        _validate_condition(node["not"], f"{loc} → not", report)
        return
    if "if" in node:
        _validate_if(node, loc, report)
        return
    for quant in ("for_each", "any_of", "none_of", "count"):
        if quant in node:
            _validate_quantifier(quant, node[quant], loc, report)
            return
    if "field" in node:
        _validate_leaf(node, loc, report)
        return

    report.add_error(
        loc,
        f"unrecognized condition with keys {sorted(node)}.",
        hint="A condition needs one of: field, all, any, not, if, "
        "for_each, any_of, none_of, count — or use an expression string: "
        "check: \"data.amount <= 1000\".",
    )


def _validate_logical_list(
    node: dict[str, Any], loc: str, report: ValidationReport
) -> None:
    key = "all" if "all" in node else "any"
    children = node[key]
    if not isinstance(children, list) or not children:
        report.add_error(
            f"{loc} → {key}", f"'{key}' must be a non-empty list of conditions."
        )
        return
    for i, child in enumerate(cast(list[Any], children)):
        _validate_condition(child, f"{loc} → {key}[{i}]", report)


def _validate_if(node: dict[str, Any], loc: str, report: ValidationReport) -> None:
    _validate_condition(node["if"], f"{loc} → if", report)
    if "then" not in node:
        report.add_error(loc, "an 'if' condition needs a 'then' branch.")
    else:
        _validate_condition(node["then"], f"{loc} → then", report)
    if "else" in node:
        _validate_condition(node["else"], f"{loc} → else", report)


def _validate_quantifier(
    quant: str, spec: Any, loc: str, report: ValidationReport
) -> None:
    qloc = f"{loc} → {quant}"
    if not isinstance(spec, dict):
        report.add_error(
            qloc, f"'{quant}' must be a mapping with a 'field' and 'match'."
        )
        return
    spec = cast(dict[str, Any], spec)

    if not spec.get("field") or not isinstance(spec.get("field"), str):
        report.add_error(qloc, "needs a 'field' naming the array to check.")

    _warn_unknown_keys(spec, _QUANTIFIER_KEYS, qloc, report)

    match = spec.get("match", spec.get("where"))
    if quant == "count":
        op = spec.get("op")
        if op not in BINARY_OPERATORS:
            report.add_error(
                qloc,
                f"'count' needs a comparison 'op' (got {op!r}).",
                hint=_suggest_operator(op),
            )
        if "value" not in spec:
            report.add_error(
                qloc, "'count' needs a 'value' to compare the count against."
            )
        if match is not None:
            if isinstance(match, str):
                _validate_expression_str(match, f"{qloc} \u2192 match", report)
            else:
                _validate_condition(match, f"{qloc} \u2192 match", report)
    else:
        if match is None:
            report.add_error(
                qloc, f"'{quant}' needs a 'match' condition applied to each element."
            )
        elif isinstance(match, str):
            _validate_expression_str(match, f"{qloc} \u2192 match", report)
        else:
            _validate_condition(match, f"{qloc} → match", report)


def _validate_leaf(node: dict[str, Any], loc: str, report: ValidationReport) -> None:
    field_path = node.get("field")
    if not field_path or not isinstance(field_path, str):
        report.add_error(
            loc, "'field' must be a non-empty dotted path like 'data.amount'."
        )

    op = node.get("op", "required")
    _warn_unknown_keys(node, _LEAF_KEYS, loc, report)

    if op in UNARY_OPERATORS:
        if "value" in node or "field_value" in node:
            report.add_warning(loc, f"operator '{op}' ignores 'value'/'field_value'.")
        return

    if op not in BINARY_OPERATORS:
        report.add_error(loc, f"unknown operator '{op}'.", hint=_suggest_operator(op))
        return

    if "value" not in node and "field_value" not in node:
        report.add_error(
            loc,
            f"operator '{op}' needs a 'value' (a literal) or 'field_value' (another field).",
        )
    if "value" in node and "field_value" in node:
        report.add_warning(
            loc, "both 'value' and 'field_value' set; 'field_value' wins."
        )
    if op == "between":
        val: Any = node.get("value")
        if (
            not isinstance(val, (list, tuple))
            or len(cast("list[Any] | tuple[Any, ...]", val)) != 2
        ):
            report.add_error(
                loc, "'between' needs a two-item 'value' like [low, high]."
            )


def _warn_unknown_keys(
    node: dict[str, Any], allowed: set[str], loc: str, report: ValidationReport
) -> None:
    unknown = [k for k in node if k not in allowed]
    if unknown:
        report.add_warning(loc, f"unexpected key(s) {unknown} will be ignored.")


def _suggest_operator(op: Any) -> str:
    if isinstance(op, str):
        close = difflib.get_close_matches(op, ALL_OPERATORS, n=3)
        if close:
            return f"Did you mean: {', '.join(close)}?"
    return f"Valid operators: {', '.join(ALL_OPERATORS)}."


def _validate_expression_str(
    text: str, loc: str, report: ValidationReport
) -> None:
    """Try to parse *text* as an expression; surface any ExpressionError."""
    from .expressions import ExpressionError, parse_expression  # noqa: PLC0415

    try:
        parse_expression(text)
    except ExpressionError as exc:
        report.add_error(
            loc,
            f"invalid expression: {exc.message}",
            hint=(
                f"at position {exc.pos} in: {text!r}"
                if exc.pos >= 0
                else f"in expression: {text!r}"
            ),
        )


def _is_valid_enum(value: Any, allowed: set[Verdict]) -> bool:
    try:
        return Verdict(str(value).upper()) in allowed
    except ValueError:
        return False
