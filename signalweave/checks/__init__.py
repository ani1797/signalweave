"""Deterministic rule/check engine for SignalWeave.

Evaluates a data payload against a set of declarative checks written in the
standard rule format (see ``docs/RULES_FORMAT.md``) and returns results that match
the output schema defined in ``instructions.txt``.

Public API::

    from signalweave.checks import evaluate, load_ruleset, find_ruleset_for_process

    ruleset = find_ruleset_for_process("health-claim-adjudication", "skills")
    report = evaluate(ruleset, payload)
    print(report.to_summary())     # human-readable
    print(report.to_dict())        # machine-readable (instructions schema)
"""

from .conditions import RuleFormatError, evaluate_condition
from .engine import evaluate
from .fields import FieldUsage, collect_required_fields
from .loader import find_ruleset_for_process, list_processes, load_ruleset
from .models import (
    CheckResult,
    Escalation,
    EvaluationReport,
    Rule,
    RuleSet,
    Verdict,
)
from .validation import ValidationIssue, ValidationReport, validate_file

__all__ = [
    "CheckResult",
    "Escalation",
    "EvaluationReport",
    "FieldUsage",
    "Rule",
    "RuleFormatError",
    "RuleSet",
    "ValidationIssue",
    "ValidationReport",
    "Verdict",
    "collect_required_fields",
    "evaluate",
    "evaluate_condition",
    "find_ruleset_for_process",
    "list_processes",
    "load_ruleset",
    "validate_file",
]
