---
name: health-claim-adjudication
description: Health insurance medical claim auto-adjudication skill. It gathers a claim record from multiple source systems, validates it against a set of rules, and performs the end action (auto-approve, deny, or escalate). Use this skill when the user mentions Health Claim Adjudication, adjudicating a medical/health insurance claim, or processing a claim by its claim id in the conversation.
---

# Pre-requisites

1. Require a `claim_id` field (e.g. `CLM-1001`).

# Source Systems

This process assembles one claim record from several source systems. Each loader
returns a single namespaced slice; together they form the `data` payload:

| Source system                         | Tool                | Slice key            |
| ------------------------------------- | ------------------- | -------------------- |
| Claims Intake System                  | `load_claim`        | `claim`              |
| Membership / Eligibility System       | `load_eligibility`  | `eligibility`        |
| Provider Network & Pricing System     | `load_provider`     | `provider`           |
| Utilization Management System         | `load_authorization`| `authorization`      |
| Special Investigations / Fraud System | `load_fraud_signal` | `fraud`              |

# Step by Step

1. Call `load_claim` with the `claim_id`. The returned `claim` slice contains the
   `member_id` and `provider_npi` used to look up the other systems.
2. Gather the remaining slices from their source systems:
   - `load_eligibility` with `member_id` (from the claim slice).
   - `load_provider` with `provider_npi` (from the claim slice).
   - `load_authorization` with `claim_id`.
   - `load_fraud_signal` with `claim_id`.
   If any loader returns an `error`, report it and stop — the record is incomplete.
3. Assemble the merged payload by nesting each slice under a single `data` object:

   ```json
   {
     "data": {
       "claim": { ...from load_claim... },
       "eligibility": { ...from load_eligibility... },
       "provider": { ...from load_provider... },
       "authorization": { ...from load_authorization... },
       "fraud": { ...from load_fraud_signal... }
     }
   }
   ```

4. Call the `run_checks` tool with:
   - `process` = `health-claim-adjudication`
   - `payload` = the merged payload from step 3
   The tool evaluates the standard-format rules in `references/rules.yaml`
   deterministically and returns `case_status`, per-check results, and any
   escalations. Do not re-judge the checks yourself.
5. Perform the end action based on `case_status` (this is the terminal step):
   - **PASS** → call `complete_processing` with `outcome` = `pass`, `process` =
     `health-claim-adjudication`, `work_id` = the `claim_id`, `report` = the
     `run_checks` result, and `case_detail` = the merged payload. The claim is
     auto-approved for payment.
   - **FAIL** → call `complete_processing` with `outcome` = `fail` and the same
     arguments. The claim is denied and returned.
   - **ESCALATE** → call `log_escalation` with `process`, `work_id` = the
     `claim_id`, `report` = the `run_checks` result, and `case_detail` = the
     merged payload. Each responsible authority is logged with the full case
     detail for review.
6. Render the result using the output format in the agent instructions, and state
   which end action was taken (and the returned reference id).

# Notes

- The rules live in `references/rules.yaml` in the standard rule format
  documented in `docs/RULES_FORMAT.md`. Field paths are namespaced by source
  system (`data.claim.*`, `data.eligibility.*`, `data.provider.*`,
  `data.authorization.*`, `data.fraud.*`). To change validation behavior, edit
  that file — no code changes needed.
- Two rules compare values that originate in different source systems: H005
  (service date vs. eligibility coverage window) and H008 (billed amount vs.
  contracted allowed amount).
- Always perform exactly one end action (step 5) after `run_checks`. PASS and
  FAIL use `complete_processing`; ESCALATE uses `log_escalation`.
- If `run_checks` reports an unknown process, surface the available processes it
  returns.
