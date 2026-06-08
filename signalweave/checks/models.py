"""Data models for the SignalWeave check engine.

These mirror the output contract declared in ``instructions.txt`` so the
deterministic engine and the agent speak the same language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Outcome of a single check or of the overall case."""

    PASS = "PASS"
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"


# Severity drives what a failing check becomes; missing-data handling drives
# what happens when a check cannot be evaluated because data is absent.
VALID_SEVERITIES = {Verdict.FAIL, Verdict.ESCALATE}
VALID_ON_MISSING = {"fail", "escalate", "skip"}


@dataclass
class Rule:
    """A single declarative rule in the standard format.

    Attributes:
        id: Stable identifier (e.g. ``R001``).
        name: Short human-readable name.
        description: What the rule enforces and why.
        check: The condition tree that must evaluate to TRUE for a PASS.
        severity: Verdict assigned when ``check`` is FALSE (FAIL or ESCALATE).
        on_missing: What to do when required data is absent
            (``fail`` | ``escalate`` | ``skip``).
        authority: Escalation authority surfaced when the result is ESCALATE.
    """

    id: str
    name: str
    check: dict[str, Any] | str
    description: str = ""
    severity: Verdict = Verdict.FAIL
    on_missing: str = "escalate"
    authority: str = ""


@dataclass
class RuleSet:
    """A named collection of rules for one process."""

    process: str
    rules: list[Rule]
    description: str = ""
    source_path: str = ""


@dataclass
class CheckResult:
    """Result of evaluating one rule against the data."""

    id: str
    name: str
    result: Verdict
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "result": self.result.value,
            "reason": self.reason,
        }


@dataclass
class Escalation:
    """An escalation entry surfaced when a check requires human authority."""

    check_id: str
    context: str
    authority: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "context": self.context,
            "authority": self.authority,
        }


@dataclass
class EvaluationReport:
    """Full evaluation outcome, matching the ``instructions.txt`` schema."""

    process: str
    checks: list[CheckResult] = field(default_factory=list)
    escalations: list[Escalation] = field(default_factory=list)

    @property
    def case_status(self) -> Verdict:
        results = {c.result for c in self.checks}
        if Verdict.ESCALATE in results:
            return Verdict.ESCALATE
        if Verdict.FAIL in results:
            return Verdict.FAIL
        return Verdict.PASS

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "case_status": self.case_status.value,
            "checks": [c.to_dict() for c in self.checks],
        }
        if self.escalations:
            out["escalations"] = [e.to_dict() for e in self.escalations]
        return out

    def to_summary(self) -> str:
        """Render the default human-readable summary from ``instructions.txt``."""
        lines = [f"Case Status: {self.case_status.value}", "", "Checks:"]
        for c in self.checks:
            lines.append(f"- [{c.id}] {c.name} — {c.result.value}: {c.reason}")
        if self.escalations:
            lines.append("")
            lines.append("Escalations:")
            for e in self.escalations:
                lines.append(f"- [{e.check_id}] {e.context} | {e.authority}")
        return "\n".join(lines)
