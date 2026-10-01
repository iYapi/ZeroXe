from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Asset:
    id: str
    name: str
    asset_type_id: str
    asset_type: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Asset":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            asset_type_id=data.get("entity_type_id", ""),
            asset_type=data.get("entity_type", ""),
        )

@dataclass
class AssetType:
    id: str
    name: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "AssetType":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
        )