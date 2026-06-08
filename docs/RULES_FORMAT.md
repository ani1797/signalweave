# SignalWeave Standard Rule Format

Every process declares its checks in a single file at
`signalweave/skills/<process>/references/rules.yaml`. The deterministic engine in the
`signalweave/checks/` package loads this file, evaluates a data payload against it, and
returns results matching the schema in [`instructions.txt`](../signalweave/instructions.txt).

## File shape

```yaml
process: health-claim-adjudication  # optional; defaults to the skill folder name
description: Short summary       # optional
rules:
  - id: R001
    name: Claim number required
    description: Every claim must carry a claim number.
    severity: fail               # fail (default) | escalate
    on_missing: fail             # fail | escalate (default) | skip
    authority: Claims Supervisor # used only when a result is ESCALATE
    check:                        # condition that must be TRUE for PASS
      field: data.claim_number
      op: required
```

## Rule fields

| Field         | Required | Description |
|---------------|----------|-------------|
| `id`          | no\*     | Stable id (e.g. `R001`). Auto-assigned if omitted. |
| `name`        | yes      | Short human-readable name. |
| `description` | no       | What the rule enforces and why. |
| `check`       | yes      | Condition tree **or** expression string (see below). |
| `severity`    | no       | Verdict when `check` is FALSE: `fail` (default) or `escalate`. |
| `on_missing`  | no       | When required data is absent: `escalate` (default), `fail`, or `skip`. |
| `authority`   | no       | Escalation authority, surfaced when the result is `ESCALATE`. |

\* Recommended for traceability.

## Structured form (condition tree)

A condition node is exactly one of: a **leaf**, a **logical** node, a
**conditional** node, or an **array quantifier**. They nest arbitrarily, which
covers complex field rules.

### 1. Field existence

```yaml
check: { field: data.claim_number, op: exists }     # field is present
check: { field: data.legacy_id,    op: not_exists } # field must be absent
```

### 2. Required / empty fields

```yaml
check: { field: data.diagnosis_code, op: required } # present AND non-empty
check: { field: data.notes,          op: empty }    # absent OR empty
```

### 3. Field value comparisons

```yaml
check: { field: data.billed_amount,  op: lte, value: 1000 }
check: { field: data.currency,       op: eq,  value: USD }
check: { field: data.claim_type,     op: in,  value: [Medical, Dental, Vision] }
check: { field: data.claim_ref,      op: regex, value: "^CLM-" }
```

Operators: `eq` `ne` `gt` `gte` `lt` `lte` `in` `not_in` `contains`
`not_contains` `regex` `starts_with` `ends_with` `between` `len_eq` `len_gt`
`len_lt`. Presence operators (no operand): `exists` `not_exists` `required`
`empty`.

### 4. Field-to-field comparisons

Compare one field to another with `field_value` instead of `value`:

```yaml
check: { field: data.paid_amount, op: lte, field_value: data.billed_amount }
```

Combine several fields with logical nodes:

```yaml
check:
  all:                                   # every child must pass (AND)
    - { field: data.claim_type,      op: required }
    - { field: data.diagnosis_code,  op: required }
check:
  any:                                   # at least one child must pass (OR)
    - { field: data.email, op: required }
    - { field: data.phone, op: required }
check:
  not: { field: data.status, op: eq, value: voided }   # negation
```

### 5. Complex / conditional rules

```yaml
check:
  if:   { field: data.claim_type, op: eq, value: Pharmacy }
  then: { field: data.ndc_code,   op: required }
  else: { field: data.cpt_code,   op: required }   # 'else' optional
```

When the `if` antecedent is false and there is no `else`, the rule is treated
as not applicable and passes.

### 6. Checks across an object array

Quantifier nodes target a condition at the elements of an array. The inner
`match` condition is evaluated with **each element as its own root**, so its
`field` paths are relative to the element. This lets one check cover several
fields per element.

```yaml
# Every element must satisfy the (multi-field) condition
check:
  for_each:
    field: data.line_items
    match:
      all:
        - { field: procedure_code, op: required }
        - { field: billed_amount,  op: gt, value: 0 }

# At least one element satisfies the condition
check:
  any_of:
    field: data.addresses
    match: { field: type, op: eq, value: primary }

# No element may satisfy the condition
check:
  none_of:
    field: data.line_items
    match: { field: billed_amount, op: gt, value: 10000 }

# Constrain how many elements match (match is optional; omit to count all)
check:
  count:
    field: data.line_items
    match: { field: status, op: eq, value: approved }
    op: between
    value: [1, 3]
```

Quantifier semantics:

| Node       | Passes when |
|------------|-------------|
| `for_each` | every element matches (empty array passes vacuously) |
| `any_of`   | at least one element matches |
| `none_of`  | no element matches |
| `count`    | the number of matching elements satisfies `op`/`value` |

If the targeted field is missing or is not an array, the quantifier is treated
as **missing** and the rule's `on_missing` policy applies.

---

## Expression form

Instead of writing a condition mapping, you can write a natural-language
expression string directly as the `check` value.  The engine parses and
evaluates it safely — no `eval()` is used.

```yaml
# Bare string  (simplest, recommended for new rules)
check: "data.billed_amount <= 1000"

# Mapping form  (use when nesting inside a structured all/any/if node)
check:
  expr: "data.billed_amount <= 1000"
```

Both forms are fully **backward-compatible**: all existing structured-form
rules continue to work exactly as before.

### Grammar reference

Operator precedence (loosest → tightest):

| Level | Form | Description |
|-------|------|-------------|
| 1 | `if C then T else E` | Conditional (ternary) |
| 2 | `A or B` | Boolean OR |
| 3 | `A and B` | Boolean AND |
| 4 | `not A` | Boolean NOT |
| 5 | comparisons | `==` `!=` `>` `>=` `<` `<=` `in` `not in` `between … and …` `is present` `is not present` `is empty` `is not empty` |
| 6 | `A + B`, `A - B` | Addition / subtraction |
| 7 | `A * B`, `A / B` | Multiplication / division |
| 8 | `-A` | Unary minus |
| 9 | literals, field refs, `(…)`, function calls | Primary |

Keywords: `and` `or` `not` `in` `between` `is` `where` `if` `then` `else`
`true` `false` `null`

### Literals

```yaml
check: "data.amount == 100"        # number
check: "data.currency == 'USD'"    # single-quoted string
check: "data.currency == \"USD\""  # double-quoted string
check: "data.flag == true"         # boolean
check: "data.value != null"        # null
check: "data.status in [Active, Pending, Review]"   # bare words in lists become strings
```

### Field references and projections

```yaml
check: "data.claim.amount >= 0"                # dotted path
check: "data.claim_number is present"          # presence predicate
check: "sum(data.line_items[].billed_amount)"  # projection: list[].field
```

### Arithmetic

```yaml
check: "data.base_premium + data.rider_premium == data.total_premium"
check: "data.discount_amount / data.billed_amount <= 0.25"
check: "(data.subtotal - data.discount_amount) == data.net_amount"
```

### Comparisons

```yaml
check: "data.age >= 18"
check: "data.status == 'Active'"
check: "data.amount between 100 and 500"
check: "data.category not in [Excluded, Voided]"
```

### Presence predicates

```yaml
check: "data.policy_number is present"
check: "data.legacy_id is not present"
check: "data.notes is empty"
check: "data.diagnosis_code is not empty"
```

### Built-in functions

| Function | Argument | Returns | Notes |
|----------|----------|---------|-------|
| `count(field)` | field path | number | list length |
| `count(field where pred)` | field path + predicate | number | elements matching predicate |
| `all(field where pred)` | field path + predicate | boolean | every element matches |
| `any(field where pred)` | field path + predicate | boolean | at least one matches |
| `none(field where pred)` | field path + predicate | boolean | no element matches |
| `sum(field[].sub)` | projection | number | sum of numeric values |
| `min(field[].sub)` | projection | number | minimum value |
| `max(field[].sub)` | projection | number | maximum value |
| `avg(field[].sub)` | projection | number | arithmetic mean |
| `length(field)` / `len(field)` | field path | number | string or list length |
| `present(field)` | field path | boolean | alias for `is present` |

Inside a `where` predicate, field paths are **element-relative**, not
`data`-relative. So `any(data.beneficiaries where is_minor == true)` tests the
`is_minor` property of each element in `data.beneficiaries`.

```yaml
check: "count(data.beneficiaries) >= 1"
check: "sum(data.beneficiaries[].share_percentage) == 100"
check: "all(data.beneficiaries where share_percentage > 0)"
check: "none(data.beneficiaries where share_percentage > 100)"
check: "any(data.line_items where status == 'Rejected')"
check: "min(data.line_items[].billed_amount) > 0"
```

### Conditional (ternary)

```yaml
# If condition is false → rule does not apply, passes vacuously
check: "if any(data.beneficiaries where is_minor == true) then data.guardian_id is present"

# With else branch
check: "if data.claim_type == 'Pharmacy' then data.ndc_code is present else data.cpt_code is present"
```

When the `if` antecedent is false and there is no `else`, the engine returns a
`PASS` with reason "precondition not met; rule not applicable" — matching the
behaviour of the structured `if/then` form.

### Equivalence table (structured ↔ expression)

| Structured form | Expression form |
|-----------------|-----------------|
| `{field: data.claim_number, op: exists}` | `data.claim_number is present` |
| `{field: data.notes, op: empty}` | `data.notes is empty` |
| `{field: data.amount, op: lte, value: 1000}` | `data.amount <= 1000` |
| `{field: data.status, op: in, value: [A, B]}` | `data.status in [A, B]` |
| `{field: data.amount, op: between, value: [1, 100]}` | `data.amount between 1 and 100` |
| `{field: a, op: ne, field_value: b}` | `data.a != data.b` |
| `{all: [{field: x, op: required}, {field: y, op: required}]}` | `data.x is present and data.y is present` |
| `{not: {field: data.s, op: eq, value: closed}}` | `not data.s == 'closed'` |
| `{for_each: {field: data.items, match: {field: qty, op: gt, value: 0}}}` | `all(data.items where qty > 0)` |
| `{any_of: {field: data.items, match: {field: status, op: eq, value: ok}}}` | `any(data.items where status == 'ok')` |
| `{count: {field: data.items, op: gte, value: 1}}` | `count(data.items) >= 1` |
| `{if: …antecedent…, then: …consequence…}` | `if … then …` |

---

## Running checks

```bash
python -m signalweave.checks --process health-claim-adjudication --data payload.json        # human summary
python -m signalweave.checks --process health-claim-adjudication --data payload.json --json # JSON
python -m signalweave.checks --rules path/to/rules.yaml --data - < payload.json
python -m signalweave.checks --list                                           # list processes
```

## Validating your rules

After editing a rules file, check it before relying on it. The validator
reports *every* problem at once in plain language — broken YAML, a missing
`name` or `check`, duplicate ids, unknown operators (with suggestions),
invalid `severity`/`on_missing`, malformed conditions, **and expression-string
parse errors**.

```bash
python -m signalweave.checks --validate --process health-claim-adjudication
python -m signalweave.checks --validate --rules signalweave/skills/health-claim-adjudication/references/rules.yaml
```

Exit code is `0` when valid, `1` when there are errors — handy in CI.

## Discovering required fields

To see exactly what data a payload must contain for a process, list the fields
the rules reference (marked `required` or `optional`):

```bash
python -m signalweave.checks --fields --process annuity-beneficiary-designation
```

Fields inside an array quantifier (or expression projection) appear with `[]`,
e.g. `data.beneficiaries[].share_percentage`.
