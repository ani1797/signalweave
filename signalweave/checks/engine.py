"""Core evaluation: run every rule in a rule set against a data payload."""

from __future__ import annotations

from typing import Any

from .conditions import evaluate_condition
from .models import (
    CheckResult,
    Escalation,
    EvaluationReport,
    Rule,
    RuleSet,
    Verdict,
)

DEFAULT_AUTHORITY = "Process Owner"


def evaluate(ruleset: RuleSet, data: Any) -> EvaluationReport:
    """Evaluate ``data`` against every rule in ``ruleset``.

    Deterministic: identical inputs always yield an identical report.
    """
    report = EvaluationReport(process=ruleset.process)
    for rule in ruleset.rules:
        result = _evaluate_rule(rule, data)
        if result is None:  # skipped due to on_missing == "skip"
            continue
        report.checks.append(result)
        if result.result is Verdict.ESCALATE:
            report.escalations.append(
                Escalation(
                    check_id=result.id,
                    context=result.reason,
                    authority=rule.authority or DEFAULT_AUTHORITY,
                )
            )
    return report


def _evaluate_rule(rule: Rule, data: Any) -> CheckResult | None:
    outcome = evaluate_condition(rule.check, data)

    if outcome.missing:
        if rule.on_missing == "skip":
            return None
        verdict = Verdict.ESCALATE if rule.on_missing == "escalate" else Verdict.FAIL
        reason = f"Required data missing — {outcome.reason}"
    elif outcome.passed:
        verdict = Verdict.PASS
        reason = outcome.reason
    else:
        verdict = rule.severity
        reason = outcome.reason

    return CheckResult(id=rule.id, name=rule.name, result=verdict, reason=reason)
