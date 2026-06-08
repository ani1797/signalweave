"""
Provider Network & Pricing System loader.

Source of record for whether the rendering provider is in network and the
contracted allowed amount used to price the claim. Keyed by provider NPI
(obtained from the claim).
"""

from typing import Any

from agent_framework import tool

# Provider network + contracted pricing records keyed by NPI.
_PROVIDERS: dict[str, dict[str, Any]] = {
    "1457382910": {
        "provider_npi": "1457382910",
        "provider_name": "Lakeside Family Medicine",
        "in_network": True,
        "allowed_amount": 240.00,
    },
    "1902846571": {
        "provider_npi": "1902846571",
        "provider_name": "Downtown Imaging Center",
        "in_network": True,
        "allowed_amount": 1600.00,
    },
    "1730024856": {
        "provider_npi": "1730024856",
        "provider_name": "Coastal Surgical Associates",
        "in_network": True,
        "allowed_amount": 19000.00,
    },
}


@tool
def load_provider(provider_npi: str) -> dict[str, Any]:
    """Load network status and contracted pricing from the Provider Network System.

    Args:
        provider_npi: The rendering provider's NPI from the claim
            (e.g. ``1457382910``).

    Returns:
        ``{"provider": {...}}`` ready to be merged into the ``data`` payload for
        ``run_checks``. On an unknown NPI, returns an ``error`` plus available
        NPIs.
    """
    record = _PROVIDERS.get(provider_npi)
    if record is None:
        return {
            "error": f"No provider record found for NPI '{provider_npi}'.",
            "available_provider_npis": sorted(_PROVIDERS),
        }
    return {"provider": dict(record)}
