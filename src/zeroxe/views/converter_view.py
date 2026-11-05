"""Converter View Component.

Pure PySide6 presentation widget for media conversion (Image Sequence & Video to MP4).
Delegates all conversion logic, preset dispatching, and background execution to ConverterController.
"""


from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QWidget,
)

from zeroxe.controllers.converter_controller import (
    COL_COUNT,
    COL_NAME,
    COL_OUTPUT,
    COL_SOURCE,
    COL_STATUS,
    COL_TYPE,
    COL_VERSION,
    ConverterController,
)
from zeroxe.ui.ui_converter import Ui_Form


class ConverterView(QWidget):
    """Main Converter Tab Widget."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self._setup_ui_elements()
        self._setup_drag_and_drop()

        # Attach controller to handle business logic and worker thread
        self.controller = ConverterController(self)

    # ------------------------------------------------------------------
    # 1. UI Configuration
    # ------------------------------------------------------------------
    def _setup_ui_elements(self) -> None:
        """Configure widget styling, headers, and auxiliary action buttons."""
        # Configure Table View attributes
        table = self.ui.tableView_available
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Enable editing for editable cells (Name, Version, Output Path columns)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_VERSION, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_COUNT, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_SOURCE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_OUTPUT, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        table.setColumnWidth(COL_NAME, 150)
        table.setColumnWidth(COL_SOURCE, 220)
        table.setColumnWidth(COL_OUTPUT, 220)

        # Proportional layout: table (left) and control panel (right)
        self.ui.gridLayout_available.setColumnStretch(0, 3)
        self.ui.gridLayout_available.setColumnStretch(1, 2)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Master lineEdit_output placeholder
        self.ui.lineEdit_output.setPlaceholderText("Master Output Directory (optional)")
        self.ui.lineEdit_output.setToolTip("Master output directory. If set, all convert outputs will be saved here. You can also edit individual output paths directly in the table.")

        # Configure Framerate Spinbox (extend range beyond 31)
        self.ui.spinBox_framerate.setRange(1, 240)
        self.ui.spinBox_framerate.setValue(24)
        self.ui.spinBox_framerate.setSuffix(" fps")
        self.ui.spinBox_framerate.setToolTip("Target framerate for output video (e.g. 24 fps)")

        # Configure Quality Spinbox (1 = best, 31 = lowest)
        self.ui.spinBox_qualityLevel.setRange(1, 31)
        self.ui.spinBox_qualityLevel.setValue(1)
        # self.ui.spinBox_qualityLevel.setSuffix(" (qscale)")
        self.ui.spinBox_qualityLevel.setToolTip("Quality level 1-31 (1 = best quality, 31 = lowest quality, default: 1)")

        # Configure Image Preview Label
        self.ui.label_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui.label_preview.setText("No Preview")
        self.ui.label_preview.setMinimumHeight(150)
        self.ui.label_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.ui.label_preview.setStyleSheet(
            "QLabel { background-color: #1a1a1e; border: 1px solid #2e2e38; border-radius: 6px; color: #888899; }"
        )

        # Search placeholder
        self.ui.lineEdit_availableSearch.setPlaceholderText("Filter items by name, type, or path...")

    # ------------------------------------------------------------------
    # 2. Drag & Drop Support
    # ------------------------------------------------------------------
    def _setup_drag_and_drop(self) -> None:
        """Enable native file manager drag and drop onto the view and table."""
        self.setAcceptDrops(True)
        self.ui.tableView_available.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                self.controller.add_dropped_paths(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def fit_columns(self) -> None:
        """Fit table columns to content cleanly without over-stretching."""
        table = self.ui.tableView_available
        table.resizeColumnToContents(COL_NAME)
        table.resizeColumnToContents(COL_VERSION)
        table.resizeColumnToContents(COL_TYPE)
        table.resizeColumnToContents(COL_COUNT)
        table.resizeColumnToContents(COL_STATUS)

        # Keep interactive columns within clean, comfortable limits
        if table.columnWidth(COL_NAME) < 130:
            table.setColumnWidth(COL_NAME, 130)
        elif table.columnWidth(COL_NAME) > 240:
            table.setColumnWidth(COL_NAME, 240)

        if table.columnWidth(COL_SOURCE) < 180:
            table.setColumnWidth(COL_SOURCE, 180)
        elif table.columnWidth(COL_SOURCE) > 320:
            table.setColumnWidth(COL_SOURCE, 320)

        if table.columnWidth(COL_OUTPUT) < 180:
            table.setColumnWidth(COL_OUTPUT, 180)
        elif table.columnWidth(COL_OUTPUT) > 320:
            table.setColumnWidth(COL_OUTPUT, 320)

    # ------------------------------------------------------------------
    # 3. Lifecycle & Tab Synchronization
    # ------------------------------------------------------------------
    def refresh_presets(self) -> None:
        """Reload pipeline presets dynamically when switching to this tab."""
        if hasattr(self, "controller"):
            self.controller.load_presets(force_reload=False)

    def closeEvent(self, event) -> None:
        """Clean up background workers on close."""
        if hasattr(self, "controller"):
            self.controller.cleanup()
        super().closeEvent(event)
