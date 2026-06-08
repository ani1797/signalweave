from typing import Any
from .base import DataSource


class InMemorySource(DataSource):
    """A data source backed by an in-memory dictionary."""
    kind = "in-memory"

    def __init__(self, name: str, data: dict[str, dict[str, Any]]):
        self.name = name
        self._data = data

    def fetch(self, key: str) -> dict[str, Any]:
        result = self._data.get(key)
        if result is None:
            return {
                "error": f"Key '{key}' not found in {self.name}.",
                "available_keys": sorted(self._data.keys())
            }
        return result
