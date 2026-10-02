"""Setting Controller.

Mediates business logic, persistent configuration (QSettings),
and user interactions for SettingsView. Encrypts sensitive credentials locally.
"""

from typing import TYPE_CHECKING, Optional
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from zeroxe import config
from zeroxe.api.gazu_client import init_kitsu
from zeroxe.utils.security import decrypt_string, encrypt_string

if TYPE_CHECKING:
    from zeroxe.views.settings_view import SettingsView


class SettingController(QObject):
    """Controls settings logic and bridges SettingsView with QSettings storage."""

    settings_changed = Signal()


    def __init__(self, view: "SettingsView"):
        super().__init__(view)
        self.view = view
        self.settings = QSettings(config.ORGANIZATION_NAME, config.APP_NAME)

        self._bind_signals()
        self.load_settings()

    def _bind_signals(self) -> None:
        """Connect UI signals to controller action slots."""
        # Main Action Buttons (Ok, Apply, Exit)
        self.view.ui.pushButton_apply.clicked.connect(self.on_apply)
        self.view.ui.pushButton_ok.clicked.connect(self.on_ok)
        self.view.ui.pushButton_exit.clicked.connect(self.view.close)

        # Software Settings - Blender
        sw_ui = self.view.software_ui
        sw_ui.toolButton_locateBlender.clicked.connect(self.on_locate_blender)
        sw_ui.toolButton_addBlender.clicked.connect(self.on_add_blender)
        sw_ui.pushButton_applyBlender.clicked.connect(self.on_set_active_blender)
        sw_ui.listWidget_blenderList.itemClicked.connect(self.on_blender_item_selected)

        # Software Settings - PureRef
        sw_ui.pushButton_locatePureref.clicked.connect(self.on_locate_pureref)

        # NAS Settings
        self.view.nas_ui.toolButton_locateMap.clicked.connect(self.on_locate_zeroxe_map)

        # Kitsu Login
        self.view.kitsu_ui.pushButton_login.clicked.connect(self.on_login_kitsu)

    # ------------------------------------------------------------------
    # Settings Load & Save
    # ------------------------------------------------------------------
    def load_settings(self) -> None:
        """Load settings from QSettings into UI form fields."""
        # 1. Kitsu Configuration
        kitsu_url = self.settings.value("kitsu/url", config.KITSU_API_URL, type=str)
        kitsu_email = self.settings.value("kitsu/email", "", type=str)

        # Load and decrypt password
        encrypted_password = self.settings.value("kitsu/password_enc", "", type=str)
        kitsu_password = decrypt_string(encrypted_password)

        self.view.kitsu_ui.lineEdit_kitsuUrl.setText(kitsu_url)
        self.view.kitsu_ui.lineEdit_email.setText(kitsu_email)
        self.view.kitsu_ui.lineEdit_password.setText(kitsu_password)

        # 2. Software Configuration
        blender_list = self.settings.value("software/blender_paths", [], type=list)
        active_blender = self.settings.value("software/active_blender", "", type=str)
        pureref_path = self.settings.value("software/pureref_path", "", type=str)

        self.view.software_ui.listWidget_blenderList.clear()
        for path in blender_list:
            if path:
                self.view.software_ui.listWidget_blenderList.addItem(str(path))

        self.view.software_ui.lineEdit_selectedBlender.setText(active_blender)
        self.view.software_ui.lineEdit_pureref.setText(pureref_path)

        # 3. NAS Configuration
        zeroxe_map_path = self.settings.value("nas/zeroxe_map_path", "", type=str)
        version_folder = self.settings.value("nas/version_folder", "", type=str)
        self.view.nas_ui.lineEdit_zeroxeMap.setText(zeroxe_map_path)
        self.view.nas_ui.lineEdit_versionFolder.setText(version_folder)

    def save_settings(self) -> None:
        """Persist current UI inputs to QSettings with encrypted password."""
        # 1. Save Kitsu
        kitsu_url = self.view.kitsu_ui.lineEdit_kitsuUrl.text().strip()
        kitsu_email = self.view.kitsu_ui.lineEdit_email.text().strip()
        raw_password = self.view.kitsu_ui.lineEdit_password.text().strip()

        # Encrypt password before saving
        encrypted_password = encrypt_string(raw_password)

        self.settings.setValue("kitsu/url", kitsu_url)
        self.settings.setValue("kitsu/email", kitsu_email)
        self.settings.setValue("kitsu/password_enc", encrypted_password)
        # Ensure any old plaintext password key is wiped
        self.settings.remove("kitsu/password")

        # 2. Save Software Paths
        blender_items = [
            self.view.software_ui.listWidget_blenderList.item(i).text()
            for i in range(self.view.software_ui.listWidget_blenderList.count())
        ]
        active_blender = self.view.software_ui.lineEdit_selectedBlender.text().strip()
        pureref_path = self.view.software_ui.lineEdit_pureref.text().strip()

        self.settings.setValue("software/blender_paths", blender_items)
        self.settings.setValue("software/active_blender", active_blender)
        self.settings.setValue("software/pureref_path", pureref_path)

        # 3. Save NAS Configuration
        zeroxe_map_path = self.view.nas_ui.lineEdit_zeroxeMap.text().strip()
        version_folder = self.view.nas_ui.lineEdit_versionFolder.text().strip()
        self.settings.setValue("nas/zeroxe_map_path", zeroxe_map_path)
        self.settings.setValue("nas/version_folder", version_folder)
        self.settings.sync()

    # ------------------------------------------------------------------
    # Action Handlers
    # ------------------------------------------------------------------
    def on_apply(self) -> None:
        """Apply and persist changes."""
        self.save_settings()
        self.settings_changed.emit()
        QMessageBox.information(self.view, "Settings", "Settings saved successfully.")

    def on_ok(self) -> None:
        """Apply changes and close dialog."""
        self.save_settings()
        self.settings_changed.emit()
        self.view.close()

    def on_login_kitsu(self) -> None:
        """Authenticate with Kitsu using currently entered form values."""
        url = self.view.kitsu_ui.lineEdit_kitsuUrl.text().strip()
        email = self.view.kitsu_ui.lineEdit_email.text().strip()
        password = self.view.kitsu_ui.lineEdit_password.text().strip()

        if not url or not email or not password:
            QMessageBox.warning(
                self.view,
                "Missing Information",
                "Please fill in Kitsu URL, Email, and Password before attempting to log in.",
            )
            return

        login_btn = self.view.kitsu_ui.pushButton_login
        login_btn.setEnabled(False)
        login_btn.setText("Logging in...")
        QApplication.processEvents()

        try:
            success, message = init_kitsu(url=url, email=email, password=password)
            if success:
                # Automatically persist settings upon successful login
                self.save_settings()
                self.settings_changed.emit()
                QMessageBox.information(
                    self.view,
                    "Kitsu Login",
                    f"Successfully connected to Kitsu!\n\nLogged in as: {email}",
                )
            else:
                QMessageBox.critical(
                    self.view,
                    "Kitsu Login Failed",
                    f"Could not log in to Kitsu:\n\n{message}",
                )
        finally:
            login_btn.setEnabled(True)
            login_btn.setText("LogIn")

    def on_locate_blender(self) -> None:
        """Open file dialog to locate Blender executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Locate Blender Executable",
            "",
            "Executables (*);;All Files (*)",
        )
        if file_path:
            self.view.software_ui.lineEdit_kitsuUrl.setText(file_path)

    def on_add_blender(self) -> None:
        """Add entered path into Blender versions list."""
        path = self.view.software_ui.lineEdit_kitsuUrl.text().strip()
        if not path:
            return

        list_widget = self.view.software_ui.listWidget_blenderList
        existing_items = [list_widget.item(i).text() for i in range(list_widget.count())]

        if path not in existing_items:
            list_widget.addItem(path)
            self.view.software_ui.lineEdit_kitsuUrl.clear()
        else:
            QMessageBox.warning(self.view, "Warning", "This Blender path is already listed.")

    def on_blender_item_selected(self, item) -> None:
        """Update selected blender line edit on item click."""
        self.view.software_ui.lineEdit_selectedBlender.setText(item.text())

    def on_set_active_blender(self) -> None:
        """Confirm active Blender selection."""
        current_item = self.view.software_ui.listWidget_blenderList.currentItem()
        if current_item:
            self.view.software_ui.lineEdit_selectedBlender.setText(current_item.text())

    def on_locate_pureref(self) -> None:
        """Open file dialog to locate PureRef executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Locate PureRef Executable",
            "",
            "Executables (*);;All Files (*)",
        )
        if file_path:
            self.view.software_ui.lineEdit_pureref.setText(file_path)

    def on_locate_zeroxe_map(self) -> None:
        """Open file dialog to locate zeroxe_map.yaml file."""
        current_path = self.view.nas_ui.lineEdit_zeroxeMap.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Locate Zeroxe Map",
            current_path or "",
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if file_path:
            self.view.nas_ui.lineEdit_zeroxeMap.setText(file_path)