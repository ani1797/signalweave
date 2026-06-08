"""Canonical filesystem locations for SignalWeave.

Resolving these once, here, keeps every module agreeing on where the
runtime content lives instead of recomputing ``parent.parent`` chains.
"""

from __future__ import annotations

from pathlib import Path

# .../signalweave
PACKAGE_DIR = Path(__file__).resolve().parent

# Repository root — the package lives one level below it.
PROJECT_ROOT = PACKAGE_DIR.parent

# Runtime content ships *inside* the package so it travels with installs and
# container images. Skills are discovered from SKILL.md files under this dir.
SKILLS_DIR = PACKAGE_DIR / "skills"

# The agent's system instructions.
INSTRUCTIONS_PATH = PACKAGE_DIR / "instructions.txt"

__all__ = ["PACKAGE_DIR", "PROJECT_ROOT", "SKILLS_DIR", "INSTRUCTIONS_PATH"]
