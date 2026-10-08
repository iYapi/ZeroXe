"""Tests for non-blocking LoadingDialog, AsyncWorker, and animated GIF resolution."""

import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from zeroxe.ui.loading_dialog import (
    AsyncWorker,
    LoadingDialog,
    get_loading_gif_path,
    run_async_task,
)


def test_get_loading_gif_path():
    """Verify that get_loading_gif_path locates the loading.gif file."""
    gif_path = get_loading_gif_path()
    assert gif_path is not None
    assert gif_path.is_file()
    assert gif_path.name == "loading.gif"


def test_async_worker_execution(qtbot):
    """Verify that AsyncWorker executes tasks in background thread and emits signals."""
    results = []

    def sample_task(x, y):
        return x + y

    worker = AsyncWorker(sample_task, 10, 25)
    worker.task_finished.connect(lambda val: results.append(val))

    with qtbot.waitSignal(worker.task_finished, timeout=3000):
        worker.start()

    assert results == [35]


def test_async_worker_progress_reporting(qtbot):
    """Verify that AsyncWorker passes progress_callback to task functions."""
    progress_records = []

    def batch_task(progress_callback=None):
        for i in range(1, 4):
            if progress_callback:
                progress_callback(i, 3, f"Step {i}")
        return "Done"

    worker = AsyncWorker(batch_task)
    worker.progress_updated.connect(lambda cur, tot, msg: progress_records.append((cur, tot, msg)))

    with qtbot.waitSignal(worker.task_finished, timeout=3000):
        worker.start()

    assert len(progress_records) == 3
    assert progress_records[0] == (1, 3, "Step 1")
    assert progress_records[2] == (3, 3, "Step 3")


def test_async_worker_error_handling(qtbot):
    """Verify that AsyncWorker captures exceptions and emits task_failed."""
    errors = []

    def failing_task():
        raise ValueError("Simulated background error")

    worker = AsyncWorker(failing_task)
    worker.task_failed.connect(lambda err, tb: errors.append(err))

    with qtbot.waitSignal(worker.task_failed, timeout=3000):
        worker.start()

    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert "Simulated background error" in str(errors[0])


def test_loading_dialog_ui(qtbot):
    """Verify LoadingDialog initialization, movie playback, and progress bar updates."""
    dialog = LoadingDialog(
        parent=None,
        title="Testing Dialog",
        message="Loading test data...",
        total_steps=10,
        can_cancel=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Testing Dialog"
    assert dialog.title_label.text() == "Testing Dialog"
    assert dialog.message_label.text() == "Loading test data..."
    assert dialog.progress_bar.maximum() == 10
    assert hasattr(dialog, "cancel_button")
    assert dialog.gif_label.width() == 72
    assert dialog.gif_label.height() == 48

    dialog.set_progress(5, 10, "Halfway done")
    assert dialog.progress_bar.value() == 5
    assert dialog.message_label.text() == "Halfway done"

    # Verify window flags and fixed size (unresizable, unminimizable, uncloseable)
    flags = dialog.windowFlags()
    assert not (flags & Qt.WindowType.WindowCloseButtonHint)
    assert not (flags & Qt.WindowType.WindowMinimizeButtonHint)
    assert not (flags & Qt.WindowType.WindowMaximizeButtonHint)
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog.width() == 380


def test_loading_dialog_cannot_be_closed_while_busy(qtbot):
    """Verify that LoadingDialog rejects close and reject events while worker is active."""
    dialog = LoadingDialog(
        parent=None,
        title="Busy Dialog",
        message="Working...",
    )
    qtbot.addWidget(dialog)

    class DummyWorker:
        def isRunning(self):
            return True

    dialog.worker = DummyWorker()
    dialog._is_finished = False

    # Attempt reject (e.g. Esc key)
    dialog.reject()
    assert dialog.isVisible() or dialog.result is None

    # Finished
    dialog._is_finished = True
    dialog.accept()



def test_pipeline_execute_feature_loading_integration(qtbot, monkeypatch, tmp_path):
    """Verify PipelineService.execute_feature properly triggers run_async_task when parent is provided."""
    from zeroxe.services.pipeline_service import PipelineService
    from PySide6.QtWidgets import QWidget

    parent_widget = QWidget()
    qtbot.addWidget(parent_widget)

    # Mock pipeline module
    class MockModule:
        @staticmethod
        def run_pipeline_feature(**kwargs):
            return {
                "success": True,
                "message": "Script generated",
                "script": "import bpy\nprint('Done')",
                "target_path": str(tmp_path / "test.blend"),
            }

    monkeypatch.setattr(PipelineService, "load_pipeline_module", lambda project_name=None: MockModule())
    monkeypatch.setattr(PipelineService, "get_active_pipeline_yaml_path", lambda project_name=None: tmp_path / "pipe.yaml")
    
    from zeroxe.services.settings_service import SettingsService
    fake_blender = tmp_path / "fake_blender"
    fake_blender.write_text("#!/bin/sh\nexit 0")
    fake_blender.chmod(0o755)
    monkeypatch.setattr(SettingsService, "get_active_blender", lambda: str(fake_blender))

    # Mock execute_blender_script
    executed_async = []

    def mock_execute_blender(script, blender_path=None, timeout=180):
        # Create target file
        (tmp_path / "test.blend").write_text("blend")
        executed_async.append(True)
        return True, "Success"

    monkeypatch.setattr(PipelineService, "execute_blender_script", mock_execute_blender)

    # Trigger execute_feature with parent
    success, msg, target = PipelineService.execute_feature(
        feature_name="Generate",
        filepath=str(tmp_path / "test.blend"),
        parent=parent_widget,
    )

    assert success is True
    assert executed_async == [True]

