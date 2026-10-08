"""Logs View implementation for ZeroXe.

Allows real-time inspection, switching, filtering, and export of process-separated logs
(App, DCC Software, Pipeline Presets, Batch Operations, Kitsu Sync).
"""

import datetime
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from zeroxe.ui.ui_logs import Ui_Form
from zeroxe.utils.log_util import (
    clear_process_logs,
    get_logs_base_dir,
    list_process_logs,
    open_file_in_system,
    read_process_log,
)

logger = logging.getLogger(__name__)


class LogsView(QWidget):
    """View displaying process logs with process selection, refresh, save, and clear actions."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self._current_log_path: Optional[Path] = None
        self._log_entries = []

        self._setup_ui_styling()
        self._bind_signals()
        self.refresh_log_list()

    def _setup_ui_styling(self) -> None:
        """Apply monospace font to log editor and configure default view state."""
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.ui.plainTextEdit_logs.setFont(font)
        self.ui.plainTextEdit_logs.setReadOnly(True)

        # Hide progress bar by default in logs view unless an export/clear operation is running
        self.ui.progressBar.setVisible(False)

    def _bind_signals(self) -> None:
        """Bind UI buttons and combobox signals."""
        self.ui.comboBox_logs.currentIndexChanged.connect(self._on_log_selection_changed)
        self.ui.pushButton_clearLogs.clicked.connect(self._on_clear_logs)
        self.ui.pushButton_saveLogs.clicked.connect(self._on_save_log)

    def refresh_log_list(self) -> None:
        """Scan logs directory and update the combobox."""
        self.ui.comboBox_logs.blockSignals(True)
        self.ui.comboBox_logs.clear()

        self._log_entries = list_process_logs()

        if not self._log_entries:
            self.ui.comboBox_logs.addItem("No process logs found", None)
            self.ui.plainTextEdit_logs.setPlainText("[No process logs recorded yet.]")
            self._current_log_path = None
            self.ui.comboBox_logs.blockSignals(False)
            return

        for item in self._log_entries:
            cat_tag = f"[{item['category_label']}]"
            disp = f"{cat_tag} {item['filename']} ({item['mtime_str']})"
            self.ui.comboBox_logs.addItem(disp, item["path"])

        self.ui.comboBox_logs.blockSignals(False)
        self._on_log_selection_changed(0)

    def _on_log_selection_changed(self, index: int) -> None:
        """Load and display the selected log file content."""
        if index < 0 or index >= len(self._log_entries):
            return

        item = self._log_entries[index]
        log_path: Path = item["path"]
        self._current_log_path = log_path

        content = read_process_log(log_path)
        self.ui.plainTextEdit_logs.setPlainText(content)

        # Scroll to bottom to view latest lines
        scrollbar = self.ui.plainTextEdit_logs.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _on_clear_logs(self) -> None:
        """Confirm and clear old or current logs."""
        if not self._log_entries:
            return

        reply = QMessageBox.question(
            self,
            "Clear Process Logs",
            "Do you want to clear all process logs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = clear_process_logs()
            self.refresh_log_list()
            QMessageBox.information(self, "Logs Cleared", f"Cleared {count} process log file(s).")

    def _on_save_log(self) -> None:
        """Export current log content to a user-chosen destination."""
        if not self._current_log_path or not self._current_log_path.is_file():
            QMessageBox.warning(self, "No Log Selected", "Please select a valid log to save.")
            return

        default_name = self._current_log_path.name
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log File",
            default_name,
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        )
        if dest_path:
            try:
                content = self.ui.plainTextEdit_logs.toPlainText()
                Path(dest_path).write_text(content, encoding="utf-8")
                QMessageBox.information(self, "Log Saved", f"Log successfully exported to:\n{dest_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save log file:\n{e}")
