"""Launcher Controller.

Coordinates data flow between UI (LauncherView) and user domain services:
- ProjectService
- DepartmentService
- ShotService
- AssetService
- SettingsService
"""

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PySide6.QtCore import QObject, QProcess, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QAbstractItemView, QMessageBox

from zeroxe.models.asset_model import Asset, AssetType
from zeroxe.models.department_model import Department
from zeroxe.models.project_model import Project
from zeroxe.models.shot_model import Episode, Sequence, Shot
from zeroxe.services.asset_service import AssetService
from zeroxe.services.department_service import DepartmentService
from zeroxe.services.lock_service import LockService
from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.project_service import ProjectService
from zeroxe.services.settings_service import SettingsService
from zeroxe.services.shot_service import ShotService
from zeroxe.utils.log_util import extract_error_summary, show_error_dialog

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
        self.current_asset_types: List[AssetType] = []
        self.current_shot: Optional[Shot] = None
        self.current_asset: Optional[Asset] = None
        self.current_version: str = ""
        self.selected_file_path: Optional[str] = None

        # Track active DCC child processes for auto-unlock
        self._active_processes: Dict[str, QProcess] = {}

        self._bind_signals()
        self.load_initial_data()

    @property
    def is_shot_mode(self) -> bool:
        """Check if launcher is currently in Shot mode."""
        return self.view.ui.pushButton_shot.isChecked()

    @property
    def is_asset_mode(self) -> bool:
        """Check if launcher is currently in Asset mode."""
        return self.view.ui.pushButton_asset.isChecked()

    def _bind_signals(self) -> None:
        """Wire UI events from LauncherView to controller methods."""
        ui = self.view.ui

        # Search filter
        ui.lineEdit_searchAsset.textChanged.connect(
            self.view.item_proxy_model.setFilterFixedString
        )

        # Type buttons (Shot vs Asset)
        self.view.type_group.buttonClicked.connect(self.on_type_toggled)

        # Category / Episode / AssetType dropdown change
        ui.comboBox_category.currentTextChanged.connect(self.on_category_changed)

        # Selection changes
        ui.listView_project.selectionModel().currentChanged.connect(self.on_project_selected)
        ui.listView_department.selectionModel().currentChanged.connect(self.on_department_selected)
        ui.listView_assetList.selectionModel().currentChanged.connect(self.on_item_selected)
        ui.listView_version.selectionModel().currentChanged.connect(self.on_version_selected)

        # Action buttons
        exec_btn = getattr(ui, "pushButton_execute", getattr(ui, "pushButton", None))
        if exec_btn:
            exec_btn.clicked.connect(self.on_execute_action)
        ui.pushButton_open.clicked.connect(self.on_open_path)
        ui.pushButton_unlock.clicked.connect(self.on_unlock_task)

        # Multi-select checkbox
        multi_cb = getattr(ui, "checkBox_multiSelect", getattr(ui, "comboBox_multiSelect", None))
        if multi_cb:
            multi_cb.toggled.connect(self.on_multi_select_toggled)

    def on_multi_select_toggled(self, checked: bool) -> None:
        """Toggle single vs extended multi-selection mode on the shot/asset list view."""
        mode = (
            QAbstractItemView.SelectionMode.ExtendedSelection
            if checked
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        self.view.ui.listView_assetList.setSelectionMode(mode)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    def on_settings_updated(self) -> None:
        """Handle live configuration updates from Settings view."""
        PipelineService.clear_cache()
        self.refresh_features()
        if self.current_shot or self.current_asset:
            self.refresh_versions()
        else:
            self.load_initial_data()

    @property
    def feature_combobox(self):
        """Retrieve the action / feature combo box widget."""
        return getattr(self.view.ui, "comboBox_feature", getattr(self.view.ui, "comboBox", None))

    def refresh_features(self) -> None:
        """Dynamically query and populate available pipeline features from pipeline module/config."""
        combo = self.feature_combobox
        if not combo:
            return

        dept_name = self.current_department.name if self.current_department else ""
        proj_name = self.current_project.name if self.current_project else None

        try:
            features = PipelineService.list_features(department=dept_name, project_name=proj_name)
        except Exception as e:
            logger.warning(f"Could not list pipeline features: {e}")
            features = []

        current_choice = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        if features:
            combo.addItems(features)
            if current_choice and current_choice in features:
                combo.setCurrentText(current_choice)
            else:
                combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def load_initial_data(self) -> None:
        """Populate initial dropdowns, actions, departments, and project list."""
        # 1. Pipeline Action / Feature Dropdown (dynamically discovered)
        self.refresh_features()

        # 2. Load Departments
        self.load_departments()

        # 3. Load Projects
        self.load_projects()


    def load_projects(self) -> None:
        """Fetch projects via ProjectService and populate project_model with zeroxe_map.yaml fallback."""
        self.view.project_model.clear()
        try:
            projects = ProjectService.get_all_projects()
        except Exception as e:
            logger.error(f"Failed to fetch projects: {e}")
            projects = []

        # Fallback to projects configured in zeroxe_map.yaml if Kitsu is offline or empty
        if not projects:
            zeroxe_map = SettingsService.get_zeroxe_map() or {}
            map_projects = zeroxe_map.get("project", {})
            for p_key, p_info in map_projects.items():
                if isinstance(p_info, dict):
                    p_name = p_info.get("name") or p_key
                    p_code = p_info.get("code") or ""
                    p_id = p_info.get("kitsu_id") or ""
                    projects.append(Project(id=p_id, name=p_name, code=p_code))

        for p in projects:
            item = QStandardItem(p.name)
            item.setData(p, Qt.ItemDataRole.UserRole)
            self.view.project_model.appendRow(item)

        if self.view.project_model.rowCount() > 0:
            first_idx = self.view.project_model.index(0, 0)
            self.view.ui.listView_project.setCurrentIndex(first_idx)
        else:
            self.current_project = None
            self.view.ui.label_project.setText("Project: None")
            self.load_categories("")
            self._clear_item_details()

    def load_departments(self) -> None:
        """Fetch departments via DepartmentService and populate department_model with pipeline.yaml fallback."""
        self.view.department_model.clear()
        try:
            departments = DepartmentService.get_all_departments()
        except Exception as e:
            logger.error(f"Failed to fetch departments: {e}")
            departments = []

        # Fallback to departments configured in pipeline.yaml if Kitsu is offline or empty
        if not departments:
            import yaml

            pipe_yaml = PipelineService.get_active_pipeline_yaml_path(project_name=None)
            if pipe_yaml and pipe_yaml.is_file():
                try:
                    with open(pipe_yaml, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                    dept_map = cfg.get("departments", {})
                    for d_name, d_info in dept_map.items():
                        if isinstance(d_info, dict):
                            d_code = d_info.get("code", "")
                            d_id = d_info.get("kitsu_id", "")
                            departments.append(Department(id=d_id, name=d_name, code=d_code))
                except Exception as e:
                    logger.debug(f"Could not load fallback departments from {pipe_yaml}: {e}")

        for d in departments:
            item = QStandardItem(d.name)
            item.setData(d, Qt.ItemDataRole.UserRole)
            self.view.department_model.appendRow(item)

        if self.view.department_model.rowCount() > 0:
            first_idx = self.view.department_model.index(0, 0)
            self.view.ui.listView_department.setCurrentIndex(first_idx)
        else:
            self.current_department = None
            self.view.ui.label_department.setText("Department: None")
            self.update_metadata_table()

    def load_categories(self, project_id: str) -> None:
        """Fetch categories (episodes for Shot mode, asset types for Asset mode) to populate category dropdown."""
        self.view.ui.comboBox_category.blockSignals(True)
        self.view.ui.comboBox_category.clear()

        category_items = ["None"]
        if project_id:
            if self.is_shot_mode:
                try:
                    self.current_episodes = ShotService.get_episodes_by_project_id(project_id)
                except Exception as e:
                    logger.error(f"Failed to fetch episodes for project {project_id}: {e}")
                    self.current_episodes = []

                if self.current_episodes:
                    category_items.extend([ep.name for ep in self.current_episodes if ep.name])
            else:
                try:
                    self.current_asset_types = AssetService.get_asset_types_by_project_id(project_id)
                except Exception as e:
                    logger.error(f"Failed to fetch asset types for project {project_id}: {e}")
                    self.current_asset_types = []

                if self.current_asset_types:
                    category_items.extend([at.name for at in self.current_asset_types if at.name])
        else:
            self.current_episodes = []
            self.current_asset_types = []

        self.view.ui.comboBox_category.addItems(category_items)
        self.view.ui.comboBox_category.setCurrentIndex(0)
        self.view.ui.comboBox_category.blockSignals(False)

    def load_items(self) -> None:
        """Load items (shots or assets) based on current active mode."""
        if self.is_shot_mode:
            self.load_shots()
        else:
            self.load_assets()

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
                shots = ShotService.get_shots_by_episode_id(target_ep.id, episode_name=target_ep.name)
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

    def load_assets(self) -> None:
        """Fetch assets via AssetService and populate item list."""
        if not self.current_project:
            return

        selected_category = self.view.ui.comboBox_category.currentText()
        self.view.item_source_model.clear()

        # If None is selected, keep asset list empty
        if not selected_category or selected_category == "None":
            self._clear_item_details()
            return

        assets: List[Asset] = []
        try:
            assets = AssetService.get_assets_by_type(
                self.current_project.id,
                asset_type_name=selected_category,
            )
        except Exception as e:
            logger.error(f"Failed to fetch assets: {e}")

        # Sort assets alphabetically by name
        assets.sort(key=lambda a: (a.name or "").lower())

        for asset in assets:
            item = QStandardItem(asset.name)
            item.setData(asset, Qt.ItemDataRole.UserRole)
            self.view.item_source_model.appendRow(item)

        if self.view.item_proxy_model.rowCount() > 0:
            first_proxy_idx = self.view.item_proxy_model.index(0, 0)
            self.view.ui.listView_assetList.setCurrentIndex(first_proxy_idx)
        else:
            self._clear_item_details()

    def get_current_entity_key(self) -> Optional[str]:
        """Construct normalized entity key for the currently selected shot/asset."""
        if not self.current_project:
            return None

        dept_name = self.current_department.name if self.current_department else "Layout"
        proj_name = self.current_project.name

        if self.current_shot:
            ep = self.current_shot.episode or self.view.ui.comboBox_category.currentText()
            sq = self.current_shot.sequence or ""
            sh = self.current_shot.name
            return LockService.build_entity_key(
                department=dept_name,
                episode=ep,
                sequence=sq,
                shot=sh,
                project_name=proj_name,
            )
        elif self.current_asset:
            asset_name = self.current_asset.name
            return f"asset_{asset_name}_{dept_name}".lower().replace(" ", "_")

        return None

    def update_metadata_table(self) -> None:
        """Format and update metadata property/value table with real-time lock status."""
        self.view.metadata_model.removeRows(0, self.view.metadata_model.rowCount())
        dept_name = self.current_department.name if self.current_department else "None"
        proj_name = self.current_project.name if self.current_project else "None"

        # Check lock and history status
        entity_key = self.get_current_entity_key()
        lock_status = "Available (Unlocked)"
        locked_by_str = ""
        locked_at_str = ""
        locked_ws_str = ""

        latest_opened_by = ""
        latest_opened_at = ""
        latest_opened_ws = ""
        latest_version_author = ""

        if entity_key:
            try:
                # 1. Check active lock
                is_locked, lock_data = LockService.check_lock(entity_key, project_name=proj_name)
                if is_locked and lock_data:
                    k_id = lock_data.get("kitsu_id") or "N/A"
                    name = lock_data.get("name") or "Unknown"
                    ws = lock_data.get("workstation") or "Unknown"
                    at = lock_data.get("locked_at") or "Unknown"

                    lock_status = f"LOCKED by {name}"
                    locked_by_str = f"{name} (Kitsu ID: {k_id})"
                    locked_at_str = str(at)
                    locked_ws_str = str(ws)

                # 2. Query history for Latest Opened By audit trail
                hist_data = LockService.get_history(entity_key, project_name=proj_name)
                activity_log = hist_data.get("activity_log", [])
                for entry in reversed(activity_log):
                    if entry.get("action") in ("OPEN_FILE", "SAVE_VERSION"):
                        u_name = entry.get("user") or "Unknown"
                        k_id = entry.get("kitsu_id") or ""
                        latest_opened_by = f"{u_name} (Kitsu ID: {k_id})" if k_id else u_name
                        latest_opened_at = str(entry.get("timestamp") or "")
                        latest_opened_ws = str(entry.get("workstation") or "")
                        break

                # 3. Check author for current version
                versions = hist_data.get("versions", [])
                matching_v = next((v for v in versions if v.get("version") == self.current_version), None)
                if matching_v:
                    latest_version_author = matching_v.get("author", "")

            except Exception as e:
                logger.debug(f"Could not query lock/history for {entity_key}: {e}")

        if self.current_shot:
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
                "Selected File": self.selected_file_path or "None",
                "Lock Status": lock_status,
            }
            if locked_by_str:
                metadata["Currently Opened By"] = locked_by_str
                metadata["Current Workstation"] = locked_ws_str
                metadata["Opened At"] = locked_at_str
            elif latest_opened_by:
                metadata["Latest Opened By"] = latest_opened_by
                metadata["Latest Opened At"] = latest_opened_at
                metadata["Latest Workstation"] = latest_opened_ws

            if latest_version_author:
                metadata["Version Author"] = latest_version_author

        elif self.current_asset:
            metadata = {
                "Asset Name": self.current_asset.name,
                "Asset Type": self.current_asset.asset_type or "None",
                "Department": dept_name,
                "Project": proj_name,
                "Version": self.current_version or "None",
                "Selected File": self.selected_file_path or "None",
                "Lock Status": lock_status,
            }
            if locked_by_str:
                metadata["Currently Opened By"] = locked_by_str
                metadata["Current Workstation"] = locked_ws_str
                metadata["Opened At"] = locked_at_str
            elif latest_opened_by:
                metadata["Latest Opened By"] = latest_opened_by
                metadata["Latest Opened At"] = latest_opened_at
                metadata["Latest Workstation"] = latest_opened_ws

            if latest_version_author:
                metadata["Version Author"] = latest_version_author
        else:
            return

        for k, v in metadata.items():
            k_item = QStandardItem(str(k))
            v_item = QStandardItem(str(v))
            self.view.metadata_model.appendRow([k_item, v_item])

    def _clear_item_details(self) -> None:
        """Reset item details in the view."""
        self.current_shot = None
        self.current_asset = None
        self.current_version = ""
        self.selected_file_path = None
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

        # 1. Clear item list and details immediately before loading new project data
        self.view.item_source_model.clear()
        self._clear_item_details()

        self.current_project = current.data(Qt.ItemDataRole.UserRole)
        self.view.ui.label_project.setText(f"Project: {self.current_project.name}")

        self.refresh_features()
        self.load_categories(self.current_project.id)
        self.load_items()

    def on_department_selected(self, current, previous) -> None:
        """Handle department selection change."""
        if not current.isValid():
            return
        self.current_department = current.data(Qt.ItemDataRole.UserRole)
        dept_name = self.current_department.name if self.current_department else ""
        self.view.ui.label_department.setText(f"Department: {dept_name}")

        self.refresh_features()
        # Refresh version list for newly selected department if item is active
        if self.current_shot or self.current_asset:
            self.refresh_versions()
        else:
            self.update_metadata_table()

    def on_type_toggled(self, button) -> None:
        """Handle Shot vs Asset toggle."""
        self.view.item_source_model.clear()
        self._clear_item_details()
        if self.current_project:
            self.load_categories(self.current_project.id)
            self.load_items()

    def on_category_changed(self, category_text: str) -> None:
        """Handle category (episode or asset type) selection change."""
        self.view.item_source_model.clear()
        self._clear_item_details()
        self.load_items()

    def on_item_selected(self, current, previous) -> None:
        """Handle item (shot or asset) selection."""
        if not current.isValid():
            return
        source_idx = self.view.item_proxy_model.mapToSource(current)
        selected_data = source_idx.data(Qt.ItemDataRole.UserRole)

        if isinstance(selected_data, Shot):
            self.current_shot = selected_data
            self.current_asset = None
            seq_name = self.current_shot.sequence or ""
            display_name = f"{seq_name}_{self.current_shot.name}" if seq_name else self.current_shot.name
            self.view.ui.label_title.setText(f"<b>{display_name}</b>")
        elif isinstance(selected_data, Asset):
            self.current_asset = selected_data
            self.current_shot = None
            self.view.ui.label_title.setText(f"<b>{self.current_asset.name}</b>")
        else:
            self._clear_item_details()
            return

        self.refresh_versions()

    def refresh_versions(self) -> None:
        """Scan pipeline versioning files for currently selected item and populate listView_version."""
        self.view.version_model.clear()

        if self.current_shot:
            proj_name = self.current_project.name if self.current_project else None
            dept_name = self.current_department.name if self.current_department else "Layout"
            ep = self.current_shot.episode or self.view.ui.comboBox_category.currentText()
            sq = self.current_shot.sequence or ""
            sh = self.current_shot.name

            try:
                # 1. Resolve master path via PipelineService
                shot_path_res = PipelineService.resolve_shot(
                    department=dept_name,
                    episode=ep,
                    sequence=sq,
                    shot=sh,
                    project_name=proj_name,
                )

                # 2. Master is ALWAYS on top (Row 0)
                master_item = QStandardItem("Master")
                master_item.setData(str(shot_path_res.master_path), Qt.ItemDataRole.UserRole)
                self.view.version_model.appendRow(master_item)

                # 3. Scan existing version files in the version folder (e.g. progress/)
                existing_versions = PipelineService.list_versions(
                    department=dept_name,
                    episode=ep,
                    sequence=sq,
                    shot=sh,
                    project_name=proj_name,
                )

                for ver_num, ver_path in existing_versions:
                    ver_item = QStandardItem(f"v{ver_num:03d}")
                    ver_item.setData(str(ver_path), Qt.ItemDataRole.UserRole)
                    self.view.version_model.appendRow(ver_item)

            except Exception as e:
                logger.warning(f"Could not scan versions for shot {sh}: {e}")
                self.current_version = "Pipeline Error"
                self.selected_file_path = None
                self.view.ui.label_version.setText("<font color='#f87171'><b>Pipeline Error</b></font>")
                self.update_metadata_table()
                return

        elif self.current_asset:
            proj_name = self.current_project.name if self.current_project else None
            dept_name = self.current_department.name if self.current_department else ""
            at_type = self.current_asset.asset_type or self.view.ui.comboBox_category.currentText()
            asset_name = self.current_asset.name

            try:
                # 1. Resolve master path via PipelineService
                asset_path_res = PipelineService.resolve_asset(
                    asset_type=at_type,
                    asset_name=asset_name,
                    department=dept_name,
                    project_name=proj_name,
                )

                # 2. Master is ALWAYS on top (Row 0)
                master_item = QStandardItem("Master")
                master_item.setData(str(asset_path_res.master_path), Qt.ItemDataRole.UserRole)
                self.view.version_model.appendRow(master_item)

                # 3. Scan existing version files in the version folder (e.g. progress/)
                existing_versions = PipelineService.list_asset_versions(
                    asset_type=at_type,
                    asset_name=asset_name,
                    department=dept_name,
                    project_name=proj_name,
                )

                for ver_num, ver_path in existing_versions:
                    ver_item = QStandardItem(f"v{ver_num:03d}")
                    ver_item.setData(str(ver_path), Qt.ItemDataRole.UserRole)
                    self.view.version_model.appendRow(ver_item)

            except Exception as e:
                logger.warning(f"Could not scan versions for asset {asset_name}: {e}")
                self.current_version = "Pipeline Error"
                self.selected_file_path = None
                self.view.ui.label_version.setText("<font color='#f87171'><b>Pipeline Error</b></font>")
                self.update_metadata_table()
                return



        # 4. Auto-select the latest version by default
        total_rows = self.view.version_model.rowCount()
        if total_rows > 1:
            # Select latest version (last item in list)
            latest_idx = self.view.version_model.index(total_rows - 1, 0)
            self.view.ui.listView_version.setCurrentIndex(latest_idx)
        elif total_rows == 1:
            # Only Master exists
            first_idx = self.view.version_model.index(0, 0)
            self.view.ui.listView_version.setCurrentIndex(first_idx)
        else:
            self.current_version = ""
            self.selected_file_path = None
            self.view.ui.label_version.setText("No version")
            self.update_metadata_table()


    def on_version_selected(self, current, previous) -> None:
        """Handle version selection change."""
        if not current.isValid():
            return
        self.current_version = current.data(Qt.ItemDataRole.DisplayRole)
        self.selected_file_path = current.data(Qt.ItemDataRole.UserRole)
        self.view.ui.label_version.setText(f"Version: <b>{self.current_version}</b>")
        self.update_metadata_table()

    def on_execute_action(self) -> None:
        """Execute selected pipeline action (single or batch across multiple selected shots/assets)."""
        combo = self.feature_combobox
        action = combo.currentText() if combo else ""
        if not action:
            return

        active_blender = SettingsService.get_active_blender()
        if not active_blender or not Path(active_blender).is_file():
            QMessageBox.warning(
                self.view,
                "Blender Not Configured",
                "Blender executable path is missing or invalid. Please configure it in Settings -> Software.",
            )
            return

        proj_name = self.current_project.name if self.current_project else None
        dept_name = self.current_department.name if self.current_department else ""

        # Check multi-select mode and gather selected items from list
        multi_cb = getattr(self.view.ui, "checkBox_multiSelect", getattr(self.view.ui, "comboBox_multiSelect", None))
        is_multi = multi_cb.isChecked() if multi_cb else False

        selected_indexes = self.view.ui.listView_assetList.selectionModel().selectedIndexes()
        selected_items = []
        for idx in selected_indexes:
            source_idx = self.view.item_proxy_model.mapToSource(idx)
            item_data = source_idx.data(Qt.ItemDataRole.UserRole)
            if item_data and item_data not in selected_items:
                selected_items.append(item_data)

        # ------------------------------------------------------------------
        # A. Batch Execution (Multiple items selected)
        # ------------------------------------------------------------------
        if is_multi and len(selected_items) > 1:
            reply = QMessageBox.question(
                self.view,
                f"Confirm Batch {action}",
                f"You have selected {len(selected_items)} items.\n\n"
                f"Do you want to execute '{action}' on all {len(selected_items)} items in batch?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            success_list = []
            failed_list = []

            for item in selected_items:
                try:
                    target_filepath = None
                    item_key = None
                    item_label = ""

                    shot_data_dict = None
                    if isinstance(item, Shot):
                        ep = item.episode or self.view.ui.comboBox_category.currentText()
                        sq = item.sequence or ""
                        sh = item.name
                        item_label = f"{sq}_{sh}" if sq else sh

                        shot_res = PipelineService.resolve_shot(
                            department=dept_name,
                            episode=ep,
                            sequence=sq,
                            shot=sh,
                            project_name=proj_name,
                        )
                        versions = PipelineService.list_versions(
                            department=dept_name,
                            episode=ep,
                            sequence=sq,
                            shot=sh,
                            project_name=proj_name,
                        )
                        target_filepath = str(versions[-1][1]) if versions else str(shot_res.master_path)
                        item_key = LockService.build_entity_key(
                            department=dept_name,
                            episode=ep,
                            sequence=sq,
                            shot=sh,
                            project_name=proj_name,
                        )
                        shot_data_dict = {
                            "id": item.id,
                            "name": item.name,
                            "sequence": sq,
                            "episode": ep,
                            "assets": item.assets,
                            "data": {
                                "frame_in": item.frame_in,
                                "frame_out": item.frame_out,
                                "fps": item.fps,
                                "resolution": item.resolution,
                            },
                        }

                    elif isinstance(item, Asset):
                        at_type = item.asset_type or self.view.ui.comboBox_category.currentText()
                        asset_name = item.name
                        item_label = asset_name

                        asset_res = PipelineService.resolve_asset(
                            asset_type=at_type,
                            asset_name=asset_name,
                            department=dept_name,
                            project_name=proj_name,
                        )
                        versions = PipelineService.list_asset_versions(
                            asset_type=at_type,
                            asset_name=asset_name,
                            department=dept_name,
                            project_name=proj_name,
                        )
                        target_filepath = str(versions[-1][1]) if versions else str(asset_res.master_path)
                        item_key = f"asset_{asset_name}_{dept_name}".lower().replace(" ", "_")

                    if not target_filepath:
                        failed_list.append((item_label, "Could not resolve file path."))
                        continue

                    # Execute pipeline feature
                    success, msg, target_path = PipelineService.execute_feature(
                        feature_name=action,
                        filepath=target_filepath,
                        department=dept_name,
                        project_name=proj_name,
                        shot_data=shot_data_dict,
                    )

                    if success:
                        success_list.append((item_label, target_path or msg))
                        # Record in history/audit log
                        if item_key and target_path:
                            try:
                                if "generate" in action.lower():
                                    ver_name = Path(target_path).stem.split("_")[-1] if target_path else "v001"
                                    file_size_mb = 0.0
                                    if Path(target_path).is_file():
                                        file_size_mb = round(Path(target_path).stat().st_size / (1024 * 1024), 2)

                                    LockService.record_version(
                                        entity_key=item_key,
                                        version=ver_name,
                                        file_path=str(target_path),
                                        comment="Batch generation (v001)",
                                        file_size_mb=file_size_mb,
                                        project_name=proj_name,
                                    )
                                    try:
                                        from versioning import VersioningSystem
                                    except ImportError:
                                        from pipeline.Commands.versioning import VersioningSystem

                                    master_path = VersioningSystem.get_master_path(target_path)
                                    m_size = round(Path(master_path).stat().st_size / (1024 * 1024), 2) if Path(master_path).is_file() else 0.0
                                    LockService.record_version(
                                        entity_key=item_key,
                                        version="Master",
                                        file_path=str(master_path),
                                        comment="Batch generation (Up Master)",
                                        file_size_mb=m_size,
                                        project_name=proj_name,
                                    )
                                else:
                                    ver_name = "Master" if "master" in action.lower() else Path(target_path).stem.split("_")[-1]
                                    file_size_mb = 0.0
                                    if Path(target_path).is_file():
                                        file_size_mb = round(Path(target_path).stat().st_size / (1024 * 1024), 2)

                                    LockService.record_version(
                                        entity_key=item_key,
                                        version=ver_name,
                                        file_path=str(target_path),
                                        comment=f"Batch execution: {action}",
                                        file_size_mb=file_size_mb,
                                        project_name=proj_name,
                                    )
                            except Exception as ex:
                                logger.warning(f"Could not record version history for {item_label}: {ex}")
                    else:
                        failed_list.append((item_label, msg))

                except Exception as ex:
                    failed_list.append((getattr(item, "name", "Unknown"), str(ex)))

            # Refresh view after batch
            self.refresh_versions()
            self.update_metadata_table()

            # Present summary
            if failed_list:
                batch_log_lines = [
                    f"Batch '{action}' Execution Errors ({len(failed_list)} failed / {len(selected_items)} total):",
                    "=" * 60,
                ]
                for item_name, err in failed_list:
                    batch_log_lines.append(f"--- Item: {item_name} ---")
                    batch_log_lines.append(str(err))
                    batch_log_lines.append("")

                batch_full_log = "\n".join(batch_log_lines)
                failed_names = [l for l, _ in failed_list]
                names_preview = ", ".join(failed_names[:4])
                if len(failed_names) > 4:
                    names_preview += f" (+{len(failed_names) - 4} more)"

                short_summary = (
                    f"Batch execution for '{action}' finished with {len(failed_list)} error(s):\n\n"
                    f"• Total Processed : {len(selected_items)}\n"
                    f"• Successful      : {len(success_list)}\n"
                    f"• Failed          : {len(failed_list)}\n\n"
                    f"Failed items: {names_preview}"
                )
                show_error_dialog(
                    parent=self.view,
                    title=f"Batch {action} Results",
                    summary=short_summary,
                    full_log=batch_full_log,
                    prefix=f"zeroxe_batch_{action.lower()}",
                )
            else:
                summary = [
                    f"Batch execution for '{action}' finished:",
                    f"• Total Processed: {len(selected_items)}",
                    f"• Successful: {len(success_list)}",
                ]
                QMessageBox.information(self.view, f"Batch {action} Complete", "\n".join(summary))
            return

        # ------------------------------------------------------------------
        # B. Single Item Execution
        # ------------------------------------------------------------------
        if not self.selected_file_path or self.current_version == "Pipeline Error":
            QMessageBox.warning(
                self.view,
                "No File Selected",
                "Please select a valid shot or asset version to perform this pipeline action.",
            )
            return

        entity_key = self.get_current_entity_key()

        shot_data_dict = None
        if self.current_shot:
            assets = list(self.current_shot.assets)
            if not assets and self.current_shot.id:
                try:
                    from zeroxe.services.shot_service import ShotService

                    assets = ShotService.get_assets_for_shot(self.current_shot.id)
                except Exception:
                    pass

            formatted_assets = []
            for a in assets:
                if isinstance(a, dict):
                    formatted_assets.append(a)
                elif hasattr(a, "name"):
                    formatted_assets.append({
                        "id": getattr(a, "id", ""),
                        "name": getattr(a, "name", ""),
                        "entity_type_id": getattr(a, "entity_type_id", getattr(a, "asset_type_id", "")),
                        "asset_type": getattr(a, "asset_type", ""),
                    })

            shot_data_dict = {
                "id": self.current_shot.id,
                "name": self.current_shot.name,
                "sequence": self.current_shot.sequence,
                "episode": self.current_shot.episode,
                "assets": formatted_assets,
                "data": {
                    "frame_in": self.current_shot.frame_in,
                    "frame_out": self.current_shot.frame_out,
                    "fps": self.current_shot.fps,
                    "resolution": self.current_shot.resolution,
                },
            }

        try:
            success, msg, target_path = PipelineService.execute_feature(
                feature_name=action,
                filepath=self.selected_file_path,
                department=dept_name,
                project_name=proj_name,
                shot_data=shot_data_dict,
            )

            if success:
                # Refresh versions and metadata
                self.refresh_versions()
                self.update_metadata_table()

                # Record version in audit log if target path exists
                if entity_key and target_path:
                    try:
                        if "generate" in action.lower():
                            # 1. Record v001 version
                            ver_name = Path(target_path).stem.split("_")[-1] if target_path else "v001"
                            file_size_mb = 0.0
                            if Path(target_path).is_file():
                                file_size_mb = round(Path(target_path).stat().st_size / (1024 * 1024), 2)

                            LockService.record_version(
                                entity_key=entity_key,
                                version=ver_name,
                                file_path=str(target_path),
                                comment="Initial generation (v001)",
                                file_size_mb=file_size_mb,
                                project_name=proj_name,
                            )
                            # 2. Record Master version
                            try:
                                from versioning import VersioningSystem
                            except ImportError:
                                from pipeline.Commands.versioning import VersioningSystem

                            master_path = VersioningSystem.get_master_path(target_path)
                            m_size = round(Path(master_path).stat().st_size / (1024 * 1024), 2) if Path(master_path).is_file() else 0.0
                            LockService.record_version(
                                entity_key=entity_key,
                                version="Master",
                                file_path=str(master_path),
                                comment="Initial generation (Up Master)",
                                file_size_mb=m_size,
                                project_name=proj_name,
                            )
                        else:
                            ver_name = "Master" if "master" in action.lower() else Path(target_path).stem.split("_")[-1]
                            file_size_mb = 0.0
                            if Path(target_path).is_file():
                                file_size_mb = round(Path(target_path).stat().st_size / (1024 * 1024), 2)

                            LockService.record_version(
                                entity_key=entity_key,
                                version=ver_name,
                                file_path=str(target_path),
                                comment=f"Automated execution: {action}",
                                file_size_mb=file_size_mb,
                                project_name=proj_name,
                            )
                    except Exception as ex:
                        logger.warning(f"Failed to record version history: {ex}")

                QMessageBox.information(
                    self.view,
                    f"{action} Complete",
                    msg or f"Successfully executed '{action}'",
                )
            else:
                summary = extract_error_summary(action, msg)
                show_error_dialog(
                    parent=self.view,
                    title=f"{action} Failed",
                    summary=summary,
                    full_log=msg or f"Failed to execute '{action}'",
                    prefix=f"zeroxe_{action.lower()}_error",
                )

        except Exception as e:
            logger.error(f"Error executing feature '{action}': {e}")
            import traceback
            tb = traceback.format_exc()
            summary = extract_error_summary(action, str(e))
            show_error_dialog(
                parent=self.view,
                title=f"{action} Error",
                summary=summary,
                full_log=tb,
                prefix=f"zeroxe_{action.lower()}_error",
            )

    def on_open_path(self) -> None:
        """Open the currently selected item file using active Blender executable with automatic locking."""
        active_blender = SettingsService.get_active_blender()
        if not active_blender or not Path(active_blender).is_file():
            QMessageBox.warning(
                self.view,
                "Blender Not Configured",
                "Blender executable path is missing or invalid. Please configure it in Settings -> Software.",
            )
            return

        if not self.selected_file_path or self.current_version == "Pipeline Error":
            QMessageBox.warning(
                self.view,
                "Pipeline / File Error",
                "Cannot open file because the pipeline could not be loaded or no valid file is selected.\n\n"
                "Please configure the zeroxe_map path in Settings -> NAS.",
            )
            return

        target_file = Path(self.selected_file_path)
        entity_key = self.get_current_entity_key()
        proj_name = self.current_project.name if self.current_project else None

        # 1. Lock Validation Check
        if entity_key:
            is_locked, lock_data = LockService.check_lock(entity_key, project_name=proj_name)
            current_user = LockService.get_current_user()

            if is_locked and lock_data:
                existing_kitsu_id = str(lock_data.get("kitsu_id", ""))
                existing_name = str(lock_data.get("name", ""))
                existing_ws = str(lock_data.get("workstation", ""))

                # Check if locked by another user
                is_other_user = True
                if (
                    (current_user.kitsu_id and existing_kitsu_id == current_user.kitsu_id)
                    or (current_user.name and existing_name.lower() == current_user.name.lower())
                ) and (existing_ws == current_user.workstation):
                    is_other_user = False

                if is_other_user:
                    QMessageBox.warning(
                        self.view,
                        "File Is Locked",
                        f"This shot/asset is currently LOCKED by another artist:\n\n"
                        f"• Artist: {existing_name or 'Unknown'}\n"
                        f"• Kitsu ID: {existing_kitsu_id or 'N/A'}\n"
                        f"• Workstation: {existing_ws or 'Unknown'}\n"
                        f"• Locked Since: {lock_data.get('locked_at', 'Unknown')}\n\n"
                        f"You cannot open this file while another artist is editing it.\n"
                        f"If this is a stale lock, click 'Unlock' to Force Unlock.",
                    )
                    return

        # 2. Ensure target file or directory exists
        if not target_file.is_file():
            reply = QMessageBox.question(
                self.view,
                "File Does Not Exist",
                f"The selected file does not exist on disk yet:\n\n{target_file}\n\nDo you want to create the directory and open Blender with this path?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                show_error_dialog(
                    parent=self.view,
                    title="Directory Creation Error",
                    summary=f"Failed to create directory structure for '{target_file.name}'.",
                    full_log=str(e),
                    prefix="zeroxe_mkdir_error",
                )
                return

        # 3. Acquire Lock in Pipeline
        if entity_key:
            success, msg, active_lock = LockService.acquire_lock(
                entity_key=entity_key,
                working_file=str(target_file),
                current_version=self.current_version,
                project_name=proj_name,
            )
            if not success:
                QMessageBox.warning(
                    self.view,
                    "Lock Failed",
                    f"Could not acquire pipeline lock:\n\n{msg}",
                )
                return

        # 4. Launch Blender via QProcess and monitor for auto-unlock
        try:
            process = QProcess(self)
            if entity_key:
                self._active_processes[entity_key] = process
                process.finished.connect(
                    lambda exit_code, exit_status, k=entity_key, p=proj_name: self._on_dcc_finished(k, p, exit_code)
                )

            process.start(active_blender, [str(target_file)])
            self.update_metadata_table()

        except Exception as e:
            # Release lock if launch failed
            if entity_key:
                LockService.release_lock(entity_key, project_name=proj_name)
                self.update_metadata_table()

            import traceback
            tb = traceback.format_exc()
            show_error_dialog(
                parent=self.view,
                title="Error Opening File",
                summary="Failed to launch Blender executable.",
                full_log=tb or str(e),
                prefix="zeroxe_launch_error",
            )

    def _on_dcc_finished(self, entity_key: str, project_name: Optional[str], exit_code: int) -> None:
        """Handle Blender process exit by automatically releasing lock."""
        logger.info(f"DCC closed for '{entity_key}' (exit code: {exit_code}). Auto-releasing lock...")
        try:
            LockService.release_lock(entity_key, project_name=project_name)
        except Exception as e:
            logger.error(f"Failed to auto-release lock for '{entity_key}': {e}")

        if entity_key in self._active_processes:
            del self._active_processes[entity_key]

        if self.get_current_entity_key() == entity_key:
            self.update_metadata_table()

    def on_unlock_task(self) -> None:
        """Handle Unlock button click by performing a Force Unlock with user confirmation."""
        entity_key = self.get_current_entity_key()
        if not entity_key:
            QMessageBox.warning(self.view, "No Selection", "Please select a shot or asset to unlock.")
            return

        proj_name = self.current_project.name if self.current_project else None
        is_locked, lock_data = LockService.check_lock(entity_key, project_name=proj_name)

        if not is_locked or not lock_data:
            QMessageBox.information(self.view, "Unlock", "This item is currently NOT locked.")
            return

        holder_name = lock_data.get("name", "Unknown")
        holder_kitsu = lock_data.get("kitsu_id", "N/A")
        holder_ws = lock_data.get("workstation", "Unknown")
        locked_at = lock_data.get("locked_at", "Unknown")

        reply = QMessageBox.question(
            self.view,
            "Force Unlock Confirmation",
            f"This item is currently locked by:\n\n"
            f"• Artist: {holder_name}\n"
            f"• Kitsu ID: {holder_kitsu}\n"
            f"• Workstation: {holder_ws}\n"
            f"• Locked Since: {locked_at}\n\n"
            f"Are you sure you want to FORCE UNLOCK this file?\n"
            f"This action will be recorded in the pipeline audit log.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, msg, _ = LockService.force_unlock(
                entity_key=entity_key,
                reason="Manual force unlock via ZeroXe Launcher",
                project_name=proj_name,
            )
            if success:
                QMessageBox.information(
                    self.view,
                    "Force Unlocked",
                    f"Item successfully unlocked:\n\n{msg}",
                )
                self.update_metadata_table()
            else:
                show_error_dialog(
                    parent=self.view,
                    title="Unlock Failed",
                    summary="Failed to force unlock task.",
                    full_log=str(msg),
                    prefix="zeroxe_unlock_error",
                )



