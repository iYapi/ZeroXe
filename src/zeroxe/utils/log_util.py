"""Log utilities for ZeroXe.

Provides temporary log file creation, error dialogs with concise summaries,
and system-level log file opening (xdg-open / QDesktopServices / os.startfile).
"""

import datetime
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Optional, Union

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)

TEMP_LOGS_DIR = Path(tempfile.gettempdir()) / "zeroxe_logs"


def get_temp_logs_dir() -> Path:
    """Return the temporary log directory path, creating it if it does not exist."""
    TEMP_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_LOGS_DIR


def write_temp_error_log(
    title: str,
    summary: str,
    full_log: str,
    prefix: str = "zeroxe_error",
) -> Path:
    """Write full error details to a timestamped file in the temporary directory.

    Returns the Path to the written log file.
    """
    logs_dir = get_temp_logs_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Sanitize prefix
    safe_prefix = re.sub(r"[^\w\-]", "_", prefix).strip("_") or "zeroxe_error"
    log_filename = f"{safe_prefix}_{timestamp}.log"
    log_path = logs_dir / log_filename

    header = [
        "=" * 70,
        f"ZeroXe Error Log - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Title   : {title}",
        f"Summary : {summary}",
        "=" * 70,
        "",
        full_log,
        "",
        "=" * 70,
    ]

    try:
        log_path.write_text("\n".join(header), encoding="utf-8")
        logger.info(f"Written temporary error log to: {log_path}")
    except Exception as e:
        logger.error(f"Failed to write error log to {log_path}: {e}")

    return log_path


def open_file_in_system(file_path: Union[str, Path]) -> bool:
    """Open a file with the default system application (editor/viewer)."""
    p = Path(file_path).resolve()
    if not p.is_file():
        logger.warning(f"Cannot open non-existent file: {p}")
        return False

    # 1. Try QDesktopServices
    try:
        url = QUrl.fromLocalFile(str(p))
        if QDesktopServices.openUrl(url):
            return True
    except Exception as e:
        logger.debug(f"QDesktopServices.openUrl failed for {p}: {e}")

    # 2. Fallback to OS commands
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(p)])
            return True
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(p)])
            return True
        elif sys.platform.startswith("win32"):
            os.startfile(str(p))  # type: ignore[attr-defined]
            return True
    except Exception as e:
        logger.error(f"Failed to launch system viewer for {p}: {e}")

    return False


def extract_error_summary(action: str, raw_msg: str) -> str:
    """Extract a clean, concise 1-2 line summary from raw error or traceback output."""
    if not raw_msg:
        return f"Failed to execute '{action}'."

    cleaned = raw_msg.strip()

    # If it's a short single-line message without tracebacks
    if len(cleaned) < 120 and "\n" not in cleaned and "Traceback" not in cleaned:
        return cleaned

    # Check for target file missing
    if "target file was not created" in cleaned:
        match = re.search(r"target file was not created:\s*([^\n]+)", cleaned)
        if match:
            return f"Blender executed but target file was not created:\n{Path(match.group(1).strip()).name}"
        return "Blender executed but target file was not created on disk."

    # Look for last Python exception line (e.g. "Error: ...", "Exception: ...", "ModuleNotFoundError: ...")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(line.startswith(err_type) for err_type in (
            "ModuleNotFoundError:",
            "ImportError:",
            "KeyError:",
            "ValueError:",
            "TypeError:",
            "FileNotFoundError:",
            "AttributeError:",
            "IndexError:",
            "RuntimeError:",
            "PermissionError:",
            "ZeroDivisionError:",
            "Error:",
            "Exception:",
        )):
            return f"{action} error: {line}"

    if "Blender execution error" in cleaned:
        return f"Blender execution failed while executing '{action}'."

    # Fallback to first non-empty line (capped to 100 chars)
    first_line = lines[0] if lines else f"Failed to execute '{action}'."
    if len(first_line) > 100:
        first_line = first_line[:97] + "..."
    return first_line


def show_error_dialog(
    parent: Optional[QWidget],
    title: str,
    summary: str,
    full_log: str,
    prefix: str = "zeroxe_error",
) -> Path:
    """Display a concise error dialog to the user, saving full logs to a temporary file.

    Includes an 'Open Log File' button to immediately inspect the full output in the OS text viewer.
    """
    log_path = write_temp_error_log(
        title=title,
        summary=summary,
        full_log=full_log,
        prefix=prefix,
    )

    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(summary.strip())
    msg_box.setInformativeText(f"Full log file saved to:\n{log_path}")

    if full_log:
        msg_box.setDetailedText(full_log)

    open_log_btn = msg_box.addButton("Open Log File", QMessageBox.ButtonRole.ActionRole)
    msg_box.addButton(QMessageBox.StandardButton.Ok)

    msg_box.exec()

    if msg_box.clickedButton() == open_log_btn:
        open_file_in_system(log_path)

    return log_path
