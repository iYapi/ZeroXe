"""Tests for execute button popup warning and confirmation dialogs."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from zeroxe.models.project_model import Project
from zeroxe.models.shot_model import Shot
from zeroxe.views.launcher_view import LauncherView
from zeroxe.services.pipeline_service import PipelineService


@pytest.fixture
def launcher_view(qtbot, tmp_path, monkeypatch):
    # Mock Blender path so it passes SettingsService check
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("#!/bin/sh\n")
    fake_blender.chmod(0o755)

    monkeypatch.setattr(
        "zeroxe.services.settings_service.SettingsService.get_active_blender",
        lambda: str(fake_blender),
    )

    view = LauncherView()
    qtbot.addWidget(view)
    controller = view.controller

    controller.current_project = Project(id="proj-1", name="MDT", code="mdt")
    return view, controller, fake_blender


def test_execute_no_action_shows_warning(launcher_view):
    """Verify clicking execute with no action selected displays a warning popup."""
    view, controller, _ = launcher_view

    # Ensure action combo is empty
    if controller.feature_combobox:
        controller.feature_combobox.clear()

    with patch.object(QMessageBox, "warning") as mock_warning:
        controller.on_execute_action()
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "No Action Selected" in args[1]


def test_execute_multi_select_empty_shows_warning(launcher_view):
    """Verify clicking execute with multi-select enabled but no selection displays warning."""
    view, controller, _ = launcher_view

    if controller.feature_combobox:
        controller.feature_combobox.clear()
        controller.feature_combobox.addItem("Generate")

    # Enable multi-select
    if hasattr(view.ui, "checkBox_multiSelect"):
        view.ui.checkBox_multiSelect.setChecked(True)

    with patch.object(QMessageBox, "warning") as mock_warning:
        controller.on_execute_action()
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "No Items Selected" in args[1]


def test_execute_single_item_user_cancels(launcher_view, tmp_path):
    """Verify that when user clicks No on confirmation warning, execution is aborted."""
    view, controller, _ = launcher_view

    if controller.feature_combobox:
        controller.feature_combobox.clear()
        controller.feature_combobox.addItem("Up Master")

    if hasattr(view.ui, "checkBox_multiSelect"):
        view.ui.checkBox_multiSelect.setChecked(False)

    fake_file = tmp_path / "sq01_sh010_anm_v001.blend"
    fake_file.write_text("blend")
    controller.selected_file_path = str(fake_file)
    controller.current_version = "v001"
    controller.current_shot = Shot.from_kitsu({
        "id": "shot-1",
        "name": "sq01_sh010",
        "sequence": "sq01",
        "episode": "ep01",
    })

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.No
    ) as mock_warning, patch.object(
        PipelineService, "execute_feature"
    ) as mock_exec:
        controller.on_execute_action()

        # Warning confirmation was shown
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "Confirm Up Master" in args[1]
        assert "Are you sure you want to execute 'Up Master' on 'sq01_sh010'?" in args[2]

        # Pipeline execution should NOT have been called
        mock_exec.assert_not_called()


def test_execute_single_item_user_confirms(launcher_view, tmp_path):
    """Verify that when user clicks Yes on confirmation warning, execution proceeds."""
    view, controller, _ = launcher_view

    if controller.feature_combobox:
        controller.feature_combobox.clear()
        controller.feature_combobox.addItem("Up Master")

    if hasattr(view.ui, "checkBox_multiSelect"):
        view.ui.checkBox_multiSelect.setChecked(False)

    fake_file = tmp_path / "sq01_sh010_anm_v001.blend"
    fake_file.write_text("blend")
    controller.selected_file_path = str(fake_file)
    controller.current_version = "v001"
    controller.current_shot = Shot.from_kitsu({
        "id": "shot-1",
        "name": "sq01_sh010",
        "sequence": "sq01",
        "episode": "ep01",
    })

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes
    ) as mock_warning, patch.object(
        PipelineService, "execute_feature", return_value=(True, "Success", str(fake_file))
    ) as mock_exec, patch.object(
        QMessageBox, "information"
    ):
        controller.on_execute_action()

        # Warning confirmation was shown
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "Confirm Up Master" in args[1]
        assert "Are you sure you want to execute 'Up Master' on 'sq01_sh010'?" in args[2]

        # Pipeline execution was called
        mock_exec.assert_called_once()
        assert mock_exec.call_args[1]["feature_name"] == "Up Master"


def test_batch_warning_fallback():
    """Verify that batch fallback prompts with QMessageBox.warning."""
    selected_items = [{"name": "sh010"}, {"name": "sh020"}]

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.No
    ) as mock_warning:
        params = PipelineService.prompt_batch_parameters(
            department="Animation",
            action="Up Master",
            selected_items=selected_items,
        )
        assert params is None
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "Confirm Batch Up Master" in args[1]
        assert "Are you sure you want to execute 'Up Master' on all 2 items in batch?" in args[2]


def test_execute_batch_user_cancels(launcher_view):
    """Verify that clicking No on batch confirmation warning cancels batch execution."""
    from PySide6.QtGui import QStandardItem
    view, controller, _ = launcher_view

    if controller.feature_combobox:
        controller.feature_combobox.clear()
        controller.feature_combobox.addItem("Up Master")

    if hasattr(view.ui, "checkBox_multiSelect"):
        view.ui.checkBox_multiSelect.setChecked(True)

    shot1 = Shot.from_kitsu({"id": "s1", "name": "sh0010", "sequence": "sq01", "episode": "ep01"})
    shot2 = Shot.from_kitsu({"id": "s2", "name": "sh0020", "sequence": "sq01", "episode": "ep01"})

    view.item_source_model.clear()
    it1 = QStandardItem("sq01_sh0010")
    it1.setData(shot1, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it1)

    it2 = QStandardItem("sq01_sh0020")
    it2.setData(shot2, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it2)

    view.ui.listView_assetList.selectAll()

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.No
    ) as mock_warning, patch(
        "zeroxe.controllers.launcher_controller.run_async_task"
    ) as mock_async_task:
        controller.on_execute_action()

        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "Confirm Batch Up Master" in args[1]
        assert "Are you sure you want to execute 'Up Master' on all 2 items in batch?" in args[2]

        mock_async_task.assert_not_called()


def test_execute_batch_user_confirms(launcher_view):
    """Verify that clicking Yes on batch confirmation warning proceeds with batch execution."""
    from PySide6.QtGui import QStandardItem
    view, controller, _ = launcher_view

    if controller.feature_combobox:
        controller.feature_combobox.clear()
        controller.feature_combobox.addItem("Up Master")

    if hasattr(view.ui, "checkBox_multiSelect"):
        view.ui.checkBox_multiSelect.setChecked(True)

    shot1 = Shot.from_kitsu({"id": "s1", "name": "sh0010", "sequence": "sq01", "episode": "ep01"})
    shot2 = Shot.from_kitsu({"id": "s2", "name": "sh0020", "sequence": "sq01", "episode": "ep01"})

    view.item_source_model.clear()
    it1 = QStandardItem("sq01_sh0010")
    it1.setData(shot1, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it1)

    it2 = QStandardItem("sq01_sh0020")
    it2.setData(shot2, Qt.ItemDataRole.UserRole)
    view.item_source_model.appendRow(it2)

    view.ui.listView_assetList.selectAll()

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes
    ) as mock_warning, patch(
        "zeroxe.controllers.launcher_controller.run_async_task", return_value=([], [])
    ) as mock_async_task, patch.object(
        QMessageBox, "information"
    ):
        controller.on_execute_action()

        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "Confirm Batch Up Master" in args[1]
        assert "Are you sure you want to execute 'Up Master' on all 2 items in batch?" in args[2]

        mock_async_task.assert_called_once()


