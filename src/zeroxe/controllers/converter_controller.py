"""Converter Controller for ZeroXe.

Coordinates the Converter View, background conversion worker thread,
and dynamic pipeline preset service.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSortFilterProxyModel, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMenu, QMessageBox

from zeroxe.services.converter_service import ConverterPreset, ConverterService
from zeroxe.services.notification_service import NotificationService
from zeroxe.utils.log_util import open_file_in_system

logger = logging.getLogger(__name__)

# Model Column Indexes
COL_NAME = 0
COL_VERSION = 1
COL_TYPE = 2
COL_COUNT = 3
COL_STATUS = 4
COL_SOURCE = 5
COL_OUTPUT = 6
TOTAL_COLUMNS = 7


class ConverterWorker(QThread):
    """Background worker thread to execute batch conversions sequentially without blocking UI."""

    item_started = Signal(int, str)
    item_progress = Signal(int, str)
    item_finished = Signal(int, bool, str)
    all_finished = Signal(int, int, int)

    def __init__(
        self,
        items: list[dict[str, Any]],
        preset: ConverterPreset,
        framerate: int = 24,
        quality: int = 15,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.items = items
        self.preset = preset
        self.framerate = framerate
        self.quality = quality
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker thread to stop."""
        self._is_cancelled = True

    def run(self) -> None:
        total = len(self.items)
        successful = 0
        failed = 0

        logger.info(f"Starting batch conversion of {total} item(s) using preset '{self.preset.name}'...")

        for idx, item in enumerate(self.items):
            if self._is_cancelled:
                logger.info("Batch conversion was cancelled by user.")
                break

            name = item.get("name", f"Item #{idx + 1}")
            source_path = item.get("source_path", "")
            output_path = item.get("output_path", "")

            self.item_started.emit(idx, name)

            def make_progress_cb(item_idx: int):
                def progress_cb(prog: Any) -> None:
                    if self._is_cancelled:
                        return
                    if hasattr(prog, "fps") and hasattr(prog, "frame"):
                        p_text = f"Frame: {prog.frame} (FPS: {prog.fps:.1f})"
                    elif isinstance(prog, dict):
                        p_text = str(prog.get("status", "Converting..."))
                    else:
                        p_text = str(prog)
                    self.item_progress.emit(item_idx, p_text)
                return progress_cb

            try:
                success, msg = ConverterService.execute_preset(
                    preset=self.preset,
                    input_path=source_path,
                    output_file=output_path,
                    framerate=self.framerate,
                    quality=self.quality,
                    progress_callback=make_progress_cb(idx),
                )
            except Exception as ex:
                success = False
                msg = str(ex)

            if success:
                successful += 1
                logger.info(f"✓ Converted '{name}' -> {output_path}")
            else:
                failed += 1
                logger.error(f"✗ Failed '{name}': {msg}")

            self.item_finished.emit(idx, success, msg)

        self.all_finished.emit(total, successful, failed)


class ConverterController(QObject):
    """Controller managing the Converter tab presentation and business logic."""

    def __init__(self, view: Any):
        super().__init__(view)
        self.view = view
        self.ui = view.ui

        self.model = QStandardItemModel(0, TOTAL_COLUMNS, self)
        self.model.setHorizontalHeaderLabels([
            "Name", "Version", "Type", "Items / Duration", "Status", "Source Path", "Output Path"
        ])

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Filter across all columns

        self.ui.tableView_available.setModel(self.proxy_model)

        self._current_presets: list[ConverterPreset] = []
        self._active_worker: ConverterWorker | None = None
        self._thumbnail_cache: dict[str, QPixmap] = {}
        self._is_updating_model: bool = False

        self._bind_signals()
        self.load_presets()

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------
    def _bind_signals(self) -> None:
        """Connect UI signals to controller actions."""
        # Presets dropdown
        self.ui.comboBox_preset.currentIndexChanged.connect(self._on_preset_changed)

        # Search filter
        self.ui.lineEdit_availableSearch.textChanged.connect(self.proxy_model.setFilterFixedString)

        # Table Selection
        selection_model = self.ui.tableView_available.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_changed)

        # In-place table cell edits (Name, Version, Output Path)
        self.model.itemChanged.connect(self._on_item_changed)

        # Master Output Directory Edit & Locate
        self.ui.lineEdit_output.textEdited.connect(self._on_master_output_edited)
        self.ui.pushButton_locateOutput.clicked.connect(self._on_locate_master_output)

        # Clear and Remove buttons
        self.ui.pushButton_removeFolder.clicked.connect(self.remove_selected_items)
        self.ui.pushButton_clearFolder.clicked.connect(self.clear_all_items)

        # Convert button
        self.ui.pushButton_convert.clicked.connect(self.start_conversion)

        # Context Menu on Table
        self.ui.tableView_available.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableView_available.customContextMenuRequested.connect(self._show_context_menu)

    # ------------------------------------------------------------------
    # Presets Discovery & Loading
    # ------------------------------------------------------------------
    def load_presets(self, force_reload: bool = False) -> None:
        """Scan pipeline and populate comboBox_preset with available presets."""
        self.ui.comboBox_preset.blockSignals(True)
        self.ui.comboBox_preset.clear()

        self._current_presets = ConverterService.list_presets(force_reload=force_reload)

        if not self._current_presets:
            self.ui.comboBox_preset.addItem("No presets found in pipeline", None)
            self.ui.comboBox_preset.blockSignals(False)
            return

        for p in self._current_presets:
            type_tag = f"[{p.input_type.upper()}]" if p.input_type != "any" else "[ALL]"
            disp = f"{type_tag} {p.name}"
            self.ui.comboBox_preset.addItem(disp, p.id)

        self.ui.comboBox_preset.blockSignals(False)

        # Trigger selection update for first preset
        self._on_preset_changed(0)

    def _on_preset_changed(self, index: int) -> None:
        """Update property spinboxes and tooltips when preset selection changes."""
        preset = self.get_selected_preset()
        if not preset:
            return

        # Update framerate and quality spinboxes with preset defaults
        self.ui.spinBox_framerate.blockSignals(True)
        self.ui.spinBox_qualityLevel.blockSignals(True)

        if preset.default_framerate > 0:
            self.ui.spinBox_framerate.setValue(preset.default_framerate)

        if preset.default_quality > 0:
            self.ui.spinBox_qualityLevel.setValue(preset.default_quality)

        self.ui.spinBox_framerate.blockSignals(False)
        self.ui.spinBox_qualityLevel.blockSignals(False)

        # Update tooltip
        desc = preset.description or f"Preset {preset.name}"
        self.ui.comboBox_preset.setToolTip(f"{preset.name}\n{desc}\nSource: {preset.file_path or 'Built-in'}")

    def get_selected_preset(self) -> ConverterPreset | None:
        """Return currently selected ConverterPreset object."""
        idx = self.ui.comboBox_preset.currentIndex()
        if idx < 0 or idx >= len(self._current_presets):
            return None
        return self._current_presets[idx]

    # ------------------------------------------------------------------
    # Adding Items (Folders / Videos / Drag & Drop)
    # ------------------------------------------------------------------
    def add_folder_dialog(self) -> None:
        """Open directory picker to add an image sequence folder."""
        folder = QFileDialog.getExistingDirectory(
            self.view,
            "Select Image Sequence Folder",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.add_item_path(folder, prompt_output_name=True)

    def add_video_dialog(self) -> None:
        """Open file dialog to add one or more video files."""
        files, _ = QFileDialog.getOpenFileNames(
            self.view,
            "Select Video File(s)",
            "",
            "Video Files (*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v *.ts *.m2ts);;All Files (*.*)",
        )
        for f in files:
            self.add_item_path(f, prompt_output_name=True)

    def add_item_path(
        self,
        path_str: str,
        output_name: str | None = None,
        version: str | None = None,
        prompt_output_name: bool = False,
    ) -> bool:
        """Inspect and append a single path (folder or video) to the table."""
        info = ConverterService.inspect_input_path(path_str)
        if not info.get("is_valid"):
            logger.warning(f"Skipping invalid or unsupported path: {path_str}")
            return False

        # Check if already in table
        source_path = info.get("override_path", path_str)
        for r in range(self.model.rowCount()):
            if self.model.item(r, COL_SOURCE).text() == source_path:
                logger.info(f"Item already in queue: {source_path}")
                return False

        # 1. Output name from first image inside (for folder) or video stem
        derived_name = info.get("name") or (Path(source_path).stem if Path(source_path).is_file() else Path(source_path).name)
        derived_version = version or info.get("version") or "_v001"

        if prompt_output_name and output_name is None:
            chosen_name, ok = QInputDialog.getText(
                self.view,
                "Set Output Name",
                f"Set output name for:\n{Path(source_path).name}",
                QLineEdit.EchoMode.Normal,
                derived_name,
            )
            if not ok:
                return False
            output_name = chosen_name.strip() if chosen_name.strip() else derived_name
        elif output_name is None:
            output_name = derived_name

        clean_name = output_name[:-4] if output_name.lower().endswith(".mp4") else output_name

        # 2. Output directory: master output directory (lineEdit_output) if set, else source parent
        master_dir = self.ui.lineEdit_output.text().strip()
        if master_dir:
            target_dir = Path(master_dir)
        else:
            target_dir = Path(source_path).parent

        preset = self.get_selected_preset()
        ext = preset.output_extension if preset else ".mp4"
        default_out = str((target_dir / f"{clean_name}{derived_version}{ext}").resolve())

        # 3. Construct row items
        item_name = QStandardItem(clean_name)
        item_name.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

        item_version = QStandardItem(derived_version)
        item_version.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

        item_type = QStandardItem(info.get("type", "").title())
        item_count = QStandardItem(info.get("count_display", ""))
        item_status = QStandardItem("Ready")
        item_status.setForeground(QColor("#a0a0b0"))

        item_source = QStandardItem(source_path)

        item_output = QStandardItem(default_out)
        item_output.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

        # Columns without editing
        for it in (item_type, item_count, item_status, item_source):
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        # Store metadata in Name item UserRole
        item_name.setData({
            "name": clean_name,
            "version": derived_version,
            "source_path": source_path,
            "output_path": default_out,
            "type": info.get("type"),
            "preview_image": info.get("preview_image"),
            "file_count": info.get("file_count", 1),
        }, Qt.ItemDataRole.UserRole)

        self.model.appendRow([
            item_name, item_version, item_type, item_count, item_status, item_source, item_output
        ])

        # Select newly added item if only item
        if self.model.rowCount() == 1:
            self.ui.tableView_available.selectRow(0)

        if hasattr(self.view, "fit_columns"):
            self.view.fit_columns()

        return True

    def add_dropped_paths(self, paths: list[str]) -> None:
        """Handle multiple paths dropped via drag-and-drop."""
        added_count = 0
        for p in paths:
            if self.add_item_path(p, prompt_output_name=False):
                added_count += 1
        if added_count > 0:
            logger.info(f"Added {added_count} item(s) to Converter queue.")

    # ------------------------------------------------------------------
    # Selection and Output Path Handling
    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        """Update image preview for selected item without overwriting master output path."""
        indexes = self.ui.tableView_available.selectionModel().selectedRows()
        if not indexes:
            self._set_preview_placeholder("Select an item to preview")
            return

        proxy_idx = indexes[0]
        src_idx = self.proxy_model.mapToSource(proxy_idx)
        row = src_idx.row()

        name_item = self.model.item(row, COL_NAME)
        data = name_item.data(Qt.ItemDataRole.UserRole) or {}
        preview_img = data.get("preview_image")
        source_path = data.get("source_path", "")
        item_type = data.get("type", "")

        self._update_preview(preview_img, source_path, item_type)

    def _on_item_changed(self, item: QStandardItem) -> None:
        """Synchronize in-place edits in Name, Version, and Output Path columns."""
        if self._is_updating_model:
            return

        col = item.column()
        row = item.row()

        if col not in (COL_NAME, COL_VERSION, COL_OUTPUT):
            return

        self._is_updating_model = True
        try:
            name_item = self.model.item(row, COL_NAME)
            version_item = self.model.item(row, COL_VERSION)
            out_item = self.model.item(row, COL_OUTPUT)
            source_item = self.model.item(row, COL_SOURCE)
            if not (name_item and version_item and out_item and source_item):
                return

            data = name_item.data(Qt.ItemDataRole.UserRole) or {}
            preset = self.get_selected_preset()
            ext = preset.output_extension if preset else ".mp4"

            if col == COL_NAME:
                new_name = item.text().strip()
                if not new_name:
                    new_name = data.get("name") or "output"
                    item.setText(new_name)

                clean_name = new_name[:-4] if new_name.lower().endswith(".mp4") else new_name
                if clean_name != new_name:
                    item.setText(clean_name)
                    new_name = clean_name

                ver_str = version_item.text().strip()
                old_out = out_item.text().strip()
                target_dir = Path(old_out).parent if old_out else Path(source_item.text()).parent
                new_out = str((target_dir / f"{clean_name}{ver_str}{ext}").resolve())
                out_item.setText(new_out)

                data["name"] = clean_name
                data["output_path"] = new_out
                name_item.setData(data, Qt.ItemDataRole.UserRole)

            elif col == COL_VERSION:
                ver_str = item.text().strip()
                name_str = name_item.text().strip()
                old_out = out_item.text().strip()
                target_dir = Path(old_out).parent if old_out else Path(source_item.text()).parent
                new_out = str((target_dir / f"{name_str}{ver_str}{ext}").resolve())
                out_item.setText(new_out)

                data["version"] = ver_str
                data["output_path"] = new_out
                name_item.setData(data, Qt.ItemDataRole.UserRole)

            elif col == COL_OUTPUT:
                new_out = item.text().strip()
                data["output_path"] = new_out
                name_item.setData(data, Qt.ItemDataRole.UserRole)

        finally:
            self._is_updating_model = False
            if hasattr(self.view, "fit_columns"):
                self.view.fit_columns()

    def _on_master_output_edited(self, new_text: str) -> None:
        """When user sets lineEdit_output, update all convert outputs in the queue."""
        master_dir = new_text.strip()
        if not master_dir or self._is_updating_model:
            return

        self._is_updating_model = True
        try:
            target_dir = Path(master_dir)
            preset = self.get_selected_preset()
            ext = preset.output_extension if preset else ".mp4"

            for r in range(self.model.rowCount()):
                name_item = self.model.item(r, COL_NAME)
                version_item = self.model.item(r, COL_VERSION)
                out_item = self.model.item(r, COL_OUTPUT)
                if not (name_item and version_item and out_item):
                    continue

                name_str = name_item.text().strip()
                ver_str = version_item.text().strip()
                new_out = str((target_dir / f"{name_str}{ver_str}{ext}").resolve())
                out_item.setText(new_out)

                data = name_item.data(Qt.ItemDataRole.UserRole) or {}
                data["output_path"] = new_out
                name_item.setData(data, Qt.ItemDataRole.UserRole)
        finally:
            self._is_updating_model = False
            if hasattr(self.view, "fit_columns"):
                self.view.fit_columns()

    def _on_locate_master_output(self) -> None:
        """Browse for master output directory and apply to all items."""
        current_val = self.ui.lineEdit_output.text().strip()
        dest_dir = QFileDialog.getExistingDirectory(
            self.view,
            "Select Master Output Directory",
            current_val or "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if dest_dir:
            self.ui.lineEdit_output.setText(dest_dir)
            self._on_master_output_edited(dest_dir)

    # ------------------------------------------------------------------
    # Image / Thumbnail Preview
    # ------------------------------------------------------------------
    def _set_preview_placeholder(self, text: str) -> None:
        """Render clean placeholder text inside preview label."""
        self.ui.label_preview.clear()
        self.ui.label_preview.setText(text)
        self.ui.label_preview.setStyleSheet(
            "QLabel { background-color: #1a1a1e; border: 1px solid #2e2e38; border-radius: 6px; color: #888899; font-size: 11px; }"
        )

    def _update_preview(self, img_path: str | None, source_path: str, item_type: str) -> None:
        """Generate and display thumbnail for image sequence or video item."""
        pixmap: QPixmap | None = None

        # Check thumbnail cache
        cache_key = img_path or source_path
        if cache_key in self._thumbnail_cache:
            self._render_pixmap(self._thumbnail_cache[cache_key])
            return

        # 1. Direct load for standard image files
        if img_path and Path(img_path).is_file():
            ext = Path(img_path).suffix.lower()
            if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'):
                pm = QPixmap(img_path)
                if not pm.isNull():
                    pixmap = pm

        # 2. Fast FFmpeg extraction for EXR or video files
        if pixmap is None:
            pixmap = self._extract_thumbnail_via_ffmpeg(img_path or source_path)

        if pixmap and not pixmap.isNull():
            self._thumbnail_cache[cache_key] = pixmap
            self._render_pixmap(pixmap)
        else:
            self._set_preview_placeholder(f"Preview unavailable\n({Path(source_path).name})")

    def _render_pixmap(self, pixmap: QPixmap) -> None:
        """Scale and display pixmap preserving aspect ratio within label bounds."""
        target_size = self.ui.label_preview.size()
        w = max(target_size.width() - 10, 160)
        h = max(target_size.height() - 10, 120)
        scaled = pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.ui.label_preview.setPixmap(scaled)
        self.ui.label_preview.setStyleSheet(
            "QLabel { background-color: #121216; border: 1px solid #2e2e38; border-radius: 6px; }"
        )

    def _extract_thumbnail_via_ffmpeg(self, file_path: str) -> QPixmap | None:
        """Extract a single frame thumbnail using system ffmpeg binary."""
        if not file_path or not Path(file_path).exists():
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name

            cmd = [
                "ffmpeg", "-y", "-ss", "00:00:00.500", "-i", str(file_path),
                "-vframes", "1", "-vf", "scale=360:-1", "-q:v", "3", tmp_path,
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            if res.returncode == 0 and Path(tmp_path).is_file():
                pm = QPixmap(tmp_path)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                return pm if not pm.isNull() else None

            if Path(tmp_path).is_file():
                os.unlink(tmp_path)
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Item Queue Operations
    # ------------------------------------------------------------------
    def remove_selected_items(self) -> None:
        """Remove currently selected item rows from table."""
        selected = self.ui.tableView_available.selectionModel().selectedRows()
        if not selected:
            return

        source_rows = sorted(
            [self.proxy_model.mapToSource(idx).row() for idx in selected],
            reverse=True,
        )
        for r in source_rows:
            self.model.removeRow(r)

    def clear_all_items(self) -> None:
        """Clear all items from table."""
        if self.model.rowCount() == 0:
            return

        if self._active_worker and self._active_worker.isRunning():
            QMessageBox.warning(self.view, "Cannot Clear", "A conversion is currently running. Please wait or cancel first.")
            return

        self.model.removeRows(0, self.model.rowCount())
        self._set_preview_placeholder("Queue cleared")

    # ------------------------------------------------------------------
    # Context Menu
    # ------------------------------------------------------------------
    def _show_context_menu(self, pos) -> None:
        """Show context menu on table view with operational actions."""
        menu = QMenu(self.view)

        act_add_folder = menu.addAction("Add Folder (Image Sequence)...")
        act_add_folder.triggered.connect(self.add_folder_dialog)

        act_add_video = menu.addAction("Add Video File(s)...")
        act_add_video.triggered.connect(self.add_video_dialog)

        menu.addSeparator()

        selected = self.ui.tableView_available.selectionModel().selectedRows()
        if selected:
            proxy_idx = selected[0]
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            source_p = self.model.item(src_idx.row(), COL_SOURCE).text()
            output_p = self.model.item(src_idx.row(), COL_OUTPUT).text()

            act_open_source = menu.addAction("Open Source Location")
            act_open_source.triggered.connect(
                lambda: open_file_in_system(Path(source_p).parent if Path(source_p).is_file() else Path(source_p))
            )

            if Path(output_p).exists():
                act_open_output = menu.addAction("Open Output Location")
                act_open_output.triggered.connect(lambda: open_file_in_system(Path(output_p).parent))

            act_remove = menu.addAction("Remove Selected")
            act_remove.triggered.connect(self.remove_selected_items)

        act_clear = menu.addAction("Clear All")
        act_clear.triggered.connect(self.clear_all_items)

        menu.exec(self.ui.tableView_available.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Conversion Execution
    # ------------------------------------------------------------------
    def start_conversion(self) -> None:
        """Start batch conversion of all queued items using selected pipeline preset."""
        if self._active_worker and self._active_worker.isRunning():
            # If already running, treat button click as cancel
            reply = QMessageBox.question(
                self.view,
                "Cancel Conversion",
                "Are you sure you want to cancel the running conversion?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._active_worker.cancel()
                self.ui.pushButton_convert.setText("Cancelling...")
                self.ui.pushButton_convert.setEnabled(False)
            return

        total_rows = self.model.rowCount()
        if total_rows == 0:
            QMessageBox.information(
                self.view,
                "Queue Empty",
                "Please add image sequence folders or video files to the queue before converting.",
            )
            return

        preset = self.get_selected_preset()
        if not preset:
            QMessageBox.warning(
                self.view,
                "No Preset Selected",
                "Please select a valid converter preset from the dropdown.",
            )
            return

        framerate = self.ui.spinBox_framerate.value()
        quality = self.ui.spinBox_qualityLevel.value()

        # Build items list
        items: list[dict[str, Any]] = []
        for r in range(total_rows):
            name = self.model.item(r, COL_NAME).text().strip()
            version = self.model.item(r, COL_VERSION).text().strip()
            source_p = self.model.item(r, COL_SOURCE).text()
            output_p = self.model.item(r, COL_OUTPUT).text().strip()
            items.append({
                "row": r,
                "name": f"{name}{version}",
                "source_path": source_p,
                "output_path": output_p,
            })
            self.model.item(r, COL_STATUS).setText("Pending")
            self.model.item(r, COL_STATUS).setForeground(QColor("#a0a0b0"))

        # Launch background worker
        self._active_worker = ConverterWorker(
            items=items,
            preset=preset,
            framerate=framerate,
            quality=quality,
            parent=self,
        )

        self._active_worker.item_started.connect(self._on_worker_item_started)
        self._active_worker.item_progress.connect(self._on_worker_item_progress)
        self._active_worker.item_finished.connect(self._on_worker_item_finished)
        self._active_worker.all_finished.connect(self._on_worker_all_finished)

        self.ui.pushButton_convert.setText("Cancel Conversion")
        self.ui.pushButton_convert.setStyleSheet("background-color: #a82222; color: #ffffff; font-weight: bold;")
        self.ui.pushButton_removeFolder.setEnabled(False)
        self.ui.pushButton_clearFolder.setEnabled(False)

        self._active_worker.start()

    def _on_worker_item_started(self, idx: int, name: str) -> None:
        """Update row status when item starts processing."""
        if idx < self.model.rowCount():
            item = self.model.item(idx, COL_STATUS)
            item.setText("Converting...")
            item.setForeground(QColor("#4da6ff"))

    def _on_worker_item_progress(self, idx: int, progress_text: str) -> None:
        """Update live status text for currently processing row."""
        if idx < self.model.rowCount():
            self.model.item(idx, COL_STATUS).setText(f"Converting ({progress_text})")

    def _on_worker_item_finished(self, idx: int, success: bool, msg: str) -> None:
        """Update row status upon individual item completion."""
        if idx < self.model.rowCount():
            item = self.model.item(idx, COL_STATUS)
            if success:
                item.setText("Completed")
                item.setForeground(QColor("#44cc66"))
            else:
                item.setText(f"Failed ({msg[:30]})")
                item.setForeground(QColor("#ff5555"))
                item.setToolTip(msg)

    def _on_worker_all_finished(self, total: int, successful: int, failed: int) -> None:
        """Handle completion of all queue items."""
        self.ui.pushButton_convert.setText("Convert")
        self.ui.pushButton_convert.setStyleSheet("")
        self.ui.pushButton_convert.setEnabled(True)
        self.ui.pushButton_removeFolder.setEnabled(True)
        self.ui.pushButton_clearFolder.setEnabled(True)
        self._active_worker = None

        summary_msg = f"Conversion finished!\n\nTotal: {total}\nSuccessful: {successful}\nFailed: {failed}"
        logger.info(summary_msg.replace("\n", " "))

        NotificationService.show_notification(
            title="ZeroXe Converter",
            message=f"Completed {successful}/{total} conversion(s).",
        )

        if failed > 0:
            QMessageBox.warning(self.view, "Conversion Finished with Errors", summary_msg)
        else:
            QMessageBox.information(self.view, "Conversion Complete", summary_msg)

    def cleanup(self) -> None:
        """Clean up background workers on application exit."""
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.cancel()
            self._active_worker.wait(3000)
