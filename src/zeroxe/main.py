import sys
from zeroxe import config

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from zeroxe.views.main_view import MainView


def run():
    app = QApplication(sys.argv)

    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORGANIZATION_NAME)
    app.setOrganizationDomain(config.ORGANIZATION_DOMAIN)

    window = MainView()
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    run()