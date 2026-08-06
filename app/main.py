import os
import sys
import requests
from io import BytesIO
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtWidgets import QApplication, QMainWindow, QTreeWidgetItem, QListWidgetItem

from app.config import Settings
from app.modules.startup.handle_login import LoginHandler
from app.utils.auth import AuthServices
from app.ui.main.main_window_ui import Ui_MainWindow as MainWindowUI
from app.core.app_states import AppState

from app.modules.blender.b_launcher.handle_b_launcher import HandleBLauncher
from app.modules.test.setup.setup_department import HandleSetupDepartment
from app.modules.test.b_launcher.handle_b_launcher import HandleBLauncherPreview
from app.modules.ffmpeg.handle_ffmpeg_mp4 import HandleFFMPEGMP4
from app.modules.collector.cl_playblast.handle_cl_playblast import HandleClPlayblast

class MainUI(QMainWindow):
    def __init__(self):
        super().__init__()

        # Instantiate and set up UI
        self.ui = MainWindowUI()
        self.ui.setupUi(self)
        self.setWindowTitle(f"{Settings.APP_NAME} - {Settings.BUILD_VERSION}")

        if self.load_saved_login():
            self.load_ui()
        else:
            if self.prelaunch():
                self.load_ui()
                self.show()
            else:
                self.close()

    @staticmethod
    def prelaunch():
        # Show login window first
        login_handler = LoginHandler()

        if login_handler.exec():  # Wait for login to complete
            return True
        return False

    def load_ui(self):
        # Load main UI components
        self.ui.label_programName.setText(Settings.APP_NAME)
        self.ui.pushButton_logOut.clicked.connect(self.handle_logout)
        self.ui.label_buildVersion.setText(f"Build: {Settings.BUILD_VERSION}")
        self.ui.label_username.setText(AppState().user_data["user"]["full_name"] or AppState().user_data["user"]["email"])
        if AppState().user_data["user"]["has_avatar"] and os.path.exists(Settings.AVATAR_FILE):
            self.load_avatar_image(f"{Settings.AVATAR_FILE}")

        # Set up tabs
        self.ui.tabWidget.clear()
        # self.ui.tabWidget.addTab(HandleBLauncher(), "BLauncher")
        self.ui.tabWidget.addTab(HandleBLauncherPreview(), "BLauncher(preview)")
        self.ui.tabWidget.addTab(HandleFFMPEGMP4(), "ffmpegMP4")
        self.ui.tabWidget.addTab(HandleClPlayblast(), "ClPlayblast")
        self.ui.tabWidget.addTab(HandleSetupDepartment(), "Setup(preview)")
        self.ui.radioButton_printLog.toggled.connect(
            lambda checked: self.print_log(checked)
        )

# PyQt Program =====================================================================================
    def handle_logout(self):
        print("[!] Logging out...")
        AuthServices.api_req_logout()
        if self.prelaunch():
            self.load_ui()
            self.show()
        else:
            self.close()

    def load_avatar_image(self, file_path):
        # Load image directly from local file path
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():  # Check if image loaded successfully
            scaled_pixmap = pixmap.scaled(25, 25, Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            self.ui.label_userimage.setPixmap(scaled_pixmap)
            self.ui.label_userimage.setFixedSize(25, 25)
            self.ui.label_userimage.setScaledContents(True)
        else:
            print(f"[-] Failed to load avatar image from: {file_path}")

    @staticmethod
    def print_log(checked):
        Settings.print_log = checked

    @staticmethod
    def load_saved_login():
        login_data = Settings().read_user_data()
        if login_data:
            print("[*] Found saved login data, attempting auto-login...")
            try:
                response = AuthServices.authenticate_user(login_data["email"], login_data["password"])
                if response.get('success'):
                    # Set user data in AppState
                    user_data = response.get("user", {})
                    AppState().set_access_token(user_data.get("access_token"))
                    AppState().set_user_data(user_data)
                    print("[+] Auto-login successful")
                    return True
                else:
                    print(f"[-] Auto-login failed: {response.get('message', 'Unknown error')}")
            except Exception as e:
                print(f"[-] Auto-login failed: {e}")
        else:
            print("[*] No saved login data found.")
        return False

if __name__== "__main__":
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.show()
    app.exec()