import sys
from zeroxe import config
from zeroxe.api.gazu_client import init_kitsu

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from zeroxe.utils.icon_util import get_app_icon
from zeroxe.views.main_view import MainView


def run():
    app = QApplication(sys.argv)

    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORGANIZATION_NAME)
    app.setOrganizationDomain(config.ORGANIZATION_DOMAIN)
    app.setDesktopFileName("zeroxe.desktop")

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    init_kitsu()

    window = MainView()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    run()