# Annuity Beneficiary Designation

This skill validates a beneficiary designation request for an annuity policy
against the standard designation rules.

## When to use

Use this skill when a user or downstream system submits an annuity beneficiary
designation request and needs a structured compliance verdict before the change
is committed.

## Required information

Ask for (or extract from context):
- `request_id` — the designation request identifier (e.g. `BEN-PASS-001`)

## Workflow

1. Call `load_beneficiary_case(request_id=<id>)`.
   - If the result contains `"error"`, inform the user and stop.
2. Extract the `data` field from the returned payload.
3. Call `run_checks(process="annuity-beneficiary-designation", payload=<data>)`.
4. Render the result clearly:
   - **PASS** → confirm the designation meets all policy rules.
   - **FAIL** → list each failing rule with its reason; do **not** re-judge.
   - **ESCALATE** → state which rule triggered escalation and the escalation
     authority; do **not** approve or deny yourself.
5. Do **not** call `complete_processing` or `log_escalation` unless the user
   explicitly asks you to proceed.

## Output format

Present the verdict as a short summary followed by a rule-by-rule breakdown:

```
Verdict: PASS / FAIL / ESCALATE

Rule results:
  ✓ policy-number-present — field 'data.policy_number' is present
  ✓ at-least-one-beneficiary — count(data.beneficiaries) = 2 satisfies >= 1
  ✗ shares-sum-to-100 — sum = 80.0 does not satisfy == 100.0
  ...
```

Never add your own judgements about whether the policy change *should* be
approved — the rule engine output is the authoritative verdict.
