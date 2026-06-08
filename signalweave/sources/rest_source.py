from typing import Any
from .base import DataSource


class RestSource(DataSource):
    """A data source simulating a REST API call."""
    kind = "rest"
    
    def __init__(self, name: str, base_url: str, mocked_responses: dict[str, dict[str, Any]]):
        self.name = name
        self.base_url = base_url
        self._mocked_responses = mocked_responses

    def fetch(self, key: str) -> dict[str, Any]:
        # Simulate an HTTP GET request to f"{self.base_url}/{key}"
        result = self._mocked_responses.get(key)
        if result is None:
            return {
                "error": f"HTTP 404 from {self.base_url}/{key}",
                "available_keys": sorted(self._mocked_responses.keys())
            }
        return result
