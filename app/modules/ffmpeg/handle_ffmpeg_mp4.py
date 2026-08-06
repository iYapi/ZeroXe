import os
import re
import asyncio
from pathlib import Path
from typing import List

from PyQt6.QtGui import QStandardItem, QStandardItemModel, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QFileDialog, QMessageBox, QAbstractItemView, QHeaderView,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel

from app.utils.ffmpeg_manager import FFMPEGManager
from app.utils.file_manager import FileManager
from app.ui.modules.ffmpeg.ffmpeg_mp4_ui import Ui_Form

VIDEO_EXTENSIONS = (
    ".mp4", ".mov", ".avi", ".mkv",
    ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg"
)


class RemoveSuffixDialog(QDialog):
    def __init__(self, original_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remove Suffix / Frame Number")
        self.resize(400, 160)

        # Calculate stripped suggestion (removes trailing frame numbers like _0001, .0001, -0100)
        self.cleaned_name = re.sub(r'[\._\-\s]?\d+$', '', original_name)
        if not self.cleaned_name:
            self.cleaned_name = original_name

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"First File Name: <b>{original_name}</b>"))

        layout.addWidget(QLabel("Output Base Name:"))
        self.lineEdit_name = QLineEdit(self.cleaned_name, self)
        layout.addWidget(self.lineEdit_name)

        self.checkBox_apply_all = QCheckBox("Apply suffix removal rule to remaining items", self)
        layout.addWidget(self.checkBox_apply_all)

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("OK", self)
        self.btn_use_original = QPushButton("Use Original", self)
        self.btn_cancel = QPushButton("Cancel", self)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_use_original.clicked.connect(self.use_original)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_use_original)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.original_name = original_name

    def use_original(self):
        self.lineEdit_name.setText(self.original_name)
        self.accept()

    def get_result(self):
        return self.lineEdit_name.text().strip(), self.checkBox_apply_all.isChecked()


class HandleFFMPEGMP4(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        # Models
        self.model_available = QStandardItemModel(self)
        self.model_available.setHorizontalHeaderLabels(["Name", "Suffix"])

        # Proxy for search
        self.proxyScan = QSortFilterProxyModel(self.ui.tableView_available)
        self.proxyScan.setSourceModel(self.model_available)
        self.proxyScan.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxyScan.setFilterKeyColumn(0)
        self.ui.tableView_available.setModel(self.proxyScan)
        self.ui.lineEdit_availableSearch.textChanged.connect(self.proxyScan.setFilterFixedString)

        # Table view configuration
        self.ui.tableView_available.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableView_available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.tableView_available.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ui.tableView_available.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)

        # Store folder data: {folder_path: media_info}
        self.folder_data = {}

        # Batch drop state
        self.batch_apply_all = False

        # Buttons
        self.ui.pushButton_locateOutput.clicked.connect(self.on_browse_output)
        self.ui.pushButton_removeFolder.clicked.connect(self.on_remove_selected_folders)
        self.ui.pushButton_clearFolder.clicked.connect(self.on_clear_all_folders)
        self.ui.pushButton_convert.clicked.connect(self.on_convert_all_folders)

        # Spinbox value
        self.ui.spinBox_qualityLevel.setMinimum(1)
        self.ui.spinBox_qualityLevel.setMaximum(31)
        self.ui.spinBox_qualityLevel.setValue(10)

        # Enable drag and drop
        self.enable_drag_drop_tableview()
        self.enable_drag_drop_output()

    def enable_drag_drop_tableview(self):
        """Enable drag and drop for folders and videos to tableView_available"""
        self.ui.tableView_available.setAcceptDrops(True)
        self.ui.tableView_available.setDragEnabled(True)
        self.ui.tableView_available.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        def drag_enter_event(event):
            if event.mimeData().hasUrls():
                for url in event.mimeData().urls():
                    if url.isLocalFile():
                        path = Path(url.toLocalFile())
                        if (
                            path.is_dir()
                            or (
                                path.is_file()
                                and path.suffix.lower() in VIDEO_EXTENSIONS
                            )
                        ):
                            event.acceptProposedAction()
                            return
            event.ignore()

        def drop_event(event):
            if event.mimeData().hasUrls():
                self.batch_apply_all = False
                for url in event.mimeData().urls():
                    if not url.isLocalFile():
                        continue
                    path = Path(url.toLocalFile())
                    if path.is_dir():
                        self.add_folder_to_list(str(path))
                    elif (
                        path.is_file()
                        and path.suffix.lower() in VIDEO_EXTENSIONS
                    ):
                        self.add_video_to_list(str(path))
                event.acceptProposedAction()
                return
            event.ignore()

        self.ui.tableView_available.dragEnterEvent = drag_enter_event
        self.ui.tableView_available.dropEvent = drop_event

    def enable_drag_drop_output(self):
        """Enable drag and drop for output path"""
        self.ui.lineEdit_output.setAcceptDrops(True)

        def handle_drag_enter(event):
            if event.mimeData().hasUrls():
                for url in event.mimeData().urls():
                    if url.isLocalFile():
                        path = Path(url.toLocalFile())
                        if path.is_dir():
                            event.acceptProposedAction()
                            return
            event.ignore()

        def handle_drop(event):
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir():
                        self.ui.lineEdit_output.setText(str(path))
                        event.acceptProposedAction()
                        return
            event.ignore()

        self.ui.lineEdit_output.dragEnterEvent = handle_drag_enter
        self.ui.lineEdit_output.dropEvent = handle_drop

    def add_folder_to_list(self, folder_path: str):
        """Add a folder to the table using the first file inside the folder for base name"""
        folder_path = str(Path(folder_path).resolve())

        # Check if folder contains image files
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx')
        image_files = sorted([
            f for f in Path(folder_path).iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ])

        if not image_files:
            QMessageBox.warning(self, "Warning", "Folder does not contain any image files.")
            return

        if folder_path in self.folder_data:
            return

        # Use first file inside the folder
        first_image = image_files[0]
        first_name = first_image.stem

        if self.batch_apply_all:
            cleaned = re.sub(r'[\._\-\s]?\d+$', '', first_name)
            base_name = cleaned if cleaned else first_name
        else:
            dialog = RemoveSuffixDialog(first_name, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                base_name, apply_all = dialog.get_result()
                if apply_all:
                    self.batch_apply_all = True
            else:
                # User cancelled adding this item
                return

        if not base_name:
            base_name = first_name

        media_info = {
            "type": "folder",
            "path": folder_path
        }
        self.folder_data[folder_path] = media_info

        item_name = QStandardItem(base_name)
        item_name.setData(media_info, Qt.ItemDataRole.UserRole)
        item_suffix = QStandardItem("_v001")

        self.model_available.appendRow([item_name, item_suffix])
        self.model_available.sort(0, Qt.SortOrder.AscendingOrder)

    def add_video_to_list(self, video_path: str):
        """Add a video file to the table if it's not already there"""
        video_path = str(Path(video_path).resolve())
        file_path = Path(video_path)
        video_name = file_path.stem

        if video_path in self.folder_data:
            return

        media_info = {
            "type": "video",
            "path": video_path
        }
        self.folder_data[video_path] = media_info

        item_name = QStandardItem(video_name)
        item_name.setData(media_info, Qt.ItemDataRole.UserRole)
        item_suffix = QStandardItem("_v001")

        self.model_available.appendRow([item_name, item_suffix])
        self.model_available.sort(0, Qt.SortOrder.AscendingOrder)

    def on_browse_output(self):
        """Browse for output directory"""
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.ui.lineEdit_output.setText(path)

    def on_remove_selected_folders(self):
        """Remove selected items from the table"""
        selected_indexes = self.ui.tableView_available.selectionModel().selectedRows()
        if not selected_indexes:
            return

        rows_to_remove = set()
        for proxy_idx in selected_indexes:
            src_idx = self.proxyScan.mapToSource(proxy_idx)
            rows_to_remove.add(src_idx.row())

        for row in sorted(rows_to_remove, reverse=True):
            item_name = self.model_available.item(row, 0)
            if item_name:
                media_info = item_name.data(Qt.ItemDataRole.UserRole)
                if media_info and "path" in media_info:
                    path = media_info["path"]
                    if path in self.folder_data:
                        del self.folder_data[path]
            self.model_available.removeRow(row)

    def on_clear_all_folders(self):
        """Clear all items from the table"""
        self.model_available.removeRows(0, self.model_available.rowCount())
        self.folder_data.clear()

    def on_convert_all_folders(self):
        """Convert all folders/videos to MP4"""
        if self.model_available.rowCount() == 0:
            QMessageBox.information(self, "Info", "No items to convert.")
            return

        output_dir = self.ui.lineEdit_output.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Warning", "Please specify an output directory.")
            return

        output_path = Path(output_dir)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create output directory:\n{e}")
                return

        try:
            quality = int(self.ui.spinBox_qualityLevel.value())
            framerate = int(self.ui.spinBox_framerate.value())
        except Exception:
            quality = 10
            framerate = 24

        failed: List[str] = []

        for i in range(self.model_available.rowCount()):
            item_name = self.model_available.item(i, 0)
            item_suffix = self.model_available.item(i, 1)

            if not item_name:
                continue

            base_name = item_name.text().strip()
            suffix = item_suffix.text().strip() if item_suffix else ""

            out_filename = f"{base_name}{suffix}"
            if not out_filename.lower().endswith(".mp4"):
                out_filename += ".mp4"

            media_info = item_name.data(Qt.ItemDataRole.UserRole)
            if not media_info:
                failed.append(f"{base_name} (data not found)")
                continue

            media_type = media_info["type"]
            source_path = media_info["path"]

            if not source_path or not Path(source_path).exists():
                failed.append(f"{base_name} (source not found)")
                continue

            try:
                output_file = str(output_path / out_filename)

                print(f"\n{'='*60}")
                print(f"Converting: {base_name}")
                print(f"  Source: {source_path}")
                print(f"  Output: {output_file}")
                print(f"  Quality: {quality}")
                print(f"  Framerate: {framerate}")
                print(f"{'='*60}\n")

                if media_type == "folder":
                    result = asyncio.run(
                        FFMPEGManager().folder_to_mp4(
                            folder_path=source_path,
                            output_file=output_file,
                            framerate=framerate,
                            quality=quality
                        )
                    )

                elif media_type == "video":
                    result = asyncio.run(
                        FFMPEGManager().video_to_mp4(
                            input_file=source_path,
                            output_file=output_file,
                            quality=quality
                        )
                    )

                if not result:
                    failed.append(f"{base_name} (conversion failed)")

            except Exception as e:
                import traceback
                failed.append(f"{base_name} -> {e}")
                print(f"Error details: {traceback.format_exc()}")

        if failed:
            msg = "Some conversions failed:\n\n" + "\n".join(failed)
            QMessageBox.warning(self, "Completed with errors", msg)
        else:
            QMessageBox.information(self, "Success", "All items converted successfully.")