"""
Claims Intake System loader.

Source of record for the core claim facts a member's provider submitted: the
claim identifier, the linking member id and provider NPI (used to fan out to the
other source systems), the coded services, and the billed amount.
"""

from typing import Any

from agent_framework import tool

# Core claim facts as captured by the claims intake system, keyed by claim id.
# CLM-1001 -> clean (PASS), CLM-2002 -> coding/doc gaps + overbilled (FAIL),
# CLM-3003 -> high-dollar surgical claim that trips escalations (ESCALATE).
_CLAIMS: dict[str, dict[str, Any]] = {
    "CLM-1001": {
        "claim_id": "CLM-1001",
        "member_id": "M-558201",
        "member_name": "Jordan Avery",
        "provider_npi": "1457382910",
        "service_date": "2026-05-12",
        "diagnosis_code": "J20.9",
        "procedure_code": "99213",
        "documentation_complete": True,
        "billed_amount": 240.00,
    },
    "CLM-2002": {
        "claim_id": "CLM-2002",
        "member_id": "M-771043",
        "member_name": "Priya Nair",
        "provider_npi": "1902846571",
        "service_date": "2026-04-03",
        "diagnosis_code": "M54.5",
        "procedure_code": None,
        "documentation_complete": False,
        "billed_amount": 1850.00,
    },
    "CLM-3003": {
        "claim_id": "CLM-3003",
        "member_id": "M-330987",
        "member_name": "Marcus Delgado",
        "provider_npi": "1730024856",
        "service_date": "2026-05-28",
        "diagnosis_code": "K35.80",
        "procedure_code": "44970",
        "documentation_complete": True,
        "billed_amount": 18750.00,
    },
}


@tool
def load_claim(claim_id: str) -> dict[str, Any]:
    """Load core claim facts from the Claims Intake System.

    This is the entry-point loader: the returned ``member_id`` and
    ``provider_npi`` are used to look up the remaining source systems
    (eligibility, provider network, etc.).

    Args:
        claim_id: The claim identifier (e.g. ``CLM-1001``).

    Returns:
        ``{"claim": {...}}`` ready to be merged into the ``data`` payload for
        ``run_checks``. On an unknown id, returns an ``error`` plus available
        claim ids.
    """
    claim = _CLAIMS.get(claim_id)
    if claim is None:
        return {
            "error": f"No claim found for id '{claim_id}'.",
            "available_claim_ids": sorted(_CLAIMS),
        }
    return {"claim": dict(claim)}
