"""Tests for fast instant episode switching and non-blocking shot loading."""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from zeroxe.models.project_model import Project
from zeroxe.models.shot_model import Episode, Sequence, Shot
from zeroxe.services.shot_service import ShotService
from zeroxe.views.launcher_view import LauncherView


@pytest.fixture(autouse=True)
def clean_shot_cache():
    ShotService.clear_cache()
    yield
    ShotService.clear_cache()


def test_shot_service_get_shots_by_project_id():
    """Verify ShotService.get_shots_by_project_id bulk fetches and populates episode caches."""
    raw_episodes = [
        {"id": "ep-1", "name": "ep01", "project_id": "proj-1"},
        {"id": "ep-2", "name": "ep02", "project_id": "proj-1"},
    ]
    raw_sequences = [
        {"id": "seq-1", "name": "sq01", "parent_id": "ep-1", "project_id": "proj-1"},
        {"id": "seq-2", "name": "sq02", "parent_id": "ep-2", "project_id": "proj-1"},
    ]
    raw_shots = [
        {"id": "shot-1", "name": "sh0010", "parent_id": "seq-1", "episode_id": "ep-1"},
        {"id": "shot-2", "name": "sh0020", "parent_id": "seq-1", "episode_id": "ep-1"},
        {"id": "shot-3", "name": "sh0010", "parent_id": "seq-2", "episode_id": "ep-2"},
    ]

    with patch("zeroxe.services.shot_service.is_kitsu_connected", return_value=True), \
         patch("gazu.context.all_episodes_for_project", return_value=raw_episodes), \
         patch("gazu.shot.all_sequences_for_project", return_value=raw_sequences), \
         patch("gazu.shot.all_shots_for_project", return_value=raw_shots):

        shots = ShotService.get_shots_by_project_id("proj-1")
        assert len(shots) == 3

        # Verify project shot cache is populated
        assert "proj-1" in ShotService._project_shot_cache
        assert len(ShotService._project_shot_cache["proj-1"]) == 3

        # Verify episode-level shot caches are populated
        assert "ep-1" in ShotService._shot_cache
        assert len(ShotService._shot_cache["ep-1"]) == 2
        assert ShotService._shot_cache["ep-1"][0].name == "sh0010"
        assert ShotService._shot_cache["ep-1"][0].sequence == "sq01"
        assert ShotService._shot_cache["ep-1"][0].episode == "ep01"

        assert "ep-2" in ShotService._shot_cache
        assert len(ShotService._shot_cache["ep-2"]) == 1
        assert ShotService._shot_cache["ep-2"][0].name == "sh0010"
        assert ShotService._shot_cache["ep-2"][0].sequence == "sq02"
        assert ShotService._shot_cache["ep-2"][0].episode == "ep02"


def test_episode_change_instant_cached(qtbot):
    """Verify switching episodes in LauncherController is instant and uses in-memory cache without modal dialog."""
    view = LauncherView()
    qtbot.addWidget(view)
    controller = view.controller

    controller.current_project = Project(id="proj-1", name="Project A", code="pa")
    ep1 = Episode(id="ep-1", name="ep01", project_id="proj-1")
    ep2 = Episode(id="ep-2", name="ep02", project_id="proj-1")
    controller.current_episodes = [ep1, ep2]

    # Pre-populate cache for ep-1 and ep-2
    shot_ep1 = [
        Shot.from_kitsu({"id": "s1", "name": "sh0010", "sequence": "sq01", "episode": "ep01"}),
        Shot.from_kitsu({"id": "s2", "name": "sh0020", "sequence": "sq01", "episode": "ep01"}),
    ]
    shot_ep2 = [
        Shot.from_kitsu({"id": "s3", "name": "sh0030", "sequence": "sq02", "episode": "ep02"}),
    ]
    ShotService._shot_cache["ep-1"] = shot_ep1
    ShotService._shot_cache["ep-2"] = shot_ep2

    # Populate category dropdown
    view.ui.comboBox_category.blockSignals(True)
    view.ui.comboBox_category.clear()
    view.ui.comboBox_category.addItems(["None", "ep01", "ep02"])
    view.ui.comboBox_category.blockSignals(False)

    # Patch run_async_task to ensure it is NEVER called when changing episode
    with patch("zeroxe.controllers.launcher_controller.run_async_task") as mock_async_task:
        # Switch to ep01
        view.ui.comboBox_category.setCurrentText("ep01")
        assert view.item_source_model.rowCount() == 2
        assert view.item_source_model.item(0).text() == "sq01_sh0010"
        assert view.item_source_model.item(1).text() == "sq01_sh0020"

        # Switch to ep02
        view.ui.comboBox_category.setCurrentText("ep02")
        assert view.item_source_model.rowCount() == 1
        assert view.item_source_model.item(0).text() == "sq02_sh0030"

        # Switch back to ep01
        view.ui.comboBox_category.setCurrentText("ep01")
        assert view.item_source_model.rowCount() == 2

        # Assert no modal loading dialog task was triggered
        mock_async_task.assert_not_called()


def test_episode_change_async_non_cached(qtbot):
    """Verify switching episodes when cache is empty triggers run_async_task loading popup."""
    view = LauncherView()
    qtbot.addWidget(view)
    controller = view.controller

    controller.current_project = Project(id="proj-1", name="Project A", code="pa")
    ep1 = Episode(id="ep-1", name="ep01", project_id="proj-1")
    controller.current_episodes = [ep1]

    view.ui.comboBox_category.blockSignals(True)
    view.ui.comboBox_category.clear()
    view.ui.comboBox_category.addItems(["None", "ep01"])
    view.ui.comboBox_category.blockSignals(False)

    mock_shots = [
        Shot.from_kitsu({"id": "s1", "name": "sh0010", "sequence": "sq01", "episode": "ep01"}),
    ]

    with patch("zeroxe.controllers.launcher_controller.run_async_task", return_value=mock_shots) as mock_async_task:
        # Switch to ep01
        view.ui.comboBox_category.setCurrentText("ep01")

        # Assert run_async_task (modal popup) WAS called
        mock_async_task.assert_called_once()
        assert view.item_source_model.rowCount() == 1
        assert view.item_source_model.item(0).text() == "sq01_sh0010"
