"""Launcher View Component.

Connects the compiled Qt UI (Ui_Form) to the LauncherService mock data.
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHeaderView,
    QMessageBox,
    QWidget,
)

from zeroxe.services.launcher_service import LauncherService
from zeroxe.ui.ui_launcher import Ui_Form


class LauncherView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.service = LauncherService

        # Current selection state cache
        self.current_project: Optional[Dict[str, Any]] = None
        self.current_department: str = ""
        self.current_item: Optional[Dict[str, Any]] = None
        self.current_version: str = ""

        self._init_models()
        self._setup_ui_elements()
        self._setup_signals()
        self._load_initial_data()

    # ------------------------------------------------------------------
    # 1. Models Setup
    # ------------------------------------------------------------------
    def _init_models(self):
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
    def _setup_ui_elements(self):
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

    # ------------------------------------------------------------------
    # 3. Signal & Slot Connections
    # ------------------------------------------------------------------
    def _setup_signals(self):
        # Instant search filter
        self.ui.lineEdit_searchAsset.textChanged.connect(
            self.item_proxy_model.setFilterFixedString
        )

        # Type buttons toggle (Shot vs Asset)
        self.type_group.buttonClicked.connect(self._on_type_toggled)

        # Category filter change (Episode / Asset Type)
        self.ui.comboBox_category.currentTextChanged.connect(self._on_category_changed)

        # Selection changed signals
        self.ui.listView_project.selectionModel().currentChanged.connect(self._on_project_selected)
        self.ui.listView_department.selectionModel().currentChanged.connect(self._on_dept_selected)
        self.ui.listView_assetList.selectionModel().currentChanged.connect(self._on_item_selected)
        self.ui.listView_version.selectionModel().currentChanged.connect(self._on_version_selected)

        # Action buttons
        self.ui.pushButton.clicked.connect(self._on_execute_clicked)
        self.ui.pushButton_open.clicked.connect(self._on_open_clicked)
        self.ui.pushButton_unlock.clicked.connect(self._on_unlock_clicked)

    # ------------------------------------------------------------------
    # 4. Data Loading Logic
    # ------------------------------------------------------------------
    def _load_initial_data(self):
        # 1. Populate Feature/Action ComboBox
        self.ui.comboBox.clear()
        self.ui.comboBox.addItems(self.service.get_applications())

        # 2. Populate Categories (Shot by default)
        self._load_categories("Shot")

        # 3. Populate Projects
        self.project_model.clear()
        projects = self.service.get_projects()
        for p in projects:
            item = QStandardItem(p["name"])
            item.setData(p, Qt.ItemDataRole.UserRole)
            self.project_model.appendRow(item)

        # Select first project by default if exists
        if self.project_model.rowCount() > 0:
            first_idx = self.project_model.index(0, 0)
            self.ui.listView_project.setCurrentIndex(first_idx)

    def _load_categories(self, item_type: str):
        """Populate category dropdown with episodes for Shots, or asset types for Assets."""
        self.ui.comboBox_category.blockSignals(True)
        self.ui.comboBox_category.clear()
        categories = self.service.get_categories(item_type)
        self.ui.comboBox_category.addItems(categories)
        self.ui.comboBox_category.blockSignals(False)

    def _load_departments(self, project_id: str):
        self.department_model.clear()
        depts = self.service.get_departments(project_id)
        for d in depts:
            item = QStandardItem(d)
            self.department_model.appendRow(item)

        if self.department_model.rowCount() > 0:
            first_idx = self.department_model.index(0, 0)
            self.ui.listView_department.setCurrentIndex(first_idx)

    def _load_items(self):
        if not self.current_project:
            return

        item_type = "Shot" if self.ui.pushButton_shot.isChecked() else "Asset"
        category = self.ui.comboBox_category.currentText() or "All"

        self.item_source_model.clear()

        items = self.service.get_items(self.current_project["id"], item_type, category=category)
        for it in items:
            item = QStandardItem(it["name"])
            item.setData(it, Qt.ItemDataRole.UserRole)
            self.item_source_model.appendRow(item)

        if self.item_proxy_model.rowCount() > 0:
            first_proxy_idx = self.item_proxy_model.index(0, 0)
            self.ui.listView_assetList.setCurrentIndex(first_proxy_idx)
        else:
            self._clear_item_details()

    def _load_versions(self, item_id: str):
        self.version_model.clear()
        versions = self.service.get_versions(item_id)
        for v in versions:
            item = QStandardItem(v)
            self.version_model.appendRow(item)

        if self.version_model.rowCount() > 0:
            first_idx = self.version_model.index(0, 0)
            self.ui.listView_version.setCurrentIndex(first_idx)

    def _update_metadata_table(self):
        if not self.current_item:
            self.metadata_model.removeRows(0, self.metadata_model.rowCount())
            return

        metadata = self.service.get_metadata(
            item_data=self.current_item,
            version=self.current_version,
            dept=self.current_department,
        )

        self.metadata_model.removeRows(0, self.metadata_model.rowCount())
        for k, v in metadata.items():
            k_item = QStandardItem(str(k))
            v_item = QStandardItem(str(v))
            self.metadata_model.appendRow([k_item, v_item])

    def _clear_item_details(self):
        self.current_item = None
        self.current_version = ""
        self.version_model.clear()
        self.metadata_model.removeRows(0, self.metadata_model.rowCount())
        self.ui.label_title.setText("No item selected")
        self.ui.label_version.setText("No version")

    # ------------------------------------------------------------------
    # 5. Event Handlers
    # ------------------------------------------------------------------
    def _on_project_selected(self, current, previous):
        if not current.isValid():
            return
        self.current_project = current.data(Qt.ItemDataRole.UserRole)
        self.ui.label_project.setText(f"Project: {self.current_project['name']}")
        self._load_departments(self.current_project["id"])
        self._load_items()

    def _on_dept_selected(self, current, previous):
        if not current.isValid():
            return
        self.current_department = current.data(Qt.ItemDataRole.DisplayRole)
        self.ui.label_department.setText(f"Department: {self.current_department}")
        self._update_metadata_table()

    def _on_type_toggled(self, button):
        item_type = "Shot" if self.ui.pushButton_shot.isChecked() else "Asset"
        self._load_categories(item_type)
        self._load_items()

    def _on_category_changed(self, category_text: str):
        self._load_items()

    def _on_item_selected(self, current, previous):
        if not current.isValid():
            return
        source_idx = self.item_proxy_model.mapToSource(current)
        self.current_item = source_idx.data(Qt.ItemDataRole.UserRole)

        self.ui.label_title.setText(f"<b>{self.current_item['name']}</b>")
        self._load_versions(self.current_item["id"])

    def _on_version_selected(self, current, previous):
        if not current.isValid():
            return
        self.current_version = current.data(Qt.ItemDataRole.DisplayRole)
        self.ui.label_version.setText(f"Version: <b>{self.current_version}</b>")
        self._update_metadata_table()

    def _on_execute_clicked(self):
        feature = self.ui.comboBox.currentText()
        item_name = self.current_item["name"] if self.current_item else "None"
        msg = self.service.execute_action(feature, item_name, self.current_version)
        QMessageBox.information(self, "Execute Feature", msg)

    def _on_open_clicked(self):
        if self.current_item:
            QMessageBox.information(
                self, "Open Path", f"Opening file browser for: {self.current_item['name']}"
            )

    def _on_unlock_clicked(self):
        QMessageBox.information(self, "Unlock", "File / task locks released.")
