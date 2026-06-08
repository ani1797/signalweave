from typing import Any
from .base import DataSource


class SqlSource(DataSource):
    """A data source simulating a SQL Database."""
    kind = "db"
    
    def __init__(self, name: str, connection_string: str, table: str, mocked_rows: dict[str, dict[str, Any]]):
        self.name = name
        self.connection_string = connection_string
        self.table = table
        self._mocked_rows = mocked_rows

    def fetch(self, key: str) -> dict[str, Any]:
        # Simulate: SELECT * FROM {self.table} WHERE id = '{key}'
        result = self._mocked_rows.get(key)
        if result is None:
            return {
                "error": f"No row found in {self.table} for id '{key}' (simulated via {self.connection_string})",
                "available_keys": sorted(self._mocked_rows.keys())
            }
        return result
