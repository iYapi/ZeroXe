"""Playblast Collector Dialog for ZeroXe Pipeline.

Provides a builder-style interactive UI dialog allowing artists to:
1. Preview selected shots and resolved pipeline render source path.
2. Select destination folder with browse button (persisting last chosen directory).
3. Configure playblast format extension (.mov, .mp4, etc.).
4. Run collection with real-time feedback and clean result summaries.
"""

from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .playblast_collector import (
    CollectPlayblastResult,
    PlayblastCollector,
    get_render_path,
)


class PlayblastCollectDialog(QDialog):
    """Builder-style configuration dialog for Playblast Collector."""

    def __init__(
        self,
        selected_items: List[Any],
        department: Optional[str] = None,
        project_name: Optional[str] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        render_path: Optional[Union[str, Path]] = None,
        parent: Optional[QWidget] = None,
        **kwargs: Any,
    ):
        super().__init__(parent)
        self.selected_items = list(selected_items or [])
        self.department = department or "Layout"
        self.project_name = project_name or ""
        self.episode = episode or ""
        self.sequence = sequence or ""
        self.config_path = config_path

        # Resolve render path from pipeline config if not explicitly passed
        self.render_path = render_path or get_render_path(config_path=self.config_path)

        # Resolve initial destination directory and format from persistent settings
        from PySide6.QtCore import QSettings

        settings = QSettings("ZeroXe", "PipelineTools")
        self.initial_dest = settings.value("playblast/last_destination_dir", str(Path.home() / "Desktop"), type=str)
        self.initial_format = settings.value("playblast/file_format", ".mov", type=str)

        if not self.initial_dest or not Path(self.initial_dest).is_dir():
            self.initial_dest = str(Path.home())

        self.dept_code = PlayblastCollector.get_department_code(
            self.department, config_path=self.config_path
        )

        self._init_ui()

    def _init_ui(self) -> None:
        count = len(self.selected_items)
        self.setWindowTitle("Playblast Collector")
        self.resize(580, 480)
        self.setMinimumSize(500, 380)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 1. Header Title & Description
        header_text = f"<b>Playblast Collector ({count} shot{'s' if count != 1 else ''} selected)</b>"
        header = QLabel(header_text)
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        desc = QLabel(
            "Scan the render directory recursively to collect the latest playblasts for the "
            "selected shots and copy them to your destination folder:"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # 2. Selected Shots Overview
        shots_group = QGroupBox(f"Target Shots ({count})")
        shots_layout = QVBoxLayout(shots_group)
        shots_layout.setSpacing(6)
        shots_layout.setContentsMargins(12, 10, 12, 10)

        self.list_shots = QListWidget()
        self.list_shots.setMaximumHeight(100)
        self.list_shots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        for item in self.selected_items:
            name = getattr(item, "name", str(item))
            seq = getattr(item, "sequence", "") or ""
            disp = f"{seq}_{name}" if seq and not name.startswith(f"{seq}_") else name
            QListWidgetItem(f"• {disp}", self.list_shots)

        shots_layout.addWidget(self.list_shots)
        layout.addWidget(shots_group, 0)

        # 3. Settings GroupBox
        settings_group = QGroupBox("Collection Settings")
        grp_layout = QVBoxLayout(settings_group)
        grp_layout.setSpacing(10)
        grp_layout.setContentsMargins(12, 12, 12, 12)

        # A. Render Source Preview
        src_label = QLabel("<b>Render Source Directory:</b>")
        grp_layout.addWidget(src_label)

        self.edit_render_src = QLineEdit()
        self.edit_render_src.setReadOnly(True)
        if self.render_path and Path(self.render_path).is_dir():
            self.edit_render_src.setText(str(self.render_path))
            self.edit_render_src.setStyleSheet("QLineEdit { color: #88c0d0; background: rgba(0, 0, 0, 0.15); }")
        else:
            r_str = str(self.render_path) if self.render_path else "Not configured in pipeline.yaml"
            self.edit_render_src.setText(f"{r_str} (Path not accessible)")
            self.edit_render_src.setStyleSheet("QLineEdit { color: #bf616a; background: rgba(0, 0, 0, 0.15); }")

        grp_layout.addWidget(self.edit_render_src)

        # B. Destination Folder Picker
        dest_label = QLabel("<b>Destination Folder:</b>")
        grp_layout.addWidget(dest_label)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)

        self.edit_destination = QLineEdit()
        self.edit_destination.setText(self.initial_dest)
        self.edit_destination.setPlaceholderText("/path/to/destination/folder")
        dest_row.addWidget(self.edit_destination, 1)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_destination)
        dest_row.addWidget(self.btn_browse, 0)

        grp_layout.addLayout(dest_row)

        # C. Department and File Format row
        opts_row = QHBoxLayout()
        opts_row.setSpacing(12)

        dept_code = getattr(self, "dept_code", "")
        dept = getattr(self, "department", "Layout")
        dept_display = f"{dept} ({dept_code})" if dept_code else dept
        lbl_dept = QLabel(f"<b>Department:</b> {dept_display}")
        opts_row.addWidget(lbl_dept, 1)

        lbl_fmt = QLabel("<b>Format:</b>")
        opts_row.addWidget(lbl_fmt, 0)

        self.combo_format = QComboBox()
        self.combo_format.setEditable(True)
        formats = [".mov", ".mp4", ".avi", ".mkv", ".png", ".exr"]
        clean_fmt = ("." + self.initial_format.lstrip(".")).lower()
        if clean_fmt not in formats:
            formats.insert(0, clean_fmt)
        self.combo_format.addItems(formats)
        self.combo_format.setCurrentText(clean_fmt)
        opts_row.addWidget(self.combo_format, 0)

        grp_layout.addLayout(opts_row)
        layout.addWidget(settings_group, 1)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_collect = QPushButton("Collect Playblasts")
        self.btn_collect.setDefault(True)
        self.btn_collect.clicked.connect(self._on_accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_collect)
        layout.addLayout(btn_layout, 0)

    def _browse_destination(self) -> None:
        """Open directory chooser dialog to update destination path."""
        start_dir = self.edit_destination.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder to Copy Playblast(s)",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self.edit_destination.setText(chosen)

    def _on_accept(self) -> None:
        """Validate destination folder and persist user preferences."""
        dest = self.edit_destination.text().strip()
        if not dest:
            QMessageBox.warning(self, "Invalid Destination", "Please specify a destination folder.")
            return

        dest_path = Path(dest)
        if not dest_path.is_dir():
            try:
                dest_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Cannot Create Directory",
                    f"Could not create destination directory:\n{dest}\n\nError: {e}",
                )
                return

        # Save user preferences
        try:
            from PySide6.QtCore import QSettings

            settings = QSettings("ZeroXe", "PipelineTools")
            settings.setValue("playblast/last_destination_dir", dest)
            fmt = self.combo_format.currentText().strip()
            if fmt:
                if not fmt.startswith("."):
                    fmt = f".{fmt}"
                settings.setValue("playblast/file_format", fmt)
            settings.sync()
        except Exception:
            pass

        self.accept()

    def get_destination_dir(self) -> str:
        """Return selected destination folder path."""
        return self.edit_destination.text().strip()

    def get_file_format(self) -> str:
        """Return configured file format extension (e.g. '.mov')."""
        fmt = self.combo_format.currentText().strip()
        if fmt and not fmt.startswith("."):
            fmt = f".{fmt}"
        return fmt or ".mov"

    def get_parameters(self) -> Dict[str, Any]:
        """Return full parameters dictionary for collection execution."""
        return {
            "destination_dir": self.get_destination_dir(),
            "file_format": self.get_file_format(),
            "shots": getattr(self, "selected_items", []),
            "render_path": getattr(self, "render_path", None),
            "department": getattr(self, "department", "Layout"),
            "episode": getattr(self, "episode", ""),
            "sequence": getattr(self, "sequence", ""),
        }


class PlayblastResultDialog(QDialog):
    """Builder-style summary dialog showing Playblast Collection results."""

    def __init__(
        self,
        result: CollectPlayblastResult,
        total_shots: int,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.result = result
        self.total_shots = total_shots
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Playblast Collect Results")
        self.resize(540, 400)
        self.setMinimumSize(460, 320)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header
        copied_count = len(self.result.copied_files)
        if copied_count > 0:
            header_text = f"<b>Playblast Collection Completed ({copied_count}/{self.total_shots} copied)</b>"
        else:
            header_text = "<b>No Playblasts Found</b>"

        header = QLabel(header_text)
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        dest_text = f"Destination: {self.result.destination_dir}"
        dest_label = QLabel(dest_text)
        dest_label.setWordWrap(True)
        layout.addWidget(dest_label, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # Copied files list
        details_list = QListWidget()
        details_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if self.result.copied_files:
            for cf in self.result.copied_files:
                size_mb = round(cf.size_bytes / (1024 * 1024), 2)
                item = QListWidgetItem(
                    f"✓ {cf.shot}: {cf.destination.name} ({size_mb} MB) [Version {cf.version_number}]",
                    details_list,
                )
                item.setForeground(Qt.GlobalColor.darkGreen)

        if self.result.missing_shots:
            for ms in self.result.missing_shots:
                item = QListWidgetItem(f"✗ {ms}: No matching playblast found", details_list)
                item.setForeground(Qt.GlobalColor.red)

        layout.addWidget(details_list, 1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        if self.result.destination_dir and Path(self.result.destination_dir).is_dir():
            self.btn_open_folder = QPushButton("Open Destination Folder")
            self.btn_open_folder.clicked.connect(self._open_destination_folder)
            btn_layout.addWidget(self.btn_open_folder, 0)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close, 0)

        layout.addLayout(btn_layout, 0)

    def _open_destination_folder(self) -> None:
        """Open destination directory in system file explorer."""
        try:
            dest = str(self.result.destination_dir)
            if sys.platform.startswith("linux"):
                import subprocess
                subprocess.Popen(["xdg-open", dest])
            elif sys.platform.startswith("win32"):
                import os
                os.startfile(dest)
            elif sys.platform.startswith("darwin"):
                import subprocess
                subprocess.Popen(["open", dest])
        except Exception:
            pass
