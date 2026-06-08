"""
End-processing action tools for automated process adjudication.

After ``run_checks`` returns a verdict, a process skill calls one of these tools
to perform the *terminal* action for the case:

* ``complete_processing`` — finalize a decided case (PASS -> approve, FAIL ->
  deny). This is the "pass action" / "fail action" hook: the single place where
  real downstream processing (payment, EOB generation, denial letter) would be
  invoked. For now it logs the action to demonstrate feasibility.
* ``log_escalation`` — when the case status is ESCALATE, record an audit entry
  for each responsible authority with the *full* case detail so the authority
  has everything needed to review and dispose of the case.

These tools never raise; they return a JSON-serializable confirmation dict.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from agent_framework import tool

logger = logging.getLogger("signalweave.actions")

# Maps a terminal outcome to the concrete downstream action that would run in a
# real system. Kept here so the mapping is data, not branching logic.
_OUTCOME_ACTIONS: dict[str, str] = {
    "pass": "auto-approved for payment",
    "fail": "denied and returned to sender",
}


def _reference(prefix: str) -> str:
    """Generate a short, unique, human-quotable reference id for an action."""
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _complete_processing(
    process: str,
    work_id: str,
    outcome: str,
    report: dict[str, Any],
    case_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plain (untooled) implementation, for direct testing."""
    normalized = str(outcome).strip().lower()
    if normalized not in _OUTCOME_ACTIONS:
        return {
            "logged": False,
            "error": (
                f"Unsupported outcome '{outcome}'. "
                "Expected 'pass' or 'fail'."
            ),
        }

    reference = _reference("PROC")
    action = _OUTCOME_ACTIONS[normalized]
    case_status = (report or {}).get("case_status", "UNKNOWN")

    record: dict[str, Any] = {
        "reference": reference,
        "timestamp": _now(),
        "process": process,
        "work_id": work_id,
        "outcome": normalized.upper(),
        "action": action,
        "case_status": case_status,
        "report": report,
        "case_detail": case_detail or {},
    }
    logger.info(
        "PROCESSING COMPLETE [%s] process=%s work_id=%s outcome=%s action=%s\n%s",
        reference,
        process,
        work_id,
        normalized.upper(),
        action,
        json.dumps(record, indent=2, default=str),
    )

    return {
        "logged": True,
        "reference": reference,
        "process": process,
        "work_id": work_id,
        "outcome": normalized.upper(),
        "action": action,
        "case_status": case_status,
    }


def _log_escalation(
    process: str,
    work_id: str,
    report: dict[str, Any],
    case_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plain (untooled) implementation, for direct testing."""
    escalations: list[dict[str, Any]] = list((report or {}).get("escalations") or [])
    if not escalations:
        return {
            "logged": False,
            "error": (
                "No escalations present in the report; nothing to log. "
                "Only call this tool when case_status is ESCALATE."
            ),
        }

    logged: list[dict[str, Any]] = []
    for esc in escalations:
        authority = esc.get("authority", "Process Owner")
        reference = _reference("ESC")
        record: dict[str, Any] = {
            "reference": reference,
            "timestamp": _now(),
            "process": process,
            "work_id": work_id,
            "authority": authority,
            "check_id": esc.get("check_id"),
            "context": esc.get("context"),
            "case_status": (report or {}).get("case_status", "ESCALATE"),
            # Full detail so the authority can review the entire case.
            "report": report,
            "case_detail": case_detail or {},
        }
        logger.warning(
            "ESCALATION LOGGED [%s] authority=%s process=%s work_id=%s check=%s\n%s",
            reference,
            authority,
            process,
            work_id,
            esc.get("check_id"),
            json.dumps(record, indent=2, default=str),
        )
        logged.append(
            {
                "reference": reference,
                "authority": authority,
                "check_id": esc.get("check_id"),
                "context": esc.get("context"),
            }
        )

    return {
        "logged": True,
        "process": process,
        "work_id": work_id,
        "escalation_count": len(logged),
        "escalations": logged,
    }


@tool
def complete_processing(
    process: str,
    work_id: str,
    outcome: str,
    report: dict[str, Any],
    case_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform the terminal action for a decided case (the PASS / FAIL hook).

    Call this exactly once after ``run_checks`` when the case is fully decided
    and does NOT require escalation: ``outcome='pass'`` approves the case for
    downstream processing, ``outcome='fail'`` denies and returns it. This is
    where real end processing (payment, denial notice) would be triggered; for
    now the action is logged for audit.

    Args:
        process: The process / skill name (e.g. ``health-claim-adjudication``).
        work_id: The work item / claim id the action applies to.
        outcome: ``'pass'`` (approve) or ``'fail'`` (deny).
        report: The full report returned by ``run_checks``.
        case_detail: The original payload / work item, for the audit record.

    Returns:
        A confirmation dict with ``logged``, a generated ``reference`` id, and
        the ``action`` taken. On an unsupported outcome, returns ``logged:
        False`` and an ``error``.
    """
    return _complete_processing(process, work_id, outcome, report, case_detail)


@tool
def log_escalation(
    process: str,
    work_id: str,
    report: dict[str, Any],
    case_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log an escalation for each responsible authority with full case detail.

    Call this after ``run_checks`` when the case status is ESCALATE. For every
    escalation in the report, this records an audit entry addressed to the
    named ``authority`` containing the full report and case detail, so the
    authority has everything required to review and dispose of the case.

    Args:
        process: The process / skill name (e.g. ``health-claim-adjudication``).
        work_id: The work item / claim id being escalated.
        report: The full report returned by ``run_checks`` (must contain
            ``escalations``).
        case_detail: The original payload / work item, attached to each entry.

    Returns:
        A confirmation dict with ``logged``, ``escalation_count``, and a per
        authority list of generated ``reference`` ids. If the report has no
        escalations, returns ``logged: False`` and an ``error``.
    """
    return _log_escalation(process, work_id, report, case_detail)
