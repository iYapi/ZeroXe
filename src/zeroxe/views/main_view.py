import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSpacerItem, QSizePolicy, QDialog, QVBoxLayout, QLabel, \
    QDialogButtonBox, QWidget, QProgressBar, QPushButton
from zeroxe import config
from zeroxe.api.update_api import UpdateAPI

class UpdateWorker(QThread):
    status_updated = Signal(str)
    update_available = Signal(dict)
    download_progress = Signal(int)
    download_finished = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, task="check", update_info=None, target_path=None):
        super().__init__()
        self.task = task
        self.update_info = update_info
        self.target_path = target_path

    def run(self):
        try:
            if self.task == "check":
                self.status_updated.emit("Checking for updates...")
                has_update, info = UpdateAPI.check_for_updates()
                if has_update:
                    self.update_available.emit(info)
                else:
                    self.status_updated.emit("App is up to date.")

            elif self.task == "download":
                self.status_updated.emit("Downloading new version...")
                url = self.update_info["download_url"]
                UpdateAPI.download_update(
                    url, self.target_path,
                    progress_callback=self.download_progress.emit
                )
                self.download_finished.emit(self.target_path)

        except Exception as e:
            self.error_occurred.emit(str(e))

class MainView(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(800, 600)

        self.latest_update_info = None

        self._create_menu_bar()

    def _create_menu_bar(self):
        menubar = self.menuBar()
        help_menu = menubar.addMenu('&Help')
        check_update_action = QAction('&Check for update', self)
        check_update_action.triggered.connect(self.on_check_update)
        help_menu.addAction(check_update_action)

        about_action = QAction('&About', self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)

    def on_check_update(self):
        self.update_window = QWidget(self, Qt.WindowType.Window)
        self.update_window.setWindowTitle(f"Update {config.APP_NAME}")
        self.update_window.resize(400, 300)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        layout = QVBoxLayout(self.update_window)

        label = QLabel(
            f'<b>{config.APP_NAME}</b><br>'
            f'Version {config.APP_VERSION}<br>'
            f'Change log: {(self.latest_update_info or {}).get("release_notes", "")}<br>'
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        self.update_button = QPushButton("Check for Updates")
        self.update_button.clicked.connect(self._on_check_update)
        layout.addWidget(self.update_button)

        layout.addWidget(self.progress_bar)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.update_window.close)
        layout.addWidget(button_box)

        self.update_window.show()

    def on_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('About Zeroxe')
        dialog.setFixedSize(400, 200)

        layout = QVBoxLayout(dialog)

        label = QLabel(
            f'<b>{config.APP_NAME}</b><br>'
            f'Version {config.APP_VERSION}<br>'
            f'Maintained by <a href="{config.MAINTAINER_WEB}">{config.MAINTAINER}</a>'
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        button_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_close.rejected.connect(dialog.close)
        layout.addWidget(button_close)

        dialog.exec()

#region Update Helper
    def _on_check_update(self):
        if self.latest_update_info is None:
            self.update_button.setEnabled(False)
            self.worker = UpdateWorker(task="check")
            self.worker.status_updated.connect(self.status_label.setText)
            self.worker.update_available.connect(self._on_update_found)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.start()
        else:
            self.update_button.setEnabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)

            temp_target = os.path.abspath('update.bin')
            self.worker = UpdateWorker(
                task="download",
                update_info=self.latest_update_info,
                target_path=temp_target
            )
            self.worker.status_updated.connect(self.status_label.setText)
            self.worker.download_progress.connect(self.progress_bar.setValue)
            self.worker.download_finished.connect(self._on_download_finished)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.start()

    def _on_update_found(self, info):
        self.latest_update_info = info
        self.status_label.setText(f"Update available: <b>v{info.get('version')}</b>")
        self.update_button.setText("Download & Install")
        self.update_button.setEnabled(True)

    def _on_download_finished(self, file_path):
        expected_hash = self.latest_update_info.get("sha256")
        if expected_hash and not UpdateAPI.verify_integrity(file_path, expected_hash):
            self._on_error("SHA256 verification failed!")
            return

        QMessageBox.information(
            self, "Update Ready", "Update downloaded. The application will restart."
        )
        try:
            UpdateAPI.install_and_restart(file_path)
        except Exception as e:
            self._on_error(f"Failed to restart: {e}")

    def _on_error(self, message):
        self.status_label.setText("Error during update.")
        self.update_button.setText("Check for Updates")
        self.update_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Update Error", message)
#endregion