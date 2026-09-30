"""Launcher View Component.

Pure PySide6 presentation widget for the project launcher.
Configures Qt models and delegates all data handling to LauncherController.
"""

from typing import Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHeaderView,
    QWidget,
)

from zeroxe.controllers.launcher_controller import LauncherController
from zeroxe.ui.ui_launcher import Ui_Form


class LauncherView(QWidget):
    """Main Launcher UI container widget."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self._init_models()
        self._setup_ui_elements()

        # Attach controller to handle all signal wiring and service data flow
        self.controller = LauncherController(self)

    # ------------------------------------------------------------------
    # 1. Models Setup
    # ------------------------------------------------------------------
    def _init_models(self) -> None:
        """Initialize Qt item models and search proxy."""
        # Projects Model
        self.project_model = QStandardItemModel(self)
        self.ui.listView_project.setModel(self.project_model)

        # Departments Model
        self.department_model = QStandardItemModel(self)
        self.ui.listView_department.setModel(self.department_model)

        # Asset/Shot Model + Search Filter Proxy
        self.item_source_model = QStandardItemModel(self)
        self.item_proxy_model = QSortFilterProxyModel(self)
        self.item_proxy_model.setSourceModel(self.item_source_model)
        self.item_proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.ui.listView_assetList.setModel(self.item_proxy_model)

        # Versions Model
        self.version_model = QStandardItemModel(self)
        self.ui.listView_version.setModel(self.version_model)

        # Metadata Table Model (Key / Value)
        self.metadata_model = QStandardItemModel(self)
        self.metadata_model.setHorizontalHeaderLabels(["Property", "Value"])
        self.ui.tableView_metadata.setModel(self.metadata_model)

    # ------------------------------------------------------------------
    # 2. UI Configuration
    # ------------------------------------------------------------------
    def _setup_ui_elements(self) -> None:
        """Configure UI widget attributes and visual constraints."""
        # Make Type buttons exclusive (Shot vs Asset)
        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.ui.pushButton_shot, 1)
        self.type_group.addButton(self.ui.pushButton_asset, 2)
        self.type_group.setExclusive(True)
        self.ui.pushButton_shot.setChecked(True)

        # Configure Table header
        header = self.ui.tableView_metadata.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Read-only list views
        for lv in [
            self.ui.listView_project,
            self.ui.listView_department,
            self.ui.listView_assetList,
            self.ui.listView_version,
            self.ui.tableView_metadata,
        ]:
            lv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Search placeholder
        self.ui.lineEdit_searchAsset.setPlaceholderText("Search item...")
