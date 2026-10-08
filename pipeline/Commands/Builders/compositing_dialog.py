"""Compositing Mastershot Selection Dialog.

Provides interactive UI dialogs for both single-shot and batch Compositing scene generation,
allowing artists to choose between:
1. Using the Kitsu MS_COMP asset cast in the shot.
2. Using another shot in the sequence/episode as the mastershot template (via searchable list matching assetList).
3. Browsing for a custom .blend template file.
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


def _resolve_sibling_shot_comp_path(
    sibling_shot_name: str,
    shot_data: Dict[str, Any],
    current_department: Optional[Dict[str, Any]] = None,
    project_path: Optional[str] = None,
) -> Optional[Path]:
    """Resolve the compositing .blend file path for a sibling shot."""
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

    # 1. Try via PipelineService if available
    try:
        from zeroxe.services.pipeline_service import PipelineService
        shot_res = PipelineService.resolve_shot(
            department="Compositing",
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
                department="Compositing",
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

    # 2. Try via ShotPathGenerator if available
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
                department="Compositing",
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

    # 3. Filesystem search fallback
    base_comp_dir = None
    if current_department:
        dept_cfg = current_department.get("Compositing") or next(iter(current_department.values()), {})
        if isinstance(dept_cfg, dict) and dept_cfg.get("base_path"):
            b_path = dept_cfg["base_path"]
            if project_path:
                b_path = b_path.replace("@project_path@", project_path.rstrip("/\\"))
            base_comp_dir = Path(b_path)

    if base_comp_dir and base_comp_dir.exists():
        shot_dir_candidates = [
            base_comp_dir / target_ep / f"{target_ep}_{target_sq}" / f"{target_ep}_{target_sq}_{clean_sh}",
            base_comp_dir / target_sq / f"{target_sq}_{clean_sh}",
            base_comp_dir / f"{target_sq}_{clean_sh}",
            base_comp_dir / clean_sh,
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


class CompositingDialog(QDialog):
    """Dialog for selecting the Mastershot template for a single Compositing scene."""

    def __init__(
        self,
        shot_data: Dict[str, Any],
        kitsu_ms_comp_file: Optional[Path] = None,
        kitsu_ms_comp_name: str = "",
        current_department: Optional[Dict[str, Any]] = None,
        available_shots: Optional[List[str]] = None,
        project_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.shot_data = shot_data or {}
        self.kitsu_ms_comp_file = kitsu_ms_comp_file
        self.kitsu_ms_comp_name = kitsu_ms_comp_name
        self.current_department = current_department
        self.project_path = project_path
        self.available_shots = list(available_shots or [])

        self._selected_mode = "kitsu"  # "kitsu", "shot", "custom"
        self._selected_master_file: Optional[str] = None
        self._selected_shot_name: Optional[str] = None

        self._discover_available_shots()
        self._init_ui()

    def _discover_available_shots(self) -> None:
        """Populate sibling shots from ShotService / Kitsu exactly matching assetList format."""
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

        self.setWindowTitle(f"Compositing Builder - Select Mastershot ({display_shot})")
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
        header = QLabel(f"<b>Compositing Scene Setup: {display_shot}</b>")
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        desc = QLabel(
            "Select the template source file for this Compositing scene:"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # 2. Radio Button Group Box
        group = QGroupBox("Mastershot Source")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(10)

        self.button_group = QButtonGroup(self)

        # Option A: Kitsu MS_COMP Asset
        kitsu_has_ms = bool(self.kitsu_ms_comp_file and str(self.kitsu_ms_comp_file).strip())
        kitsu_label = f"Use Kitsu MS_COMP ({self.kitsu_ms_comp_name})" if self.kitsu_ms_comp_name else "Use Kitsu MS_COMP"
        if not kitsu_has_ms:
            kitsu_label += "  [Not Cast in Kitsu]"

        self.rb_kitsu = QRadioButton(kitsu_label)
        self.button_group.addButton(self.rb_kitsu, 1)
        grp_layout.addWidget(self.rb_kitsu, 0)

        if kitsu_has_ms:
            ms_path_lbl = QLabel(f"<span style='color: gray; font-size: 11px;'>Path: {self.kitsu_ms_comp_file}</span>")
            ms_path_lbl.setWordWrap(True)
            grp_layout.addWidget(ms_path_lbl, 0)

        # Option B: Sibling Shot as Mastershot (Searchable List)
        shot_box = QVBoxLayout()
        shot_box.setSpacing(6)
        self.rb_shot = QRadioButton("Use Another Shot as Mastershot")
        self.button_group.addButton(self.rb_shot, 2)
        shot_box.addWidget(self.rb_shot, 0)

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

        # Shot List Widget - expands to take all vertical space smoothly
        self.list_shots = QListWidget()
        self.list_shots.setMinimumHeight(130)
        self.list_shots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._populate_shot_list(self.available_shots)
        self.list_shots.currentItemChanged.connect(self._on_list_item_changed)
        self.list_shots.itemClicked.connect(lambda _: self.rb_shot.setChecked(True))
        list_layout.addWidget(self.list_shots, 1)

        # Compact preview status frame (fixed height container, prevents overlapping and whitespace)
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
        self.rb_custom = QRadioButton("Use Custom .blend File")
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

        # Default selection: Kitsu if available, otherwise Shot list
        if kitsu_has_ms:
            self.rb_kitsu.setChecked(True)
        elif self.available_shots:
            self.rb_shot.setChecked(True)
        else:
            self.rb_custom.setChecked(True)

        if self.list_shots.count() > 0:
            self.list_shots.setCurrentRow(0)

        # 3. Action Buttons
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Generate Compositing Scene")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_accept)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box, 0)

    def _populate_shot_list(self, shots: List[str]) -> None:
        self.list_shots.clear()
        for s in shots:
            item = QListWidgetItem(str(s))
            self.list_shots.addItem(item)

    def _filter_shot_list(self, filter_text: str) -> None:
        query = (filter_text or "").strip().lower()
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if not query:
                item.setHidden(False)
            else:
                item.setHidden(query not in item.text().lower())

    def _on_list_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self.shot_path_preview.setText("<span style='color: gray; font-size: 11px;'>No shot selected</span>")
            return
        shot_name = current.text().strip()
        self._selected_shot_name = shot_name
        self._on_shot_selection_changed(shot_name)

    def _browse_custom_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom Compositing .blend Template",
            "",
            "Blender Files (*.blend);;All Files (*)",
        )
        if file_path:
            self.edit_custom_path.setText(file_path)
            self.rb_custom.setChecked(True)

    def _on_shot_selection_changed(self, shot_name: str) -> None:
        if not shot_name:
            self.shot_path_preview.setText("<span style='color: gray; font-size: 11px;'>No shot selected</span>")
            return
        resolved = _resolve_sibling_shot_comp_path(
            sibling_shot_name=shot_name,
            shot_data=self.shot_data,
            current_department=self.current_department,
            project_path=self.project_path,
        )
        if resolved:
            exists = resolved.is_file()
            status = "✓ Exists" if exists else "⚠️ File not created yet"
            color = "#16a34a" if exists else "#ca8a04"
            self.shot_path_preview.setText(
                f"<span style='color: {color}; font-weight: bold; font-size: 11px;'>[{status}]</span> "
                f"<span style='font-size: 11px;'>{resolved}</span>"
            )
        else:
            self.shot_path_preview.setText(
                "<span style='color: gray; font-size: 11px;'>No template file found for this shot yet</span>"
            )

    def set_selected_shot(self, shot_name: str) -> None:
        """Helper to programmatically select a shot in the list."""
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if item.text().strip() == shot_name.strip():
                self.list_shots.setCurrentItem(item)
                self.rb_shot.setChecked(True)
                return

    def _on_accept(self) -> None:
        if self.rb_kitsu.isChecked():
            self._selected_mode = "kitsu"
            self._selected_master_file = str(self.kitsu_ms_comp_file) if self.kitsu_ms_comp_file else None
        elif self.rb_shot.isChecked():
            self._selected_mode = "shot"
            cur_item = self.list_shots.currentItem()
            chosen_shot = cur_item.text().strip() if cur_item else (self._selected_shot_name or "")
            self._selected_shot_name = chosen_shot
            resolved = _resolve_sibling_shot_comp_path(
                sibling_shot_name=chosen_shot,
                shot_data=self.shot_data,
                current_department=self.current_department,
                project_path=self.project_path,
            )
            self._selected_master_file = str(resolved) if resolved else None
        elif self.rb_custom.isChecked():
            self._selected_mode = "custom"
            custom_p = self.edit_custom_path.text().strip()
            if not custom_p:
                QMessageBox.warning(self, "Missing File", "Please select a custom .blend file.")
                return
            self._selected_master_file = custom_p

        self.accept()

    def get_result(self) -> Dict[str, Any]:
        """Return user selections dictionary."""
        return {
            "master_mode": self._selected_mode,
            "master_file": self._selected_master_file,
            "master_shot": self._selected_shot_name,
        }


class CompositingBatchDialog(QDialog):
    """Dialog for choosing the Mastershot template strategy during Batch Compositing generation."""

    def __init__(
        self,
        selected_items: List[Any],
        available_shots: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.selected_items = selected_items or []
        self.available_shots = list(available_shots or [])
        self._selected_shot_name: Optional[str] = None

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

        # Try discovering all shots in the episode from Kitsu / ShotService
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
        self.setWindowTitle("Batch Compositing - Mastershot Setup")
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
        header = QLabel(f"<b>Batch Compositing Generation ({count} shots selected)</b>")
        title_font = QFont()
        title_font.setPointSize(11)
        header.setFont(title_font)
        layout.addWidget(header, 0)

        desc = QLabel(
            "Choose how Mastershot templates should be assigned for all selected shots:"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider, 0)

        # 2. Options Group
        group = QGroupBox("Batch Template Mode")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(10)

        self.button_group = QButtonGroup(self)

        # Option A: Individual Kitsu MS_COMP per shot
        self.rb_kitsu = QRadioButton("Use each shot's Kitsu MS_COMP asset (Default)")
        self.button_group.addButton(self.rb_kitsu, 1)
        self.rb_kitsu.setChecked(True)
        grp_layout.addWidget(self.rb_kitsu, 0)

        # Option B: Single Hero Shot for all (Searchable List)
        shot_box = QVBoxLayout()
        shot_box.setSpacing(6)
        self.rb_shot = QRadioButton("Use a Single Master Shot for all selected shots")
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

        # List Widget - expands smoothly to fill vertical space
        self.list_shots = QListWidget()
        self.list_shots.setMinimumHeight(130)
        self.list_shots.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._populate_shot_list(self.available_shots)
        self.list_shots.currentItemChanged.connect(self._on_list_item_changed)
        self.list_shots.itemClicked.connect(lambda _: self.rb_shot.setChecked(True))
        list_layout.addWidget(self.list_shots, 1)

        # Compact preview status card container
        self.preview_frame = QFrame()
        self.preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.preview_frame.setMinimumHeight(34)
        self.preview_frame.setStyleSheet(
            "QFrame { background-color: rgba(128, 128, 128, 0.08); border-radius: 4px; border: 1px solid rgba(128, 128, 128, 0.18); }"
        )
        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setContentsMargins(8, 6, 8, 6)
        preview_inner.setSpacing(0)

        self.shot_path_preview = QLabel("Select a master shot above for all items")
        self.shot_path_preview.setWordWrap(True)
        self.shot_path_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.shot_path_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.shot_path_preview.setStyleSheet("QLabel { background: transparent; border: none; font-size: 11px; color: gray; }")
        preview_inner.addWidget(self.shot_path_preview)

        list_layout.addWidget(self.preview_frame, 0)

        shot_box.addWidget(list_container, 1)
        grp_layout.addLayout(shot_box, 1)

        # Option C: Custom File for all
        custom_box = QVBoxLayout()
        self.rb_custom = QRadioButton("Use Custom .blend Template File for all shots")
        self.button_group.addButton(self.rb_custom, 3)
        custom_box.addWidget(self.rb_custom, 0)

        custom_layout = QHBoxLayout()
        custom_layout.setContentsMargins(22, 0, 0, 0)
        self.edit_custom_path = QLineEdit()
        self.edit_custom_path.setPlaceholderText("/path/to/template.blend")
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_custom_file)
        custom_layout.addWidget(self.edit_custom_path)
        custom_layout.addWidget(self.btn_browse)
        custom_box.addLayout(custom_layout)
        grp_layout.addLayout(custom_box, 0)

        layout.addWidget(group, 1)

        if self.list_shots.count() > 0:
            self.list_shots.setCurrentRow(0)

        # 3. Action Buttons
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Start Batch Generation")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_accept)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box, 0)

    def _populate_shot_list(self, shots: List[str]) -> None:
        self.list_shots.clear()
        for s in shots:
            item = QListWidgetItem(str(s))
            self.list_shots.addItem(item)

    def _filter_shot_list(self, filter_text: str) -> None:
        query = (filter_text or "").strip().lower()
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if not query:
                item.setHidden(False)
            else:
                item.setHidden(query not in item.text().lower())

    def _on_list_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self.shot_path_preview.setText("<span style='color: gray; font-size: 11px;'>No shot selected</span>")
            return
        shot_name = current.text().strip()
        self._selected_shot_name = shot_name
        self.shot_path_preview.setText(
            f"<span style='color: #2563eb; font-weight: bold; font-size: 11px;'>[Selected Mastershot]</span> "
            f"<span style='font-size: 11px;'><b>{shot_name}</b> (applied to all selected batch shots)</span>"
        )

    def set_selected_shot(self, shot_name: str) -> None:
        """Helper to programmatically select a shot in the list."""
        for i in range(self.list_shots.count()):
            item = self.list_shots.item(i)
            if item.text().strip() == shot_name.strip():
                self.list_shots.setCurrentItem(item)
                self.rb_shot.setChecked(True)
                return

    def _browse_custom_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom Mastershot .blend Template",
            "",
            "Blender Files (*.blend);;All Files (*)",
        )
        if file_path:
            self.edit_custom_path.setText(file_path)
            self.rb_custom.setChecked(True)

    def _on_accept(self) -> None:
        if self.rb_shot.isChecked():
            cur_item = self.list_shots.currentItem()
            if cur_item:
                self._selected_shot_name = cur_item.text().strip()
        elif self.rb_custom.isChecked():
            if not self.edit_custom_path.text().strip():
                QMessageBox.warning(self, "Missing File", "Please select a custom .blend template file.")
                return
        self.accept()

    def get_result(self) -> Dict[str, Any]:
        """Return selected batch parameters dictionary."""
        if self.rb_shot.isChecked():
            cur_item = self.list_shots.currentItem()
            chosen_shot = cur_item.text().strip() if cur_item else (self._selected_shot_name or "")
            return {
                "master_mode": "shot",
                "master_shot": chosen_shot,
            }
        elif self.rb_custom.isChecked():
            return {
                "master_mode": "custom",
                "master_file": self.edit_custom_path.text().strip(),
            }
        return {
            "master_mode": "kitsu",
        }

