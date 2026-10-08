"""Tests for ZeroXe log utilities and error dialog handling."""

from pathlib import Path
import tempfile
import pytest

from PySide6.QtWidgets import QMessageBox

from zeroxe.utils.log_util import (
    extract_error_summary,
    get_temp_logs_dir,
    open_file_in_system,
    show_error_dialog,
    write_temp_error_log,
)


def test_get_temp_logs_dir():
    """Verify that temp logs directory exists and is accessible."""
    log_dir = get_temp_logs_dir()
    assert log_dir.exists()
    assert log_dir.is_dir()


def test_write_temp_error_log():
    """Verify that write_temp_error_log writes timestamped log with header and body."""
    title = "Generate Layout Error"
    summary = "Blender execution failed."
    full_log = (
        "Traceback (most recent call last):\n"
        "  File '/tmp/script.py', line 12, in <module>\n"
        "    import missing_addon\n"
        "ModuleNotFoundError: No module named 'missing_addon'\n"
    )

    log_path = write_temp_error_log(title=title, summary=summary, full_log=full_log, prefix="test_error")
    assert log_path.is_file()
    assert "test_error" in log_path.name
    content = log_path.read_text(encoding="utf-8")
    assert title in content
    assert summary in content
    assert "ModuleNotFoundError: No module named 'missing_addon'" in content

    # Cleanup
    try:
        log_path.unlink()
    except Exception:
        pass


def test_extract_error_summary():
    """Verify smart error summary extraction from raw tracebacks and logs."""
    # 1. Short message
    assert extract_error_summary("Up Master", "Invalid format") == "Invalid format"

    # 2. Traceback with specific exception
    traceback_log = (
        "Blender 4.2.0 (hash abc1234)\n"
        "Traceback (most recent call last):\n"
        "  File '/tmp/script.py', line 45, in <module>\n"
        "    bpy.ops.camera.add_rig()\n"
        "AttributeError: 'bpy_ops' object has no attribute 'camera'\n"
    )
    summary = extract_error_summary("Generate", traceback_log)
    assert "AttributeError: 'bpy_ops' object has no attribute 'camera'" in summary

    # 3. Missing target file log
    missing_file_log = (
        "Blender completed but target file was not created:\n"
        "/mnt/I/production/02_layout/ep998/ep998_sq01_sh0040_lay_v001.blend\n\n"
        "Blender Log:\nSome terminal output"
    )
    summary2 = extract_error_summary("Generate", missing_file_log)
    assert "target file was not created" in summary2
    assert "ep998_sq01_sh0040_lay_v001.blend" in summary2

    # 4. Blender execution error fallback
    generic_blender_err = "Blender execution error:\n\nFatal error in C++ addon"
    summary3 = extract_error_summary("Generate", generic_blender_err)
    assert "Blender execution failed" in summary3


def test_open_file_in_system(monkeypatch):
    """Verify open_file_in_system gracefully handles existing and non-existing files."""
    # Non-existent file
    assert open_file_in_system("/non/existent/path/zeroxe_error.log") is False

    # Existing file with mocked QDesktopServices
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        f.write(b"test log")
        tmp_p = Path(f.name)

    try:
        from PySide6.QtGui import QDesktopServices
        monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)
        assert open_file_in_system(tmp_p) is True
    finally:
        tmp_p.unlink(missing_ok=True)


def test_show_error_dialog(qtbot, monkeypatch):
    """Verify show_error_dialog creates log file and sets up QMessageBox properly."""
    dialog_executed = False

    def mock_exec(self):
        nonlocal dialog_executed
        dialog_executed = True
        # Verify dialog configuration
        assert self.windowTitle() == "Test Title"
        assert "Test Summary" in self.text()
        assert "Full log file saved to:" in self.informativeText()
        assert "Detailed error stack" in self.detailedText()
        # Find 'Open Log File' button
        button_texts = [btn.text() for btn in self.buttons()]
        assert "Open Log File" in button_texts
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", mock_exec)

    log_path = show_error_dialog(
        parent=None,
        title="Test Title",
        summary="Test Summary",
        full_log="Detailed error stack",
        prefix="pytest_test",
    )

    assert dialog_executed is True
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    log_path.unlink(missing_ok=True)


def test_process_logs_separation():
    """Verify that process logs are separated by category (app, dcc, pipeline, batch, kitsu)."""
    from zeroxe.utils.log_util import (
        clear_process_logs,
        get_category_logs_dir,
        list_process_logs,
        read_process_log,
        write_process_log,
    )

    # 1. Test directory resolution
    dcc_dir = get_category_logs_dir("dcc")
    assert dcc_dir.exists()
    assert dcc_dir.name == "dcc"

    pipeline_dir = get_category_logs_dir("pipeline")
    assert pipeline_dir.exists()
    assert pipeline_dir.name == "pipeline"

    # 2. Test writing process logs
    dcc_log = write_process_log(
        category="dcc",
        process_name="blender_launch_test",
        content="Blender 4.2 launched with scene.blend",
        command=["blender", "scene.blend"],
        exit_code=0,
    )
    assert dcc_log.is_file()
    assert "blender_launch_test" in dcc_log.name
    assert dcc_log.parent.name == "dcc"

    batch_log = write_process_log(
        category="batch",
        process_name="batch_lighting_test",
        content="Batch lighting executed for 5 shots.",
        extra_meta={"Shots": 5, "Status": "Success"},
    )
    assert batch_log.is_file()
    assert batch_log.parent.name == "batch"

    # 3. Test listing process logs
    all_logs = list_process_logs()
    assert len(all_logs) >= 2
    categories_found = {item["category"] for item in all_logs}
    assert "dcc" in categories_found
    assert "batch" in categories_found

    # 4. Test reading process log
    content = read_process_log(dcc_log)
    assert "ZeroXe Process Log: blender_launch_test" in content
    assert "Blender 4.2 launched with scene.blend" in content
    assert "Command     : blender scene.blend" in content

    # 5. Clean up test logs
    dcc_log.unlink(missing_ok=True)
    batch_log.unlink(missing_ok=True)

