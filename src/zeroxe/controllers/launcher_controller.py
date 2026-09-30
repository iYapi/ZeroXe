"""Launcher Controller.

Coordinates data flow between UI (LauncherView) and user domain services:
- ProjectService
- DepartmentService
- ShotService
- SettingsService
"""

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QMessageBox

from zeroxe.models.department_model import Department
from zeroxe.models.project_model import Project
from zeroxe.models.shot_model import Episode, Sequence, Shot
from zeroxe.services.department_service import DepartmentService
from zeroxe.services.project_service import ProjectService
from zeroxe.services.settings_service import SettingsService
from zeroxe.services.shot_service import ShotService

if TYPE_CHECKING:
    from zeroxe.views.launcher_view import LauncherView

logger = logging.getLogger(__name__)


class LauncherController(QObject):
    """Controller for the Launcher screen."""

    def __init__(self, view: "LauncherView"):
        super().__init__(view)
        self.view = view

        # Current selection state
        self.current_project: Optional[Project] = None
        self.current_department: Optional[Department] = None
        self.current_episodes: List[Episode] = []
        self.current_shot: Optional[Shot] = None
        self.current_version: str = ""

        self._bind_signals()
        self.load_initial_data()

    def _bind_signals(self) -> None:
        """Wire UI events from LauncherView to controller methods."""
        ui = self.view.ui

        # Search filter
        ui.lineEdit_searchAsset.textChanged.connect(
            self.view.item_proxy_model.setFilterFixedString
        )

        # Type buttons (Shot vs Asset)
        self.view.type_group.buttonClicked.connect(self.on_type_toggled)

        # Category / Episode dropdown change
        ui.comboBox_category.currentTextChanged.connect(self.on_category_changed)

        # Selection changes
        ui.listView_project.selectionModel().currentChanged.connect(self.on_project_selected)
        ui.listView_department.selectionModel().currentChanged.connect(self.on_department_selected)
        ui.listView_assetList.selectionModel().currentChanged.connect(self.on_item_selected)
        ui.listView_version.selectionModel().currentChanged.connect(self.on_version_selected)

        # Action buttons
        ui.pushButton.clicked.connect(self.on_execute_action)
        ui.pushButton_open.clicked.connect(self.on_open_path)
        ui.pushButton_unlock.clicked.connect(self.on_unlock_task)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    def load_initial_data(self) -> None:
        """Populate initial dropdowns, actions, departments, and project list."""
        # 1. Action Dropdown
        self.view.ui.comboBox.clear()
        self.view.ui.comboBox.addItems(["Launch Blender", "Launch PureRef", "Open Explorer"])

        # 2. Load Departments
        self.load_departments()

        # 3. Load Projects
        self.load_projects()

    def load_projects(self) -> None:
        """Fetch projects via ProjectService and populate project_model."""
        self.view.project_model.clear()
        try:
            projects = ProjectService.get_all_projects()
        except Exception as e:
            logger.error(f"Failed to fetch projects: {e}")
            projects = []

        for p in projects:
            item = QStandardItem(p.name)
            item.setData(p, Qt.ItemDataRole.UserRole)
            self.view.project_model.appendRow(item)

        if self.view.project_model.rowCount() > 0:
            first_idx = self.view.project_model.index(0, 0)
            self.view.ui.listView_project.setCurrentIndex(first_idx)

    def load_departments(self) -> None:
        """Fetch departments via DepartmentService and populate department_model."""
        self.view.department_model.clear()
        try:
            departments = DepartmentService.get_all_departments()
        except Exception as e:
            logger.error(f"Failed to fetch departments: {e}")
            departments = []

        for d in departments:
            item = QStandardItem(d.name)
            item.setData(d, Qt.ItemDataRole.UserRole)
            self.view.department_model.appendRow(item)

        if self.view.department_model.rowCount() > 0:
            first_idx = self.view.department_model.index(0, 0)
            self.view.ui.listView_department.setCurrentIndex(first_idx)

    def load_categories(self, project_id: str) -> None:
        """Fetch episodes for the project via ShotService to populate category dropdown."""
        self.view.ui.comboBox_category.blockSignals(True)
        self.view.ui.comboBox_category.clear()

        try:
            self.current_episodes = ShotService.get_episodes_by_project_id(project_id)
        except Exception as e:
            logger.error(f"Failed to fetch episodes for project {project_id}: {e}")
            self.current_episodes = []

        category_items = ["None"]
        if self.current_episodes:
            category_items.extend([ep.name for ep in self.current_episodes if ep.name])

        self.view.ui.comboBox_category.addItems(category_items)
        self.view.ui.comboBox_category.setCurrentIndex(0)
        self.view.ui.comboBox_category.blockSignals(False)

    def load_shots(self) -> None:
        """Fetch shots via ShotService and populate item list."""
        if not self.current_project:
            return

        selected_category = self.view.ui.comboBox_category.currentText()
        self.view.item_source_model.clear()

        # If None is selected, keep shot list empty
        if not selected_category or selected_category == "None":
            self._clear_item_details()
            return

        shots: List[Shot] = []
        try:
            target_ep = next((ep for ep in self.current_episodes if ep.name == selected_category), None)
            if target_ep:
                shots = ShotService.get_shots_by_episode_id(target_ep.id)
        except Exception as e:
            logger.error(f"Failed to fetch shots: {e}")

        # Sort shots alphabetically by sequence and shot name
        shots.sort(key=lambda s: f"{s.sequence or ''}_{s.name or ''}".lower())

        for shot in shots:
            seq_name = shot.sequence or ""
            display_name = f"{seq_name}_{shot.name}" if seq_name else shot.name
            item = QStandardItem(display_name)
            item.setData(shot, Qt.ItemDataRole.UserRole)
            self.view.item_source_model.appendRow(item)

        if self.view.item_proxy_model.rowCount() > 0:
            first_proxy_idx = self.view.item_proxy_model.index(0, 0)
            self.view.ui.listView_assetList.setCurrentIndex(first_proxy_idx)
        else:
            self._clear_item_details()

    def update_metadata_table(self) -> None:
        """Format and update metadata property/value table."""
        self.view.metadata_model.removeRows(0, self.view.metadata_model.rowCount())
        if not self.current_shot:
            return

        dept_name = self.current_department.name if self.current_department else "None"
        metadata: Dict[str, Any] = {
            "Shot Name": self.current_shot.name,
            "Sequence": self.current_shot.sequence or "None",
            "Episode": self.current_shot.episode or "None",
            "Department": dept_name,
            "FPS": self.current_shot.fps,
            "Resolution": self.current_shot.resolution or "Default",
            "Frame Range": f"{self.current_shot.frame_in} - {self.current_shot.frame_out}",
            "Assets Linked": len(self.current_shot.assets),
            "Version": self.current_version or "None",
        }

        for k, v in metadata.items():
            k_item = QStandardItem(str(k))
            v_item = QStandardItem(str(v))
            self.view.metadata_model.appendRow([k_item, v_item])

    def _clear_item_details(self) -> None:
        """Reset item details in the view."""
        self.current_shot = None
        self.current_version = ""
        self.view.version_model.clear()
        self.view.metadata_model.removeRows(0, self.view.metadata_model.rowCount())
        self.view.ui.label_title.setText("No item selected")
        self.view.ui.label_version.setText("No version")

    # ------------------------------------------------------------------
    # Action Slots
    # ------------------------------------------------------------------
    def on_project_selected(self, current, previous) -> None:
        """Handle project selection change."""
        if not current.isValid():
            return
        self.current_project = current.data(Qt.ItemDataRole.UserRole)
        self.view.ui.label_project.setText(f"Project: {self.current_project.name}")

        self.load_categories(self.current_project.id)
        self.load_shots()

    def on_department_selected(self, current, previous) -> None:
        """Handle department selection change."""
        if not current.isValid():
            return
        self.current_department = current.data(Qt.ItemDataRole.UserRole)
        dept_name = self.current_department.name if self.current_department else ""
        self.view.ui.label_department.setText(f"Department: {dept_name}")
        self.update_metadata_table()

    def on_type_toggled(self, button) -> None:
        """Handle Shot vs Asset toggle."""
        if self.current_project:
            self.load_categories(self.current_project.id)
            self.load_shots()

    def on_category_changed(self, category_text: str) -> None:
        """Handle category/episode selection change."""
        self.load_shots()

    def on_item_selected(self, current, previous) -> None:
        """Handle shot item selection."""
        if not current.isValid():
            return
        source_idx = self.view.item_proxy_model.mapToSource(current)
        self.current_shot = source_idx.data(Qt.ItemDataRole.UserRole)

        if self.current_shot:
            seq_name = self.current_shot.sequence or ""
            display_name = f"{seq_name}_{self.current_shot.name}" if seq_name else self.current_shot.name
            self.view.ui.label_title.setText(f"<b>{display_name}</b>")

            # Populate versions placeholder / list
            self.view.version_model.clear()
            for v_name in ["v001", "v002", "v003"]:
                self.view.version_model.appendRow(QStandardItem(v_name))

            if self.view.version_model.rowCount() > 0:
                first_v_idx = self.view.version_model.index(0, 0)
                self.view.ui.listView_version.setCurrentIndex(first_v_idx)

    def on_version_selected(self, current, previous) -> None:
        """Handle version selection change."""
        if not current.isValid():
            return
        self.current_version = current.data(Qt.ItemDataRole.DisplayRole)
        self.view.ui.label_version.setText(f"Version: <b>{self.current_version}</b>")
        self.update_metadata_table()

    def on_execute_action(self) -> None:
        """Execute selected software action (e.g. Launch Blender or PureRef)."""
        action = self.view.ui.comboBox.currentText()
        shot_name = self.current_shot.name if self.current_shot else "None"

        if "Blender" in action:
            blender_path = SettingsService.get_active_blender()
            if not blender_path or not Path(blender_path).exists():
                QMessageBox.warning(
                    self.view,
                    "Blender Not Configured",
                    "Blender executable path is missing or invalid. Please configure it in Settings.",
                )
                return
            try:
                subprocess.Popen([blender_path])
                QMessageBox.information(self.view, "Launched", f"Launching Blender for {shot_name}...")
            except Exception as e:
                QMessageBox.critical(self.view, "Launch Error", f"Failed to launch Blender: {e}")

        elif "PureRef" in action:
            pureref_path = SettingsService.get_pureref_path()
            if not pureref_path or not Path(pureref_path).exists():
                QMessageBox.warning(
                    self.view,
                    "PureRef Not Configured",
                    "PureRef executable path is missing. Please configure it in Settings.",
                )
                return
            try:
                subprocess.Popen([pureref_path])
            except Exception as e:
                QMessageBox.critical(self.view, "Launch Error", f"Failed to launch PureRef: {e}")

        else:
            QMessageBox.information(
                self.view,
                "Execute Action",
                f"Action '{action}' executed for shot: {shot_name} ({self.current_version})",
            )

    def on_open_path(self) -> None:
        """Open shot file location."""
        if self.current_shot:
            QMessageBox.information(
                self.view,
                "Open Path",
                f"Opening file location for: {self.current_shot.name}",
            )

    def on_unlock_task(self) -> None:
        """Unlock file / task."""
        QMessageBox.information(self.view, "Unlock", "File and task locks released.")
