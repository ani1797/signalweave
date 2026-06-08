"""Load rule sets written in the standard format from YAML (or JSON) files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from .models import VALID_ON_MISSING, VALID_SEVERITIES, Rule, RuleSet, Verdict

# Standard location of a process's rules, relative to its skill folder.
RULES_FILENAME = "rules.yaml"
RULES_SUBPATH = Path("references") / RULES_FILENAME


def load_ruleset(path: str | Path) -> RuleSet:
    """Load and validate a :class:`RuleSet` from ``path``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    loaded = _load_structured(path)
    if not isinstance(loaded, dict):
        raise ValueError(f"Rules file must be a mapping at the top level: {path}")
    raw = cast(dict[str, Any], loaded)

    process = raw.get("process") or path.parent.parent.name
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ValueError(f"Rules file '{path}' must contain a non-empty 'rules' list")

    items = cast(list[Any], rules_raw)
    rules = [_parse_rule(item, index, path) for index, item in enumerate(items)]
    return RuleSet(
        process=process,
        rules=rules,
        description=raw.get("description", ""),
        source_path=str(path),
    )


def find_ruleset_for_process(process: str, skills_dir: str | Path) -> RuleSet:
    """Find and load the rule set for ``process`` under ``skills_dir``.

    Matches on the skill folder name (normalized) or the ``process`` field
    declared inside a rules file.
    """
    return load_ruleset(find_rules_path(process, skills_dir))


def find_rules_path(process: str, skills_dir: str | Path) -> Path:
    """Locate the rules file for ``process`` without loading/validating it."""
    skills_dir = Path(skills_dir)
    target = _normalize(process)

    candidate = skills_dir / process / RULES_SUBPATH
    if candidate.exists():
        return candidate

    matches: list[Path] = []
    for rules_file in sorted(skills_dir.glob(f"*/{RULES_SUBPATH.as_posix()}")):
        folder = rules_file.parent.parent.name
        if _normalize(folder) == target:
            return rules_file
        try:
            declared = _load_structured(rules_file).get("process", "")
        except Exception:  # noqa: BLE001 - skip unreadable candidates during discovery
            declared = ""
        if _normalize(declared) == target:
            matches.append(rules_file)

    if len(matches) == 1:
        return matches[0]

    available = ", ".join(list_processes(skills_dir)) or "(none)"
    raise FileNotFoundError(
        f"No rule set found for process '{process}'. Available processes: {available}"
    )


def list_processes(skills_dir: str | Path) -> list[str]:
    """List process names that have a standard rules file."""
    skills_dir = Path(skills_dir)
    processes: list[str] = []
    for rules_file in sorted(skills_dir.glob(f"*/{RULES_SUBPATH.as_posix()}")):
        processes.append(rules_file.parent.parent.name)
    return processes


def _parse_rule(raw_item: Any, index: int, path: Path) -> Rule:
    if not isinstance(raw_item, dict):
        raise ValueError(f"Rule #{index} in '{path}' must be a mapping")
    item = cast(dict[str, Any], raw_item)

    rule_id = str(item.get("id") or f"R{index + 1:03d}")
    name = item.get("name")
    check = item.get("check")
    if not name:
        raise ValueError(f"Rule '{rule_id}' in '{path}' is missing 'name'")
    if not isinstance(check, (dict, str)):
        raise ValueError(
            f"Rule '{rule_id}' in '{path}' is missing a 'check' "
            f"(must be a condition mapping or an expression string)"
        )
    if isinstance(check, dict):
        check = cast(dict[str, Any], check)

    severity = _parse_severity(item.get("severity", "fail"), rule_id)
    on_missing = str(item.get("on_missing", "escalate")).lower()
    if on_missing not in VALID_ON_MISSING:
        raise ValueError(
            f"Rule '{rule_id}': on_missing must be one of {sorted(VALID_ON_MISSING)}"
        )

    return Rule(
        id=rule_id,
        name=str(name),
        description=str(item.get("description", "")),
        check=check,
        severity=severity,
        on_missing=on_missing,
        authority=str(item.get("authority", "")),
    )


def _parse_severity(value: Any, rule_id: str) -> Verdict:
    try:
        verdict = Verdict(str(value).upper())
    except ValueError as exc:
        raise ValueError(
            f"Rule '{rule_id}': severity must be 'fail' or 'escalate'"
        ) from exc
    if verdict not in VALID_SEVERITIES:
        raise ValueError(f"Rule '{rule_id}': severity must be 'fail' or 'escalate'")
    return verdict


def _load_structured(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())
