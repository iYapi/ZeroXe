"""Unit tests for VersioningSystem, Up Version, and Up Master pipeline features."""

from pathlib import Path
import sys
import tempfile
import yaml
import pytest

# Ensure src/ and pipeline/ are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline.Commands.versioning import VersioningSystem
from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.settings_service import SettingsService


def test_get_master_path():
    """Verify get_master_path correctly extracts master path from versioned or master paths."""
    # From version in progress folder
    v_path = "/projects/mdt/02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/progress/mdt_ep998_sq01_sh0020_lay_v002.blend"
    m_path = VersioningSystem.get_master_path(v_path)
    assert m_path == "/projects/mdt/02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_lay.blend"

    # From existing master path
    direct_m = "/projects/mdt/02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_lay.blend"
    assert VersioningSystem.get_master_path(direct_m) == direct_m

    # From asset version
    asset_v = "/projects/mdt/02_production/01_asset/01_char/c-hero/progress/c-hero_v005.blend"
    assert VersioningSystem.get_master_path(asset_v) == "/projects/mdt/02_production/01_asset/01_char/c-hero/c-hero.blend"


def test_get_next_version_path(tmp_path):
    """Verify get_next_version_path scans directory and computes next incremental version."""
    shot_dir = tmp_path / "ep998_sq01_sh0020"
    ver_dir = shot_dir / "progress"
    ver_dir.mkdir(parents=True, exist_ok=True)

    # Initially empty -> should be v001
    master_file = shot_dir / "mdt_ep998_sq01_sh0020_lay.blend"
    next_ver = VersioningSystem.get_next_version_path(master_file)
    assert Path(next_ver).name == "mdt_ep998_sq01_sh0020_lay_v001.blend"

    # Create v001 and v002 files on disk
    (ver_dir / "mdt_ep998_sq01_sh0020_lay_v001.blend").touch()
    (ver_dir / "mdt_ep998_sq01_sh0020_lay_v002.blend").touch()

    # Next should be v003
    next_ver = VersioningSystem.get_next_version_path(master_file)
    assert Path(next_ver).name == "mdt_ep998_sq01_sh0020_lay_v003.blend"

    # Passing a version file itself should also compute v003
    next_ver_from_v2 = VersioningSystem.get_next_version_path(ver_dir / "mdt_ep998_sq01_sh0020_lay_v002.blend")
    assert Path(next_ver_from_v2).name == "mdt_ep998_sq01_sh0020_lay_v003.blend"


def test_up_version_script_generation(tmp_path):
    """Verify up_version produces correct template substitutions."""
    shot_file = tmp_path / "shot_lay.blend"
    shot_file.touch()

    script, version_path = VersioningSystem.up_version(str(shot_file))

    assert f'bpy.ops.wm.open_mainfile(filepath="{str(shot_file)}")' in script
    assert f'bpy.ops.wm.save_as_mainfile(filepath="{version_path}", copy=True)' in script
    assert "bpy.ops.wm.quit_blender()" in script
    assert "shot_lay_v001.blend" in version_path


def test_up_master_script_generation_with_preset(tmp_path):
    """Verify up_master embeds preset code between start_script and end_script."""
    shot_file = tmp_path / "progress" / "shot_anm_v002.blend"
    shot_file.parent.mkdir(parents=True, exist_ok=True)
    shot_file.touch()

    # Create dummy preset script
    preset_file = tmp_path / "preset_bake.py"
    preset_code = "# PRESET: Bake animations\nbpy.ops.nla.bake(frame_start=1, frame_end=100)"
    preset_file.write_text(preset_code, encoding="utf-8")

    setting_data = {"script": str(preset_file)}
    script, master_path = VersioningSystem.up_master(str(shot_file), setting_data=setting_data)

    assert master_path.endswith("shot_anm.blend")
    assert f'bpy.ops.wm.open_mainfile(filepath="{str(shot_file)}")' in script
    assert preset_code in script
    assert "bpy.ops.wm.quit_blender()" in script


def test_pipeline_service_integration(tmp_path):
    """Verify PipelineService delegating to VersioningSystem and resolving presets."""
    pipe_yaml = tmp_path / "pipeline.yaml"
    preset_py = tmp_path / "bake.py"
    preset_py.write_text("# Bake preset code", encoding="utf-8")

    pipe_config = {
        "global": {
            "code": "mdt",
            "mounts": {"linux": str(tmp_path), "windows": str(tmp_path), "darwin": str(tmp_path)},
        },
        "departments": {
            "Animation": {
                "code": "anm",
                "scripts": {
                    "up_master": f"@project_path@/{preset_py.name}",
                },
            }
        },
    }
    pipe_yaml.write_text(yaml.dump(pipe_config), encoding="utf-8")

    map_yaml = tmp_path / "zeroxe_map.yaml"
    map_config = {
        "project": {
            "TestProject": {
                "code": "mdt",
                "name": "TestProject",
                "pipeline_path": str(pipe_yaml),
            }
        }
    }
    map_yaml.write_text(yaml.dump(map_config), encoding="utf-8")

    SettingsService.set_zeroxe_map_path(str(map_yaml))
    PipelineService.clear_cache()

    # Test preset resolution
    script_path = PipelineService.get_department_script("Animation", "up_master")
    assert script_path is not None
    assert Path(script_path).resolve() == preset_py.resolve()

    # Test up_master with department preset resolution
    v_file = tmp_path / "mdt_ep998_sq01_sh0010_anm_v001.blend"
    v_file.touch()

    script, master_path = VersioningSystem.up_master(str(v_file), setting_data={"script": str(preset_py)})
    assert "# Bake preset code" in script
    assert "mdt_ep998_sq01_sh0010_anm.blend" in master_path


def test_dynamic_feature_discovery_and_execution(tmp_path):
    """Verify dynamic discovery of pipeline features from registry in external pipeline."""
    ext_pipeline_dir = tmp_path / "ext_pipeline"
    ext_commands = ext_pipeline_dir / "Commands"
    ext_commands.mkdir(parents=True, exist_ok=True)

    repo_pipeline = REPO_ROOT / "pipeline"
    if (repo_pipeline / "Commands").is_dir():
        import shutil
        shutil.copytree(repo_pipeline / "Commands", ext_commands, dirs_exist_ok=True)

    pipe_yaml = ext_pipeline_dir / "pipeline.yaml"
    pipe_config = {
        "global": {
            "code": "mdt",
            "mounts": {"linux": str(tmp_path), "windows": str(tmp_path), "darwin": str(tmp_path)},
        },
        "departments": {
            "Animation": {
                "code": "anm",
                "scripts": {
                    "up_master": "@project_path@/fake_master.py",
                    "playblast": "@project_path@/fake_playblast.py",
                },
            }
        },
    }
    pipe_yaml.write_text(yaml.dump(pipe_config), encoding="utf-8")

    map_yaml = tmp_path / "zeroxe_map.yaml"
    map_config = {
        "project": {
            "TestProject": {
                "code": "mdt",
                "name": "TestProject",
                "pipeline_path": str(pipe_yaml),
            }
        }
    }
    map_yaml.write_text(yaml.dump(map_config), encoding="utf-8")

    SettingsService.set_zeroxe_map_path(str(map_yaml))
    PipelineService.clear_cache()

    # 1. Configured project has features
    features = PipelineService.list_features(department="Animation", project_name="TestProject")
    assert "Generate" in features
    assert "Up Version" in features
    assert "Up Master" in features
    assert len(features) == 3

    # 2. Unconfigured project has NO features
    unconfigured_features = PipelineService.list_features(department="Animation", project_name="UnconfiguredProject")
    assert unconfigured_features == []

    # 3. None project falls back to active project pipeline features
    none_project_features = PipelineService.list_features(department="Animation", project_name=None)
    assert "Generate" in none_project_features
    assert "Up Version" in none_project_features

    # Execute feature 'Up Version' on configured project
    test_blend = tmp_path / "test.blend"
    test_blend.touch()

    success, msg, target = PipelineService.execute_feature(
        feature_name="Up Version",
        filepath=str(test_blend),
        department="Animation",
        project_name="TestProject",
    )
    assert success is True
    assert target is not None and "test_v001.blend" in target


def test_batch_execution_pipeline_features(tmp_path):
    """Verify batch execution over multiple shot files through external pipeline."""
    ext_pipeline_dir = tmp_path / "ext_pipeline"
    ext_commands = ext_pipeline_dir / "Commands"
    ext_commands.mkdir(parents=True, exist_ok=True)

    repo_pipeline = REPO_ROOT / "pipeline"
    if (repo_pipeline / "Commands").is_dir():
        import shutil
        shutil.copytree(repo_pipeline / "Commands", ext_commands, dirs_exist_ok=True)

    pipe_yaml = ext_pipeline_dir / "pipeline.yaml"
    pipe_config = {
        "global": {
            "code": "mdt",
            "mounts": {"linux": str(tmp_path), "windows": str(tmp_path), "darwin": str(tmp_path)},
        },
        "departments": {
            "Layout": {"code": "lay"},
        },
    }
    pipe_yaml.write_text(yaml.dump(pipe_config), encoding="utf-8")

    map_yaml = tmp_path / "zeroxe_map.yaml"
    map_config = {
        "project": {
            "TestProject": {
                "code": "mdt",
                "name": "TestProject",
                "pipeline_path": str(pipe_yaml),
            }
        }
    }
    map_yaml.write_text(yaml.dump(map_config), encoding="utf-8")

    SettingsService.set_zeroxe_map_path(str(map_yaml))
    PipelineService.clear_cache()

    shots = ["ep998_sq01_sh0010", "ep998_sq01_sh0020", "ep998_sq01_sh0030"]
    created_files = []
    for sh in shots:
        sh_dir = tmp_path / sh / "progress"
        sh_dir.mkdir(parents=True, exist_ok=True)
        f = sh_dir / f"{sh}_lay_v001.blend"
        f.touch()
        created_files.append(f)

    # 1. Batch Up Version
    up_version_results = []
    for f in created_files:
        success, msg, target = PipelineService.execute_feature(
            feature_name="Up Version",
            filepath=str(f),
            project_name="TestProject",
        )
        assert success is True
        assert target is not None and target.endswith("_v002.blend")
        up_version_results.append(target)

    assert len(up_version_results) == 3

    # 2. Batch Up Master
    up_master_results = []
    for f in created_files:
        success, msg, target = PipelineService.execute_feature(
            feature_name="Up Master",
            filepath=str(f),
            project_name="TestProject",
        )
        assert success is True
        assert target is not None and target.endswith("_lay.blend")
        assert "/progress/" not in target
        up_master_results.append(target)

    assert len(up_master_results) == 3


def test_animatic_builder(tmp_path):
    """Verify AnimaticBuilder generates scene setup with frame range and quit commands."""
    from pipeline.Commands.Builders.animatic_builder import AnimaticBuilder

    builder = AnimaticBuilder()
    ver_file = tmp_path / "progress" / "mdt_ep998_sq01_sh0010_anc_v001.blend"
    final_file = tmp_path / "mdt_ep998_sq01_sh0010_anc.blend"

    shot_data = {"data": {"frame_in": 101, "frame_out": 184, "fps": 24, "resolution": "2560x1080"}}
    script = builder.extract_data(
        filepath={"version": str(ver_file), "final": str(final_file)},
        shot_data=shot_data,
    )

    assert ver_file.parent.is_dir()
    assert "bpy.context.scene.frame_start = 101" in script
    assert "bpy.context.scene.frame_end = 184" in script
    assert "bpy.context.scene.render.fps = 24" in script
    assert "bpy.context.scene.render.resolution_x = 2560" in script
    assert "bpy.context.scene.render.resolution_y = 1080" in script
    assert f'bpy.ops.wm.save_as_mainfile(filepath="{str(ver_file)}")' in script
    assert f'bpy.ops.wm.save_as_mainfile(filepath="{str(final_file)}", copy=True)' in script
    assert "bpy.ops.wm.quit_blender()" in script


def test_layout_builder(tmp_path):
    """Verify LayoutBuilder generates asset collection linking, camera rig, and presets."""
    from pipeline.Commands.Builders.layout_builder import LayoutBuilder

    builder = LayoutBuilder()
    ver_file = tmp_path / "progress" / "mdt_ep998_sq01_sh0010_lay_v001.blend"
    final_file = tmp_path / "mdt_ep998_sq01_sh0010_lay.blend"

    asset_types = {
        "CHAR": {"id": "char_id", "code": "chr", "base_path": str(tmp_path / "assets" / "char")},
        "PROPS": {"id": "prop_id", "code": "prp", "base_path": str(tmp_path / "assets" / "prop")},
        "SET": {"id": "set_id", "code": "set", "base_path": str(tmp_path / "assets" / "set")},
    }
    shot_data = {
        "name": "sh0010",
        "assets": [
            {"name": "c-baha", "entity_type_id": "char_id"},
            {"name": "p-dagangan", "entity_type_id": "prop_id"},
            {"name": "s-sekolah", "entity_type_id": "set_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 84, "fps": 24, "resolution": "1920x1080"},
    }
    dept_info = {"Layout": {"code": "lay", "source": "init"}}

    asset_dept = {"Asset": {"asset_type": asset_types}}
    script = builder.extract_data(
        asset_department=asset_dept,
        current_department=dept_info,
        shot_data=shot_data,
        filepath={"version": str(ver_file), "final": str(final_file)},
    )

    assert ver_file.parent.is_dir()
    assert "link_collection(collections)" in script
    assert "add_camera_rig()" in script
    assert "c-baha.blend" in script
    assert "p-dagangan.blend" in script
    assert "s-sekolah.blend" in script
    assert "bpy.context.scene.frame_end = settings[\"frame_out\"]" in script
    assert "bpy.ops.wm.quit_blender()" in script

    # Verify fallback when resolution is None / missing
    bad_shot_data = {"data": {"resolution": None, "frame_in": None, "frame_out": ""}}
    bad_script = builder.extract_data(
        asset_department=asset_dept,
        current_department=dept_info,
        shot_data=bad_shot_data,
        filepath={"version": str(ver_file), "final": str(final_file)},
    )
    assert "'resolution': [1920, 1080]" in bad_script


def test_animation_builder_source_and_sync(tmp_path):
    """Verify BlockingAnimationBuilder copies from source, applies preset and saves."""
    from pipeline.Commands.Builders.animation_builder import BlockingAnimationBuilder

    builder = BlockingAnimationBuilder()
    ver_file = tmp_path / "progress" / "mdt_ep998_sq01_sh0020_anm_v001.blend"
    final_file = tmp_path / "mdt_ep998_sq01_sh0020_anm.blend"
    src_file = tmp_path / "fallback_layout.blend"

    dept_info = {
        "Animation": {
            "code": "anm",
            "source": "Layout",
            "presets": {"playblast": {"path": ""}},
        }
    }
    filepath_dict = {
        "version": str(ver_file),
        "final": str(final_file),
        "source": str(src_file),
    }

    script = builder.extract_data(
        current_department=dept_info,
        filepath=filepath_dict,
    )

    assert ver_file.parent.is_dir()
    assert str(src_file) in script
    assert str(ver_file) in script
    assert str(final_file) in script


def test_builder_factory_and_generate_feature(tmp_path):
    """Verify BuilderFactory and Generate feature execution via PipelineService."""
    ext_pipeline_dir = tmp_path / "ext_pipeline"
    ext_commands = ext_pipeline_dir / "Commands"
    ext_commands.mkdir(parents=True, exist_ok=True)

    repo_pipeline = REPO_ROOT / "pipeline"
    if (repo_pipeline / "Commands").is_dir():
        import shutil
        shutil.copytree(repo_pipeline / "Commands", ext_commands, dirs_exist_ok=True)

    pipe_yaml = ext_pipeline_dir / "pipeline.yaml"
    pipe_config = {
        "global": {
            "code": "mdt",
            "mounts": {"linux": str(tmp_path), "windows": str(tmp_path), "darwin": str(tmp_path)},
        },
        "departments": {
            "Layout": {"code": "lay", "source": "init", "base_path": "@project_path@/layout/"},
            "Animation": {"code": "anm", "source": "Layout", "base_path": "@project_path@/animation/"},
        },
        "asset_type": {
            "CHAR": {"id": "c_id", "code": "chr", "base_path": "@project_path@/assets/char/"},
        },
    }
    pipe_yaml.write_text(yaml.dump(pipe_config), encoding="utf-8")

    map_yaml = tmp_path / "zeroxe_map.yaml"
    map_config = {
        "project": {
            "TestProject": {
                "code": "mdt",
                "name": "TestProject",
                "pipeline_path": str(pipe_yaml),
            }
        }
    }
    map_yaml.write_text(yaml.dump(map_config), encoding="utf-8")

    SettingsService.set_zeroxe_map_path(str(map_yaml))
    PipelineService.clear_cache()

    target_shot = tmp_path / "layout" / "ep01" / "ep01_sq01" / "ep01_sq01_sh0010" / "progress" / "mdt_ep01_sq01_sh0010_lay_v001.blend"

    shot_dict = {
        "name": "sh0010",
        "assets": [{"name": "c-hero", "entity_type_id": "c_id"}],
        "data": {"frame_in": 1, "frame_out": 50, "fps": 24, "resolution": "1920x1080"},
    }

    # Execute Generate via PipelineService
    success, msg, target_path = PipelineService.execute_feature(
        feature_name="Generate",
        filepath=str(target_shot),
        department="Layout",
        project_name="TestProject",
        shot_data=shot_dict,
    )

    assert success is True
    assert target_path is not None and "mdt_ep01_sq01_sh0010_lay_v001.blend" in target_path

    # Even when v001 already exists and we re-generate from master path, it must target v001 (NOT increment to v002)
    master_shot = tmp_path / "layout" / "ep01" / "ep01_sq01" / "ep01_sq01_sh0010" / "mdt_ep01_sq01_sh0010_lay.blend"
    success2, msg2, target_path2 = PipelineService.execute_feature(
        feature_name="Generate",
        filepath=str(master_shot),
        department="Layout",
        project_name="TestProject",
        shot_data=shot_dict,
    )
    assert success2 is True
    assert target_path2 is not None and target_path2.endswith("mdt_ep01_sq01_sh0010_lay_v001.blend")


def test_dynamic_division_builder_from_custom_path(tmp_path):
    """Verify BuilderFactory dynamically discovers and executes custom division builders from search path without hardcoding."""
    from pipeline.Commands.Builders.builder_factory import BuilderFactory

    # Create the builder directory: 00_tools/01_preset_script/zeroxe-conf/builder
    builder_dir = tmp_path / "00_tools" / "01_preset_script" / "zeroxe-conf" / "builder"
    builder_dir.mkdir(parents=True, exist_ok=True)

    # Place a custom division builder script: lighting_builder.py (or custom_division_builder.py)
    custom_builder_file = builder_dir / "lighting_builder.py"
    custom_code = """
class LightingBuilder:
    def extract_data(self, filepath, shot_data, **kwargs):
        return f"# CUSTOM LIGHTING BUILDER EXECUTED FOR {filepath['version']}"
"""
    custom_builder_file.write_text(custom_code, encoding="utf-8")

    # Define department without hardcoded rules
    dept_info = {"code": "lgt", "source": "Animation", "base_path": "@project_path@/03_lighting/"}
    shot_data = {"name": "sh0010", "assets": []}
    ver_path = str(tmp_path / "03_lighting" / "ep01" / "sh0010" / "progress" / "sh0010_lgt_v001.blend")

    # Test get_builder finds the file in project_path's builder dir
    builder = BuilderFactory.get_builder(
        department="Lighting",
        department_config=dept_info,
        project_path=str(tmp_path),
    )
    assert builder.__class__.__name__ == "LightingBuilder"

    # Test generate_shot_script executes the custom builder
    res = BuilderFactory.generate_shot_script(
        filepath=ver_path,
        department="Lighting",
        shot_data=shot_data,
        project_path=str(tmp_path),
    )
    assert res.success is True
    assert "# CUSTOM LIGHTING BUILDER EXECUTED FOR" in res.script


def test_all_division_builders_built_in(tmp_path):
    """Verify Lighting, VFX, Compositing, and Editing builders generate appropriate scripts."""
    from pipeline.Commands.Builders import (
        LightingBuilder,
        VFXBuilder,
        CompositingBuilder,
        EditingBuilder,
    )

    ver = str(tmp_path / "progress" / "test_v001.blend")
    final = str(tmp_path / "test.blend")
    shot_data = {
        "name": "sh0010",
        "assets": [
            {"name": "LIT_s-ext_sekolah_PAGI", "entity_type_id": "ms_lit_id"},
            {"name": "COMP_s-ext_sekolah_PAGI", "entity_type_id": "ms_comp_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 100, "fps": 24, "resolution": "1920x1080"},
    }
    asset_types = {
        "SET": {"id": "set_id", "code": "set", "base_path": str(tmp_path / "set")},
        "MS_LIT": {"id": "ms_lit_id", "code": "ms", "base_path": str(tmp_path / "ms_lit")},
        "MS_COMP": {"id": "ms_comp_id", "code": "ms", "base_path": str(tmp_path / "ms_comp")},
    }
    mastershots = {
        "mastershots": {
            "mastershot_lit": {"code": "ms-lit", "base_path": str(tmp_path / "ms_lit")},
            "mastershot_compositing": {"code": "ms-comp", "base_path": str(tmp_path / "ms_comp")},
        }
    }

    # 1. Lighting
    lgt_builder = LightingBuilder()
    lgt_script = lgt_builder.extract_data(
        shot_data=shot_data,
        current_department={"Lighting": {"code": "lgt", "source": "Animation"}},
        asset_department={"Asset": {"asset_type": asset_types}},
        mastershots_data=mastershots,
        addons_data={"addons": {}},
        filepath={"version": ver, "final": final, "source": str(tmp_path / "anim.blend")},
    )
    assert "link_animation()" in lgt_script
    assert "update_camera()" in lgt_script

    # 2. VFX
    vfx_builder = VFXBuilder()
    vfx_script = vfx_builder.extract_data(
        shot_data=shot_data,
        current_department={"code": "fx", "source": "Animation"},
        asset_department=asset_types,
        filepath={"version": ver, "final": final, "source": str(tmp_path / "anim.blend")},
    )
    assert "link_animation()" in vfx_script

    # 3. Compositing
    comp_builder = CompositingBuilder()
    comp_script = comp_builder.extract_data(
        shot_data=shot_data,
        current_department={"Compositing": {"code": "comp", "source": "Lighting"}},
        asset_department={"Asset": {"asset_type": asset_types}},
        mastershots_data=mastershots,
        addons_data={"addons": {}},
        filepath={"version": ver, "final": final},
    )
    assert "open_mainfile" in comp_script

    # 4. Editing
    edit_builder = EditingBuilder()
    edit_script = edit_builder.extract_data(
        filepath={"version": ver, "final": final},
    )
    assert "save_as_mainfile" in edit_script


def test_live_builder_directory_discovery_if_available():
    """Verify BuilderFactory dynamically scans and matches real files in the NAS builder directory if present."""
    nas_builder_dir = Path("/mnt/I/20260222_melangkah_dari_timur/00_tools/01_preset_script/zeroxe-conf/builder")
    if not nas_builder_dir.is_dir():
        pytest.skip("NAS builder directory not mounted in local test environment")

    from pipeline.Commands.Builders.builder_factory import BuilderFactory

    divisions = [
        ("2D", {"code": "anc", "source": ""}),
        ("Layout", {"code": "lay", "source": "init"}),
        ("Blocking", {"code": "blk", "source": "Layout"}),
        ("Animation", {"code": "anm", "source": "Layout"}),
        ("Lighting", {"code": "lgt", "source": "Animation"}),
        ("FX", {"code": "fx", "source": "Animation"}),
        ("Compositing", {"code": "comp", "source": "Lighting"}),
        ("Editing", {"code": "edit", "source": ""}),
    ]

    for dept_name, dept_cfg in divisions:
        builder_file = BuilderFactory._find_builder_file(
            department=dept_name,
            dept_cfg=dept_cfg,
            search_paths=[nas_builder_dir],
            project_path="/mnt/I/20260222_melangkah_dari_timur",
        )
        assert builder_file is not None, f"Builder file not found for division '{dept_name}' in {nas_builder_dir}"
        assert builder_file.is_file()





