"""Lighting Asset Layer Selection Dialog.

Provides an interactive pop-up UI during Lighting scene generation allowing artists
to select which shot assets belong to the Foreground (fg) layer versus Background (bg).
"""

from typing import Any, Dict, List, Optional, Set
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LightingAssetDialog(QDialog):
    """Dialog for assigning shot assets to Foreground (fg) or Background (bg) layers."""

    def __init__(
        self,
        shot_data: Dict[str, Any],
        asset_department: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.shot_data = shot_data or {}
        self.asset_department = asset_department or {}
        self._checkbox_map: Dict[str, QCheckBox] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        shot_name = self.shot_data.get("name", "Shot")
        seq_name = self.shot_data.get("sequence", "")
        display_shot = f"{seq_name}_{shot_name}" if seq_name else shot_name

        self.setWindowTitle(f"Lighting Builder - Asset Layers ({display_shot})")
        self.resize(460, 480)
        self.setMinimumSize(400, 360)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Header Title & Description
        header_label = QLabel(f"<b>Lighting Scene Setup: {display_shot}</b>")
        title_font = QFont()
        title_font.setPointSize(11)
        header_label.setFont(title_font)
        main_layout.addWidget(header_label)

        desc_label = QLabel(
            "Select assets to place in the <b>Foreground (fg)</b> collection.<br>"
            "Unselected assets and background elements will be placed in <b>Background (bg)</b>."
        )
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(divider)

        # 2. Scrollable Asset List
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(12, 12, 12, 12)

        # Categorize assets (characters, props, vehicles, others)
        categorized_assets = self._categorize_shot_assets()

        has_any_assets = False
        for cat_label, asset_items in categorized_assets.items():
            if not asset_items:
                continue
            has_any_assets = True

            group = QGroupBox(f"{cat_label} ({len(asset_items)})")
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(6)

            for asset_name in asset_items:
                cb = QCheckBox(f"{asset_name}  →  [FG]")
                # Default characters/props to checked (FG), or user can toggle
                cb.setChecked(True)
                self._checkbox_map[asset_name] = cb
                group_layout.addWidget(cb)

            container_layout.addWidget(group)

        if not has_any_assets:
            no_assets_lbl = QLabel("No character, prop, or vehicle assets found for this shot.\nAll animated elements in the ANM file will be routed to bg.")
            no_assets_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(no_assets_lbl)

        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # 3. Quick Action Buttons (Select All / Deselect All)
        if has_any_assets:
            quick_box = QHBoxLayout()
            btn_all_fg = QPushButton("Select All FG")
            btn_all_fg.clicked.connect(self._select_all)
            btn_none_fg = QPushButton("Deselect All (All to BG)")
            btn_none_fg.clicked.connect(self._deselect_all)

            quick_box.addWidget(btn_all_fg)
            quick_box.addWidget(btn_none_fg)
            quick_box.addStretch()
            main_layout.addLayout(quick_box)

        # 4. Dialog Buttons (OK / Cancel)
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Generate Lighting Scene")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        main_layout.addLayout(btn_box)

    def _categorize_shot_assets(self) -> Dict[str, List[str]]:
        """Group shot assets by type (Characters, Props, Vehicles, Others), ignoring Set & MS."""
        raw_assets = self.shot_data.get("assets", []) or []
        if not raw_assets and self.shot_data.get("id"):
            try:
                import gazu
                raw_assets = gazu.asset.all_assets_for_shot(self.shot_data["id"]) or []
            except Exception:
                try:
                    from zeroxe.services.shot_service import ShotService
                    raw_assets = ShotService.get_assets_for_shot(self.shot_data["id"]) or []
                except Exception:
                    pass

        asset_types = self.asset_department.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in self.asset_department:
            asset_types = self.asset_department.get("asset_type", {})

        type_map = {}
        for cat_key, cfg in asset_types.items():
            if isinstance(cfg, dict):
                tid = cfg.get("id") or cfg.get("kitsu_id")
                if tid:
                    type_map[str(tid)] = (cat_key, cfg)

        groups: Dict[str, List[str]] = {
            "Characters": [],
            "Props": [],
            "Vehicles": [],
            "Other Assets": [],
        }

        seen = set()
        for a in raw_assets:
            if isinstance(a, dict):
                name = a.get("name", "").strip()
                type_id = str(a.get("entity_type_id", ""))
            elif hasattr(a, "name"):
                name = getattr(a, "name", "").strip()
                type_id = str(getattr(a, "entity_type_id", getattr(a, "asset_type_id", "")))
            else:
                continue

            if not name or name in seen:
                continue
            seen.add(name)

            category_key = ""
            if type_id in type_map:
                category_key = type_map[type_id][0].lower()

            # Filter out Set (s-*) and Mastershot (ms_*)
            if category_key == "set" or name.startswith("s-"):
                continue
            if category_key.startswith("ms_") or name.startswith("ms_") or name.startswith("LIT_") or name.startswith("COMP_"):
                continue

            # Categorize by prefix or category key
            if category_key == "char" or name.startswith("c-"):
                groups["Characters"].append(name)
            elif category_key == "props" or name.startswith("p-"):
                groups["Props"].append(name)
            elif category_key == "vehicle" or name.startswith("v-"):
                groups["Vehicles"].append(name)
            else:
                groups["Other Assets"].append(name)

        return groups

    def _select_all(self) -> None:
        for cb in self._checkbox_map.values():
            cb.setChecked(True)

    def _deselect_all(self) -> None:
        for cb in self._checkbox_map.values():
            cb.setChecked(False)

    def get_selected_fg_assets(self) -> List[str]:
        """Return list of asset names selected for the Foreground (fg) layer."""
        return [
            name
            for name, cb in self._checkbox_map.items()
            if cb.isChecked()
        ]


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    mock_shot = {
        "name": "sh0010",
        "sequence": "sq01",
        "assets": [
            {"name": "c-hero", "entity_type_id": "1"},
            {"name": "c-villain", "entity_type_id": "1"},
            {"name": "p-sword", "entity_type_id": "2"},
            {"name": "v-car", "entity_type_id": "3"},
            {"name": "s-forest", "entity_type_id": "4"},
        ],
    }
    mock_assets = {
        "Asset": {
            "asset_type": {
                "CHAR": {"id": "1", "code": "chr", "prefix": "c-"},
                "PROPS": {"id": "2", "code": "prp", "prefix": "p-"},
                "VEHICLE": {"id": "3", "code": "vhc", "prefix": "v-"},
                "SET": {"id": "4", "code": "set", "prefix": "s-"},
            }
        }
    }
    dlg = LightingAssetDialog(shot_data=mock_shot, asset_department=mock_assets)
    if dlg.exec():
        print("Selected FG Assets:", dlg.get_selected_fg_assets())
    else:
        print("Cancelled.")

