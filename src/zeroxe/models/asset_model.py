from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Asset:
    id: str
    name: str
    asset_type_id: str
    asset_type: str
    file_preview_id: str
    project_id: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Asset":
        custom_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        preview_id = (
            data.get("preview_file_id")
            or data.get("file_preview_id")
            or data.get("thumbnail_id")
            or custom_data.get("preview_file_id")
            or custom_data.get("file_preview_id")
            or custom_data.get("thumbnail_id")
            or ""
        )
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            asset_type_id=data.get("entity_type_id", ""),
            asset_type=data.get("entity_type", ""),
            file_preview_id=str(preview_id) if preview_id else "",
            project_id=data.get("project_id", "") or "",
        )

    @property
    def preview_file_id(self) -> str:
        return self.file_preview_id


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