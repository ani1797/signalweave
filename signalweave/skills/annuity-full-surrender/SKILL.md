---
name: annuity-full-surrender
description: Annuity full surrender (cash-out) workflow skill. It loads a full-surrender request, validates the contract status, payout arithmetic, and tax/suitability controls against declarative rules, and returns a structured PASS / FAIL / ESCALATE verdict. Use this skill when the user mentions an annuity full surrender, surrendering or cashing out an annuity contract, or asks to process a surrender request by its request id.
---

# Annuity Full Surrender

This skill validates a **full surrender** (complete cash-out) of an annuity
contract against the standard surrender rules: the contract must be in force,
the payout figures must reconcile, and tax/suitability conditions are routed for
human review when triggered.

## When to use

Use this skill when a user or downstream system submits an annuity full
surrender request and needs a deterministic compliance verdict before the
disbursement is committed.

## Required information

Ask for (or extract from context):
- `request_id` — the surrender request identifier (e.g. `SURR-PASS-001`)

## Workflow

1. Call `load_surrender_case(request_id=<id>)`.
   - If the result contains `"error"`, inform the user and stop.
2. The returned payload already contains a `data` object with every field the
   rules reference. Pass that payload straight through.
3. Call `run_checks(process="annuity-full-surrender", payload=<the returned payload>)`.
4. Render the result clearly:
   - **PASS** → confirm the surrender meets all policy rules and the payout
     figures reconcile.
   - **FAIL** → list each failing rule with its reason; do **not** re-judge.
   - **ESCALATE** → state which rule triggered escalation and the escalation
     authority; do **not** approve or deny yourself.
5. Do **not** call `complete_processing` or `log_escalation` unless the user
   explicitly asks you to proceed.

## What the rules check

| Rule | Meaning |
| ---- | ------- |
| `policy-number-present` | A policy number is on the request. |
| `contract-in-force` | The contract status is `in_force`. |
| `surrender-type-full` | The request is a full (not partial) surrender. |
| `surrender-form-signed` | A signed surrender request form is present. |
| `surrender-charge-non-negative` | The surrender charge (CDSC) is not negative. |
| `net-surrender-value-correct` | `contract_value − surrender_charge + market_value_adjustment − outstanding_loan_balance` equals `net_surrender_value`. |
| `net-payout-after-withholding` | `net_surrender_value − federal_withholding − state_withholding` equals `net_payout`. |
| `net-payout-positive` | The owner receives a positive payout. |
| `surrender-charge-consistent` | A surrender charge applies while still inside the surrender-charge period. |
| `early-withdrawal-tax-review` *(escalate)* | Owners under 59½ must acknowledge the tax penalty → **Annuity Tax Compliance Desk**. |
| `large-surrender-review` *(escalate)* | Contract value above the auto-process threshold → **Annuity Operations Supervisor**. |
| `replacement-suitability-review` *(escalate)* | A replacement / 1035 exchange needs a completed suitability review → **Suitability Review Committee**. |

## Canned scenarios

| Request id | Outcome | Why |
| ---------- | ------- | --- |
| `SURR-PASS-001` | **PASS** | In-force contract; payout figures reconcile; owner is 67; amount under threshold. |
| `SURR-FAIL-001` | **FAIL** | Surrender form not signed; stated net surrender value does not match the computed value. |
| `SURR-ESC-001`  | **ESCALATE** | Owner is 47 without a tax-penalty acknowledgement (Tax Compliance Desk); `$480,000` exceeds the auto-process threshold (Operations Supervisor); replacement flagged with no suitability review (Suitability Review Committee). |

## Output format

Present the verdict as a short summary followed by a rule-by-rule breakdown:

```
Verdict: PASS / FAIL / ESCALATE

Rule results:
  ✓ policy-number-present — field 'data.policy_number' is present
  ✓ contract-in-force — data.contract_status == 'in_force'
  ✗ surrender-form-signed — data.signed_surrender_form == true is false
  ...
```

Never add your own judgement about whether the surrender *should* be approved —
the rule engine output is the authoritative verdict.
