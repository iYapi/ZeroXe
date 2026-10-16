"""Unit tests for Playblast Collect feature.

Verifies:
1. Feature discovery in feature_registry and PipelineService.
2. Render path resolution from pipeline.yaml.
3. Recursive scanning and version extraction of playblasts.
4. PipelineService.collect_playblasts execution.
5. Integration with LauncherController execution flow.
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.Commands.feature_registry import execute_feature, list_available_features
from zeroxe.models.department_model import Department
from zeroxe.models.project_model import Project
from zeroxe.models.shot_model import Shot
from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.settings_service import SettingsService


def test_playblast_collect_feature_discovered():
    """Verify that 'Playblast Collect' appears in available pipeline features."""
    features_all = list_available_features()
    features_anm = list_available_features(department="Animation")
    features_lay = list_available_features(department="Layout")

    assert "Playblast Collect" in features_all
    assert "Playblast Collect" in features_anm
    assert "Playblast Collect" in features_lay


def test_feature_requires_dcc():
    """Verify that feature_requires_dcc correctly identifies DCC vs pure-pipeline features."""
    assert PipelineService.feature_requires_dcc("Playblast Collect") is False
    assert PipelineService.feature_requires_dcc("Generate") is True
    assert PipelineService.feature_requires_dcc("Sync") is True


def test_pipeline_get_render_path():
    """Verify render path is resolved from pipeline.yaml by pipeline collector."""
    from pipeline.Commands.Additional.playblast_collector import get_render_path

    render_path = get_render_path()
    assert render_path is not None
    assert "melangkah_dari_timur" in str(render_path)


def test_pipeline_collect_playblasts(tmp_path):
    """Verify collect_playblasts in pipeline scans and copies latest versions."""
    from pipeline.Commands.Additional.playblast_collector import collect_playblasts

    render_root = tmp_path / "renders"
    dest_dir = tmp_path / "destination"

    # Create dummy render structure
    # mdt_ep998_sq01_sh0010_lay_v001.mov and v002
    shot_dir = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0010" / "playblast" / "lay"
    shot_dir.mkdir(parents=True, exist_ok=True)

    v1 = shot_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov"
    v2 = shot_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov"
    v1.write_text("version 1")
    v2.write_text("version 2 (latest)")

    shot_obj = Shot(
        id="shot_1",
        name="sh0010",
        sequence_id="sq_1",
        sequence="sq01",
        episode_id="ep_1",
        episode="ep998",
        preview_file_id="",
        resolution="1920x1080",
        fps=24,
        frame_in=1,
        frame_out=100,
        assets=[],
    )

    res = collect_playblasts(
        destination_dir=dest_dir,
        shots=[shot_obj],
        department="Layout",
        file_format=".mov",
        render_path=render_root,
        episode="ep998",
        sequence="sq01",
    )

    assert res.success is True
    assert len(res.copied_files) == 1
    copied = res.copied_files[0]
    assert copied.destination.name == "mdt_ep998_sq01_sh0010_lay_v002.mov"
    assert copied.version_number == 2
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov").is_file()
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov").read_text() == "version 2 (latest)"


def test_execute_feature_registry_playblast_collect(tmp_path):
    """Verify execution through feature registry dispatch."""
    render_root = tmp_path / "renders"
    dest_dir = tmp_path / "destination"
    shot_dir = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0020" / "playblast" / "anm"
    shot_dir.mkdir(parents=True, exist_ok=True)

    pb_file = shot_dir / "mdt_ep998_sq01_sh0020_anm_v001.mov"
    pb_file.write_text("pb animation")

    res = execute_feature(
        feature_name="Playblast Collect",
        filepath="",
        department="Animation",
        shots=["sh0020"],
        destination_dir=dest_dir,
        render_path=render_root,
        file_format=".mov",
        episode="ep998",
    )

    assert res.success is True
    assert res.data.get("copied_count") == 1
    assert (dest_dir / "mdt_ep998_sq01_sh0020_anm_v001.mov").is_file()


def test_launcher_controller_playblast_collect_flow(qtbot, tmp_path, monkeypatch):
    """Verify LauncherController generic dispatch executes Playblast Collect via pipeline."""
    from zeroxe.views.launcher_view import LauncherView
    from zeroxe.controllers.launcher_controller import LauncherController
    from pipeline.Commands.Additional.playblast_dialog import PlayblastCollectDialog, PlayblastResultDialog

    # Setup temporary QSettings and mock zeroxe_map pointing to local pipeline.yaml
    ini_file = str(tmp_path / "test_launcher.ini")
    test_settings = QSettings(ini_file, QSettings.Format.IniFormat)
    monkeypatch.setattr(
        "zeroxe.services.settings_service.SettingsService._settings",
        lambda: test_settings,
    )
    monkeypatch.setattr(
        "zeroxe.services.settings_service.SettingsService.get_zeroxe_map",
        lambda: {
            "project": {
                "Melangkah Dari Timur": {
                    "name": "Melangkah Dari Timur",
                    "code": "MDT",
                    "pipeline_path": str(REPO_ROOT / "pipeline" / "pipeline.yaml"),
                }
            }
        },
    )
    monkeypatch.setattr(
        "zeroxe.services.shot_service.ShotService.get_assets_for_shot",
        lambda *args, **kwargs: [],
    )
    PipelineService.clear_cache()

    # Setup render directory
    render_root = tmp_path / "renders"
    dest_dir = tmp_path / "my_collected_playblasts"
    shot_dir = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0010" / "playblast" / "lay"
    shot_dir.mkdir(parents=True, exist_ok=True)
    (shot_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov").write_text("v1")
    (shot_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov").write_text("v2 latest")

    # Load pipeline module so internal references exist
    PipelineService.load_pipeline_module("Melangkah Dari Timur")
    import Additional.playblast_dialog as apd
    import pipeline.Commands.Additional.playblast_dialog as pcapd

    # Bypass confirmation and completion dialogs
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    # Mock PlayblastCollectDialog to set destination and render path
    orig_init = apd.PlayblastCollectDialog.__init__

    def mock_dlg_init(self, *args, **kwargs):
        kwargs["render_path"] = render_root
        orig_init(self, *args, **kwargs)
        self.edit_destination.setText(str(dest_dir))

    result_exec_mock = MagicMock(return_value=True)

    for mod in [apd, pcapd]:
        monkeypatch.setattr(mod.PlayblastCollectDialog, "__init__", mock_dlg_init)
        monkeypatch.setattr(mod.PlayblastCollectDialog, "exec", lambda self: 1)
        monkeypatch.setattr(mod.PlayblastResultDialog, "exec", result_exec_mock)

    for k, v in list(sys.modules.items()):
        if "feature_registry" in k:
            if hasattr(v, "PlayblastCollectDialog") and v.PlayblastCollectDialog:
                monkeypatch.setattr(v.PlayblastCollectDialog, "__init__", mock_dlg_init)
                monkeypatch.setattr(v.PlayblastCollectDialog, "exec", lambda self: 1)
            if hasattr(v, "PlayblastResultDialog") and v.PlayblastResultDialog:
                monkeypatch.setattr(v.PlayblastResultDialog, "exec", result_exec_mock)

    view = LauncherView()
    qtbot.addWidget(view)
    ctrl = LauncherController(view)

    # Mock current project and department
    ctrl.current_project = Project(id="p1", name="Melangkah Dari Timur", code="MDT")
    ctrl.current_department = Department(id="d1", name="Layout")
    view.ui.comboBox_category.addItem("ep998")
    view.ui.comboBox_category.setCurrentText("ep998")

    # Set mock shot and filepath
    shot_10 = Shot(
        id="s1",
        name="sh0010",
        sequence_id="sq1",
        sequence="sq01",
        episode_id="ep1",
        episode="ep998",
        preview_file_id="",
        resolution="1920x1080",
        fps=24,
        frame_in=1,
        frame_out=100,
        assets=[],
    )
    ctrl.current_shot = shot_10
    ctrl.selected_file_path = str(tmp_path / "dummy.blend")

    # Set feature combobox to Playblast Collect
    ctrl.feature_combobox.addItem("Playblast Collect")
    ctrl.feature_combobox.setCurrentText("Playblast Collect")

    # Trigger generic action
    ctrl.on_execute_action()

    # Check that file was copied
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov").is_file()
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov").read_text() == "v2 latest"
    assert result_exec_mock.called


def test_feature_handles_batch():
    """Verify feature_handles_batch identifies Playblast Collect as handling batch natively."""
    assert PipelineService.feature_handles_batch("Playblast Collect") is True
    assert PipelineService.feature_handles_batch("Generate") is False
    assert PipelineService.feature_handles_batch("Sync") is False


def test_launcher_controller_multi_shot_playblast_collect(qtbot, tmp_path, monkeypatch):
    """Verify LauncherController correctly collects multiple selected shots in a single execution."""
    from PySide6.QtGui import QStandardItem
    from zeroxe.views.launcher_view import LauncherView
    from zeroxe.controllers.launcher_controller import LauncherController
    import Additional.playblast_dialog as apd
    import pipeline.Commands.Additional.playblast_dialog as pcapd

    render_root = tmp_path / "renders"
    dest_dir = tmp_path / "collected_multi"
    s1_dir = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0010" / "playblast" / "lay"
    s2_dir = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0020" / "playblast" / "lay"
    s1_dir.mkdir(parents=True, exist_ok=True)
    s2_dir.mkdir(parents=True, exist_ok=True)

    (s1_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov").write_text("shot 10 v1")
    (s2_dir / "mdt_ep998_sq01_sh0020_lay_v001.mov").write_text("shot 20 v1")

    PipelineService.load_pipeline_module("Melangkah Dari Timur")

    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    orig_init = apd.PlayblastCollectDialog.__init__

    def mock_dlg_init(self, *args, **kwargs):
        kwargs["render_path"] = render_root
        orig_init(self, *args, **kwargs)
        self.edit_destination.setText(str(dest_dir))

    result_exec_mock = MagicMock(return_value=True)

    for mod in [apd, pcapd]:
        monkeypatch.setattr(mod.PlayblastCollectDialog, "__init__", mock_dlg_init)
        monkeypatch.setattr(mod.PlayblastCollectDialog, "exec", lambda self: 1)
        monkeypatch.setattr(mod.PlayblastResultDialog, "exec", result_exec_mock)

    for k, v in list(sys.modules.items()):
        if "feature_registry" in k:
            if hasattr(v, "PlayblastCollectDialog") and v.PlayblastCollectDialog:
                monkeypatch.setattr(v.PlayblastCollectDialog, "__init__", mock_dlg_init)
                monkeypatch.setattr(v.PlayblastCollectDialog, "exec", lambda self: 1)
            if hasattr(v, "PlayblastResultDialog") and v.PlayblastResultDialog:
                monkeypatch.setattr(v.PlayblastResultDialog, "exec", result_exec_mock)

    view = LauncherView()
    qtbot.addWidget(view)
    ctrl = LauncherController(view)

    ctrl.current_project = Project(id="p1", name="Melangkah Dari Timur", code="MDT")
    ctrl.current_department = Department(id="d1", name="Layout")
    view.ui.comboBox_category.addItem("ep998")
    view.ui.comboBox_category.setCurrentText("ep998")

    shot_10 = Shot(
        id="s1",
        name="sh0010",
        sequence_id="sq1",
        sequence="sq01",
        episode_id="ep1",
        episode="ep998",
        preview_file_id="",
        resolution="1920x1080",
        fps=24,
        frame_in=1,
        frame_out=100,
        assets=[],
    )
    shot_20 = Shot(
        id="s2",
        name="sh0020",
        sequence_id="sq1",
        sequence="sq01",
        episode_id="ep1",
        episode="ep998",
        preview_file_id="",
        resolution="1920x1080",
        fps=24,
        frame_in=1,
        frame_out=100,
        assets=[],
    )

    # Enable multi-select mode and populate source model
    view.ui.checkBox_multiSelect.setChecked(True)
    view.item_source_model.clear()

    it1 = QStandardItem("sh0010")
    it1.setData(shot_10, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it1)

    it2 = QStandardItem("sh0020")
    it2.setData(shot_20, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it2)

    # Select both items in the list view
    sel_model = view.ui.listView_assetList.selectionModel()
    idx1 = view.item_proxy_model.index(0, 0)
    idx2 = view.item_proxy_model.index(1, 0)
    sel_model.select(idx1, sel_model.SelectionFlag.Select)
    sel_model.select(idx2, sel_model.SelectionFlag.Select)

    ctrl.feature_combobox.addItem("Playblast Collect")
    ctrl.feature_combobox.setCurrentText("Playblast Collect")

    # Execute action
    ctrl.on_execute_action()

    # Both shots should have been collected into dest_dir
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov").is_file()
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov").read_text() == "shot 10 v1"

    assert (dest_dir / "mdt_ep998_sq01_sh0020_lay_v001.mov").is_file()
    assert (dest_dir / "mdt_ep998_sq01_sh0020_lay_v001.mov").read_text() == "shot 20 v1"

    # PlayblastResultDialog should have been shown once summarizing both shots
    assert result_exec_mock.call_count == 1


