from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    """Base class for all data sources."""
    
    name: str = "Unknown"
    kind: str = "unknown"

    @abstractmethod
    def fetch(self, key: str) -> dict[str, Any]:
        """Fetch data for the given key.
        
        Returns:
            A dictionary containing the data slice, or an error mapping.
        """
        pass
