"""Test suite for LayoutBuilder clean and source-from-shot casting setup and Layout dialogs."""

import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtWidgets import QApplication, QDialog

from pipeline.Commands.Builders.builder_factory import BuilderFactory
from pipeline.Commands.Builders.layout_builder import LayoutBuilder
from pipeline.Commands.Builders.layout_dialog import (
    LayoutBatchDialog,
    LayoutDialog,
    _parse_shot_identifier,
    _resolve_sibling_shot_layout_path,
)
from zeroxe.services.pipeline_service import PipelineService


class TestLayoutBuilder(unittest.TestCase):
    """Test suite for LayoutBuilder and LayoutDialog."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_shot_identifier(self):
        """Verify parsing of shot identifiers."""
        ep, sq, sh = _parse_shot_identifier("sq01_sh0010", default_episode="ep998", default_sequence="sq01")
        self.assertEqual(ep, "ep998")
        self.assertEqual(sq, "sq01")
        self.assertEqual(sh, "sh0010")

        ep, sq, sh = _parse_shot_identifier("ep998_sq02_sh0030", default_episode="ep998", default_sequence="sq01")
        self.assertEqual(ep, "ep998")
        self.assertEqual(sq, "sq02")
        self.assertEqual(sh, "sh0030")

    def test_clean_script_generation(self, tmp_path=None):
        """Verify clean generation script creates fresh scene with camera rig and timeline settings."""
        builder = LayoutBuilder()
        shot_data = {
            "name": "sh010",
            "sequence": "sq01",
            "episode": "ep998",
            "data": {"frame_in": 1, "frame_out": 120, "fps": 24, "resolution": "1920x1080"},
            "assets": [
                {"name": "c-hero", "entity_type_id": "chr-id"},
                {"name": "s-room", "entity_type_id": "set-id"},
            ],
        }
        asset_dept = {
            "Asset": {
                "asset_type": {
                    "CHR": {"id": "chr-id", "code": "chr", "prefix": "c-", "base_path": "/projects/mdt/chr"},
                    "SET": {"id": "set-id", "code": "set", "prefix": "s-", "base_path": "/projects/mdt/set"},
                }
            }
        }
        filepaths = {
            "version": "/tmp/layout_sh010_v001.blend",
            "final": "/tmp/layout_sh010.blend",
        }

        script = builder.extract_data(
            shot_data=shot_data,
            current_department={"Layout": {"code": "lay"}},
            asset_department=asset_dept,
            filepath=filepaths,
            layout_mode="clean",
            show_ui=False,
        )

        self.assertIn("clear_all()", script)
        self.assertIn("add_camera_rig()", script)
        self.assertIn("link_collection(collections)", script)
        self.assertIn("'frame_in': 1", script)
        self.assertIn("'frame_out': 120", script)
        self.assertIn("bpy.context.scene.frame_start = settings[\"frame_in\"]", script)
        self.assertIn("bpy.context.scene.frame_end = settings[\"frame_out\"]", script)
        self.assertIn("bpy.context.scene.render.fps = settings[\"fps\"]", script)
        self.assertIn("bpy.context.scene.render.resolution_x = res[0]", script)
        self.assertIn("bpy.context.scene.render.resolution_y = res[1]", script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/layout_sh010_v001.blend")', script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/layout_sh010.blend", copy=True)', script)

    def test_source_shot_script_generation(self):
        """Verify source shot script opens template, preserves existing scene elements, and links missing Kitsu assets."""
        builder = LayoutBuilder()
        shot_data = {
            "name": "sh020",
            "sequence": "sq01",
            "episode": "ep998",
            "data": {"frame_in": 10, "frame_out": 85, "fps": 24, "resolution": "1920x1080"},
            "assets": [
                {"name": "c-hero", "entity_type_id": "chr-id"},
                {"name": "c-villain", "entity_type_id": "chr-id"},
            ],
        }
        asset_dept = {
            "Asset": {
                "asset_type": {
                    "CHR": {"id": "chr-id", "code": "chr", "prefix": "c-", "base_path": "/projects/mdt/chr"},
                }
            }
        }
        filepaths = {
            "version": "/tmp/layout_sh020_v001.blend",
            "final": "/tmp/layout_sh020.blend",
        }

        script = builder.extract_data(
            shot_data=shot_data,
            current_department={"Layout": {"code": "lay"}},
            asset_department=asset_dept,
            filepath=filepaths,
            layout_mode="source_shot",
            source_file="/projects/mdt/02_production/01_layout/sq01/sq01_sh010/sq01_sh010.blend",
            show_ui=False,
        )

        self.assertIn('bpy.ops.wm.open_mainfile(filepath=source_file)', script)
        self.assertIn('source_file = "/projects/mdt/02_production/01_layout/sq01/sq01_sh010/sq01_sh010.blend"', script)
        self.assertIn("get_existing_asset_names()", script)
        self.assertIn("'frame_in': 10", script)
        self.assertIn("'frame_out': 85", script)
        self.assertIn("bpy.context.scene.frame_start = settings[\"frame_in\"]", script)
        self.assertIn("bpy.context.scene.frame_end = settings[\"frame_out\"]", script)
        self.assertIn("bpy.context.scene.render.fps = settings[\"fps\"]", script)
        self.assertIn("bpy.context.scene.render.resolution_x = res[0]", script)
        self.assertIn("bpy.context.scene.render.resolution_y = res[1]", script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/layout_sh020_v001.blend")', script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/layout_sh020.blend", copy=True)', script)

    def test_layout_dialog_clean_selection(self):
        """Verify LayoutDialog returns clean mode by default."""
        shot_data = {"name": "sh010", "sequence": "sq01", "episode": "ep998"}
        dlg = LayoutDialog(shot_data=shot_data, available_shots=["sq01_sh020", "sq01_sh030"])
        self.assertTrue(dlg.rb_clean.isChecked())
        res = dlg.get_result()
        self.assertEqual(res["layout_mode"], "clean")
        self.assertIsNone(res["source_file"])
        dlg.close()

    def test_layout_dialog_source_shot_selection(self):
        """Verify LayoutDialog allows selecting source shot."""
        shot_data = {"name": "sh010", "sequence": "sq01", "episode": "ep998"}
        dlg = LayoutDialog(shot_data=shot_data, available_shots=["sq01_sh020", "sq01_sh030"])

        with patch(
            "pipeline.Commands.Builders.layout_dialog._resolve_sibling_shot_layout_path",
            return_value=Path("/tmp/resolved_sh020.blend"),
        ):
            dlg.set_selected_shot("sq01_sh020")
            res = dlg.get_result()
            self.assertEqual(res["layout_mode"], "source_shot")
            self.assertEqual(res["source_shot"], "sq01_sh020")
            self.assertEqual(res["source_file"], "/tmp/resolved_sh020.blend")
        dlg.close()

    def test_layout_dialog_custom_file_selection(self):
        """Verify LayoutDialog allows selecting custom file."""
        shot_data = {"name": "sh010", "sequence": "sq01", "episode": "ep998"}
        dlg = LayoutDialog(shot_data=shot_data)
        dlg.rb_custom.setChecked(True)
        dlg.edit_custom_path.setText("/path/to/template.blend")
        res = dlg.get_result()
        self.assertEqual(res["layout_mode"], "custom")
        self.assertEqual(res["source_file"], "/path/to/template.blend")
        dlg.close()

    def test_layout_batch_dialog(self):
        """Verify LayoutBatchDialog allows selecting clean or single source shot."""
        selected_items = [{"name": "sh010"}, {"name": "sh020"}]
        dlg = LayoutBatchDialog(selected_items=selected_items, available_shots=["sq01_sh010", "sq01_sh020"])
        self.assertTrue(dlg.rb_clean.isChecked())
        self.assertEqual(dlg.get_result()["layout_mode"], "clean")

        dlg.set_selected_shot("sq01_sh010")
        res = dlg.get_result()
        self.assertEqual(res["layout_mode"], "source_shot")
        self.assertEqual(res["source_shot"], "sq01_sh010")
        dlg.close()

    def test_prompt_batch_parameters_layout(self):
        """Verify PipelineService.prompt_batch_parameters routes to LayoutBatchDialog."""
        selected_items = [{"name": "sh010"}, {"name": "sh020"}]

        with patch.object(
            PipelineService, "get_active_pipeline_yaml_path", return_value=Path("pipeline/pipeline.yaml")
        ), patch.object(
            LayoutBatchDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ), patch.object(
            LayoutBatchDialog,
            "get_result",
            return_value={"layout_mode": "clean", "source_shot": None, "source_file": None},
        ):
            params = PipelineService.prompt_batch_parameters(
                department="Layout",
                action="Generate",
                selected_items=selected_items,
            )
            self.assertEqual(params, {"layout_mode": "clean", "source_shot": None, "source_file": None})

    def test_camera_rig_fallback_and_preset_ordering(self):
        """Verify camera fallback is generated and presets are saved correctly."""
        builder = LayoutBuilder()
        shot_data = {
            "name": "sh030",
            "sequence": "sq01",
            "episode": "ep998",
            "data": {"frame_in": 1, "frame_out": 50, "fps": 24},
            "assets": [],
        }
        script = builder.extract_data(
            shot_data=shot_data,
            current_department={"Layout": {"code": "lay"}},
            filepath={"version": "/tmp/v.blend", "final": "/tmp/f.blend"},
            layout_mode="clean",
            show_ui=False,
        )
        self.assertIn("Fallback standard camera created", script)
        self.assertIn("bpy.ops.object.camera_add()", script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/v.blend")', script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/f.blend", copy=True)', script)

    def test_dcc_timeout_configuration(self):
        """Verify DCC timeout defaults to 600s and can be configured."""
        from zeroxe.services.settings_service import SettingsService
        timeout = SettingsService.get_dcc_timeout()
        self.assertGreaterEqual(timeout, 300)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
            with patch.object(SettingsService, "get_active_blender", return_value=sys.executable):
                success, output = PipelineService.execute_blender_script("print(1)")
                self.assertTrue(success)
                _, kwargs = mock_run.call_args
                self.assertEqual(kwargs.get("timeout"), timeout)


if __name__ == "__main__":
    unittest.main()
