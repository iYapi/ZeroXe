import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Ensure repo root and src are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PIPELINE_DIR = REPO_ROOT / "pipeline"

for p in [str(REPO_ROOT), str(SRC_DIR), str(PIPELINE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtWidgets import QApplication, QDialog

from pipeline.Commands.Builders.builder_factory import BuilderFactory
from pipeline.Commands.Builders.compositing_builder import CompositingBuilder
from pipeline.Commands.Builders.compositing_dialog import (
    CompositingBatchDialog,
    CompositingDialog,
)
from pipeline.Commands.Builders.lighting_dialog import LightingBatchDialog
from zeroxe.services.pipeline_service import PipelineService


class TestCompositingBuilder(unittest.TestCase):
    """Test suite for CompositingBuilder mastershot resolution and script generation."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_kitsu_ms_comp_resolution(self, tmp_path_factory=None):
        shot_data = {
            "name": "sh010",
            "sequence": "sq01",
            "episode": "ep998",
            "assets": [
                {"name": "COMP_sq01", "entity_type_id": "ms-comp-id"},
            ],
        }
        asset_dept = {
            "Asset": {
                "asset_type": {
                    "MS_COMP": {
                        "id": "ms-comp-id",
                        "code": "ms",
                        "prefix": "COMP_",
                        "base_path": "/projects/mdt/preset_comp/",
                    }
                }
            }
        }

        builder = CompositingBuilder()
        ms_file, ms_name = builder.resolve_kitsu_ms_comp(
            shot_data=shot_data,
            asset_department=asset_dept,
            project_path="/projects/mdt",
        )
        self.assertEqual(ms_name, "COMP_sq01")
        self.assertEqual(ms_file, Path("/projects/mdt/preset_comp/COMP_sq01/COMP_sq01.blend"))

    def test_extract_data_with_explicit_master_file(self, tmp_path=None):
        builder = CompositingBuilder()
        shot_data = {
            "name": "sh020",
            "sequence": "sq01",
            "episode": "ep998",
            "data": {"frame_in": 101, "frame_out": 150, "fps": 24, "resolution": "1920x1080"},
        }
        file_paths = {
            "version": "/tmp/test_comp_v001.blend",
            "final": "/tmp/test_comp.blend",
        }
        script = builder.extract_data(
            shot_data=shot_data,
            current_department={"Compositing": {"code": "comp"}},
            filepath=file_paths,
            master_file="/projects/mdt/templates/hero_template.blend",
            show_ui=False,
        )

        self.assertIn('master_file = "/projects/mdt/templates/hero_template.blend"', script)
        self.assertIn('bpy.ops.wm.open_mainfile(filepath=master_file)', script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/test_comp.blend")', script)
        self.assertIn('bpy.ops.wm.save_as_mainfile(filepath="/tmp/test_comp_v001.blend")', script)

    def test_extract_data_with_sibling_master_shot(self):
        builder = CompositingBuilder()
        shot_data = {
            "name": "sh020",
            "sequence": "sq01",
            "episode": "ep998",
            "project_name": "MDT",
        }
        file_paths = {
            "version": "/tmp/test_comp_v001.blend",
            "final": "/tmp/test_comp.blend",
        }

        with patch.object(
            CompositingBuilder,
            "resolve_sibling_shot_comp",
            return_value=Path("/projects/mdt/03_post_production/02_compositing/ep998/ep998_sq01/ep998_sq01_sh010/mdt_ep998_sq01_sh010_comp.blend"),
        ):
            script = builder.extract_data(
                shot_data=shot_data,
                current_department={"Compositing": {"code": "comp"}},
                filepath=file_paths,
                master_shot="sq01_sh010",
                show_ui=False,
            )

            self.assertIn("mdt_ep998_sq01_sh010_comp.blend", script)

    def test_compositing_dialog_interactive_kitsu_selection(self):
        shot_data = {"name": "sh010", "sequence": "sq01", "episode": "ep998"}
        kitsu_file = Path("/projects/mdt/preset_comp/COMP_sq01/COMP_sq01.blend")

        dlg = CompositingDialog(
            shot_data=shot_data,
            kitsu_ms_comp_file=kitsu_file,
            kitsu_ms_comp_name="COMP_sq01",
        )
        self.assertTrue(dlg.rb_kitsu.isChecked())
        dlg._on_accept()

        res = dlg.get_result()
        self.assertEqual(res["master_mode"], "kitsu")
        self.assertEqual(res["master_file"], str(kitsu_file))

    def test_compositing_dialog_interactive_shot_selection(self):
        shot_data = {"name": "sh020", "sequence": "sq01", "episode": "ep998"}
        dlg = CompositingDialog(
            shot_data=shot_data,
            available_shots=["sh010", "sh015"],
        )
        dlg.set_selected_shot("sh010")

        with patch(
            "pipeline.Commands.Builders.compositing_dialog._resolve_sibling_shot_comp_path",
            return_value=Path("/resolved/sh010_comp.blend"),
        ):
            dlg._on_accept()
            res = dlg.get_result()
            self.assertEqual(res["master_mode"], "shot")
            self.assertEqual(res["master_shot"], "sh010")
            self.assertEqual(res["master_file"], "/resolved/sh010_comp.blend")

    def test_compositing_batch_dialog(self):
        selected_items = [
            {"name": "sh010", "sequence": "sq01"},
            {"name": "sh020", "sequence": "sq01"},
            {"name": "sh030", "sequence": "sq01"},
        ]
        dlg = CompositingBatchDialog(selected_items=selected_items)
        self.assertTrue(dlg.rb_kitsu.isChecked())

        # Select single master shot mode via list
        dlg.set_selected_shot("sq01_sh010")
        dlg._on_accept()

        res = dlg.get_result()
        self.assertEqual(res["master_mode"], "shot")
        self.assertEqual(res["master_shot"], "sq01_sh010")

    def test_prompt_batch_parameters_compositing(self):
        selected_items = [{"name": "sh010"}, {"name": "sh020"}]

        with patch.object(
            CompositingBatchDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ), patch.object(
            CompositingBatchDialog,
            "get_result",
            return_value={"master_mode": "shot", "master_shot": "sh010"},
        ):
            params = PipelineService.prompt_batch_parameters(
                department="Compositing",
                action="Generate",
                selected_items=selected_items,
            )
            self.assertEqual(params, {"master_mode": "shot", "master_shot": "sh010"})

    def test_parse_shot_identifier(self):
        from pipeline.Commands.Builders.compositing_dialog import _parse_shot_identifier

        # 1. Standard assetList sequence_shot format
        ep, sq, sh = _parse_shot_identifier("sq01_sh0010", default_episode="ep998", default_sequence="sq01")
        self.assertEqual(ep, "ep998")
        self.assertEqual(sq, "sq01")
        self.assertEqual(sh, "sh0010")

        # 2. Episode + sequence + shot format
        ep, sq, sh = _parse_shot_identifier("ep998_sq02_sh0030", default_episode="ep998", default_sequence="sq01")
        self.assertEqual(ep, "ep998")
        self.assertEqual(sq, "sq02")
        self.assertEqual(sh, "sh0030")

        # 3. Simple shot name format
        ep, sq, sh = _parse_shot_identifier("sh0050", default_episode="ep998", default_sequence="sq01")
        self.assertEqual(ep, "ep998")
        self.assertEqual(sq, "sq01")
        self.assertEqual(sh, "sh0050")

    def test_sibling_shot_path_resolution_with_sequence_prefix(self):
        from pipeline.Commands.Builders.compositing_dialog import _resolve_sibling_shot_comp_path

        shot_data = {
            "name": "sh0020",
            "sequence": "sq01",
            "episode": "ep998",
            "project_name": "MDT",
        }
        current_dept = {
            "Compositing": {
                "code": "comp",
                "base_path": "/projects/mdt/03_post_production/02_compositing/",
            }
        }

        # Sibling shot name from assetList (e.g. sq01_sh0010)
        with patch(
            "zeroxe.services.pipeline_service.PipelineService.resolve_shot"
        ) as mock_resolve:
            mock_res = MagicMock()
            mock_res.master_path = Path("/projects/mdt/03_post_production/02_compositing/ep998/ep998_sq01/ep998_sq01_sh0010/mdt_ep998_sq01_sh0010_comp.blend")
            mock_resolve.return_value = mock_res

            resolved = _resolve_sibling_shot_comp_path(
                sibling_shot_name="sq01_sh0010",
                shot_data=shot_data,
                current_department=current_dept,
                project_path="/projects/mdt",
            )

            # Verify resolve_shot was called with clean sequence and shot tokens
            mock_resolve.assert_called_with(
                department="Compositing",
                episode="ep998",
                sequence="sq01",
                shot="sh0010",
                project_name="MDT",
                project_path="/projects/mdt",
            )
            self.assertEqual(
                resolved,
                Path("/projects/mdt/03_post_production/02_compositing/ep998/ep998_sq01/ep998_sq01_sh0010/mdt_ep998_sq01_sh0010_comp.blend"),
            )

    def test_compositing_dialog_discovers_available_shots_like_asset_list(self):
        from zeroxe.models.shot_model import Shot
        from zeroxe.services.shot_service import ShotService

        shot_data = {
            "name": "sh0020",
            "sequence": "sq01",
            "episode": "ep998",
            "episode_id": "ep-123",
        }

        mock_shots = [
            Shot.from_kitsu({"id": "1", "name": "sh0010", "sequence": "sq01", "episode": "ep998"}),
            Shot.from_kitsu({"id": "2", "name": "sh0020", "sequence": "sq01", "episode": "ep998"}),
            Shot.from_kitsu({"id": "3", "name": "sh0030", "sequence": "sq01", "episode": "ep998"}),
            Shot.from_kitsu({"id": "4", "name": "sh0010", "sequence": "sq02", "episode": "ep998"}),
        ]

        with patch.object(ShotService, "get_shots_by_episode_id", return_value=mock_shots):
            dlg = CompositingDialog(shot_data=shot_data)
            # Available sibling shots should exclude current shot (sq01_sh0020) and format like assetList
            self.assertIn("sq01_sh0010", dlg.available_shots)
            self.assertIn("sq01_sh0030", dlg.available_shots)
            self.assertIn("sq02_sh0010", dlg.available_shots)
            self.assertNotIn("sq01_sh0020", dlg.available_shots)


if __name__ == "__main__":
    unittest.main()

