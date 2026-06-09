import os
import asyncio
from pathlib import Path
from typing import List

from PyQt6.QtGui import QStandardItem, QStandardItemModel, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QWidget, QFileDialog, QMessageBox, QAbstractItemView
from PyQt6.QtCore import Qt, QSortFilterProxyModel

from app.utils.ffmpeg_manager import FFMPEGManager
from app.utils.file_manager import FileManager
from app.ui.modules.ffmpeg.ffmpeg_mp4_ui import Ui_Form

VIDEO_EXTENSIONS = (
    ".mp4", ".mov", ".avi", ".mkv",
    ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg"
)
class HandleFFMPEGMP4(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        # Models
        self.model_available = QStandardItemModel(self)
        self.ui.listView_available.setModel(self.model_available)

        # Proxy for search
        self.proxyScan = QSortFilterProxyModel(self.ui.listView_available)
        self.proxyScan.setSourceModel(self.model_available)
        self.proxyScan.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxyScan.setFilterKeyColumn(0)
        self.ui.listView_available.setModel(self.proxyScan)
        self.ui.lineEdit_availableSearch.textChanged.connect(self.proxyScan.setFilterFixedString)

        # List view selection
        self.ui.listView_available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # Store folder data: {display_name: folder_path}
        self.folder_data = {}

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
        self.enable_drag_drop_listview()
        self.enable_drag_drop_output()

    def enable_drag_drop_listview(self):
        """Enable drag and drop for folders to listView_available"""
        self.ui.listView_available.setAcceptDrops(True)
        self.ui.listView_available.setDragEnabled(True)
        self.ui.listView_available.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

        original_drag_enter = self.ui.listView_available.dragEnterEvent
        original_drop = self.ui.listView_available.dropEvent

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

        self.ui.listView_available.dragEnterEvent = drag_enter_event
        self.ui.listView_available.dropEvent = drop_event

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
        """Add a folder to the list if it's not already there"""
        folder_path = str(Path(folder_path).resolve())
        
        # Check if folder contains image files
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx')
        image_files = sorted([f for f in Path(folder_path).iterdir() 
                             if f.is_file() and f.suffix.lower() in image_extensions])
        
        if not image_files:
            QMessageBox.warning(self, "Warning", f"Folder does not contain any image files.")
            return
        
        # Get first image to determine display name
        first_image = image_files[0]
        base_name = first_image.stem
        
        # Use base name as display name
        display_name = base_name
        
        # Check if already exists
        if display_name in self.folder_data:
            return
        
        # Store just the folder path - FFMPEGManager.folder_to_mp4 will handle the rest
        self.folder_data[display_name] = {
            "type": "folder",
            "path": folder_path
        }
        self.model_available.appendRow(QStandardItem(display_name))
        self.model_available.sort(0, Qt.SortOrder.AscendingOrder)
        
    def add_video_to_list(self, video_path: str):
        video_path = str(Path(video_path).resolve())

        file_path = Path(video_path)

        display_name = file_path.stem

        if display_name in self.folder_data:
            return

        self.folder_data[display_name] = {
            "type": "video",
            "path": video_path
        }

        self.model_available.appendRow(QStandardItem(display_name))
        self.model_available.sort(0, Qt.SortOrder.AscendingOrder)
        
    def on_browse_output(self):
        """Browse for output directory"""
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.ui.lineEdit_output.setText(path)

    def on_remove_selected_folders(self):
        """Remove selected folders from the list"""
        selected = self.ui.listView_available.selectionModel().selectedIndexes()
        if not selected:
            return

        rows_to_remove = set()
        for proxy_idx in selected:
            src_idx = self.proxyScan.mapToSource(proxy_idx)
            rows_to_remove.add(src_idx.row())
            display_name = self.model_available.item(src_idx.row()).text()
            if display_name in self.folder_data:
                del self.folder_data[display_name]

        for row in sorted(rows_to_remove, reverse=True):
            self.model_available.removeRow(row)

    def on_clear_all_folders(self):
        """Clear all folders from the list"""
        self.model_available.clear()
        self.folder_data.clear()

    def on_convert_all_folders(self):
        """Convert all folders to MP4 using folder_to_mp4 method"""
        if self.model_available.rowCount() == 0:
            QMessageBox.information(self, "Info", "No folders to convert.")
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
            display_name = self.model_available.item(i).text()
            media_info = self.folder_data.get(display_name)
            if not media_info:
                failed.append(f"{display_name} (data not found)")
                continue

            media_type = media_info["type"]
            source_path = media_info["path"]
            
            if not source_path:
                failed.append(f"{display_name} (data not found)")
                continue
            
            if not Path(source_path).exists():
                failed.append(f"{display_name} (folder not found)")
                continue

            try:
                # Output file using display name
                output_file = str(output_path / f"{display_name}.mp4")
                
                print(f"\n{'='*60}")
                print(f"Converting: {display_name}")
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
                    failed.append(f"{display_name} (conversion failed)")
                
            except Exception as e:
                import traceback
                failed.append(f"{display_name} -> {e}")
                print(f"Error details: {traceback.format_exc()}")

        if failed:
            msg = "Some conversions failed:\n\n" + "\n".join(failed)
            QMessageBox.warning(self, "Completed with errors", msg)
        else:
            QMessageBox.information(self, "Success", "All folders converted successfully.")