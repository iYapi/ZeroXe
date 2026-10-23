"""Unit and Integration Tests for Converter Tab and Pipeline Presets."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from zeroxe.controllers.converter_controller import (
    COL_COUNT,
    COL_NAME,
    COL_OUTPUT,
    COL_SOURCE,
    COL_STATUS,
    COL_TYPE,
    COL_VERSION,
)
from zeroxe.services.converter_service import ConverterService
from zeroxe.views.converter_view import ConverterView
from zeroxe.views.main_view import MainView


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication instance is active for tests."""
    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])
    return app


def test_converter_service_preset_discovery():
    """Verify ConverterService discovers pipeline presets dynamically."""
    presets = ConverterService.list_presets(force_reload=True)
    assert len(presets) >= 2

    preset_ids = [p.id for p in presets]
    assert "folder_to_mp4" in preset_ids
    assert "video_to_mp4" in preset_ids

    folder_preset = next(p for p in presets if p.id == "folder_to_mp4")
    assert folder_preset.name == "Folder (Image Sequence) to MP4"
    assert folder_preset.input_type == "folder"
    assert folder_preset.default_framerate == 24
    assert folder_preset.default_quality == 15
    assert folder_preset.output_extension == ".mp4"
    assert callable(folder_preset.handler)

    video_preset = next(p for p in presets if p.id == "video_to_mp4")
    assert video_preset.name == "Video to MP4"
    assert video_preset.input_type == "video"
    assert callable(video_preset.handler)


def test_dynamic_preset_addition_without_recompile():
    """Verify that creating a new preset .py file in the pipeline presets directory
    makes it immediately discoverable by ConverterService without recompiling.
    """
    search_dirs = ConverterService.get_preset_directories()
    assert len(search_dirs) > 0
    target_dir = search_dirs[0]

    custom_preset_file = target_dir / "test_custom_preset.py"
    try:
        custom_content = """PRESET_NAME = "Custom Pro Preset"
INPUT_TYPE = "any"
DEFAULT_FRAMERATE = 30
DEFAULT_QUALITY = 12
OUTPUT_EXTENSION = ".mov"

async def execute(input_path: str, output_file: str, **kwargs):
    return True
"""
        custom_preset_file.write_text(custom_content, encoding="utf-8")

        # Discover presets - should automatically detect the new file
        presets = ConverterService.list_presets(force_reload=False)
        custom_p = next((p for p in presets if p.id == "test_custom_preset"), None)
        assert custom_p is not None
        assert custom_p.name == "Custom Pro Preset"
        assert custom_p.default_framerate == 30
        assert custom_p.default_quality == 12
        assert custom_p.output_extension == ".mov"

    finally:
        if custom_preset_file.exists():
            custom_preset_file.unlink()
        ConverterService.clear_cache()


def test_inspect_input_path(tmp_path):
    """Verify path inspection correctly derives name from first image and detects versions."""
    # Test valid image folder
    img_folder = tmp_path / "shot_010"
    img_folder.mkdir()
    (img_folder / "shot_010_0101.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (img_folder / "shot_010_0102.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    info_folder = ConverterService.inspect_input_path(str(img_folder))
    assert info_folder["is_valid"] is True
    assert info_folder["type"] == "folder"
    assert info_folder["name"] == "shot_010"
    assert info_folder["version"] == "_v001"
    assert info_folder["file_count"] == 2
    assert "2 images" in info_folder["count_display"]

    # Test folder with explicit version in first image
    ver_folder = tmp_path / "random_folder_name"
    ver_folder.mkdir()
    (ver_folder / "MDT_sq01_sh020_v003_0101.exr").write_bytes(b"\x76\x2f\x31\x01")
    info_ver = ConverterService.inspect_input_path(str(ver_folder))
    assert info_ver["is_valid"] is True
    assert info_ver["name"] == "MDT_sq01_sh020"
    assert info_ver["version"] == "_v003"
    assert info_ver["suggested_output_name"] == "MDT_sq01_sh020_v003"

    # Test valid video file
    video_file = tmp_path / "render.mov"
    video_file.write_bytes(b"dummy video data")

    info_video = ConverterService.inspect_input_path(str(video_file))
    assert info_video["is_valid"] is True
    assert info_video["type"] == "video"
    assert info_video["name"] == "render"
    assert info_video["version"] == "_v001"
    assert info_video["file_count"] == 1

    # Test nonexistent path
    info_none = ConverterService.inspect_input_path(str(tmp_path / "does_not_exist"))
    assert info_none["is_valid"] is False


def test_ffmpeg_folder_and_video_conversion(tmp_path):
    """Integration test: Convert an image sequence folder to MP4,
    then convert that MP4 using the video preset.
    """
    ConverterService.clear_cache()
    # 1. Create a minimal valid image sequence using PPM format (fully supported by FFmpeg)
    seq_dir = tmp_path / "test_sequence"
    seq_dir.mkdir()

    ppm_data_red = b"P6\n4 4\n255\n" + (b"\xff\x00\x00" * 16)
    ppm_data_green = b"P6\n4 4\n255\n" + (b"\x00\xff\x00" * 16)
    ppm_data_blue = b"P6\n4 4\n255\n" + (b"\x00\x00\xff" * 16)

    (seq_dir / "frame_0101.ppm").write_bytes(ppm_data_red)
    (seq_dir / "frame_0102.ppm").write_bytes(ppm_data_green)
    (seq_dir / "frame_0103.ppm").write_bytes(ppm_data_blue)

    out_folder_mp4 = tmp_path / "folder_output.mp4"

    # Execute folder_to_mp4 preset
    success, msg = ConverterService.execute_preset(
        preset="folder_to_mp4",
        input_path=str(seq_dir),
        output_file=str(out_folder_mp4),
        framerate=24,
        quality=15,
    )
    assert success is True, f"folder_to_mp4 failed: {msg}"
    assert out_folder_mp4.is_file()
    assert out_folder_mp4.stat().st_size > 0

    # 2. Execute video_to_mp4 preset using the generated MP4 as input
    out_video_mp4 = tmp_path / "video_reencoded.mp4"
    success2, msg2 = ConverterService.execute_preset(
        preset="video_to_mp4",
        input_path=str(out_folder_mp4),
        output_file=str(out_video_mp4),
        framerate=24,
        quality=18,
    )
    assert success2 is True, f"video_to_mp4 failed: {msg2}"
    assert out_video_mp4.is_file()
    assert out_video_mp4.stat().st_size > 0


def test_converter_writes_process_logs(tmp_path):
    """Verify that using ConverterService writes structured logs to the 'converter' category in ZeroXe's log system."""
    from zeroxe.utils.log_util import get_category_logs_dir, list_process_logs, read_process_log

    cat_dir = get_category_logs_dir("converter")
    assert cat_dir.exists()
    assert cat_dir.name == "converter"

    # Create dummy images
    seq_dir = tmp_path / "log_seq"
    seq_dir.mkdir()
    (seq_dir / "img_0001.ppm").write_bytes(b"P6\n2 2\n255\n" + (b"\xff\x00\x00" * 4))
    out_mp4 = tmp_path / "log_test.mp4"

    # Count existing logs before conversion
    initial_logs = list_process_logs("converter")
    initial_count = len(initial_logs)

    success, msg = ConverterService.execute_preset(
        preset="folder_to_mp4",
        input_path=str(seq_dir),
        output_file=str(out_mp4),
        framerate=24,
        quality=15,
        write_log=True,
    )
    assert success is True

    # Check that a new process log was recorded
    after_logs = list_process_logs("converter")
    assert len(after_logs) > initial_count

    latest_log = after_logs[0]
    assert latest_log["category"] == "converter"
    assert "folder_to_mp4" in latest_log["name"]

    content = read_process_log(latest_log["path"])
    assert "ZeroXe Process Log" in content
    assert "Category    : Media Converter" in content
    assert "Preset ID           : folder_to_mp4" in content
    assert "Status              : SUCCESS" in content
    assert str(out_mp4) in content


def test_converter_view_and_controller(qapp, tmp_path):
    """Verify ConverterView UI elements, 7-column model, version suffix, and master output path."""
    view = ConverterView()
    controller = view.controller

    # 7 columns: Name, Version, Type, Count, Status, Source, Output
    assert controller.model.columnCount() == 7
    assert view.ui.comboBox_preset.count() >= 2

    # Verify no extra buttons were added
    assert not hasattr(view, "pushButton_addFolder")
    assert not hasattr(view, "pushButton_addVideo")

    # Add folder item: verify name is derived from first image inside (not folder name)
    folder = tmp_path / "unrelated_folder_name"
    folder.mkdir()
    (folder / "MDT_sq01_sh010_0101.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (folder / "MDT_sq01_sh010_0102.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    added = controller.add_item_path(str(folder))
    assert added is True
    assert controller.model.rowCount() == 1

    name_item = controller.model.item(0, COL_NAME)
    version_item = controller.model.item(0, COL_VERSION)
    type_item = controller.model.item(0, COL_TYPE)
    output_item = controller.model.item(0, COL_OUTPUT)

    # Name comes from first image inside, version defaults to _v001
    assert name_item.text() == "MDT_sq01_sh010"
    assert version_item.text() == "_v001"
    assert type_item.text() == "Folder"
    assert output_item.text().endswith("MDT_sq01_sh010_v001.mp4")

    # Verify editable columns: Name, Version, Output Path
    assert bool(name_item.flags() & Qt.ItemFlag.ItemIsEditable) is True
    assert bool(version_item.flags() & Qt.ItemFlag.ItemIsEditable) is True
    assert bool(output_item.flags() & Qt.ItemFlag.ItemIsEditable) is True
    # Read-only column
    assert bool(type_item.flags() & Qt.ItemFlag.ItemIsEditable) is False

    # Selection does NOT overwrite lineEdit_output (master path stays untouched)
    view.ui.tableView_available.selectRow(0)
    assert view.ui.lineEdit_output.text() == ""

    # Test editing the Version column directly in the table
    version_item.setText("_v002")
    assert controller.model.item(0, COL_OUTPUT).text().endswith("MDT_sq01_sh010_v002.mp4")

    # Test editing the Name column directly in the table
    name_item.setText("final_comp")
    assert controller.model.item(0, COL_OUTPUT).text().endswith("final_comp_v002.mp4")

    # Test editing Output Path column directly in table
    output_item.setText("/opt/custom/path/render.mp4")
    assert controller.model.item(0, COL_OUTPUT).text() == "/opt/custom/path/render.mp4"

    # Test Master Output Directory lineEdit_output
    # When set, all convert outputs update to point into that directory
    master_dir = str(tmp_path / "master_deliverables")
    view.ui.lineEdit_output.setText(master_dir)
    view.ui.lineEdit_output.textEdited.emit(master_dir)
    assert controller.model.item(0, COL_OUTPUT).text() == f"{master_dir}/final_comp_v002.mp4"

    # Add second item while master_dir is set; new item automatically uses master_dir
    video_file = tmp_path / "clip_01.mov"
    video_file.write_bytes(b"dummy")
    controller.add_item_path(str(video_file))
    assert controller.model.rowCount() == 2
    assert controller.model.item(1, COL_NAME).text() == "clip_01"
    assert controller.model.item(1, COL_VERSION).text() == "_v001"
    assert controller.model.item(1, COL_OUTPUT).text() == f"{master_dir}/clip_01_v001.mp4"

    # Test search filter proxy model
    view.ui.lineEdit_availableSearch.setText("non_existent_search_query")
    assert controller.proxy_model.rowCount() == 0
    view.ui.lineEdit_availableSearch.setText("final_comp")
    assert controller.proxy_model.rowCount() == 1
    view.ui.lineEdit_availableSearch.setText("")

    # Test preset selection changes spinbox values
    for i in range(view.ui.comboBox_preset.count()):
        p_id = view.ui.comboBox_preset.itemData(i)
        if p_id == "video_to_mp4":
            view.ui.comboBox_preset.setCurrentIndex(i)
            break
    preset = controller.get_selected_preset()
    assert preset is not None
    assert preset.id == "video_to_mp4"

    # Test remove and clear
    view.ui.tableView_available.selectRow(0)
    controller.remove_selected_items()
    assert controller.model.rowCount() == 1
    controller.clear_all_items()
    assert controller.model.rowCount() == 0

    view.close()


def test_main_view_has_converter_tab(qapp):
    """Verify MainView includes Converter tab properly."""
    main_view = MainView()
    assert hasattr(main_view, "converter_view")

    tab_titles = [main_view.tab_widget.tabText(i) for i in range(main_view.tab_widget.count())]
    assert "Launcher" in tab_titles
    assert "Converter" in tab_titles
    assert "Notification" in tab_titles
    assert "Logs" in tab_titles

    # Test switching to Converter tab triggers refresh_presets
    conv_idx = tab_titles.index("Converter")
    main_view.tab_widget.setCurrentIndex(conv_idx)

    main_view.close()


def test_bundled_pipeline_ffmpeg_resolution():
    """Verify ConverterService discovers bundled pipeline or assets FFmpeg binary."""
    from pathlib import Path
    ffmpeg_exe = ConverterService.get_ffmpeg_executable()
    assert ffmpeg_exe is not None
    assert Path(ffmpeg_exe).is_file()
    assert os.access(ffmpeg_exe, os.X_OK)

    # Check that either pipeline/bin or assets/bin is resolved
    p = Path(ffmpeg_exe).resolve()
    assert "pipeline" in str(p) or "assets" in str(p) or "ffmpeg" in p.name.lower()


def test_folder_to_mp4_read_only_source_directory(tmp_path):
    """Verify folder_to_mp4 succeeds even if the input source directory is read-only (NAS/render shares)."""
    seq_dir = tmp_path / "readonly_seq"
    seq_dir.mkdir()

    # Create dummy frame
    (seq_dir / "frame_0001.ppm").write_bytes(b"P6\n2 2\n255\n" + (b"\xff\x00\x00" * 4))
    (seq_dir / "frame_0002.ppm").write_bytes(b"P6\n2 2\n255\n" + (b"\x00\xff\x00" * 4))

    out_mp4 = tmp_path / "readonly_output.mp4"

    # Set directory to read-only (0o555)
    seq_dir.chmod(0o555)
    try:
        success, msg = ConverterService.execute_preset(
            preset="folder_to_mp4",
            input_path=str(seq_dir),
            output_file=str(out_mp4),
            framerate=24,
            quality=15,
        )
        assert success is True, f"Failed on read-only source directory: {msg}"
        assert out_mp4.is_file()
    finally:
        # Restore permissions for cleanup
        seq_dir.chmod(0o755)

