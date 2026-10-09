"""Unit tests for Sync Feature (Layout & Animation).

Verifies that Sync detects newly linked Kitsu assets, imports and overrides them,
and increments the scene version only if new assets exist.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "pipeline"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.Commands.Builders.sync_builder import SyncBuilder
from pipeline.Commands.feature_registry import list_available_features, execute_feature
from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.shot_service import ShotService


def test_sync_feature_discovered_for_departments():
    """Verify that Sync is listed for Animation, Layout, and Blocking departments."""
    anm_features = list_available_features(department="Animation")
    lay_features = list_available_features(department="Layout")
    blk_features = list_available_features(department="Blocking")

    assert "Sync" in anm_features
    assert "Sync" in lay_features
    assert "Sync" in blk_features


def test_sync_builder_script_generation(tmp_path):
    """Verify SyncBuilder script generation and logic structure."""
    builder = SyncBuilder()

    current_file = tmp_path / "02_production" / "04_animation" / "ep01" / "sq01" / "sh0010" / "progress" / "sh0010_anm_v001.blend"
    current_file.parent.mkdir(parents=True, exist_ok=True)
    current_file.write_text("# Blender mock")

    mock_shot_data = {
        "name": "sh0010",
        "sequence": "sq01",
        "episode": "ep01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "c-villain", "entity_type_id": "char_id"},
            {"name": "p-sword", "entity_type_id": "prop_id"},
            {"name": "s-forest", "entity_type_id": "set_id"},
        ],
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-", "base_path": "@project_path@/02_production/01_asset/01_char"},
                "PROPS": {"id": "prop_id", "code": "prp", "prefix": "p-", "base_path": "@project_path@/02_production/01_asset/02_prop"},
                "SET": {"id": "set_id", "code": "set", "prefix": "s-", "base_path": "@project_path@/02_production/01_asset/03_set"},
            }
        }
    }
    mock_current_dept = {"Animation": {"code": "anm"}}

    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        filepath={"version": str(current_file), "final": str(current_file.parent.parent / "sh0010_anm.blend")},
        project_path=str(tmp_path),
    )

    # Check that script contains sync identification and versioning logic
    assert "get_existing_asset_names()" in script
    assert "new_assets_to_link" in script
    assert "sh0010_anm_v002.blend" in script
    assert "NO NEW VERSION CREATED" in script
    assert "make_override_library" in script

    # Check syntax correctness
    compile(script, "<sync_script>", "exec")


def test_sync_execution_via_execute_feature(tmp_path):
    """Verify executing 'Sync' via feature_registry dispatcher."""
    work_file = tmp_path / "02_production" / "04_animation" / "ep01" / "sq01" / "sh0010" / "progress" / "sh0010_anm_v001.blend"
    work_file.parent.mkdir(parents=True, exist_ok=True)
    work_file.write_text("# Mock")

    mock_shot_data = {
        "name": "sh0010",
        "sequence": "sq01",
        "episode": "ep01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "1"},
        ],
    }

    res = execute_feature(
        feature_name="Sync",
        filepath=str(work_file),
        department="Animation",
        shot_data=mock_shot_data,
        project_path=str(tmp_path),
    )

    assert res.success is True
    assert res.data["action"] == "sync"
    assert "sh0010_anm_v002.blend" in res.target_path
    assert "[SYNC]" in res.script


def test_sync_live_kitsu_casting_merge(tmp_path):
    """Verify that SyncBuilder pulls fresh live casting from ShotService when shot_id is provided."""
    builder = SyncBuilder()

    current_file = tmp_path / "02_production" / "04_animation" / "ep01" / "sq01" / "sh0010" / "progress" / "sh0010_anm_v001.blend"
    current_file.parent.mkdir(parents=True, exist_ok=True)
    current_file.write_text("# Blender mock")

    mock_shot_data = {
        "id": "shot-uuid-1234",
        "project_id": "proj-uuid-5678",
        "name": "sh0010",
        "sequence": "sq01",
        "episode": "ep01",
        "assets": [
            {"id": "a1", "name": "c-hero", "entity_type_id": "char_id"},
        ],
    }

    fresh_kitsu_casting = [
        {"id": "a1", "name": "c-hero", "entity_type_id": "char_id"},
        {"id": "a2", "name": "c-villain", "entity_type_id": "char_id"},
        {"id": "a3", "name": "p-shield", "entity_type_id": "prop_id"},
    ]

    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-", "base_path": "@project_path@/02_production/01_asset/01_char"},
                "PROPS": {"id": "prop_id", "code": "prp", "prefix": "p-", "base_path": "@project_path@/02_production/01_asset/02_prop"},
            }
        }
    }
    mock_current_dept = {"Animation": {"code": "anm"}}

    with patch.object(ShotService, "get_assets_for_shot", return_value=fresh_kitsu_casting) as mock_get_assets:
        script = builder.extract_data(
            shot_data=mock_shot_data,
            current_department=mock_current_dept,
            asset_department=mock_asset_dept,
            filepath={"version": str(current_file), "final": str(current_file.parent.parent / "sh0010_anm.blend")},
            project_path=str(tmp_path),
        )

        mock_get_assets.assert_called_once_with("shot-uuid-1234", project_id="proj-uuid-5678", force_refresh=True)
        assert "c-villain" in script
        assert "p-shield" in script


def test_sync_script_exact_matching_logic():
    """Verify that Python script generated uses exact collection/library matching to prevent false positives."""
    builder = SyncBuilder()
    script = builder.script_builder(
        current_filepath="/path/sh0010_anm_v001.blend",
        next_version_path="/path/sh0010_anm_v002.blend",
        final_filepath="/path/sh0010_anm.blend",
        kitsu_assets={
            "chr": [{"name": "car", "path": "/path/car.blend", "category": "char"}],
        },
    )

    # Ensure get_existing_asset_names does exact matches and doesn't do loose substring search
    assert "for e in existing" not in script
    assert "clean_name in existing_names" in script
