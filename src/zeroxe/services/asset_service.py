"""Asset Service.

Fetches asset data from Kitsu via Gazu and maps to asset domain models.
"""

from typing import List, Optional
import gazu
from zeroxe.models.asset_model import Asset, AssetType

class AssetService:
    @staticmethod
    def get_assets_by_project_id(project_id: str) -> List[Asset]:
        """Fetches assets by its project ID."""
        raw_assets = gazu.asset.all_assets_for_project(project_id)
        asset_types = AssetService.get_asset_types_by_project_id(project_id)

        type_lookup = {
            (at.id if hasattr(at, "id") else at["id"]): (at.name if hasattr(at, "name") else at["name"])
            for at in asset_types
        }

        for asset in raw_assets:
            type_id = asset.get("entity_type_id")
            asset["entity_type"] = type_lookup.get(type_id)

        return [Asset.from_kitsu(p) for p in raw_assets]

    @staticmethod
    def get_asset_types_by_project_id(project_id: str) -> List[AssetType]:
        """Fetches assets by its project ID."""
        raw_asset_types = gazu.asset.all_asset_types_for_project(project_id)
        return [AssetType.from_kitsu(p) for p in raw_asset_types]