"""Agent tool that runs the deterministic check engine for a process.

The agent should:
1. Resolve the process name from the user's request.
2. Load the sub-system data (e.g. via ``load_awd``).
3. Call ``run_checks`` with the process name and that data payload.

The returned report already matches the output schema in ``instructions.txt``.
"""

from typing import Any

from agent_framework import tool

from ..checks import (
    collect_required_fields,
    evaluate,
    find_ruleset_for_process,
    list_processes,
    validate_file,
)
from ..checks.loader import find_rules_path
from ..paths import SKILLS_DIR


@tool
def run_checks(process: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run all declarative checks for a process against a data payload.

    Args:
        process: The process / skill name (e.g. ``rcsa-intake``,
            ``annuity-address-change``).
        payload: The data to validate, typically the work item returned by a
            sub-system loader such as ``load_awd``.

    Returns:
        A report with ``case_status``, per-check results, and any escalations,
        matching the SignalWeave output schema. On an unknown process, returns
        an ``error`` plus the list of available processes.
    """
    try:
        ruleset = find_ruleset_for_process(process, SKILLS_DIR)
    except FileNotFoundError:
        return {
            "error": f"No rule set found for process '{process}'.",
            "available_processes": list_processes(SKILLS_DIR),
        }

    report = evaluate(ruleset, payload)
    return report.to_dict()


@tool
def describe_process(process: str) -> dict[str, Any]:
    """Describe a process: which data fields it needs and whether its rules are valid.

    Use this to tell the user what input is required before running checks, or
    to report problems in a process's rule file.

    Args:
        process: The process / skill name (e.g. ``rcsa-intake``).

    Returns:
        A mapping with ``required_fields`` (each field plus whether it is always
        required and which rules use it) and ``validation`` (integrity report).
        On an unknown process, returns an ``error`` plus available processes.
    """
    try:
        rules_path = find_rules_path(process, SKILLS_DIR)
    except FileNotFoundError:
        return {
            "error": f"No rule set found for process '{process}'.",
            "available_processes": list_processes(SKILLS_DIR),
        }

    validation = validate_file(rules_path)
    result: dict[str, Any] = {
        "process": process,
        "validation": validation.to_dict(),
    }

    # Only introspect fields when the file is structurally sound.
    if validation.is_valid:
        from ..checks import load_ruleset

        ruleset = load_ruleset(rules_path)
        result["required_fields"] = [
            u.to_dict() for u in collect_required_fields(ruleset)
        ]

    return result
