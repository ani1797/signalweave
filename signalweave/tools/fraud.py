"""
Special Investigations / Fraud Analytics System loader.

Source of record for the model-generated fraud score (0-100) for the claim. A
score at or above the rule threshold routes the claim to the Special
Investigations Unit. Keyed by claim id.
"""

from typing import Any

from agent_framework import tool

# Fraud analytics scores keyed by claim id. CLM-3003 scores high enough to
# trigger an SIU escalation.
_FRAUD_SIGNALS: dict[str, dict[str, Any]] = {
    "CLM-1001": {"claim_id": "CLM-1001", "score": 8, "model_version": "fraud-2026.1"},
    "CLM-2002": {"claim_id": "CLM-2002", "score": 22, "model_version": "fraud-2026.1"},
    "CLM-3003": {"claim_id": "CLM-3003", "score": 84, "model_version": "fraud-2026.1"},
}


@tool
def load_fraud_signal(claim_id: str) -> dict[str, Any]:
    """Load the fraud score from the Special Investigations / Fraud Analytics System.

    Args:
        claim_id: The claim identifier (e.g. ``CLM-1001``).

    Returns:
        ``{"fraud": {...}}`` ready to be merged into the ``data`` payload for
        ``run_checks``. On an unknown id, returns an ``error`` plus available
        claim ids.
    """
    record = _FRAUD_SIGNALS.get(claim_id)
    if record is None:
        return {
            "error": f"No fraud signal found for claim '{claim_id}'.",
            "available_claim_ids": sorted(_FRAUD_SIGNALS),
        }
    return {"fraud": dict(record)}
