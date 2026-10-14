"""Layout Scene Setup & Source Selection Dialog.

Provides interactive UI dialogs for both single-shot and batch Layout scene generation,
allowing artists to choose between:
1. Generating a clean scene from Kitsu data (camera rig, fresh linked assets, timeline, resolution).
2. Sourcing from another shot in the sequence/episode and matching casting (adding missing Kitsu assets,
   preserving all existing scene objects, and configuring timeline & resolution).
3. Sourcing from a custom .blend template file and matching casting.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def _parse_shot_identifier(
    shot_identifier: str,
    default_episode: str = "",
    default_sequence: str = "",
) -> Tuple[str, str, str]:
    """Parse shot identifier strings like 'sq01_sh0010', 'ep998_sq01_sh0010', or 'sh0010' into (episode, sequence, shot)."""
    raw = str(shot_identifier or "").strip()
    if not raw:
        return default_episode, default_sequence, ""

    parts = [p.strip() for p in raw.split("_") if p.strip()]
    if len(parts) >= 3 and (parts[0].lower().startswith("ep") or parts[0].lower().startswith("e")):
        # e.g. ep998_sq01_sh0010
        return parts[0], parts[1], "_".join(parts[2:])
    elif len(parts) == 2:
        # e.g. sq01_sh0010
        return default_episode, parts[0], parts[1]
    elif len(parts) == 1:
        # e.g. sh0010
        return default_episode, default_sequence, parts[0]
    else:
        # e.g. complex name
        return default_episode, parts[0], "_".join(parts[1:])


def _resolve_sibling_shot_layout_path(
    sibling_shot_name: str,
    shot_data: Dict[str, Any],
    current_department: Optional[Dict[str, Any]] = None,
    project_path: Optional[str] = None,
) -> Optional[Path]:
    """Resolve the Layout .blend file path for a sibling shot."""
    if not sibling_shot_name or not str(sibling_shot_name).strip():
        return None

    ep = shot_data.get("episode") or ""
    sq = shot_data.get("sequence") or ""
    proj = shot_data.get("project_name") or shot_data.get("project") or ""
    if isinstance(proj, dict):
        proj = proj.get("name", "")

    target_ep, target_sq, target_sh = _parse_shot_identifier(
        shot_identifier=sibling_shot_name,
        default_episode=ep,
        default_sequence=sq,
    )

    clean_sh = target_sh
    if target_sq and clean_sh.startswith(f"{target_sq}_"):
        clean_sh = clean_sh[len(target_sq) + 1:]

    # 1. Try via ShotPathGenerator if available
    try:
        from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator
        config_file = None
        if project_path:
            cand_pipe = Path(project_path) / "pipeline.yaml"
            if cand_pipe.is_file():
                config_file = cand_pipe
        if not config_file and Path("pipeline/pipeline.yaml").is_file():
            config_file = Path("pipeline/pipeline.yaml")

        if config_file:
            gen = ShotPathGenerator(config=config_file)
            res = gen.generate_shot_paths(
                department="Layout",
                episode=target_ep,
                sequence=target_sq,
                shot=clean_sh,
                project_path=project_path,
            )
            if res.master_path and res.master_path.is_file():
                return res.master_path
            if res.version_dir and res.version_dir.is_dir():
                v_blends = sorted(res.version_dir.glob("*.blend"))
                if v_blends:
                    return v_blends[-1]
            if res.master_path:
                return res.master_path
    except Exception:
        pass

    # 2. Try via PipelineService if available
    try:
        from zeroxe.services.pipeline_service import PipelineService
        shot_res = PipelineService.resolve_shot(
            department="Layout",
            episode=target_ep,
            sequence=target_sq,
            shot=clean_sh,
            project_name=proj if isinstance(proj, str) else None,
            project_path=project_path,
        )
        if shot_res and shot_res.master_path:
            m_path = Path(shot_res.master_path)
            if m_path.is_file():
                return m_path
            # Check version files if master doesn't exist
            versions = PipelineService.list_versions(
                department="Layout",
                episode=target_ep,
                sequence=target_sq,
                shot=clean_sh,
                project_name=proj if isinstance(proj, str) else None,
                project_path=project_path,
            )
            if versions:
                return Path(versions[-1][1])
            return m_path
    except Exception:
        pass

    # 3. Filesystem search fallback
    base_layout_dir = None
    if current_department:
        dept_cfg = current_department.get("Layout") or next(iter(current_department.values()), {})
        if isinstance(dept_cfg, dict) and dept_cfg.get("base_path"):
            b_path = dept_cfg["base_path"]
            if project_path:
                b_path = b_path.replace("@project_path@", project_path.rstrip("/\\"))
            base_layout_dir = Path(b_path)

    if base_layout_dir and base_layout_dir.exists():
        shot_dir_candidates = [
            base_layout_dir / target_ep / f"{target_ep}_{target_sq}" / f"{target_ep}_{target_sq}_{clean_sh}",
            base_layout_dir / target_sq / f"{target_sq}_{clean_sh}",
            base_layout_dir / f"{target_sq}_{clean_sh}",
            base_layout_dir / clean_sh,
        ]
        for s_dir in shot_dir_candidates:
            if s_dir.is_dir():
                master_blends = [f for f in s_dir.glob("*.blend") if f.is_file() and "progress" not in f.parts]
                if master_blends:
                    return master_blends[0]
                prog_dir = s_dir / "progress"
                if prog_dir.is_dir():
                    prog_blends = sorted(prog_dir.glob("*.blend"))
                    if prog_blends:
                        return prog_blends[-1]
                all_blends = list(s_dir.glob("*.blend"))
                if all_blends:
                    return all_blends[0]

    return None


class LayoutDialog(QDialog):
    """Dialog for choosing the setup strategy for a single Layout scene."""

    def __init__(
        self,
        shot_data: Dict[str, Any],
        current_department: Optional[Dict[str, Any]] = None,
        available_shots: Optional[List[str]] = None,
        project_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.shot_data = shot_data or {}
        self.current_department = current_department
        self.project_path = project_path
        self.available_shots = list(available_shots or [])

        self._selected_mode = "clean"  # "clean", "source_shot", "custom"
        self._selected_source_file: Optional[str] = None
        self._selected_shot_name: Optional[str] = None

        self._discover_available_shots()
        self._init_ui()

    def _discover_available_shots(self) -> None:
        """Populate sibling shots from ShotService / Kitsu matching assetList format."""
        if self.available_shots:
            return

        if self.shot_data.get("available_shots"):
            self.available_shots = list(self.shot_data["available_shots"])
            return

        ep = self.shot_data.get("episode")
        ep_id = self.shot_data.get("episode_id")
        sq = self.shot_data.get("sequence")
        current_sh_name = self.shot_data.get("name", "")
        current_display = f"{sq}_{current_sh_name}" if sq else current_sh_name

        try:
            from zeroxe.services.shot_service import ShotService
            from zeroxe.services.project_service import ProjectService

            shots_list = []
            if ep_id:
                shots_list = ShotService.get_shots_by_episode_id(ep_id, episode_name=ep or "")

            if not shots_list and ep:
                proj_name = self.shot_data.get("project_name") or (self.shot_data.get("project") or {}).get("name")
                proj_id = self.shot_data.get("project_id") or (self.shot_data.get("project") or {}).get("id")
                if not proj_id and proj_name:
                    proj = ProjectService.get_project_by_name(proj_name)
                    if proj:
                        proj_id = proj.id

                shots_list = ShotService.get_shots_by_sequence(
                    episode=ep,
                    sequence=None,
                    project_id=proj_id,
                )

            if shots_list:
                formatted_shots = []
                for s in shots_list:
                    if hasattr(s, "name"):
                        seq_name = getattr(s, "sequence", "") or ""
                        s_name = getattr(s, "name", "")
                        disp = f"{seq_name}_{s_name}" if seq_name else s_name
                    elif isinstance(s, dict):
                        seq_name = s.get("sequence", "") or ""
                        s_name = s.get("name", "")
                        disp = f"{seq_name}_{s_name}" if seq_name else s_name
                    else:
                        disp = str(s)

                    if disp and disp != current_display and disp != current_sh_name:
                        if disp not in formatted_shots:
                            formatted_shots.append(disp)

                if formatted_shots:
                    formatted_shots.sort(key=lambda x: x.lower())
                    self.available_shots = formatted_shots
        except Exception as e:
            logger.debug(f"Could not discover sibling shots from Kitsu: {e}")

    def _init_ui(self) -> None:
        sh_name = self.shot_data.get("name", "Shot")
        sq_name = self.shot_data.get("sequence", "")
        display_shot = f"{sq_name}_{sh_name}" if sq_name else sh_name

        self.setWindowTitle(f"Layout Builder - Scene Setup ({display_shot})")
        self.resize(600, 660)
        self.setMinimumSize(540, 580)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 1. Header
        header = QLabel(f"<b>Layout Scene Setup: {display_shot}</b>")
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        desc = QLabel("Select the scene generation strategy for this Layout shot:")
        desc.setWordWrap(True)
        layout.addWidget(desc, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # 2. Options Group Box
        group = QGroupBox("Layout Strategy")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(10)

        self.button_group = QButtonGroup(self)

        # Option A: Clean Kitsu Generate
        clean_box = QVBoxLayout()
        clean_box.setSpacing(2)
        self.rb_clean = QRadioButton("Generate from Kitsu data clean (Default)")
        self.button_group.addButton(self.rb_clean, 1)
        self.rb_clean.setChecked(True)
        clean_box.addWidget(self.rb_clean)

        clean_sub = QLabel(
            "<span style='color: gray; font-size: 11px; margin-left: 22px;'>"
            "Builds a fresh scene from scratch with camera rig and linked assets from Kitsu casting."
            "</span>"
        )
        clean_sub.setWordWrap(True)
        clean_box.addWidget(clean_sub)
        grp_layout.addLayout(clean_box)

        # Option B: Sibling Shot with Match Casting
        shot_box = QVBoxLayout()
        shot_box.setSpacing(6)
        self.rb_shot = QRadioButton("Source from other shot and match casting")
        self.button_group.addButton(self.rb_shot, 2)
        shot_box.addWidget(self.rb_shot, 0)

        shot_sub = QLabel(
            "<span style='color: gray; font-size: 11px; margin-left: 22px;'>"
            "Copies source shot scene, adds missing Kitsu assets, preserves existing scene elements, and updates timeline & resolution."
            "</span>"
        )
        shot_sub.setWordWrap(True)
        shot_box.addWidget(shot_sub, 0)

        # List & Search container
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(22, 2, 0, 2)
        list_layout.setSpacing(6)

        # Search / filter input
        self.edit_shot_filter = QLineEdit()
        self.edit_shot_filter.setPlaceholderText("Filter shots... (e.g. sq01_sh0010)")
        self.edit_shot_filter.setClearButtonEnabled(True)
        self.edit_shot_filter.textChanged.connect(self._filter_shot_list)
        list_layout.addWidget(self.edit_shot_filter, 0)

        # Shot List Widget
        self.list_shots = QListWidget()
        self.list_shots.setMinimumHeight(130)
        self.list_shots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._populate_shot_list(self.available_shots)
        self.list_shots.currentItemChanged.connect(self._on_list_item_changed)
        self.list_shots.itemClicked.connect(lambda _: self.rb_shot.setChecked(True))
        list_layout.addWidget(self.list_shots, 1)

        # Compact preview status frame
        self.preview_frame = QFrame()
        self.preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.preview_frame.setMinimumHeight(38)
        self.preview_frame.setStyleSheet(
            "QFrame { background-color: rgba(128, 128, 128, 0.08); border-radius: 4px; border: 1px solid rgba(128, 128, 128, 0.18); }"
        )
        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setContentsMargins(8, 6, 8, 6)
        preview_inner.setSpacing(0)

        self.shot_path_preview = QLabel("Select a shot from the list to preview template file")
        self.shot_path_preview.setWordWrap(True)
        self.shot_path_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.shot_path_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.shot_path_preview.setStyleSheet("QLabel { background: transparent; border: none; font-size: 11px; color: gray; }")
        preview_inner.addWidget(self.shot_path_preview)

        list_layout.addWidget(self.preview_frame, 0)
        shot_box.addWidget(list_container, 1)
        grp_layout.addLayout(shot_box, 1)

        # Option C: Custom File
        custom_box = QVBoxLayout()
        self.rb_custom = QRadioButton("Use Custom .blend File and match casting")
        self.button_group.addButton(self.rb_custom, 3)
        custom_box.addWidget(self.rb_custom, 0)

        custom_file_layout = QHBoxLayout()
        custom_file_layout.setContentsMargins(22, 0, 0, 0)
        self.edit_custom_path = QLineEdit()
        self.edit_custom_path.setPlaceholderText("/path/to/custom_template.blend")
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_custom_file)
        custom_file_layout.addWidget(self.edit_custom_path)
        custom_file_layout.addWidget(self.btn_browse)
        custom_box.addLayout(custom_file_layout)

        grp_layout.addLayout(custom_box, 0)
        layout.addWidget(group, 1)

        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Generate Layout")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_accept)

        # High-visibility styling for confirmation
        self.btn_ok.setStyleSheet(
            "QPushButton { background-color: #2b78e4; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3b88f4; }"
            "QPushButton:pressed { background-color: #1b68d4; }"
        )

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout, 0)

        # Interaction signals
        self.button_group.buttonToggled.connect(self._on_mode_changed)

    def _populate_shot_list(self, shots: List[str]) -> None:
        self.list_shots.clear()
        for s in shots:
            item = QListWidgetItem(str(s))
            self.list_shots.addItem(item)

    def set_selected_shot(self, shot_name: str) -> None:
        """Helper to programmatically select a shot in the list."""
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if item.text().strip() == shot_name.strip():
                self.list_shots.setCurrentItem(item)
                self.rb_shot.setChecked(True)
                return

    def _filter_shot_list(self, text: str) -> None:
        query = text.strip().lower()
        for idx in range(self.list_shots.count()):
            item = self.list_shots.item(idx)
            item.setHidden(query not in item.text().lower())

    def _on_list_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self.shot_path_preview.setText("No shot selected.")
            return

        shot_name = current.text().strip()
        path = _resolve_sibling_shot_layout_path(
            sibling_shot_name=shot_name,
            shot_data=self.shot_data,
            current_department=self.current_department,
            project_path=self.project_path,
        )
        if path:
            exists = path.is_file()
            color = "#2e7d32" if exists else "#e65100"
            status = "Ready" if exists else "File not created yet"
            self.shot_path_preview.setText(
                f"<span style='color: {color}; font-weight: bold;'>[{status}]</span> "
                f"<span style='color: gray; font-size: 11px;'>{path}</span>"
            )
        else:
            self.shot_path_preview.setText(
                "<span style='color: #c62828;'>[Warning]</span> Could not resolve Layout file path for this shot."
            )

    def _browse_custom_file(self) -> None:
        self.rb_custom.setChecked(True)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom .blend Template File",
            "",
            "Blender Files (*.blend);;All Files (*)",
        )
        if file_path:
            self.edit_custom_path.setText(file_path)

    def _on_mode_changed(self, button: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        if button == self.rb_clean:
            self.list_shots.setEnabled(False)
            self.edit_shot_filter.setEnabled(False)
            self.edit_custom_path.setEnabled(False)
            self.btn_browse.setEnabled(False)
        elif button == self.rb_shot:
            self.list_shots.setEnabled(True)
            self.edit_shot_filter.setEnabled(True)
            self.edit_custom_path.setEnabled(False)
            self.btn_browse.setEnabled(False)
        elif button == self.rb_custom:
            self.list_shots.setEnabled(False)
            self.edit_shot_filter.setEnabled(False)
            self.edit_custom_path.setEnabled(True)
            self.btn_browse.setEnabled(True)

    def _on_accept(self) -> None:
        if self.rb_clean.isChecked():
            self._selected_mode = "clean"
            self._selected_source_file = None
            self._selected_shot_name = None
            self.accept()
        elif self.rb_shot.isChecked():
            curr = self.list_shots.currentItem()
            if not curr:
                QMessageBox.warning(self, "No Shot Selected", "Please select a shot from the list to use as source.")
                return
            shot_name = curr.text().strip()
            path = _resolve_sibling_shot_layout_path(
                sibling_shot_name=shot_name,
                shot_data=self.shot_data,
                current_department=self.current_department,
                project_path=self.project_path,
            )
            if not path or not path.is_file():
                reply = QMessageBox.warning(
                    self,
                    "Source File Missing",
                    f"The Layout .blend file for '{shot_name}' was not found on disk yet:\n\n{path or 'Path unresolvable'}\n\n"
                    "Do you still want to proceed with this source shot?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            self._selected_mode = "source_shot"
            self._selected_shot_name = shot_name
            self._selected_source_file = str(path) if path else ""
            self.accept()
        elif self.rb_custom.isChecked():
            custom_path_str = self.edit_custom_path.text().strip()
            if not custom_path_str:
                QMessageBox.warning(self, "Missing File", "Please select a custom .blend file.")
                return
            custom_p = Path(custom_path_str)
            if not custom_p.is_file():
                QMessageBox.warning(self, "File Not Found", f"The custom template file does not exist:\n{custom_p}")
                return
            self._selected_mode = "custom"
            self._selected_source_file = str(custom_p)
            self._selected_shot_name = None
            self.accept()

    def get_result(self) -> Dict[str, Any]:
        """Return user selections dictionary."""
        mode = "clean"
        shot_name = self._selected_shot_name
        source_file = self._selected_source_file

        if hasattr(self, "rb_shot") and self.rb_shot.isChecked():
            mode = "source_shot"
            curr = self.list_shots.currentItem()
            shot_name = curr.text().strip() if curr else self._selected_shot_name
            if shot_name:
                p = _resolve_sibling_shot_layout_path(
                    sibling_shot_name=shot_name,
                    shot_data=self.shot_data,
                    current_department=self.current_department,
                    project_path=self.project_path,
                )
                source_file = str(p) if p else (self._selected_source_file or "")
        elif hasattr(self, "rb_custom") and self.rb_custom.isChecked():
            mode = "custom"
            custom_val = self.edit_custom_path.text().strip()
            source_file = custom_val if custom_val else self._selected_source_file
            shot_name = None

        return {
            "layout_mode": mode,
            "source_file": source_file,
            "source_shot": shot_name,
        }


class LayoutBatchDialog(QDialog):
    """Dialog for choosing the Layout generation strategy during Batch execution."""

    def __init__(
        self,
        selected_items: List[Any],
        available_shots: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.selected_items = selected_items or []
        self.available_shots = list(available_shots or [])
        self._selected_mode = "clean"
        self._selected_shot_name: Optional[str] = None
        self._selected_source_file: Optional[str] = None

        self._discover_available_shots()
        self._init_ui()

    def _discover_available_shots(self) -> None:
        """Populate available shots for batch template selection identical to assetList."""
        if self.available_shots:
            return

        shot_names = []
        for item in self.selected_items:
            s_name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else None)
            sq_name = getattr(item, "sequence", None) or (item.get("sequence") if isinstance(item, dict) else None)
            disp = f"{sq_name}_{s_name}" if sq_name else s_name
            if disp and disp not in shot_names:
                shot_names.append(disp)

        if self.selected_items:
            first = self.selected_items[0]
            ep = getattr(first, "episode", None) or (first.get("episode") if isinstance(first, dict) else None)
            ep_id = getattr(first, "episode_id", None) or (first.get("episode_id") if isinstance(first, dict) else None)
            try:
                from zeroxe.services.shot_service import ShotService
                shots_raw = []
                if ep_id:
                    shots_raw = ShotService.get_shots_by_episode_id(ep_id, episode_name=ep or "")
                elif ep:
                    shots_raw = ShotService.get_shots_by_sequence(episode=ep)

                for s in shots_raw:
                    seq_name = getattr(s, "sequence", "") or ""
                    s_name = getattr(s, "name", "")
                    disp = f"{seq_name}_{s_name}" if seq_name else s_name
                    if disp and disp not in shot_names:
                        shot_names.append(disp)
            except Exception:
                pass

        if shot_names:
            shot_names.sort(key=lambda x: x.lower())
            self.available_shots = shot_names

    def _init_ui(self) -> None:
        count = len(self.selected_items)
        self.setWindowTitle("Batch Layout - Scene Setup")
        self.resize(600, 620)
        self.setMinimumSize(540, 550)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 1. Header
        header = QLabel(f"<b>Batch Layout Generation ({count} shots selected)</b>")
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        desc = QLabel(
            "Choose how Layout scenes should be generated for all selected shots:"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # 2. Options Group
        group = QGroupBox("Batch Generation Strategy")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(10)

        self.button_group = QButtonGroup(self)

        # Option A: Clean Kitsu Generate for all
        self.rb_clean = QRadioButton("Generate from Kitsu data clean for all shots (Default)")
        self.button_group.addButton(self.rb_clean, 1)
        self.rb_clean.setChecked(True)
        grp_layout.addWidget(self.rb_clean, 0)

        # Option B: Single Hero Shot for all
        shot_box = QVBoxLayout()
        shot_box.setSpacing(6)
        self.rb_shot = QRadioButton("Source from a single shot and match casting for each shot")
        self.button_group.addButton(self.rb_shot, 2)
        shot_box.addWidget(self.rb_shot, 0)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(22, 2, 0, 2)
        list_layout.setSpacing(6)

        # Search filter
        self.edit_shot_filter = QLineEdit()
        self.edit_shot_filter.setPlaceholderText("Filter shots... (e.g. sq01_sh0010)")
        self.edit_shot_filter.setClearButtonEnabled(True)
        self.edit_shot_filter.textChanged.connect(self._filter_shot_list)
        list_layout.addWidget(self.edit_shot_filter, 0)

        # List Widget
        self.list_shots = QListWidget()
        self.list_shots.setMinimumHeight(130)
        self.list_shots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._populate_shot_list(self.available_shots)
        self.list_shots.currentItemChanged.connect(self._on_list_item_changed)
        self.list_shots.itemClicked.connect(lambda _: self.rb_shot.setChecked(True))
        list_layout.addWidget(self.list_shots, 1)

        # Status Preview
        self.shot_path_preview = QLabel("Select a shot from the list to preview template file")
        self.shot_path_preview.setWordWrap(True)
        self.shot_path_preview.setStyleSheet("QLabel { font-size: 11px; color: gray; padding: 4px; background: rgba(128,128,128,0.08); border-radius: 4px; }")
        list_layout.addWidget(self.shot_path_preview, 0)

        shot_box.addWidget(list_container, 1)
        grp_layout.addLayout(shot_box, 1)

        # Option C: Custom template file for all
        custom_box = QVBoxLayout()
        self.rb_custom = QRadioButton("Use Custom .blend File for all shots and match casting")
        self.button_group.addButton(self.rb_custom, 3)
        custom_box.addWidget(self.rb_custom, 0)

        custom_file_layout = QHBoxLayout()
        custom_file_layout.setContentsMargins(22, 0, 0, 0)
        self.edit_custom_path = QLineEdit()
        self.edit_custom_path.setPlaceholderText("/path/to/custom_template.blend")
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_custom_file)
        custom_file_layout.addWidget(self.edit_custom_path)
        custom_file_layout.addWidget(self.btn_browse)
        custom_box.addLayout(custom_file_layout)

        grp_layout.addLayout(custom_box, 0)
        layout.addWidget(group, 1)

        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Confirm Batch Generation")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_accept)

        self.btn_ok.setStyleSheet(
            "QPushButton { background-color: #2b78e4; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3b88f4; }"
            "QPushButton:pressed { background-color: #1b68d4; }"
        )

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout, 0)

        self.button_group.buttonToggled.connect(self._on_mode_changed)

    def _populate_shot_list(self, shots: List[str]) -> None:
        self.list_shots.clear()
        for s in shots:
            item = QListWidgetItem(str(s))
            self.list_shots.addItem(item)

    def set_selected_shot(self, shot_name: str) -> None:
        """Helper to programmatically select a shot in the list."""
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if item.text().strip() == shot_name.strip():
                self.list_shots.setCurrentItem(item)
                self.rb_shot.setChecked(True)
                return

    def _filter_shot_list(self, text: str) -> None:
        query = text.strip().lower()
        for idx in range(self.list_shots.count()):
            item = self.list_shots.item(idx)
            item.setHidden(query not in item.text().lower())

    def _on_list_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self.shot_path_preview.setText("<span style='color: gray; font-size: 11px;'>No shot selected</span>")
            return

        shot_name = current.text().strip()
        self._selected_shot_name = shot_name
        self.shot_path_preview.setText(
            f"<span style='color: #2563eb; font-weight: bold; font-size: 11px;'>[Selected Template Shot]</span> "
            f"<span style='font-size: 11px;'><b>{shot_name}</b> (used as template for all selected batch shots)</span>"
        )

    def _browse_custom_file(self) -> None:
        self.rb_custom.setChecked(True)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom .blend Template File",
            "",
            "Blender Files (*.blend);;All Files (*)",
        )
        if file_path:
            self.edit_custom_path.setText(file_path)

    def _on_mode_changed(self, button: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        if button == self.rb_clean:
            self.list_shots.setEnabled(False)
            self.edit_shot_filter.setEnabled(False)
            self.edit_custom_path.setEnabled(False)
            self.btn_browse.setEnabled(False)
        elif button == self.rb_shot:
            self.list_shots.setEnabled(True)
            self.edit_shot_filter.setEnabled(True)
            self.edit_custom_path.setEnabled(False)
            self.btn_browse.setEnabled(False)
        elif button == self.rb_custom:
            self.list_shots.setEnabled(False)
            self.edit_shot_filter.setEnabled(False)
            self.edit_custom_path.setEnabled(True)
            self.btn_browse.setEnabled(True)

    def _on_accept(self) -> None:
        if self.rb_clean.isChecked():
            self._selected_mode = "clean"
            self._selected_shot_name = None
            self._selected_source_file = None
            self.accept()
        elif self.rb_shot.isChecked():
            curr = self.list_shots.currentItem()
            if curr:
                self._selected_shot_name = curr.text().strip()
            elif not self._selected_shot_name:
                QMessageBox.warning(self, "No Shot Selected", "Please select a shot to use as template.")
                return
            self._selected_mode = "source_shot"
            self.accept()
        elif self.rb_custom.isChecked():
            custom_path_str = self.edit_custom_path.text().strip()
            if not custom_path_str:
                QMessageBox.warning(self, "Missing File", "Please select a custom .blend template file.")
                return
            custom_p = Path(custom_path_str)
            if not custom_p.is_file():
                QMessageBox.warning(self, "File Not Found", f"The custom template file does not exist:\n{custom_p}")
                return
            self._selected_mode = "custom"
            self._selected_source_file = str(custom_p)
            self._selected_shot_name = None
            self.accept()

    def get_result(self) -> Dict[str, Any]:
        """Return user selections dictionary."""
        mode = "clean"
        shot_name = self._selected_shot_name
        source_file = self._selected_source_file

        if hasattr(self, "rb_shot") and self.rb_shot.isChecked():
            mode = "source_shot"
            curr = self.list_shots.currentItem()
            if curr:
                shot_name = curr.text().strip()
            elif not shot_name:
                shot_name = self._selected_shot_name
        elif hasattr(self, "rb_custom") and self.rb_custom.isChecked():
            mode = "custom"
            custom_val = self.edit_custom_path.text().strip()
            source_file = custom_val if custom_val else self._selected_source_file
            shot_name = None

        return {
            "layout_mode": mode,
            "source_file": source_file,
            "source_shot": shot_name,
        }
