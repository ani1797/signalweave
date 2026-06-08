"""
Utilization Management System loader.

Source of record for prior-authorization requirements and medical-necessity
flags raised for the claim. Keyed by claim id.
"""

from typing import Any

from agent_framework import tool

# Utilization management determinations keyed by claim id. CLM-3003 requires a
# prior authorization that was never obtained and is flagged for medical
# necessity with no clinical review on file -> drives escalations.
_AUTHORIZATIONS: dict[str, dict[str, Any]] = {
    "CLM-1001": {
        "claim_id": "CLM-1001",
        "prior_authorization_required": False,
        "prior_authorization_number": None,
        "medical_necessity_flag": False,
        "clinical_review_id": None,
    },
    "CLM-2002": {
        "claim_id": "CLM-2002",
        "prior_authorization_required": False,
        "prior_authorization_number": None,
        "medical_necessity_flag": False,
        "clinical_review_id": None,
    },
    "CLM-3003": {
        "claim_id": "CLM-3003",
        "prior_authorization_required": True,
        "prior_authorization_number": None,
        "medical_necessity_flag": True,
        "clinical_review_id": None,
    },
}


@tool
def load_authorization(claim_id: str) -> dict[str, Any]:
    """Load prior-auth and medical-necessity determinations from Utilization Management.

    Args:
        claim_id: The claim identifier (e.g. ``CLM-1001``).

    Returns:
        ``{"authorization": {...}}`` ready to be merged into the ``data`` payload
        for ``run_checks``. On an unknown id, returns an ``error`` plus available
        claim ids.
    """
    record = _AUTHORIZATIONS.get(claim_id)
    if record is None:
        return {
            "error": f"No authorization record found for claim '{claim_id}'.",
            "available_claim_ids": sorted(_AUTHORIZATIONS),
        }
    return {"authorization": dict(record)}
