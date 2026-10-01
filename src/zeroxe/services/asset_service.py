"""Asset Service.

Provides fast, optimized querying and in-memory caching for asset types and assets.
"""

import logging
from typing import Dict, List, Optional
import gazu

from zeroxe.models.asset_model import Asset, AssetType

logger = logging.getLogger(__name__)


class AssetService:
    # In-memory cache to make switching between projects and asset types instant (0ms)
    _asset_type_cache: Dict[str, List[AssetType]] = {}
    _asset_cache: Dict[str, List[Asset]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached asset and asset type data."""
        cls._asset_type_cache.clear()
        cls._asset_cache.clear()

    @classmethod
    def get_asset_types_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[AssetType]:
        """Fetch all asset types for a project with optional in-memory caching."""
        if use_cache and project_id in cls._asset_type_cache:
            return cls._asset_type_cache[project_id]

        try:
            raw_asset_types = gazu.asset.all_asset_types_for_project(project_id) or []
            asset_types = [AssetType.from_kitsu(p) for p in raw_asset_types]
            cls._asset_type_cache[project_id] = asset_types
            return asset_types
        except Exception as e:
            logger.error(f"Failed to fetch asset types for project {project_id}: {e}")
            return []

    @classmethod
    def get_assets_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[Asset]:
        """Fetch all assets for a project with asset type lookup and optional in-memory caching."""
        if use_cache and project_id in cls._asset_cache:
            return cls._asset_cache[project_id]

        try:
            raw_assets = gazu.asset.all_assets_for_project(project_id) or []
            asset_types = cls.get_asset_types_by_project_id(project_id, use_cache=use_cache)

            type_lookup = {
                (at.id if hasattr(at, "id") else at["id"]): (at.name if hasattr(at, "name") else at["name"])
                for at in asset_types
                if hasattr(at, "id") or (isinstance(at, dict) and "id" in at)
            }

            mapped_assets: List[Asset] = []
            for asset in raw_assets:
                if not isinstance(asset, dict):
                    continue
                asset_dict = dict(asset)
                type_id = asset_dict.get("entity_type_id")
                asset_dict["entity_type"] = type_lookup.get(type_id, "")
                mapped_assets.append(Asset.from_kitsu(asset_dict))

            cls._asset_cache[project_id] = mapped_assets
            return mapped_assets
        except Exception as e:
            logger.error(f"Failed to fetch assets for project {project_id}: {e}")
            return []

    @classmethod
    def get_assets_by_type(
        cls,
        project_id: str,
        asset_type_name: str = "",
        asset_type_id: str = "",
        use_cache: bool = True,
    ) -> List[Asset]:
        """Fetch assets for a project filtered by asset type name or ID."""
        all_assets = cls.get_assets_by_project_id(project_id, use_cache=use_cache)
        if asset_type_id:
            return [a for a in all_assets if a.asset_type_id == asset_type_id]
        if asset_type_name:
            return [a for a in all_assets if a.asset_type == asset_type_name]
        return all_assets