# SignalWeave

An automated **rule evaluation agent** built with the [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview) and hosted on Microsoft Foundry.

SignalWeave takes a set of rules plus an input payload, evaluates each rule against the input, and returns a clear **PASS / FAIL** verdict per rule with a concise reason.

## Project Structure

| Path | Purpose |
|------|---------|
| `main.py` | Thin entrypoint at the repo root (required by Foundry `agentdev`, the Dockerfile, and the VS Code debug tasks). Delegates to `signalweave.app`. |
| `signalweave/` | The Python package. |
| `signalweave/app.py` | Agent setup — builds the agent and runs the Foundry hosted HTTP server (`responses` protocol). |
| `signalweave/paths.py` | Canonical filesystem locations (skills dir, instructions). |
| `signalweave/checks/` | Deterministic rule/check engine + CLI (`python -m signalweave.checks`). |
| `signalweave/tools/` | Agent tools: sub-system data loaders (`awd.py`) and the `run_checks`/`describe_process` engine tools. |
| `signalweave/instructions.txt` | The agent's system instructions (edit here to change behavior). |
| `signalweave/skills/<process>/references/rules.yaml` | Per-process rules in the standard format. |
| `docs/RULES_FORMAT.md` | The standard declarative rule format reference. |
| `agent.yaml` | Foundry hosted-agent manifest (name, protocol, resources, env vars). |
| `pyproject.toml` | Packaging metadata, dependencies, and the `signalweave-checks` console script. |
| `.env` | Local configuration (project endpoint + model deployment). Not committed. |
| `.env.example` | Template for `.env`. |
| `.vscode/` | Debug configs for the `agentdev` CLI + Foundry Agent Inspector. |

## How It Works

1. The user names a **process** (e.g. `rcsa-intake`) and supplies an input.
2. The agent selects the matching skill under `signalweave/skills/<process>/`, loads any
   required sub-system data via a tool (e.g. `load_awd`), then calls the
   `run_checks` tool.
3. `run_checks` evaluates the process's `references/rules.yaml`
   **deterministically** with the `signalweave/checks/` engine and returns a report that
   already matches the output schema in `signalweave/instructions.txt`.

Rules are declarative data, so changing validation behavior means editing a
YAML file — no code changes. See [`RULES_FORMAT.md`](docs/RULES_FORMAT.md) for the
full format (existence, required/empty, comparisons, field-to-field, logical
`all`/`any`/`not`, conditional `if/then/else`, and array quantifiers
`for_each`/`any_of`/`none_of`/`count`).

For a full end-to-end walkthrough — gathering data from multiple source systems,
running checks, and taking a terminal action (approve / deny / escalate) — see
[`HOW-TO-USE.md`](docs/HOW-TO-USE.md), which uses the `health-claim-adjudication`
process as a worked example.

## Run Checks Directly (no agent)

The engine ships as a standalone module — give it rules + data, get results:

```bash
python -m signalweave.checks --list                                   # list processes
python -m signalweave.checks --process rcsa-intake --data payload.json # human summary
python -m signalweave.checks --process rcsa-intake --data payload.json --json
python -m signalweave.checks --rules path/to/rules.yaml --data - < payload.json
```

## For Rule Authors (no coding needed)

Rules live in plain YAML at `signalweave/skills/<process>/references/rules.yaml`. After
editing, check your work with the built-in tools:

```bash
# Validate a rules file — reports every problem in plain language
python -m signalweave.checks --validate --process rcsa-intake
python -m signalweave.checks --validate --rules signalweave/skills/rcsa-intake/references/rules.yaml

# List the data fields the rules need (required vs optional)
python -m signalweave.checks --fields --process rcsa-intake
```

Validation catches broken YAML, missing `name`/`check`, duplicate ids, unknown
operators (with "did you mean" suggestions), invalid `severity`/`on_missing`,
and malformed conditions. The agent exposes the same capability through its
`describe_process` tool, so it can tell a user which fields are required before
running checks.

## Configuration

`.env` is already populated for the `internal-platform` Foundry project:

```
FOUNDRY_PROJECT_ENDPOINT="https://aif-internal-platform-ai-prod-eus2.services.ai.azure.com/api/projects/internal-platform"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

To use a different deployed model, change `AZURE_AI_MODEL_DEPLOYMENT_NAME` (e.g. `gpt-5.4`, `gpt-5.4-nano`, `grok-4.3`, `Mistral-Large-3`).

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"   # runtime + local debug tooling
```

The `[dev]` extra adds the local debugger / Foundry Agent Inspector tooling.
For a runtime-only install, use `.venv/bin/python -m pip install .`.

## Run Locally

```bash
az login                  # local auth via DefaultAzureCredential
.venv/bin/python main.py  # serves the responses protocol on http://0.0.0.0:8088
```

Send a test request:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Rules:\n1. amount must be <= 1000\n2. currency must be USD\nPayload: {\"amount\": 1500, \"currency\": \"USD\"}",
    "stream": false
  }'
```

## Debug in VS Code

Press **F5** (or run the *Debug Local Agent/Workflow HTTP Server* configuration) to launch SignalWeave under the debugger and open the Foundry Agent Inspector. Requires the Foundry Toolkit (AI Toolkit) VS Code extension.

## Customize

- **Validation rules** — edit `signalweave/skills/<process>/references/rules.yaml` (see [`RULES_FORMAT.md`](docs/RULES_FORMAT.md)).
- **Add a process** — create `signalweave/skills/<name>/SKILL.md` + `references/rules.yaml`.
- **Behavior / output format** — edit `signalweave/instructions.txt`.
- **Model** — change `AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`.
- **Add tools** — hosted agents access tools through a Foundry Toolbox MCP endpoint.

## Next Steps Toward Production

- **Tracing** — instrument the agent for monitoring and troubleshooting.
- **Evaluation** — measure rule-evaluation accuracy against a test dataset.
- **Deploy** — reply with `Deploy Agent to Foundry` to containerize and deploy SignalWeave.
