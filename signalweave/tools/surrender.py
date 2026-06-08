"""Mock tool: load annuity full surrender case data.

Used by the ``annuity-full-surrender`` skill.  Returns a canned payload for one
of three test case IDs so the agent can exercise the rule engine without a real
back-end connection.

Test cases
----------
* ``SURR-PASS-001`` — clean full surrender; all checks pass.
* ``SURR-FAIL-001`` — unsigned form and a net-surrender-value that does not
  reconcile; two ``fail`` rules trigger.
* ``SURR-ESC-001``  — under-59½ owner with no tax acknowledgement, an
  above-threshold contract value, and a replacement without a suitability
  review; three ``escalate`` rules trigger.
"""

from __future__ import annotations

from typing import Any

from agent_framework import tool  # type: ignore[import]


@tool
def load_surrender_case(request_id: str) -> dict[str, Any]:
    """Retrieve annuity full surrender data for the given *request_id*.

    Returns a structured payload whose ``data`` object holds every field the
    rules reference, so it can be passed directly to
    ``run_checks(process="annuity-full-surrender", payload=...)``.

    Recognized request IDs
    ----------------------
    * ``SURR-PASS-001`` — all checks pass
    * ``SURR-FAIL-001`` — unsigned form + net surrender value mismatch
    * ``SURR-ESC-001``  — early-withdrawal, large amount, and replacement → escalation

    Any other ID returns a ``{"error": "..."}`` mapping.
    """
    cases: dict[str, dict[str, Any]] = {
        "SURR-PASS-001": {
            "request_id": "SURR-PASS-001",
            "policy_number": "ANN-2021-04567",
            "data": {
                "policy_number": "ANN-2021-04567",
                "contract_status": "in_force",
                "surrender_type": "full",
                "signed_surrender_form": True,
                "contract_value": 120000.0,
                "surrender_charge": 2400.0,
                "market_value_adjustment": 600.0,
                "outstanding_loan_balance": 0.0,
                "net_surrender_value": 118200.0,  # 120000 - 2400 + 600 - 0
                "federal_withholding": 11820.0,
                "state_withholding": 2364.0,
                "net_payout": 104016.0,  # 118200 - 11820 - 2364
                "surrender_charge_period_remaining_years": 2,
                "owner_age": 67,
                "auto_process_threshold": 250000.0,
                "replacement_flag": False,
            },
        },
        "SURR-FAIL-001": {
            "request_id": "SURR-FAIL-001",
            "policy_number": "ANN-2019-08891",
            "data": {
                "policy_number": "ANN-2019-08891",
                "contract_status": "in_force",
                "surrender_type": "full",
                "signed_surrender_form": False,  # fails surrender-form-signed
                "contract_value": 60000.0,
                "surrender_charge": 1800.0,
                "market_value_adjustment": -300.0,
                "outstanding_loan_balance": 4000.0,
                # computed value is 53900.0; stated value below is wrong
                "net_surrender_value": 55000.0,  # fails net-surrender-value-correct
                "federal_withholding": 5500.0,
                "state_withholding": 1100.0,
                "net_payout": 48400.0,  # 55000 - 5500 - 1100 (consistent with stated value)
                "surrender_charge_period_remaining_years": 1,
                "owner_age": 72,
                "auto_process_threshold": 250000.0,
                "replacement_flag": False,
            },
        },
        "SURR-ESC-001": {
            "request_id": "SURR-ESC-001",
            "policy_number": "ANN-2023-01122",
            "data": {
                "policy_number": "ANN-2023-01122",
                "contract_status": "in_force",
                "surrender_type": "full",
                "signed_surrender_form": True,
                "contract_value": 480000.0,  # exceeds auto_process_threshold → escalate
                "surrender_charge": 19200.0,
                "market_value_adjustment": 1200.0,
                "outstanding_loan_balance": 0.0,
                "net_surrender_value": 462000.0,  # 480000 - 19200 + 1200 - 0
                "federal_withholding": 46200.0,
                "state_withholding": 9240.0,
                "net_payout": 406560.0,  # 462000 - 46200 - 9240
                "surrender_charge_period_remaining_years": 3,
                "owner_age": 47,  # under 59.5 ...
                "acknowledged_tax_penalty": False,  # ... with no acknowledgement → escalate
                "auto_process_threshold": 250000.0,
                "replacement_flag": True,  # replacement without suitability review → escalate
                "suitability_review_complete": False,
            },
        },
    }

    if request_id not in cases:
        return {
            "error": (
                f"No surrender case found for request_id '{request_id}'. "
                "Known test IDs: SURR-PASS-001, SURR-FAIL-001, SURR-ESC-001."
            )
        }

    return cases[request_id]
