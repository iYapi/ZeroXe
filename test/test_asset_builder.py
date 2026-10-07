"""Unit tests for AssetBuilder and Pipeline Asset Generation."""

import os
from pathlib import Path
import sys
import tempfile
import pytest

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline.Commands.Builders.asset_builder import AssetBuilder
from pipeline.Commands.Builders.builder_factory import BuilderFactory
from pipeline.Commands.feature_registry import execute_feature
from pipeline.Commands.main import generate_asset_builder_script, generate_builder_script


def test_asset_builder_character_script():
    """Verify AssetBuilder generates correct hierarchy for Character assets (c-hero -> hero_grp_mdl, hero_grp_rig)."""
    builder = AssetBuilder()
    file_path = "/projects/mdt/02_production/01_asset/01_char/c-hero/c-hero.blend"
    init_version_path = "/projects/mdt/02_production/01_asset/01_char/c-hero/progress/c-hero_v001.blend"

    script = builder.script_builder(filepath=file_path, init_version_path=init_version_path)

    assert "bpy.ops.wm.read_factory_settings(use_empty=True)" in script
    assert f'file_path = "{file_path}"' in script
    assert f'init_version_path = "{init_version_path}"' in script
    assert "is_s = b.startswith(\"s-\")" in script
    assert "sub_b = b if is_s else (b[2:] if len(b) > 2 and b[1] == \"-\" else b)" in script
    assert 'sfxs = ["_hi", "_lo"] if is_s else ["_grp_mdl", "_grp_rig"]' in script
    assert "r = bpy.data.collections.new(b)" in script
    assert "bpy.context.scene.collection.children.link(r)" in script
    assert "bpy.ops.wm.save_as_mainfile(filepath=file_path)" in script
    assert "bpy.ops.wm.save_as_mainfile(filepath=init_version_path)" in script
    assert "bpy.ops.wm.quit_blender()" in script


def test_asset_builder_set_script():
    """Verify AssetBuilder script for Set assets (s-forest -> s-forest_hi, s-forest_lo)."""
    builder = AssetBuilder()
    file_path = "/projects/mdt/02_production/01_asset/03_set/s-forest/s-forest.blend"
    init_version_path = "/projects/mdt/02_production/01_asset/03_set/s-forest/progress/s-forest_v001.blend"

    script = builder.script_builder(filepath=file_path, init_version_path=init_version_path)

    assert f'file_path = "{file_path}"' in script
    assert f'init_version_path = "{init_version_path}"' in script


def test_asset_collection_logic_simulation():
    """Test the exact Python collection logic from the user snippet."""
    def compute_collections(filepath: str):
        b = os.path.splitext(os.path.basename(filepath))[0]
        is_s = b.startswith("s-")
        sub_b = b if is_s else (b[2:] if len(b) > 2 and b[1] == "-" else b)
        sfxs = ["_hi", "_lo"] if is_s else ["_grp_mdl", "_grp_rig"]
        root = b
        children = [f"{sub_b}{s}" for s in sfxs]
        return root, children

    # Character
    root, children = compute_collections("/path/c-hero.blend")
    assert root == "c-hero"
    assert children == ["hero_grp_mdl", "hero_grp_rig"]

    # Props
    root, children = compute_collections("/path/p-sword.blend")
    assert root == "p-sword"
    assert children == ["sword_grp_mdl", "sword_grp_rig"]

    # Vehicle
    root, children = compute_collections("/path/v-car.blend")
    assert root == "v-car"
    assert children == ["car_grp_mdl", "car_grp_rig"]

    # Set (s- prefix)
    root, children = compute_collections("/path/s-temple.blend")
    assert root == "s-temple"
    assert children == ["s-temple_hi", "s-temple_lo"]

    # Asset with no prefix
    root, children = compute_collections("/path/building.blend")
    assert root == "building"
    assert children == ["building_grp_mdl", "building_grp_rig"]


def test_asset_builder_extract_data(tmp_path):
    """Verify extract_data creates directories and returns script."""
    builder = AssetBuilder()
    asset_dir = tmp_path / "01_char" / "c-warrior"
    master_path = asset_dir / "c-warrior.blend"
    ver_path = asset_dir / "progress" / "c-warrior_v001.blend"

    script = builder.extract_data(filepath={"final": str(master_path), "version": str(ver_path)})

    assert (asset_dir / "progress").is_dir()
    assert f'file_path = "{master_path.as_posix()}"' in script
    assert f'init_version_path = "{ver_path.as_posix()}"' in script


def test_builder_factory_generate_asset_script():
    """Verify BuilderFactory.generate_asset_script generates result properly."""
    final_p = "/projects/mdt/02_production/01_asset/01_char/c-ninja/c-ninja.blend"
    result = BuilderFactory.generate_asset_script(filepath=final_p)

    assert result.success is True
    assert result.target_final_path == final_p
    assert result.target_version_path.endswith("c-ninja_v001.blend")
    assert "bpy.ops.wm.read_factory_settings" in result.script
    assert "c-ninja" in result.script


def test_builder_factory_generate_shot_script_routes_asset():
    """Verify BuilderFactory.generate_shot_script automatically routes department='Asset' to AssetBuilder."""
    final_p = "/projects/mdt/02_production/01_asset/02_prop/p-shield/p-shield.blend"
    result = BuilderFactory.generate_shot_script(filepath=final_p, department="Asset")

    assert result.success is True
    assert result.target_final_path == final_p
    assert result.target_version_path.endswith("p-shield_v001.blend")
    assert "p-shield" in result.script


def test_feature_registry_handle_generate_asset():
    """Verify execute_feature('Generate', ...) handles asset files."""
    final_p = "/projects/mdt/02_production/01_asset/04_vehicle/v-truck/v-truck.blend"
    result = execute_feature(
        feature_name="Generate",
        filepath=final_p,
        department="Asset",
    )

    assert result.success is True
    assert result.target_path.endswith("v-truck_v001.blend")
    assert "v-truck" in result.script


def test_main_generate_asset_builder_script():
    """Verify main.py APIs generate_asset_builder_script and generate_builder_script."""
    final_p = "/projects/mdt/02_production/01_asset/01_char/c-mage/c-mage.blend"

    script, ver_path = generate_asset_builder_script(filepath=final_p)
    assert ver_path.endswith("c-mage_v001.blend")
    assert "c-mage" in script

    script2, ver_path2 = generate_builder_script(filepath=final_p, department="Asset")
    assert ver_path2.endswith("c-mage_v001.blend")
    assert "c-mage" in script2
