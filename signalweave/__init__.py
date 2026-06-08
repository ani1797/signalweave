"""SignalWeave — a declarative rule-evaluation agent on Microsoft Foundry.

The package is intentionally light at import time so the standalone check
engine (``python -m signalweave.checks``) can be used without pulling in the
agent-framework runtime. Import :func:`signalweave.app.main` for the hosted
agent entrypoint.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
