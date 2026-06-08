"""Mock tool: load beneficiary designation case data.

Used by the ``annuity-beneficiary-designation`` skill.  Returns a canned
payload for one of three test case IDs so the agent can exercise the rule
engine without a real back-end connection.

Test cases
----------
* ``BEN-PASS-001`` — valid designation; all checks should pass.
* ``BEN-FAIL-001`` — shares do not sum to 100 %; sum check should fail.
* ``BEN-ESC-001``  — a minor beneficiary with no guardian ID; ternary
  escalation rule should trigger.
"""

from __future__ import annotations

from typing import Any

from agent_framework import tool  # type: ignore[import]


@tool
def load_beneficiary_case(request_id: str) -> dict[str, Any]:
    """Retrieve beneficiary designation data for the given *request_id*.

    Returns a structured payload that the agent can pass directly to
    ``run_checks(process="annuity-beneficiary-designation", payload=...)``.

    Recognized request IDs
    ----------------------
    * ``BEN-PASS-001`` — all checks pass
    * ``BEN-FAIL-001`` — share percentages do not sum to 100
    * ``BEN-ESC-001``  — minor beneficiary without guardian → escalation

    Any other ID returns a ``{"error": "..."}`` mapping.
    """
    cases: dict[str, dict[str, Any]] = {
        "BEN-PASS-001": {
            "request_id": "BEN-PASS-001",
            "policy_number": "ANN-2024-00123",
            "data": {
                "policy_number": "ANN-2024-00123",
                "beneficiaries": [
                    {"name": "Alice Smith",   "share_percentage": 60, "is_minor": False},
                    {"name": "Bob Smith",     "share_percentage": 40, "is_minor": False},
                ],
                "base_premium": 800.0,
                "rider_premium": 200.0,
                "total_premium": 1000.0,
                "annual_contribution_limit": 6000.0,
            },
        },
        "BEN-FAIL-001": {
            "request_id": "BEN-FAIL-001",
            "policy_number": "ANN-2024-00456",
            "data": {
                "policy_number": "ANN-2024-00456",
                "beneficiaries": [
                    {"name": "Carol Jones",  "share_percentage": 50, "is_minor": False},
                    {"name": "David Jones",  "share_percentage": 30, "is_minor": False},
                    # shares sum to 80, not 100 — this should fail the sum rule
                ],
                "base_premium": 500.0,
                "rider_premium": 100.0,
                "total_premium": 600.0,
                "annual_contribution_limit": 6000.0,
            },
        },
        "BEN-ESC-001": {
            "request_id": "BEN-ESC-001",
            "policy_number": "ANN-2024-00789",
            "data": {
                "policy_number": "ANN-2024-00789",
                "beneficiaries": [
                    {"name": "Emma Brown",   "share_percentage": 100, "is_minor": True},
                    # minor beneficiary present but guardian_id is absent
                ],
                "base_premium": 300.0,
                "rider_premium": 50.0,
                "total_premium": 350.0,
                "annual_contribution_limit": 6000.0,
                # guardian_id intentionally omitted
            },
        },
    }

    if request_id not in cases:
        return {
            "error": (
                f"No beneficiary case found for request_id '{request_id}'. "
                "Known test IDs: BEN-PASS-001, BEN-FAIL-001, BEN-ESC-001."
            )
        }

    return cases[request_id]
