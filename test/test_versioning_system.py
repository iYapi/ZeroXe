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
    assert "Up Version" in features
    assert "Up Master" in features
    assert len(features) == 2

    # 2. Unconfigured project has NO features
    unconfigured_features = PipelineService.list_features(department="Animation", project_name="UnconfiguredProject")
    assert unconfigured_features == []

    # 3. None project has NO features
    none_project_features = PipelineService.list_features(department="Animation", project_name=None)
    assert none_project_features == []

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


