import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from textwrap import dedent
from string import Template

from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtGui import QPixmap, QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QTreeWidgetItem,
    QListWidgetItem,
    QPushButton,
    QHeaderView,
    QStyleOptionButton,
    QHBoxLayout,
    QAbstractItemView,
    QSizePolicy,
    QApplication,
    QMessageBox,
    QFileDialog,
    QButtonGroup
)
from gazu import project

from app.config import Settings
from app.ui.modules.special_case.comp_saveas_ui import Ui_Form
from app.core.app_states import AppState
from app.utils.api.gazu.person import PersonServices
from app.utils.api.gazu.project import ProjectServices
from app.utils.api.gazu.shot import ShotServices
from app.utils.api.gazu.asset import AssetServices
from app.utils.api.gazu.task import TaskServices
from app.utils.subprocess import SubprocessServices
from app.utils.versioning import VersioningSystem
from app.utils.blender_functions import BlenderFunctions
from app.utils.path_builder import PathBuilder
from app.utils.json_manager import JsonManager

class HandleCompSaveAs(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.zeroxe_core = ""
        self.zeroxe_conf = {}

        self.entities = [{"name": "Assets"}, {"name": "Shots"}]
        self.departments = []
        self.projects = []
        self.sequences = []
        self.shots = []
        self.paths = []
        self.assets = []
        self.asset_types = []
        self.batch_mode = False

        self.selected_item = {}
        self.selected_path = ""
        self.user_id = ""
        
        self.get_user_id()
        self.load_user_data()
        self.load_departments()
        self.mount_function()
        self.wire_search_list()

        self.source_path = ''
        self.target_path = []
    
    def mount_function(self):
        self.ui.comboBox_department.currentIndexChanged.connect(
            self.on_department_change
        )
        self.ui.comboBox_project.currentIndexChanged.connect(self.on_project_change)
        self.ui.comboBox_entity.currentIndexChanged.connect(self.on_entity_change)
        self.ui.comboBox_episode.currentIndexChanged.connect(self.on_episode_change)
        self.ui.comboBox_type.currentIndexChanged.connect(self.on_asset_type_change)
        self.ui.listWidget_list.itemClicked.connect(self.on_widget_list_double_click)
        self.ui.toolButton_blenderPath.clicked.connect(self.on_select_blender)
        self.ui.pushButton_source.clicked.connect(self.on_source_button_clicked)
        self.ui.pushButton_target.clicked.connect(self.generate_batch)
        self.ui.listWidget_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.ui.listWidget_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
    def load_user_data(self):
        user_data = Settings().read_user_data()
        if user_data and user_data.get("blender_path", None):
            self.ui.lineEdit_blenderPath.setText(user_data["blender_path"])
        else:
            self.on_select_blender()

    def get_user_id(self):
        if AppState().user_data is None:
            QMessageBox.warning(self, "Warning", "User data not found. Please log in again.")
            return
        user_data = AppState().user_data or {}
        user_dict = user_data.get("user", {}) or {}
        user_id = user_dict.get("id", "")
        self.user_id = user_id

    def on_department_change(self):
        projects = ProjectServices.get_projects()
        self.projects = projects

        self.ui.comboBox_project.clear()
        self.ui.comboBox_project.addItem("--- Select Project ---", None)
        for project in projects:
            self.ui.comboBox_project.addItem(project["name"], project["id"])

        self.ui.comboBox_project.setEnabled(True)
        self.ui.comboBox_entity.setEnabled(False)
        self.ui.comboBox_episode.setEnabled(False)
        self.ui.comboBox_type.setEnabled(False)

    def on_project_change(self):
        self.ui.comboBox_entity.clear()
        self.ui.comboBox_entity.addItem("--- Select Entity ---", None)
        self.ui.comboBox_entity.addItems([entity["name"] for entity in self.entities])

        self.ui.comboBox_entity.setEnabled(True)
        self.ui.comboBox_episode.setEnabled(False)
        self.ui.comboBox_type.setEnabled(False)

    def on_entity_change(self):
        project_id = self.ui.comboBox_project.currentData()
        if project_id is None:
            self.ui.comboBox_episode.clear()
            self.ui.comboBox_episode.setEnabled(False)
            return

        episodes = ShotServices.get_episodes_by_project_id(project_id)
        self.ui.comboBox_episode.clear()
        self.ui.comboBox_episode.addItem("--- Select Episode ---", None)
        for episode in episodes:
            if episode["name"].startswith("setting"):
                bpaths = ShotServices.get_shots_by_episode_id(episode["id"])
                asset_bpaths = AssetServices.get_assets_by_episode_id(episode["id"])
                self.paths = bpaths + asset_bpaths
                continue
            self.ui.comboBox_episode.addItem(episode["name"], episode["id"])

        entity = self.ui.comboBox_entity.currentIndex()
        self.ui.listWidget_list.clear()

        if entity == 1:
            self.load_assets()
            self.ui.label_type.setVisible(True)
            self.ui.comboBox_type.setVisible(True)
            self.ui.comboBox_type.setEnabled(True)
            self.ui.label_episode.setVisible(False)
            self.ui.comboBox_episode.setVisible(False)
            self.ui.comboBox_episode.setEnabled(False)
        elif entity == 2:
            self.ui.label_type.setVisible(False)
            self.ui.comboBox_type.setVisible(False)
            self.ui.comboBox_type.setEnabled(False)
            self.ui.label_episode.setVisible(True)
            self.ui.comboBox_episode.setVisible(True)
            self.ui.comboBox_episode.setEnabled(True)

        zeroxe_core = next(
            (
                p.get("description", "")
                for p in self.paths
                if p.get("name", "").lower().startswith("bpath-")
                and p.get("name", "").lower().endswith("zeroxe_core")
            ),
            None,
        )
        zeroxe_conf = next(
            (
                p.get("description", "")
                for p in self.paths
                if p.get("name", "").lower().startswith("bpath-")
                and p.get("name", "").lower().endswith("zeroxe_conf")
            ),
            None,
        )
        zeroxe_conf_content = JsonManager.load_json(str(zeroxe_conf))
        self.zeroxe_core = zeroxe_core
        self.zeroxe_conf = zeroxe_conf_content

    def on_episode_change(self):
        self.load_sequence_and_shot()

    def on_asset_type_change(self):
        self.ui.listWidget_list.clear()
        asset_type_id = self.ui.comboBox_type.currentData()
        if asset_type_id is None:
            return

        for asset in self.assets:
            if asset["entity_type_id"] == asset_type_id:
                item = QListWidgetItem(asset["name"])
                item.setData(Qt.ItemDataRole.UserRole, asset["id"])
                self.ui.listWidget_list.addItem(item)
               
    def on_widget_list_double_click(self, item: QListWidgetItem):
        if self.ui.comboBox_entity.currentIndex() == 1:
            asset_id = item.data(Qt.ItemDataRole.UserRole)
            self.load_metadata(asset_id)
        elif self.ui.comboBox_entity.currentIndex() == 2:
            shot_data = item.data(Qt.ItemDataRole.UserRole)
            self.load_metadata(shot_data["shot_id"])
        self.reload_version_metadata()
            
    def on_select_blender(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Blender", "", "All Files (*)"
        )
        if file_path:
            self.ui.lineEdit_blenderPath.setText(file_path)
            Settings().update_user_field(key="blender_path", value=file_path)

    def on_source_button_clicked(self):
        if not self.selected_item:
            QMessageBox.warning(
                self,
                "Warning",
                "No shot selected.",
            )
        if self.selected_item:
            self.ui.label_sourceName.setText(self.ui.listWidget_list.currentItem().text())
            self.source_path = self.selected_path
            print(self.source_path)

    # region Populate data
    # Department dropdown
    def load_departments(self):
        departments = PersonServices.get_departments()
        self.departments = departments

        self.ui.comboBox_department.clear()
        self.ui.comboBox_department.addItem("--- Select Department ---", None)
        for department in departments:
            self.ui.comboBox_department.addItem(department["name"], department["id"])

        self.ui.comboBox_project.setEnabled(False)
        self.ui.comboBox_entity.setEnabled(False)
        self.ui.comboBox_episode.setEnabled(False)
        self.ui.comboBox_type.setEnabled(False)

    # List widget for assets
    def load_assets(self):
        project_id = self.ui.comboBox_project.currentData()
        assets = AssetServices.get_assets_by_project_id(project_id)

        asset_types = AssetServices.get_asset_types_by_project_id(project_id)
        self.asset_types = asset_types

        self.ui.comboBox_type.clear()
        self.ui.comboBox_type.addItem("--- Select Type ---", None)
        for asset_type in asset_types:
            self.ui.comboBox_type.addItem(asset_type["name"], asset_type["id"])

        self.assets = []
        for asset in assets:
            if asset["name"].startswith("bpath-"):
                continue
            item = QListWidgetItem(asset["name"])
            item.setData(Qt.ItemDataRole.UserRole, asset["id"])
            self.ui.listWidget_list.addItem(item)
            self.assets.append(asset)

    # List widget for shots
    def load_sequence_and_shot(self):
        self.ui.listWidget_list.clear()
        episode_id = self.ui.comboBox_episode.currentData()
        episode_name = self.ui.comboBox_episode.currentText()
        if episode_id is None:
            return

        sequences = ShotServices.get_sequences_by_episode_id(episode_id)
        self.sequences = sequences

        shots = ShotServices.get_shots_by_episode_id(episode_id)
        self.shots = shots

        seq_lookup = {seq["id"]: seq["name"] for seq in sequences}
        for shot in shots:
            seq_name = seq_lookup.get(shot["parent_id"]) or ""
            shot_name = shot["name"]
            item_name = f"{seq_name}_{shot_name}"
            if "lib" in episode_name:
                item_name = shot_name

            item = QListWidgetItem(item_name)
            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "sequence_id": shot["parent_id"],
                    "shot_id": shot["id"],
                    "sequence_name": seq_name,
                    "shot_name": shot_name,
                },
            )
            self.ui.listWidget_list.addItem(item)

    # .zeroxe log data
    def load_latest_log(self, file_path: str | None = None):
        if self.selected_item is None:
            return

        master_path, full_path = self.shot_or_asset_path()

        if full_path and file_path is None:
            file_path = str(full_path)
        file_log = VersioningSystem.get_latest_log(str(master_path), file_path)
        if file_log:
            timestamp = file_log.get("date")
            file_log["date"] = (
                datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
                if timestamp
                else "N/A"
            )
            author = file_log.get("author")
            file_log["author"] = f"{PersonServices.get_person_by_id(author).get('first_name', '')} {PersonServices.get_person_by_id(author).get('last_name', '')}"
            file_log["locked"] = str(file_log["locked"])
        return file_log

    # Table view metadata
    def metadata_table(
        self, custom_field_map: dict | None = None, custom_item_data: dict | None = None
    ):
        if self.selected_item is None:
            return

        item_data = self.selected_item

        file_log = self.load_latest_log()
        if file_log:
            item_data["date"] = file_log["date"]
            item_data["author"] = file_log["author"]
            item_data["locked"] = file_log["locked"]

        metadata_model = QStandardItemModel()
        metadata_model.setHorizontalHeaderLabels(["Key", "Value"])

        metadata_field_map = {
            "name": "Name",
            "status": "Status",
        }
        if self.ui.comboBox_entity.currentIndex() == 1:
            metadata_field_map["asset_type_name"] = "Type"
        metadata_field_map.update(
            {
                "locked": "Locked",
                "date": "Date",
                "author": "Author",
            }
        )
        if custom_field_map:
            metadata_field_map = custom_field_map
        if custom_item_data:
            item_data = custom_item_data

        for key, label in metadata_field_map.items():
            key_value = item_data.get(key, "")
            if key_value:
                label = QStandardItem(label)
                label.setEditable(False)
                item = QStandardItem(key_value)
                item.setEditable(False)
                metadata_model.appendRow([label, item])
        self.ui.tableView_metadata.setModel(metadata_model)
        self.ui.tableView_metadata.setWordWrap(True)

    # Table view task and metadata trigger
    def load_metadata(self, asset_or_shot_id, use_master: bool = False):
        if asset_or_shot_id is None:
            return

        if self.ui.comboBox_entity.currentIndex() == 1:
            asset_data = AssetServices.get_asset_by_id(asset_or_shot_id)
            asset_tasks = TaskServices.get_tasks_by_asset_id(asset_or_shot_id)
            self.selected_item = asset_data

            self.metadata_table()

            task_model = QStandardItemModel()
            task_model.setHorizontalHeaderLabels(["Name", "Status"])

            task_field_map = {
                "task_type_name": "task_status_name",
            }

            for name, status in task_field_map.items():
                for task in asset_tasks:
                    task_type_name = task.get(name, "")
                    task_status_name = task.get(status, "")
                    if task_type_name and task_status_name:
                        item_name = QStandardItem(task_type_name)
                        item_name.setEditable(False)
                        item_status = QStandardItem(task_status_name)
                        item_status.setEditable(False)
                        task_model.appendRow([item_name, item_status])

            # self.ui.tableView_task.setModel(task_model)
            # self.ui.tableView_task.setWordWrap(True)
        elif self.ui.comboBox_entity.currentIndex() == 2:
            shot_data = ShotServices.get_shot_by_id(asset_or_shot_id)
            shot_tasks = TaskServices.get_tasks_by_shot_id(asset_or_shot_id)
            self.selected_item = shot_data

            self.metadata_table()

            task_model = QStandardItemModel()
            task_model.setHorizontalHeaderLabels(["Name", "Status"])

            task_field_map = {
                "task_type_name": "task_status_name",
            }

            for name, status in task_field_map.items():
                for task in shot_tasks:
                    task_type_name = task.get(name, "")
                    task_status_name = task.get(status, "")
                    if task_type_name and task_status_name:
                        item_name = QStandardItem(task_type_name)
                        item_name.setEditable(False)
                        item_status = QStandardItem(task_status_name)
                        item_status.setEditable(False)
                        task_model.appendRow([item_name, item_status])

            # self.ui.tableView_task.setModel(task_model)
            # self.ui.tableView_task.setWordWrap(True)

        self.load_version(show_master=use_master)

    # List view version
    def load_version(self, show_master: bool = False):
        # self.ui.listWidget_version.clear()
        if self.selected_item is None:
            return

        master_path, full_path = self.shot_or_asset_path()

        if self.ui.comboBox_entity.currentIndex() == 1:
            master_file_path = Path(master_path) / f"{self.selected_item['name']}.blend"
            if show_master:
                master_item = QListWidgetItem("Master")
                master_item.setData(Qt.ItemDataRole.UserRole, master_file_path)
                # self.ui.listWidget_version.addItem(master_item)
            self.selected_path = str(master_file_path)
        elif self.ui.comboBox_entity.currentIndex() == 2:
            if show_master:
                master_item = QListWidgetItem("Master")
                master_item.setData(Qt.ItemDataRole.UserRole, full_path)
                # self.ui.listWidget_version.addItem(master_item)
            self.selected_path = str(full_path)
        version_folder = VersioningSystem.get_version_folder(master_path)
        version_info_list = VersioningSystem.get_version_info_list(str(version_folder))
        for version_info in version_info_list:
            item = QListWidgetItem(version_info["version"])
            item.setData(Qt.ItemDataRole.UserRole, version_info["full_path"])
            # self.ui.listWidget_version.addItem(item)
        self.ui.listWidget_list.sortItems()
        if show_master:
            pass
            # self.ui.listWidget_version.setCurrentRow(0)
        elif version_info_list:
            latest_version_data = version_info_list[-1]
            self.selected_path = latest_version_data["full_path"]
            # last_row_index = self.ui.listWidget_version.count() - 1
            # self.ui.listWidget_version.setCurrentRow(last_row_index)

    # Table view metadata for version
    def load_version_metadata(self, version_name: str, version_path: str):
        if self.selected_item is None:
            return

        self.selected_path = version_path

        custom_field_map, custom_asset_data = {}, {}
        if self.ui.comboBox_entity.currentIndex() == 1:
            custom_field_map = {
                "name": "Name",
                "status": "Status",
                "asset_type_name": "Type",
                "version": "Version",
                "date": "Date",
                "author": "Author",
                "locked": "Locked",
            }
            custom_asset_data = {
                "name": self.selected_item["name"],
                "status": self.selected_item["status"],
                "asset_type_name": self.selected_item["asset_type_name"],
                "version": version_name,
            }

        elif self.ui.comboBox_entity.currentIndex() == 2:
            custom_field_map = {
                "name": "Name",
                "status": "Status",
                "department": "Department",
                "version": "Version",
                "date": "Date",
                "author": "Author",
                "locked": "Locked",
            }
            item = self.ui.listWidget_list.currentItem()
            custom_asset_data = {
                "name": item.text() if item else "Unknown",
                "status": self.selected_item["status"],
                "department": self.ui.comboBox_department.currentText(),
                "version": version_name,
            }
        file_log = self.load_latest_log(version_path)
        if file_log:
            custom_asset_data.update(
                {
                    "date": file_log["date"],
                    "author": file_log["author"],
                    "locked": file_log["locked"],
                }
            )
        self.metadata_table(
            custom_field_map=custom_field_map, custom_item_data=custom_asset_data
        )

    # Table view metadata refersh for version
    def reload_version_metadata(self, use_master: bool = False):
        # if use_master:
        version_name = "Master"
        version_path = self.selected_path
        # else:
        #     version_item = self.ui.listWidget_version.currentItem()
        #     version_name = "Master" if version_item is None else version_item.text()
        #     version_path = (
        #         self.selected_path
        #         if version_item is None
        #         else version_item.data(Qt.ItemDataRole.UserRole)
        #     )
        self.load_version_metadata(version_name, str(version_path))

    # endregion

    def generate_batch(self):
        if not self.ui.listWidget_list.selectedItems():
            QMessageBox.warning(self, "Warning", "No shot or asset selected.")
            return
        # master_path, full_path = self.shot_or_asset_path()
        # full_path_list = []
        selected_items = self.ui.listWidget_list.selectedItems()
        for item in selected_items:
            self.ui.listWidget_list.setCurrentItem(item)
            if self.ui.comboBox_entity.currentIndex() == 1:
                asset_id = item.data(Qt.ItemDataRole.UserRole)
                self.load_metadata(asset_id, use_master=True)
            elif self.ui.comboBox_entity.currentIndex() == 2:
                shot_data = item.data(Qt.ItemDataRole.UserRole)
                self.load_metadata(shot_data["shot_id"], use_master=True)
            self.reload_version_metadata(use_master=True)
            self.generate_shot()
        pass

    def generate_shot(self):
        blender_program = self.ui.lineEdit_blenderPath.text().strip()
        if self.selected_path is None or not blender_program:
            QMessageBox.warning(
                self, "Warning", "Please select a path and blender program."
            )
            return
        selected_item = self.ui.listWidget_list.currentItem()
        if selected_item is None:
            return ""
        item_data = selected_item.data(Qt.ItemDataRole.UserRole)
        shot_data = [i for i in self.shots if i["id"] == item_data.get("shot_id")]
        if shot_data is None or len(shot_data) == 0:
            return ""
        shot_assets = AssetServices.get_assets_for_shot(shot_id=shot_data[0].get("id", ""))
        shot_data[0]["assets"] = shot_assets
        filepath = Path(self.selected_path)
        preset_path = (
            self.zeroxe_conf.get("departments", {})
            .get(self.ui.comboBox_department.currentText(), {})
            .get("presets", {}).get('preset', {}).get("path")
        )
        # print(shot_data[0])
        frame_in = int(shot_data[0].get("data", {}).get("frame_in", "0"))
        frame_out = int(shot_data[0].get("data", {}).get("frame_out", "0"))
        fps = int(shot_data[0].get("data", {}).get("fps", "24"))
        res_str = str(shot_data[0].get("data", {}).get("resolution", "1920x1080"))
        resolution = (
            [int(res.strip()) for res in res_str.split("x")] if "x" in res_str else []
        )
        setting_data = {
            "frame_in": frame_in,
            "frame_out": frame_out,
            "fps": fps,
            "resolution": resolution,
            "script_path": preset_path,
        }

        comp_script = self.script_builder(
            filepath=str(filepath),
            master_file=str(self.source_path),
            setting_data=setting_data,
        )

        SubprocessServices.run_command(
            [blender_program, "-b", "--python-expr", comp_script]
        )

    def script_builder(
                self, filepath: str, master_file: str, setting_data: dict
        ):
            tpl = Template(
                dedent(
                    """
    import bpy
    from pathlib import Path

    bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

    bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
    """
                )
            )
            end_script = Template(
                dedent(
                    """
    # Save the modified Blender file
    bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
    print("File saved as: $OUTPUT_PATH")

    # Quit Blender
    bpy.ops.wm.quit_blender()
    """
                )
            )
            script = tpl.substitute(
                FILEPATH=master_file,
                OUTPUT_PATH=filepath,
            )
            end_script = end_script.substitute(
                OUTPUT_PATH=filepath
            )

            script_path = setting_data.get("script_path")
            if script_path:
                with open(script_path, "r") as f:
                    preset_code = f.read()
                    script = (
                            script
                            + "\n\n"
                            + preset_code.replace("$SETTINGS", json.dumps(setting_data))
                            + "\n\n"
                    )
            script = script + end_script
            return script

    # region Path builder
    def build_shot_path(self, custom_department: str | None = None):
        selected = self.ui.listWidget_list.currentItem()  # ui data sq and shot
        if selected is None:
            return "", ""

        item_data = selected.data(Qt.ItemDataRole.UserRole)  # open sq and shot data

        selected_project_id = (
            self.ui.comboBox_project.currentData()
        )  # ui data project id
        project = next(
            (p for p in self.projects if p["id"] == selected_project_id), None
        )
        project_code = project.get("code") if project else None

        selected_department = (
                custom_department or self.ui.comboBox_department.currentText()
        )
        if not self.zeroxe_conf:
            return ""
        department_code = (
            self.zeroxe_conf.get("departments", {})
            .get(selected_department, {})
            .get("code", "")
        )

        episode_name = self.ui.comboBox_episode.currentText()  # ui data episode

        if not self.zeroxe_conf:
            QMessageBox.warning(self, "Warning", "Zeroxe conf not found.")
            return "", ""
        base_path = (
            self.zeroxe_conf.get("departments", {})
            .get(selected_department, {})
            .get("base_path", "")
        )
        if "lib" in episode_name:
            base_path = next(
                (
                    config.get("base_path", "")
                    for config in self.zeroxe_conf.get("library", {}).values()
                    if config.get("code") == episode_name
                ),
                "",
            )
            master_path = Path(f"{base_path}/{item_data.get('shot_name', '')}")
            file_path = master_path / f"{item_data.get('shot_name', '')}.blend"
            return str(master_path), str(file_path)

        if not base_path:
            QMessageBox.warning(
                self,
                "Warning",
                "Base path description not found for the selected department.",
            )
            return "", ""
        master_path = Path(base_path) / item_data.get("name", "")
        file_path = master_path / PathBuilder.build_shot_path(
            episode_name=episode_name,
            sequence_name=item_data.get("sequence_name", ""),
            shot_name=item_data.get("shot_name", ""),
        )
        file_name = PathBuilder.build_shot_name(
            project_code=str(project_code) if project_code else "",
            episode_name=episode_name,
            sequence_name=item_data.get("sequence_name", ""),
            shot_name=item_data.get("shot_name", ""),
            department_code=department_code,
        )
        return str(file_path), str(file_path / f"{file_name}.blend")

    # Entry point to get path
    def shot_or_asset_path(self, select: int = 0):
        asset_data = self.selected_item
        if asset_data is None:
            QMessageBox.warning(self, "Warning", "Please select an item.")
            return ""

        master_path, file_path = "", ""
        if self.ui.comboBox_entity.currentIndex() == 1 or select == 1:
            # Build asset path
            selected_department = self.ui.comboBox_department.currentText()
            base_path = (
                self.zeroxe_conf.get("departments", {})
                .get(selected_department, {})
                .get("asset_type", {})
                .get(asset_data["asset_type_name"], {})
                .get("base_path", "")
            )
            master_path = Path(f"{base_path}/{asset_data['name']}")
            file_path = master_path / f"{asset_data['name']}.blend"
        elif self.ui.comboBox_entity.currentIndex() == 2 or select == 2:
            # Call function to build shot path
            master_path, file_path = self.build_shot_path()
        return str(master_path), str(file_path)

    # region List search function
    def wire_search_list(self):
        le = self.ui.lineEdit_list
        if le:
            le.textChanged.connect(self.filter_list)

    def filter_list(self, text: str):
        lw = self.ui.listWidget_list
        text_low = (text or "").lower().strip()
        for i in range(lw.count()):
            item = lw.item(i)
            if item is None:
                continue
            item.setHidden(text_low not in item.text().lower())

    # endregion