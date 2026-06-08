import csv
from pathlib import Path
from typing import Any
from .base import DataSource


class CsvFileSource(DataSource):
    """A data source that reads directly from a CSV file."""
    kind = "file"
    
    def __init__(self, name: str, filepath: Path, key_column: str):
        self.name = name
        self.filepath = filepath
        self.key_column = key_column

    def fetch(self, key: str) -> dict[str, Any]:
        if not self.filepath.exists():
            return {"error": f"File not found: {self.filepath}"}
            
        with open(self.filepath, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            available = []
            for row in reader:
                available.append(row[self.key_column])
                if row[self.key_column] == key:
                    # Parse numeric values optionally, but keeping as string is okay.
                    return {k: (float(v) if v.replace('.', '', 1).isdigit() else v) for k, v in row.items()}
                    
        return {
            "error": f"Value '{key}' not found in column '{self.key_column}' of {self.filepath}",
            "available_keys": available
        }
