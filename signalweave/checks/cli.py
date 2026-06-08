"""Command-line check runner for SignalWeave.

Three modes, all accepting either ``--process <name>`` or ``--rules <file>``:

* **evaluate** (default): run all checks against ``--data`` and print results.
* ``--validate``: check the rules file for integrity (no data needed). Ideal
  for non-technical authors verifying their edits before committing.
* ``--fields``: list the data fields the rules require.

Examples::

    # Evaluate a payload
    python -m signalweave.checks --process health-claim-adjudication --data payload.json
    cat payload.json | python -m signalweave.checks --process health-claim-adjudication --data -

    # Validate a rules file an author just edited
    python -m signalweave.checks --validate --rules signalweave/skills/health-claim-adjudication/references/rules.yaml
    python -m signalweave.checks --validate --process health-claim-adjudication

    # Discover required input fields
    python -m signalweave.checks --fields --process annuity-beneficiary-designation

    # List available processes
    python -m signalweave.checks --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .engine import evaluate
from .fields import collect_required_fields
from .loader import (
    find_rules_path,
    find_ruleset_for_process,
    list_processes,
    load_ruleset,
)
from .models import RuleSet
from .validation import validate_file

# Skills ship inside the package: checks/ -> signalweave/ -> signalweave/skills.
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    skills_dir = Path(args.skills_dir)

    if args.list:
        return _cmd_list(skills_dir)
    if args.validate:
        return _cmd_validate(args, skills_dir)
    if args.fields:
        return _cmd_fields(args, skills_dir)
    return _cmd_evaluate(args, skills_dir)


# --- commands ---------------------------------------------------------------


def _cmd_list(skills_dir: Path) -> int:
    processes = list_processes(skills_dir)
    if processes:
        print("Available processes:")
        for name in processes:
            print(f"  - {name}")
    else:
        print(f"No processes with a rules file found under {skills_dir}")
    return 0


def _cmd_validate(args: argparse.Namespace, skills_dir: Path) -> int:
    try:
        path = _resolve_rules_path(args, skills_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    report = validate_file(path)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_summary())
    return 0 if report.is_valid else 1


def _cmd_fields(args: argparse.Namespace, skills_dir: Path) -> int:
    try:
        ruleset = _resolve_ruleset(args, skills_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    usages = collect_required_fields(ruleset)
    if args.json:
        print(
            json.dumps(
                {"process": ruleset.process, "fields": [u.to_dict() for u in usages]},
                indent=2,
            )
        )
        return 0

    print(f"Data fields used by process '{ruleset.process}':")
    if not usages:
        print("  (none)")
        return 0
    width = max(len(u.path) for u in usages)
    for usage in usages:
        flag = "required" if usage.always_required else "optional"
        rules = ", ".join(sorted(usage.rules))
        print(f"  {usage.path:<{width}}  [{flag}]  ({rules})")
    return 0


def _cmd_evaluate(args: argparse.Namespace, skills_dir: Path) -> int:
    if not (args.process or args.rules):
        print(
            "Error: one of --process, --rules, or --list is required", file=sys.stderr
        )
        return 2
    if not args.data:
        print("Error: --data is required to evaluate checks", file=sys.stderr)
        return 2

    try:
        ruleset = _resolve_ruleset(args, skills_dir)
        data = _load_data(args.data)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    report = evaluate(ruleset, data)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_summary())

    # Exit code reflects the verdict for scripting: 0 PASS, 1 FAIL, 3 ESCALATE.
    return {"PASS": 0, "FAIL": 1, "ESCALATE": 3}[report.case_status.value]


# --- helpers ----------------------------------------------------------------


def _resolve_rules_path(args: argparse.Namespace, skills_dir: Path) -> Path:
    if args.rules:
        return Path(args.rules)
    if args.process:
        return find_rules_path(args.process, skills_dir)
    raise ValueError("one of --process or --rules is required")


def _resolve_ruleset(args: argparse.Namespace, skills_dir: Path) -> RuleSet:
    if args.rules:
        return load_ruleset(args.rules)
    if args.process:
        return find_ruleset_for_process(args.process, skills_dir)
    raise ValueError("one of --process or --rules is required")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m signalweave.checks",
        description="Run, validate, or inspect SignalWeave declarative checks.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--process", help="Process name (skill folder) to target.")
    source.add_argument("--rules", help="Path to a specific rules.yaml/.json file.")
    parser.add_argument("--data", help="Path to JSON/YAML payload, or '-' for stdin.")
    parser.add_argument(
        "--skills-dir",
        default=str(DEFAULT_SKILLS_DIR),
        help=f"Skills directory to search (default: {DEFAULT_SKILLS_DIR}).",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate", action="store_true", help="Validate the rules file's integrity."
    )
    mode.add_argument(
        "--fields", action="store_true", help="List the data fields the rules require."
    )
    mode.add_argument(
        "--list", action="store_true", help="List available processes and exit."
    )

    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    return parser


def _load_data(source: str) -> Any:
    if source == "-":
        text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")
        text = path.read_text(encoding="utf-8")
    # YAML is a superset of JSON, so this handles both formats.
    return yaml.safe_load(text)


if __name__ == "__main__":
    raise SystemExit(main())
