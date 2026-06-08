---
name: life-insurance-underwriting
description: Life insurance underwriting skill. It gathers data from heterogeneous source systems (in-memory, REST API, SQL Database, File/CSV), validates against underwriting rules, and performs an end action. Use this skill when the user mentions life insurance underwriting, evaluating a life policy application, or asks to adjudicate an application id.
---

# Pre-requisites

1. Require an `app_id` field (e.g. `APP-1001`).

# Source Systems

This process assembles one application record from heterogeneous source systems. Each loader returns a single namespaced slice; together they form the `data` payload:

| Source system | Tool | Slice key | TYPE |
| ------------- | ---- | --------- | ---- |
| Application Intake | `load_application` | `application` | in-memory |
| Medical Bureau API | `load_medical_report` | `medical` | REST (mock) |
| Lab Results Database | `load_lab_results` | `labs` | DB (mock) |
| Underwriting Rate File | `load_rate_class` | `rates` | file/CSV |

# Step by Step

1. Call `load_application` with the `app_id`. The returned `application` slice contains the identifiers `medical_id`, `lab_id`, and `rate_class` used to look up the other systems.
2. Gather the remaining slices from their respective source systems:
   - `load_medical_report` with `medical_id` (from the application slice).
   - `load_lab_results` with `lab_id` (from the application slice).
   - `load_rate_class` with `rate_class` (from the application slice).
   If any loader returns an `error`, report it and stop — the record is incomplete.
3. Assemble the merged payload by nesting each slice under a single `data` object:

   ```json
   {
     "data": {
       "application": { ...from load_application... },
       "medical": { ...from load_medical_report... },
       "labs": { ...from load_lab_results... },
       "rates": { ...from load_rate_class... }
     }
   }
   ```

4. Call the `run_checks` tool with:
   - `process` = `life-insurance-underwriting`
   - `payload` = the merged payload from step 3
   The tool evaluates the standard-format rules in `references/rules.yaml` deterministically and returns `case_status`, per-check results, and any escalations. Do not re-judge the checks yourself.
5. Perform the end action based on `case_status` (terminal step):
   - **PASS** → call `complete_processing` with `outcome` = `pass`, `process` = `life-insurance-underwriting`, `work_id` = the `app_id`, `report` = the `run_checks` result, and `case_detail` = the merged payload. 
   - **FAIL** → call `complete_processing` with `outcome` = `fail` and the same arguments (policy denied).
   - **ESCALATE** → call `log_escalation` with `process`, `work_id` = the `app_id`, `report` = the `run_checks` result, and `case_detail` = the merged payload. Route it to underwriting supervisors.
6. Render the result using the output format in the agent instructions, and state which end action was taken (and the returned reference id).

# Notes

- This process demonstrates how a skill can draw from any **number** and **type** of source systems.
