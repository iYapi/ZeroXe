"""Log utilities for ZeroXe.

Provides process-separated logging (App, DCC, Pipeline, Batch, Kitsu),
temporary error log creation, error dialogs with summaries,
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
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from zeroxe import config

logger = logging.getLogger(__name__)

# Base logs directory in persistent user data directory (~/.local/share/zeroxe/logs)
LOGS_BASE_DIR = config.USER_DATA_DIR / "logs"
TEMP_LOGS_DIR = Path(tempfile.gettempdir()) / "zeroxe_logs"

# Recognized process log categories
PROCESS_CATEGORIES = {
    "app": "Application",
    "dcc": "DCC Software (Blender/Maya)",
    "pipeline": "Pipeline Presets",
    "batch": "Batch Operations",
    "kitsu": "Kitsu Synchronization",
}


def get_logs_base_dir() -> Path:
    """Return the root persistent logs directory, creating it if needed."""
    LOGS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_BASE_DIR


def get_category_logs_dir(category: str = "app") -> Path:
    """Return the directory for a specific process log category."""
    cat = category.lower().strip()
    cat_dir = get_logs_base_dir() / cat
    cat_dir.mkdir(parents=True, exist_ok=True)
    return cat_dir


def get_temp_logs_dir() -> Path:
    """Return the temporary log directory path, creating it if it does not exist."""
    TEMP_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_LOGS_DIR


def create_process_log_file(category: str, process_name: str) -> Path:
    """Generate a unique timestamped log file path for a process."""
    cat_dir = get_category_logs_dir(category)
    safe_name = re.sub(r"[^\w\-]", "_", process_name).strip("_") or "process"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = cat_dir / f"{safe_name}_{timestamp}.log"
    return log_file


def write_process_log(
    category: str,
    process_name: str,
    content: str,
    command: Optional[Union[str, List[str]]] = None,
    exit_code: Optional[int] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write a structured process log entry to its category-specific directory."""
    log_path = create_process_log_file(category, process_name)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "=" * 70,
        f"ZeroXe Process Log: {process_name}",
        f"Category    : {PROCESS_CATEGORIES.get(category.lower(), category.title())}",
        f"Timestamp   : {now_str}",
    ]

    if command:
        cmd_str = " ".join(command) if isinstance(command, list) else str(command)
        lines.append(f"Command     : {cmd_str}")

    if exit_code is not None:
        lines.append(f"Exit Code   : {exit_code}")

    if extra_meta:
        for k, v in extra_meta.items():
            lines.append(f"{k.capitalize():<12}: {v}")

    lines.extend([
        "=" * 70,
        "",
        content,
        "",
        "=" * 70,
    ])

    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug(f"Process log written to: {log_path}")
    except Exception as e:
        logger.error(f"Failed to write process log {log_path}: {e}")

    return log_path


def append_process_log(log_path: Union[str, Path], text: str) -> None:
    """Append text to an ongoing process log file."""
    p = Path(log_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
    except Exception as e:
        logger.error(f"Failed to append to log {p}: {e}")


def list_process_logs(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all available process logs sorted with newest first."""
    base_dir = get_logs_base_dir()
    categories_to_scan = [category.lower()] if category else list(PROCESS_CATEGORIES.keys())

    results = []
    for cat in categories_to_scan:
        cat_dir = base_dir / cat
        if not cat_dir.is_dir():
            continue
        for log_file in cat_dir.glob("*.log"):
            try:
                stat = log_file.stat()
                results.append({
                    "category": cat,
                    "category_label": PROCESS_CATEGORIES.get(cat, cat.title()),
                    "name": log_file.stem,
                    "filename": log_file.name,
                    "path": log_file,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_str": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except Exception:
                pass

    # Sort descending by mtime (newest first)
    results.sort(key=lambda item: item["mtime"], reverse=True)
    return results


def read_process_log(log_path: Union[str, Path], max_lines: int = 5000) -> str:
    """Read contents of a process log file, capping lines if very large."""
    p = Path(log_path)
    if not p.is_file():
        return f"[Log file not found: {p}]"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            truncated = lines[-max_lines:]
            return f"[... Truncated earlier output. Showing last {max_lines} lines ...]\n" + "\n".join(truncated)
        return text
    except Exception as e:
        return f"[Error reading log file {p}: {e}]"


def clear_process_logs(category: Optional[str] = None, older_than_days: Optional[int] = None) -> int:
    """Delete log files, optionally filtering by category and age. Returns count deleted."""
    logs = list_process_logs(category)
    now = datetime.datetime.now().timestamp()
    deleted_count = 0

    for item in logs:
        p: Path = item["path"]
        if older_than_days is not None:
            age_days = (now - item["mtime"]) / 86400.0
            if age_days < older_than_days:
                continue
        try:
            p.unlink(missing_ok=True)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Could not remove log {p}: {e}")

    return deleted_count


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

    if len(cleaned) < 120 and "\n" not in cleaned and "Traceback" not in cleaned:
        return cleaned

    if "target file was not created" in cleaned:
        match = re.search(r"target file was not created:\s*([^\n]+)", cleaned)
        if match:
            return f"Blender executed but target file was not created:\n{Path(match.group(1).strip()).name}"
        return "Blender executed but target file was not created on disk."

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
    category: Optional[str] = None,
) -> Path:
    """Display a concise error dialog to the user, saving full logs to a log file.

    Includes an 'Open Log File' button to immediately inspect the full output in the OS text viewer.
    """
    if category:
        log_path = write_process_log(
            category=category,
            process_name=prefix,
            content=f"Summary: {summary}\n\n{full_log}",
            extra_meta={"Title": title},
        )
    else:
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
