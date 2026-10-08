import os
from pathlib import Path
import sys
import pytest
from PySide6.QtWidgets import QApplication

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline.Commands.Builders.lighting_builder import LightingBuilder
from pipeline.Commands.Builders.lighting_dialog import LightingAssetDialog
from pipeline.Commands.Builders.builder_factory import BuilderFactory


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_lighting_dialog_categorization(qapp):
    """Verify that LightingAssetDialog correctly categorizes assets and excludes Set & MS."""
    mock_shot_data = {
        "name": "SH001",
        "sequence": "SQ01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "c-villain", "entity_type_id": "char_id"},
            {"name": "p-sword", "entity_type_id": "prop_id"},
            {"name": "v-car", "entity_type_id": "vehicle_id"},
            {"name": "s-forest", "entity_type_id": "set_id"},
            {"name": "ms_lit_day", "entity_type_id": "ms_id"},
        ],
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-"},
                "PROPS": {"id": "prop_id", "code": "prp", "prefix": "p-"},
                "VEHICLE": {"id": "vehicle_id", "code": "vhc", "prefix": "v-"},
                "SET": {"id": "set_id", "code": "set", "prefix": "s-"},
                "MS_LIT": {"id": "ms_id", "code": "ms", "prefix": "LIT_"},
            }
        }
    }

    dialog = LightingAssetDialog(shot_data=mock_shot_data, asset_department=mock_asset_dept)
    categories = dialog._categorize_shot_assets()

    assert "c-hero" in categories["Characters"]
    assert "c-villain" in categories["Characters"]
    assert "p-sword" in categories["Props"]
    assert "v-car" in categories["Vehicles"]
    assert "s-forest" not in categories["Characters"]
    assert "s-forest" not in categories["Props"]
    assert "ms_lit_day" not in categories["Characters"]

    # Test get_selected_fg_assets (default is all in BG, so [] initially)
    default_selected = dialog.get_selected_fg_assets()
    assert default_selected == []

    # Select c-hero and c-villain
    dialog._checkbox_map["c-hero"].setChecked(True)
    dialog._checkbox_map["c-villain"].setChecked(True)
    updated_selected = dialog.get_selected_fg_assets()
    assert "c-hero" in updated_selected
    assert "c-villain" in updated_selected

    # Uncheck c-villain
    dialog._checkbox_map["c-villain"].setChecked(False)
    updated_selected = dialog.get_selected_fg_assets()
    assert "c-hero" in updated_selected
    assert "c-villain" not in updated_selected


def test_lighting_builder_script_generation(tmp_path):
    """Verify LightingBuilder script contains fg, bg, chr_fg, chr_bg, etc."""
    builder = LightingBuilder()

    final_path = tmp_path / "SH001_lighting.blend"
    ver_path = tmp_path / "progress" / "SH001_lighting_v001.blend"
    source_anim = tmp_path / "SH001_animation.blend"

    script = builder.script_builder(
        filepath=str(final_path),
        version_path=str(ver_path),
        master_file="",
        animation_file=str(source_anim),
        setting_data={"frame_in": 101, "frame_out": 200, "fps": 24, "resolution": [1920, 1080]},
        collection_list=[("chr", "c-"), ("prp", "p-"), ("vhc", "v-"), ("cam", None)],
        set_collection={"set": ["/path/s-forest.blend"]},
        fg_assets=["c-hero", "p-sword"],
    )

    # Check collection names and logic
    assert "fg_assets = ['c-hero', 'p-sword']" in script
    assert "fg_root = ensure_collection(\"fg\")" in script
    assert "bg_root = ensure_collection(\"bg\")" in script
    assert "fg_cat_name = f\"{code}_fg\"" in script
    assert "bg_cat_name = f\"{code}_bg\"" in script
    assert "is_asset_in_fg" in script
    assert "link_set_collection(collections)" in script
    assert "link_animation()" in script


def test_lighting_builder_extract_data_headless(tmp_path):
    """Verify extract_data runs in headless mode and produces correct script."""
    builder = LightingBuilder()

    mock_shot_data = {
        "name": "SH001",
        "sequence": "SQ01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "3810b978"},
            {"name": "c-villain", "entity_type_id": "3810b978"},
            {"name": "s-forest", "entity_type_id": "44b7cabe"},
        ],
        "data": {"frame_in": 101, "frame_out": 150, "fps": 24, "resolution": "1920x1080"},
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "3810b978", "code": "chr", "prefix": "c-", "base_path": "/assets/char"},
                "SET": {"id": "44b7cabe", "code": "set", "prefix": "s-", "base_path": "/assets/set"},
            }
        }
    }
    mock_current_dept = {
        "Lighting": {"code": "lgt", "presets": {}}
    }
    filepath_dict = {
        "final": str(tmp_path / "SQ01_SH001_lgt.blend"),
        "version": str(tmp_path / "progress" / "SQ01_SH001_lgt_v001.blend"),
        "source": str(tmp_path / "SQ01_SH001_anm.blend"),
    }

    # Headless without explicit fg_assets defaults to [] (all in BG)
    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        mastershots_data={},
        addons_data={},
        filepath=filepath_dict,
        show_ui=False,
    )

    assert "fg_assets = []" in script
    assert "ensure_collection(\"fg\")" in script
    assert "ensure_collection(\"bg\")" in script


def test_lighting_builder_extract_data_with_dialog(monkeypatch, tmp_path, qapp):
    """Verify extract_data connects with LightingAssetDialog and retrieves user FG selection."""
    builder = LightingBuilder()

    mock_shot_data = {
        "name": "SH001",
        "sequence": "SQ01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "c-villain", "entity_type_id": "char_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 100, "fps": 24},
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-"},
            }
        }
    }
    mock_current_dept = {"Lighting": {"code": "lgt"}}
    filepath_dict = {
        "final": str(tmp_path / "SQ01_SH001_lgt.blend"),
        "version": str(tmp_path / "progress" / "SQ01_SH001_lgt_v001.blend"),
        "source": str(tmp_path / "SQ01_SH001_anm.blend"),
    }

    # Temporarily bypass PYTEST_CURRENT_TEST to test dialog execution path
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    # 1. Test Dialog Accepted with c-hero checked
    def mock_exec_accepted(self):
        self._checkbox_map["c-hero"].setChecked(True)
        return 1

    monkeypatch.setattr(LightingAssetDialog, "exec", mock_exec_accepted)

    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        mastershots_data={},
        addons_data={},
        filepath=filepath_dict,
        show_ui=True,
    )
    assert "fg_assets = ['c-hero']" in script

    # 2. Test Dialog Cancelled
    monkeypatch.setattr(LightingAssetDialog, "exec", lambda self: 0)
    with pytest.raises(RuntimeError, match="cancelled by user"):
        builder.extract_data(
            shot_data=mock_shot_data,
            current_department=mock_current_dept,
            asset_department=mock_asset_dept,
            mastershots_data={},
            addons_data={},
            filepath=filepath_dict,
            show_ui=True,
        )


def test_lighting_builder_with_real_preset(tmp_path):
    """Verify that LightingBuilder successfully embeds pipeline/Presets/mdt_preset_lgt.py without error."""
    preset_file = REPO_ROOT / "pipeline" / "Presets" / "mdt_preset_lgt.py"
    assert preset_file.is_file()

    builder = LightingBuilder()
    mock_shot_data = {
        "name": "SH001",
        "sequence": "SQ01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "p-sword", "entity_type_id": "prop_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 100, "fps": 24},
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-"},
                "PROPS": {"id": "prop_id", "code": "prp", "prefix": "p-"},
            }
        }
    }
    mock_current_dept = {
        "Lighting": {
            "code": "lgt",
            "presets": {
                "preset": {"path": str(preset_file)},
            },
        }
    }
    filepath_dict = {
        "final": str(tmp_path / "SQ01_SH001_lgt.blend"),
        "version": str(tmp_path / "progress" / "SQ01_SH001_lgt_v001.blend"),
        "source": str(tmp_path / "SQ01_SH001_anm.blend"),
    }

    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        mastershots_data={},
        addons_data={},
        filepath=filepath_dict,
        fg_assets=["c-hero"],
        show_ui=False,
    )

    assert "setup_view_layers()" in script
    assert "View Layers configured" in script
    # Verify Python syntax validity
    compile(script, "<generated_lighting_script>", "exec")


def test_lighting_builder_fg_yaml_per_shot(tmp_path):
    """Verify that LightingBuilder extracts FG assets from per-shot YAML mapping."""
    yaml_file = tmp_path / "lighting_batch_fg.yaml"
    yaml_content = """
    sq01_sh010:
      - c-hero
      - p-sword
    sq01_sh020:
      - c-villain
    """
    yaml_file.write_text(yaml_content)

    builder = LightingBuilder()
    mock_shot_data = {
        "name": "sh010",
        "sequence": "sq01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "c-villain", "entity_type_id": "char_id"},
            {"name": "p-sword", "entity_type_id": "prop_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 100, "fps": 24},
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-"},
                "PROPS": {"id": "prop_id", "code": "prp", "prefix": "p-"},
            }
        }
    }
    mock_current_dept = {"Lighting": {"code": "lgt"}}
    filepath_dict = {
        "final": str(tmp_path / "sq01_sh010_lgt.blend"),
        "version": str(tmp_path / "progress" / "sq01_sh010_lgt_v001.blend"),
        "source": str(tmp_path / "sq01_sh010_anm.blend"),
    }

    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        mastershots_data={},
        addons_data={},
        filepath=filepath_dict,
        fg_yaml=str(yaml_file),
        show_ui=False,
    )

    assert "fg_assets = ['c-hero', 'p-sword']" in script


def test_lighting_builder_fg_yaml_wildcard_and_exclusion(tmp_path):
    """Verify wildcard matching (e.g. c-*) and bg_assets exclusion."""
    yaml_content = """
    shots:
      sq01_sh010:
        fg_assets:
          - "c-*"
          - "p-sword"
        bg_assets:
          - "c-crowd_*"
    """
    cfg = LightingBuilder.load_fg_config_from_yaml(yaml_content)
    shot_data = {"name": "sh010", "sequence": "sq01"}
    available = ["c-hero", "c-villain", "c-crowd_01", "p-sword", "p-shield"]

    resolved = LightingBuilder.resolve_fg_assets_from_config(cfg, shot_data, available)
    assert "c-hero" in resolved
    assert "c-villain" in resolved
    assert "p-sword" in resolved
    assert "c-crowd_01" not in resolved  # Excluded by bg_assets
    assert "p-shield" not in resolved


def test_lighting_builder_fg_yaml_global_list():
    """Verify global flat list YAML applies across all shots."""
    yaml_content = """
    - c-hero
    - p-sword
    """
    cfg = LightingBuilder.load_fg_config_from_yaml(yaml_content)
    shot_data = {"name": "sh099", "sequence": "sq99"}
    available = ["c-hero", "c-villain", "p-sword"]

    resolved = LightingBuilder.resolve_fg_assets_from_config(cfg, shot_data, available)
    assert resolved == ["c-hero", "p-sword"]


def test_lighting_builder_fg_auto_discovery(tmp_path):
    """Verify auto-discovery of fg_assets.yaml in shot/sequence directories."""
    # Place fg_assets.yaml in the shot directory
    fg_file = tmp_path / "fg_assets.yaml"
    fg_file.write_text("""
    sq01_sh030:
      - c-hero
    """)

    builder = LightingBuilder()
    mock_shot_data = {
        "name": "sh030",
        "sequence": "sq01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "char_id"},
            {"name": "c-villain", "entity_type_id": "char_id"},
        ],
        "data": {"frame_in": 1, "frame_out": 100, "fps": 24},
    }
    mock_asset_dept = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "char_id", "code": "chr", "prefix": "c-"},
            }
        }
    }
    mock_current_dept = {"Lighting": {"code": "lgt"}}
    filepath_dict = {
        "final": str(tmp_path / "sq01_sh030_lgt.blend"),
        "version": str(tmp_path / "progress" / "sq01_sh030_lgt_v001.blend"),
        "source": str(tmp_path / "sq01_sh030_anm.blend"),
    }

    # Don't pass fg_yaml or fg_assets: auto-discovery should find tmp_path/fg_assets.yaml
    script = builder.extract_data(
        shot_data=mock_shot_data,
        current_department=mock_current_dept,
        asset_department=mock_asset_dept,
        mastershots_data={},
        addons_data={},
        filepath=filepath_dict,
        show_ui=False,
    )

    assert "fg_assets = ['c-hero']" in script


def test_prompt_batch_parameters_lighting():
    """Verify that PipelineService.prompt_batch_parameters properly triggers LightingBatchDialog."""
    from unittest.mock import patch
    from PySide6.QtWidgets import QDialog
    from zeroxe.services.pipeline_service import PipelineService
    from pipeline.Commands.Builders.lighting_dialog import LightingBatchDialog

    selected_items = [{"name": "sh010", "sequence": "sq01"}, {"name": "sh020", "sequence": "sq01"}]

    with patch.object(
        LightingBatchDialog, "exec", return_value=QDialog.DialogCode.Accepted
    ), patch.object(
        LightingBatchDialog,
        "get_result",
        return_value={"fg_yaml": "/projects/mdt/batch_fg.yaml"},
    ):
        params = PipelineService.prompt_batch_parameters(
            department="Lighting",
            action="Generate",
            selected_items=selected_items,
            available_shots=["sq01_sh010", "sq01_sh020"],
        )
        assert params == {"fg_yaml": "/projects/mdt/batch_fg.yaml"}




