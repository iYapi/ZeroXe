"""Unit tests for Sync Feature (Layout & Animation).

Verifies that Sync detects newly linked Kitsu assets, imports and overrides them,
and increments the scene version only if new assets exist.
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "pipeline"

from pipeline.Commands.Builders.sync_builder import SyncBuilder
from pipeline.Commands.feature_registry import list_available_features, execute_feature
from zeroxe.services.pipeline_service import PipelineService


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
