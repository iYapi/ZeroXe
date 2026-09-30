from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class Department:
    id: str
    name: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Department":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
        )