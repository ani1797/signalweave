"""Dotted field-path resolution for nested payloads.

Supports dict keys and list indices, e.g. ``data.items.0.name``.
"""

from __future__ import annotations

from typing import Any

# Sentinel that means "the path did not resolve to anything".
MISSING = object()


def resolve_path(data: Any, path: str) -> Any:
    """Resolve a dotted ``path`` against ``data``.

    Returns the value at ``path`` or :data:`MISSING` if any segment is absent.
    """
    if path in ("", None):
        return data

    current = data
    for segment in str(path).split("."):
        if isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not _is_int(segment):
                return MISSING
            index = int(segment)
            if index < 0 or index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def is_empty(value: Any) -> bool:
    """True when a present value counts as 'empty' for required-field checks."""
    if value is MISSING or value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _is_int(text: str) -> bool:
    try:
        int(text)
        return True
    except (TypeError, ValueError):
        return False
