# Copyright (c) Microsoft. All rights reserved.
"""SignalWeave entrypoint.

Kept at the repository root because the Foundry host (``agentdev``), the
Dockerfile, and the VS Code debug tasks launch the agent via ``main.py``.
The implementation lives in :mod:`signalweave.app`.
"""

from signalweave.app import main

if __name__ == "__main__":
    main()
