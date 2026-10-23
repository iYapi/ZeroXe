"""Unit and Integration Tests for ZerØXe CLI Entrypoint."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure src/ and pipeline/ are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from zeroxe import config
from zeroxe.cli import main


@pytest.fixture
def dummy_pipeline_config(tmp_path):
    """Create a minimal pipeline.yaml file for CLI testing."""
    import yaml

    mount_dir = tmp_path / "projects"
    cfg = {
        "global": {
            "code": "tst",
            "name": "Test Project",
            "mounts": {
                "linux": str(mount_dir),
                "windows": str(mount_dir),
                "darwin": str(mount_dir),
            },
        },
        "departments": {
            "Layout": {
                "code": "lay",
                "base_path": "@project_path@/02_production/02_layout",
            },
            "Animation": {
                "code": "anm",
                "base_path": "@project_path@/02_production/03_animation",
            },
        },
        "asset_type": {
            "CHAR": {
                "code": "chr",
                "base_path": "@project_path@/02_production/01_asset/01_char",
            },
        },
    }
    cfg_file = tmp_path / "pipeline.yaml"
    cfg_file.write_text(yaml.dump(cfg), encoding="utf-8")
    return cfg_file


def test_cli_version(capsys):
    """Verify zeroxe --version outputs the correct version."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert config.APP_NAME in captured.out
    assert config.APP_VERSION in captured.out


def test_cli_help(capsys):
    """Verify zeroxe --help displays usage and available commands."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage: zeroxe" in captured.out
    assert "shot-path" in captured.out
    assert "asset-path" in captured.out
    assert "convert" in captured.out
    assert "lock" in captured.out
    assert "config" in captured.out


def test_cli_info_text(capsys):
    """Verify zeroxe info prints human-readable environment details."""
    ret = main(["info"])
    assert ret == 0
    captured = capsys.readouterr()
    assert config.APP_NAME in captured.out
    assert config.APP_VERSION in captured.out
    assert "Platform:" in captured.out
    assert "Python:" in captured.out


def test_cli_info_json(capsys):
    """Verify zeroxe info --json prints valid JSON with all required keys."""
    ret = main(["info", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["app_name"] == config.APP_NAME
    assert data["version"] == config.APP_VERSION
    assert "python_version" in data
    assert "user_data_dir" in data


def test_cli_shot_path(capsys, dummy_pipeline_config):
    """Verify zeroxe shot-path resolves master and version paths."""
    ret = main([
        "shot-path",
        "--config", str(dummy_pipeline_config),
        "-d", "Layout",
        "-e", "ep01",
        "-s", "sq01",
        "--sh", "sh0010",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is True
    assert "tst_ep01_sq01_sh0010_lay.blend" in data["master_path"]
    assert "tst_ep01_sq01_sh0010_lay_v001.blend" in data["version_path"]
    assert data["version_number"] == 1


def test_cli_asset_path(capsys, dummy_pipeline_config):
    """Verify zeroxe asset-path resolves asset master and version paths."""
    ret = main([
        "asset-path",
        "--config", str(dummy_pipeline_config),
        "-t", "CHAR",
        "-n", "Hero",
        "-d", "Model",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is True
    assert "hero.blend" in data["master_path"]
    assert "hero_v001.blend" in data["version_path"]


def test_cli_list_features(capsys, dummy_pipeline_config):
    """Verify zeroxe list-features queries registered pipeline features."""
    ret = main([
        "list-features",
        "--config", str(dummy_pipeline_config),
        "-d", "Animation",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "features" in data
    assert isinstance(data["features"], list)
    assert "Generate" in data["features"]


def test_cli_lock_check(capsys):
    """Verify zeroxe lock --check returns entity lock status."""
    ret = main([
        "lock",
        "-k", "test_entity_key",
        "--check",
        "--json",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["key"] == "test_entity_key"
    assert "is_locked" in data


def test_cli_list_presets(capsys):
    """Verify zeroxe list-presets lists media transcoder presets."""
    ret = main(["list-presets", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "presets" in data
    preset_ids = [p["id"] for p in data["presets"]]
    assert "folder_to_mp4" in preset_ids
    assert "video_to_mp4" in preset_ids


def test_cli_inspect_file(capsys, tmp_path):
    """Verify zeroxe inspect inspects media files."""
    dummy_file = tmp_path / "test_shot_v002.mov"
    dummy_file.write_bytes(b"dummy")

    ret = main(["inspect", "-i", str(dummy_file), "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_valid"] is True
    assert data["type"] == "video"
    assert data["name"] == "test_shot"
    assert data["version"] == "_v002"


def test_cli_config_get_set(capsys):
    """Verify zeroxe config get and set operations."""
    test_key = "test_section/test_var"
    test_val = "custom_value_42"

    # Set value
    ret_set = main(["config", "--set", test_key, test_val, "--json"])
    assert ret_set == 0
    captured = capsys.readouterr()
    data_set = json.loads(captured.out)
    assert data_set["success"] is True
    assert data_set["value"] == test_val

    # Get value
    ret_get = main(["config", "--get", test_key, "--json"])
    assert ret_get == 0
    captured_get = capsys.readouterr()
    data_get = json.loads(captured_get.out)
    assert data_get["value"] == test_val

    # Cleanup
    from zeroxe.services.settings_service import SettingsService
    SettingsService._settings().remove(test_key)
    SettingsService._settings().sync()


def test_cli_gui_default_trigger():
    """Verify running zeroxe without arguments invokes GUI run()."""
    with patch("zeroxe.cli._run_gui", return_value=0) as mock_gui:
        ret = main([])
        assert ret == 0
        mock_gui.assert_called_once_with()


def test_cli_gui_subcommand_trigger():
    """Verify running zeroxe gui explicitly invokes GUI run()."""
    with patch("zeroxe.cli._run_gui", return_value=0) as mock_gui:
        ret = main(["gui", "--project", "DemoProject"])
        assert ret == 0
        mock_gui.assert_called_once_with("DemoProject")


def test_main_module_delegation():
    """Verify zeroxe.main.main delegates to zeroxe.cli.main."""
    from zeroxe.main import main as main_func
    with patch("zeroxe.cli.main", return_value=0) as mock_cli:
        ret = main_func(["--version"])
        assert ret == 0
        mock_cli.assert_called_once_with(["--version"])
