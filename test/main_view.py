from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox


class MainView(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeroxe")
        self.resize(800, 600)

        # Build the menu bar
        self._create_menu_bar()

    def _create_menu_bar(self):
        # 1. Access the built-in menu bar
        menu_bar = self.menuBar()

        # ==================== FILE MENU ====================
        # The '&' creates keyboard accelerators (Alt + F opens File)
        file_menu = menu_bar.addMenu("&File")

        # Create actions (items inside the menu)
        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)  # Ctrl+N
        new_action.setStatusTip("Create a new project")
        new_action.triggered.connect(self.on_new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O
        open_action.triggered.connect(self.on_open_project)
        file_menu.addAction(open_action)

        file_menu.addSeparator()  # Visual dividing line

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ==================== VIEW MENU ====================
        view_menu = menu_bar.addMenu("&View")

        toggle_console_action = QAction("Show &Terminal Log", self)
        toggle_console_action.setCheckable(
            True
        )  # Can be toggled on/off with a checkmark
        toggle_console_action.setChecked(True)
        toggle_console_action.triggered.connect(self.on_toggle_console)
        view_menu.addAction(toggle_console_action)

        # ==================== HELP MENU ====================
        help_menu = menu_bar.addMenu("&Help")

        check_updates_action = QAction("Check for &Updates...", self)
        check_updates_action.triggered.connect(self.on_check_updates)
        help_menu.addAction(check_updates_action)

        about_action = QAction("&About Zeroxe", self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)

    # Slot Handlers
    def on_new_project(self):
        print("New project triggered")

    def on_open_project(self):
        print("Open project triggered")

    def on_toggle_console(self, checked: bool):
        print(f"Console visible: {checked}")

    def on_check_updates(self):
        # Connect to your updater service here
        QMessageBox.information(
            self, "Updater", "Checking for updates via API..."
        )

    def on_about(self):
        QMessageBox.about(
            self,
            "About Zeroxe",
            "<b>Zeroxe App</b><br>Version 1.0.0<br>Built with PySide6.",
        )


import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Absolute package import using the zeroxe namespace
from zeroxe import config


def run():
    # 1. Initialize Qt Application
    app = QApplication(sys.argv)

    # 2. Attach metadata from config (used by OS taskbars, settings storage)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORGANIZATION_NAME)
    app.setOrganizationDomain(config.ORGANIZATION_DOMAIN)

    # 3. Mount primary window
    main_window = MainView()
    main_window.show()

    # 4. Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
