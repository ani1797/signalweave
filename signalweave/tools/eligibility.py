"""
Membership / Eligibility System loader.

Source of record for whether a member's coverage is active and the effective and
termination dates of that coverage. Keyed by member id (obtained from the claim).
"""

from typing import Any

from agent_framework import tool

# Coverage records keyed by member id.
_ELIGIBILITY: dict[str, dict[str, Any]] = {
    "M-558201": {
        "member_id": "M-558201",
        "plan_id": "PPO-GOLD-2026",
        "coverage_status": "active",
        "coverage_effective_date": "2026-01-01",
        "coverage_termination_date": "2026-12-31",
    },
    "M-771043": {
        "member_id": "M-771043",
        "plan_id": "HMO-SILVER-2026",
        "coverage_status": "active",
        "coverage_effective_date": "2026-01-01",
        "coverage_termination_date": "2026-12-31",
    },
    "M-330987": {
        "member_id": "M-330987",
        "plan_id": "PPO-PLATINUM-2026",
        "coverage_status": "active",
        "coverage_effective_date": "2026-01-01",
        "coverage_termination_date": "2026-12-31",
    },
}


@tool
def load_eligibility(member_id: str) -> dict[str, Any]:
    """Load coverage status from the Membership / Eligibility System.

    Args:
        member_id: The member identifier from the claim (e.g. ``M-558201``).

    Returns:
        ``{"eligibility": {...}}`` ready to be merged into the ``data`` payload
        for ``run_checks``. On an unknown id, returns an ``error`` plus available
        member ids.
    """
    record = _ELIGIBILITY.get(member_id)
    if record is None:
        return {
            "error": f"No eligibility record found for member '{member_id}'.",
            "available_member_ids": sorted(_ELIGIBILITY),
        }
    return {"eligibility": dict(record)}
