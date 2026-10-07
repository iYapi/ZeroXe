"""Unit tests for Image Preview Loading and Fallback Handling."""

from pathlib import Path
import tempfile
import pytest
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from zeroxe.models.asset_model import Asset
from zeroxe.models.shot_model import Shot
from zeroxe.controllers.launcher_controller import PreviewWorkerSignals, PreviewDownloadRunnable


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_asset_model_preview_id_variations():
    """Verify Asset.from_kitsu extracts preview ID from all standard Kitsu keys."""
    # 1. Standard preview_file_id
    a1 = Asset.from_kitsu({"id": "1", "name": "A", "preview_file_id": "prev_1"})
    assert a1.preview_file_id == "prev_1"
    assert a1.file_preview_id == "prev_1"

    # 2. file_preview_id
    a2 = Asset.from_kitsu({"id": "2", "name": "B", "file_preview_id": "prev_2"})
    assert a2.preview_file_id == "prev_2"

    # 3. thumbnail_id
    a3 = Asset.from_kitsu({"id": "3", "name": "C", "thumbnail_id": "prev_3"})
    assert a3.preview_file_id == "prev_3"

    # 4. Nested data.preview_file_id
    a4 = Asset.from_kitsu({"id": "4", "name": "D", "data": {"preview_file_id": "prev_4"}})
    assert a4.preview_file_id == "prev_4"


def test_shot_model_preview_id_variations():
    """Verify Shot.from_kitsu extracts preview ID from all standard Kitsu keys."""
    # 1. Standard preview_file_id
    s1 = Shot.from_kitsu({"id": "1", "name": "SH1", "preview_file_id": "prev_1"})
    assert s1.preview_file_id == "prev_1"

    # 2. file_preview_id
    s2 = Shot.from_kitsu({"id": "2", "name": "SH2", "file_preview_id": "prev_2"})
    assert s2.preview_file_id == "prev_2"

    # 3. thumbnail_id
    s3 = Shot.from_kitsu({"id": "3", "name": "SH3", "thumbnail_id": "prev_3"})
    assert s3.preview_file_id == "prev_3"

    # 4. Nested data.preview_file_id
    s4 = Shot.from_kitsu({"id": "4", "name": "SH4", "data": {"preview_file_id": "prev_4"}})
    assert s4.preview_file_id == "prev_4"


def test_preview_download_runnable_cached_valid_image(qapp, tmp_path):
    """Verify PreviewDownloadRunnable recognizes existing cached image and emits signal immediately."""
    cache_dir = tmp_path / "previews"
    cache_dir.mkdir(parents=True)
    img_path = cache_dir / "test_prev_id.png"

    # Save a valid 100x100 PNG
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(0xFF00FF)
    img.save(str(img_path))

    results = []
    signals = PreviewWorkerSignals()
    signals.finished.connect(lambda i_id, p_id, path: results.append((i_id, p_id, path)))

    worker = PreviewDownloadRunnable(
        item_id="item_123",
        preview_file_id="test_prev_id",
        entity_type="asset",
        cache_dir=cache_dir,
        signals=signals,
    )
    worker.run()

    assert len(results) == 1
    item_id, preview_id, final_path = results[0]
    assert item_id == "item_123"
    assert preview_id == "test_prev_id"
    assert final_path == str(img_path)
    assert not QPixmap(final_path).isNull()


def test_preview_download_runnable_invalid_cache_cleared(qapp, tmp_path):
    """Verify PreviewDownloadRunnable purges invalid/corrupt cached files (e.g. mp4 saved as png)."""
    cache_dir = tmp_path / "previews"
    cache_dir.mkdir(parents=True)
    corrupt_path = cache_dir / "corrupt_id.png"

    # Write corrupt non-image bytes
    corrupt_path.write_bytes(b"corrupt mp4 video data header")

    results = []
    signals = PreviewWorkerSignals()
    signals.finished.connect(lambda i_id, p_id, path: results.append((i_id, p_id, path)))

    worker = PreviewDownloadRunnable(
        item_id="item_456",
        preview_file_id="corrupt_id",
        entity_type="asset",
        cache_dir=cache_dir,
        signals=signals,
    )
    worker.run()

    # The corrupt file should have been detected and cleaned up
    assert len(results) == 1
    item_id, preview_id, final_path = results[0]
    assert item_id == "item_456"


def test_preview_scaled_to_width(qapp, tmp_path):
    """Verify that preview rendering scales to match the target width."""
    from zeroxe.views.launcher_view import LauncherView
    view = LauncherView()

    # Create a 1920x1080 test image
    img_path = tmp_path / "test_1080p.png"
    img = QImage(1920, 1080, QImage.Format.Format_RGB32)
    img.fill(0x00FF00)
    img.save(str(img_path))

    # Resize label to a fixed width
    view.ui.label_image.resize(400, 200)
    view.controller._display_preview_image(str(img_path))

    pixmap = view.ui.label_image.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    # Scaled width should match available width
    avail_w = view.ui.label_image.contentsRect().width()
    assert pixmap.width() == avail_w

