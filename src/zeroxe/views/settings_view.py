from typing import Any, Dict, Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHeaderView,
    QMessageBox,
    QWidget,
    QStackedWidget,
)

from zeroxe.services.launcher_service import LauncherService
from zeroxe.ui.ui_settings import Ui_Form
from zeroxe.ui.ui_kitsu_setting import Ui_Form as KitsuSettingUi
from zeroxe.ui.ui_software_setting import Ui_Form as SoftwareSettingUi
from zeroxe.controllers.setting_controller import SettingController


class SettingsView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.ui.listWidget_menu.addItem("Kitsu")
        self.ui.listWidget_menu.addItem("Software")

        self.kitsu_widget = QWidget()
        self.kitsu_ui = KitsuSettingUi()
        self.kitsu_ui.setupUi(self.kitsu_widget)

        self.software_widget = QWidget()
        self.software_ui = SoftwareSettingUi()
        self.software_ui.setupUi(self.software_widget)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.kitsu_widget)  # Index 0
        self.stack.addWidget(self.software_widget)  # Index 1

        self.ui.verticalLayout.addWidget(self.stack)

        self.ui.listWidget_menu.currentRowChanged.connect(
            self.stack.setCurrentIndex
        )
        self.ui.listWidget_menu.setCurrentRow(0)

        self.ui.pushButton_exit.clicked.connect(self.close)

        self.controller = SettingController(self)