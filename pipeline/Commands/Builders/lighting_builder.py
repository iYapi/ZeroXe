import json
import logging
import os
import sys
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def _get_lighting_dialog_classes():
    """Dynamically resolve and import LightingAssetDialog and LightingBatchDialog."""
    if "pipeline.Commands.Builders.lighting_dialog" in sys.modules:
        mod = sys.modules["pipeline.Commands.Builders.lighting_dialog"]
        return getattr(mod, "LightingAssetDialog", None), getattr(mod, "LightingBatchDialog", None)

    try:
        from .lighting_dialog import LightingAssetDialog, LightingBatchDialog
        return LightingAssetDialog, LightingBatchDialog
    except Exception:
        pass

    for mod_name in [
        "pipeline.Commands.Builders.lighting_dialog",
        "Commands.Builders.lighting_dialog",
        "Builders.lighting_dialog",
        "lighting_dialog",
    ]:
        try:
            mod = __import__(mod_name, fromlist=["LightingAssetDialog", "LightingBatchDialog"])
            if hasattr(mod, "LightingAssetDialog"):
                return getattr(mod, "LightingAssetDialog"), getattr(mod, "LightingBatchDialog", None)
        except Exception:
            pass

    try:
        dialog_file = Path(__file__).parent / "lighting_dialog.py"
        if dialog_file.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("zeroxe_lighting_dialog", str(dialog_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "LightingAssetDialog", None), getattr(mod, "LightingBatchDialog", None)
    except Exception:
        pass

    return None, None


class LightingBuilder:
    """Builder for Lighting department scene generation with interactive FG/BG layer assignment."""

    def extract_data(
        self,
        shot_data: Dict[str, Any],
        current_department: Dict[str, Any],
        asset_department: Dict[str, Any],
        mastershots_data: Dict[str, Any],
        addons_data: Dict[str, Any],
        filepath: Dict[str, str],
        fg_assets: Optional[List[str]] = None,
        fg_yaml: Optional[Union[str, Path, dict, list]] = None,
        show_ui: bool = True,
        **kwargs: Any,
    ) -> str:
        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)
        
        # Get lit mastershot path
        relative_assets = {}
        asset_types = asset_department.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in asset_department:
            asset_types = asset_department.get("asset_type", {})

        shot_assets_content = shot_data.get("assets", []) or []
        if not shot_assets_content and shot_data.get("id"):
            try:
                import gazu
                shot_assets_content = gazu.asset.all_assets_for_shot(shot_data["id"]) or []
            except Exception:
                try:
                    from zeroxe.services.shot_service import ShotService
                    shot_assets_content = ShotService.get_assets_for_shot(shot_data["id"]) or []
                except Exception:
                    pass

        asset_type_map = {
            config["id"] if isinstance(config, dict) and "id" in config else config.get("kitsu_id", category_key): (category_key, config)
            for category_key, config in asset_types.items()
            if isinstance(config, dict)
        }
        
        lit_mastershot_name = ""
        lit_mastershot_base_path = ""

        for asset in shot_assets_content:
            if not isinstance(asset, dict):
                continue
            asset_type_id = asset.get("entity_type_id")
            asset_name = asset.get("name", "")
            if asset_type_id in asset_type_map:
                category_key, config = asset_type_map[asset_type_id]
                if category_key.lower() == "set" or asset_name.startswith("s-"):
                    if category_key not in relative_assets:
                        relative_assets[category_key] = {
                            "assets": [],
                            "base_path": config.get("base_path"),
                            "prefix": config.get("prefix"),
                            "code": config.get("code", "set"),
                        }
                    relative_assets[category_key]["assets"].append(asset_name)
                elif category_key.lower().startswith("ms_") or asset_name.startswith("ms_") or asset_name.startswith("LIT_"):
                    if category_key.lower() in ("ms_lit", "ms_lighting") or asset_name.startswith("LIT_"):
                        lit_mastershot_name = asset_name
                        lit_mastershot_base_path = config.get("base_path", "")
                    if category_key in asset_types:
                        del asset_types[category_key]
        
        lit_mastershot_file = (
            Path(lit_mastershot_base_path)
            / lit_mastershot_name
            / f"{lit_mastershot_name}.blend"
        ) if lit_mastershot_base_path and lit_mastershot_name else Path("")

        # Construct collection dict for high-res sets
        collections_dict = {}
        for category, data in relative_assets.items():
            paths = []
            base_dir = Path(data["base_path"]) if data.get("base_path") else Path("")

            for asset in data["assets"]:
                filename = f"{asset}.blend"
                full_path = base_dir / asset / filename

                # Convert back to string for Blender's libraries.load
                paths.append(str(full_path))

            collections_dict[data.get("code", "set")] = paths

        # Get preset
        dept_data = next(iter(current_department.values())) if current_department else {}
        preset_name = "preset"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path") if isinstance(dept_data, dict) else None

        # Get addon preset
        addon_preset_path = (
            addons_data.get("addons", {})
            .get("ops_blp", {})
            .get("base_path", "")
        ) if isinstance(addons_data, dict) else ""
        addon_preset_file = (Path(addon_preset_path) / f"{lit_mastershot_name}.json") if addon_preset_path and lit_mastershot_name else Path("")

        # Collection list for non-set asset categories (chr, prp, vhc, etc.)
        collection_list = [
            (config.get("code"), config.get("prefix"))
            for config in asset_types.values()
            if isinstance(config, dict)
            and config.get("code") not in ["ms", "set"]
            and not str(config.get("code", "")).startswith("ms")
            and config.get("prefix")
        ]
        # Add the camera entry manually
        collection_list.append(("cam", None))
        collection_list.append(("hdn", None))

        # Construct shot metadata
        shot_meta = shot_data.get("data") if isinstance(shot_data.get("data"), dict) else {}

        def safe_int(val, default):
            try:
                return int(val) if val is not None and str(val).strip() != "" else default
            except (ValueError, TypeError):
                return default

        frame_in = safe_int(shot_meta.get("frame_in") or shot_data.get("frame_in"), 0)
        frame_out = safe_int(shot_meta.get("frame_out") or shot_data.get("frame_out"), 0)
        fps = safe_int(shot_meta.get("fps") or shot_data.get("fps"), 24)

        raw_res = shot_meta.get("resolution") or shot_data.get("resolution") or "1920x1080"
        if isinstance(raw_res, (list, tuple)) and len(raw_res) >= 2:
            resolution = [safe_int(raw_res[0], 1920), safe_int(raw_res[1], 1080)]
        else:
            res_str = str(raw_res or "1920x1080")
            if "x" in res_str.lower():
                parts = res_str.lower().split("x")
                resolution = [safe_int(parts[0], 1920), safe_int(parts[1], 1080)]
            else:
                resolution = [1920, 1080]

        setting_data = {
            "frame_in": frame_in,
            "frame_out": frame_out,
            "fps": fps,
            "resolution": resolution,
            "ops_blp": str(addon_preset_file) if addon_preset_file else "",
            "script_path": preset_path,
        }

        # ------------------------------------------------------------------
        # Foreground (FG) Asset Selection (YAML Configuration / UI / Headless)
        # ------------------------------------------------------------------
        selected_fg = fg_assets

        # 1. Resolve FG assets from YAML configuration (explicit or auto-discovered)
        yaml_source = (
            fg_yaml
            or kwargs.get("fg_yaml")
            or kwargs.get("fg_yaml_path")
            or kwargs.get("fg_config")
            or kwargs.get("fg_config_path")
            or (kwargs.get("setting_data") and (
                kwargs["setting_data"].get("fg_yaml")
                or kwargs["setting_data"].get("fg_yaml_path")
                or kwargs["setting_data"].get("fg_config")
                or kwargs["setting_data"].get("fg_config_path")
            ))
            or shot_data.get("fg_yaml")
            or shot_data.get("fg_config")
        )

        if not yaml_source:
            yaml_source = self._discover_fg_yaml(filepath, shot_data)

        if selected_fg is None and yaml_source:
            fg_cfg = self.load_fg_config_from_yaml(yaml_source)
            if fg_cfg is not None:
                available_shot_assets = [
                    a.get("name")
                    for a in shot_assets_content
                    if isinstance(a, dict) and a.get("name")
                ]
                resolved_from_yaml = self.resolve_fg_assets_from_config(
                    config_data=fg_cfg,
                    shot_data=shot_data,
                    available_assets=available_shot_assets,
                )
                if resolved_from_yaml is not None:
                    selected_fg = resolved_from_yaml

        # 2. Check setting_data["fg_assets"] list
        if selected_fg is None and kwargs.get("setting_data") and "fg_assets" in kwargs["setting_data"]:
            selected_fg = kwargs["setting_data"]["fg_assets"]

        # 3. Interactive UI dialog (for single interactive execution when not in batch/test)
        import os
        is_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))

        if selected_fg is None and show_ui and not is_test_env:
            dialog_cls, _ = _get_lighting_dialog_classes()
            if dialog_cls is not None:
                try:
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if not app:
                        app = QApplication(sys.argv)

                    dialog = dialog_cls(
                        shot_data=shot_data,
                        asset_department=asset_department,
                    )
                    if dialog.exec():
                        selected_fg = dialog.get_selected_fg_assets()
                    else:
                        raise RuntimeError("Lighting Builder generation cancelled by user.")
                except RuntimeError:
                    raise
                except Exception as e:
                    import logging
                    logging.getLogger("ZeroXe.LightingBuilder").warning(
                        f"Could not display LightingAssetDialog: {e}"
                    )

        # 4. Headless fallback: by default all assets are placed in BG (fg_assets = [])
        if selected_fg is None:
            selected_fg = []

        lighting_script = self.script_builder(
            filepath=filepath["final"],
            version_path=filepath["version"],
            master_file=str(lit_mastershot_file) if lit_mastershot_file else "",
            animation_file=filepath.get("source", ""),
            setting_data=setting_data,
            collection_list=collection_list,
            set_collection=collections_dict,
            fg_assets=selected_fg,
        )
        return lighting_script

    @classmethod
    def load_fg_config_from_yaml(
        cls,
        yaml_source: Any,
    ) -> Optional[Any]:
        """Load and parse FG assets mapping from a YAML file, string, or dictionary.

        Args:
            yaml_source: Path to YAML file, YAML content string, or already parsed dict/list.

        Returns:
            Parsed YAML data (dict or list), or None if invalid.
        """
        if yaml_source is None:
            return None

        if isinstance(yaml_source, (dict, list)):
            return yaml_source

        from textwrap import dedent
        import yaml

        source_raw = str(yaml_source)
        source_str = dedent(source_raw).strip()
        if not source_str:
            return None

        # 1. If single line without newlines, check if it is a file path on disk
        if "\n" not in source_str:
            try:
                source_path = Path(source_str)
                if source_path.is_file():
                    with open(source_path, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
            except Exception as e:
                import logging
                logging.getLogger("ZeroXe.LightingBuilder").warning(
                    f"Failed to read FG YAML file '{source_str}': {e}"
                )
                return None

        # 2. Parse as raw YAML string
        try:
            parsed = yaml.safe_load(source_str)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass

        return None

    @classmethod
    def resolve_fg_assets_from_config(
        cls,
        config_data: Any,
        shot_data: Dict[str, Any],
        available_assets: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Resolve list of FG asset names for a given shot from parsed YAML configuration.

        Supported YAML Schemas:
        1. Flat list of assets (global FG across all shots):
           - chr_hero
           - prp_sword

        2. Global FG dictionary:
           fg_assets:
             - chr_hero
             - prp_sword

        3. Per-shot dictionary (keys can be 'sq01_sh010', 'sh010', or 'ep01_sq01_sh010'):
           sq01_sh010:
             - chr_hero
           sh020:
             fg_assets: [chr_villain]
             bg_assets: [prp_extra]

        4. Nested under 'shots' or 'scenes' or 'lighting':
           shots:
             sq01_sh010:
               - chr_hero

        5. Per-sequence dictionary (fallback if shot not individually defined):
           sequences:
             sq01: [chr_hero]

        6. Wildcard glob matching (e.g. 'chr_*', 'prp_hero*') against available_assets.

        Args:
            config_data: The parsed YAML data (dict or list).
            shot_data: Shot metadata dictionary containing 'name', 'sequence', 'episode'.
            available_assets: Optional list of all asset names present in the shot.

        Returns:
            List of matching FG asset names, or None if no rule matched.
        """
        if not config_data and config_data != []:
            return None

        # A. Top-level flat list: applies globally to all shots
        if isinstance(config_data, list):
            raw_list = [str(item).strip() for item in config_data if item]
            return cls._match_asset_patterns(raw_list, available_assets)

        if not isinstance(config_data, dict):
            return None

        shot_name = str(shot_data.get("name") or "").strip()
        sequence_name = str(shot_data.get("sequence") or "").strip()
        episode_name = str(shot_data.get("episode") or "").strip()

        # Build candidate lookup keys in priority order
        candidates = []
        if episode_name and sequence_name and shot_name:
            candidates.append(f"{episode_name}_{sequence_name}_{shot_name}".lower())
        if sequence_name and shot_name:
            candidates.append(f"{sequence_name}_{shot_name}".lower())
        if shot_name:
            candidates.append(shot_name.lower())

        # Helper to search a dict case-insensitively
        def _find_in_dict(d: dict, keys: List[str]) -> Optional[Any]:
            if not isinstance(d, dict):
                return None
            lower_map = {str(k).lower().strip(): v for k, v in d.items()}
            for k in keys:
                if k in lower_map:
                    return lower_map[k]
            return None

        # 1. Search in top-level dict by shot candidate keys
        matched_section = _find_in_dict(config_data, candidates)

        # 2. Search under 'shots', 'scenes', 'lighting', 'shot_list'
        if matched_section is None:
            for container_key in ["shots", "scenes", "lighting", "shot_list"]:
                sub_dict = config_data.get(container_key)
                if isinstance(sub_dict, dict):
                    matched_section = _find_in_dict(sub_dict, candidates)
                    if matched_section is not None:
                        break

        # 3. Search sequence-level fallback under 'sequences' or top-level
        if matched_section is None and sequence_name:
            seq_candidates = [sequence_name.lower()]
            if episode_name:
                seq_candidates.insert(0, f"{episode_name}_{sequence_name}".lower())

            sub_seqs = config_data.get("sequences") or config_data.get("sequence_list")
            if isinstance(sub_seqs, dict):
                matched_section = _find_in_dict(sub_seqs, seq_candidates)
            if matched_section is None:
                matched_section = _find_in_dict(config_data, seq_candidates)

        # 4. Search global fallback keys
        if matched_section is None:
            for g_key in ["fg_assets", "foreground_assets", "foreground", "fg", "default_fg"]:
                if g_key in config_data:
                    matched_section = config_data[g_key]
                    break

        if matched_section is None:
            return None

        # Extract FG patterns and BG exclusions from matched section
        fg_patterns: List[str] = []
        bg_patterns: List[str] = []

        if isinstance(matched_section, list):
            fg_patterns = [str(x).strip() for x in matched_section if x]
        elif isinstance(matched_section, dict):
            for k in ["fg_assets", "foreground_assets", "foreground", "fg", "assets"]:
                if k in matched_section and isinstance(matched_section[k], list):
                    fg_patterns = [str(x).strip() for x in matched_section[k] if x]
                    break
            for bk in ["bg_assets", "background_assets", "background", "bg", "exclude"]:
                if bk in matched_section and isinstance(matched_section[bk], list):
                    bg_patterns = [str(x).strip() for x in matched_section[bk] if x]
                    break
        elif isinstance(matched_section, str):
            fg_patterns = [matched_section.strip()]

        # Resolve patterns against available assets
        resolved_fg = cls._match_asset_patterns(fg_patterns, available_assets)

        # Apply exclusions if BG patterns specified
        if bg_patterns:
            excluded = set(cls._match_asset_patterns(bg_patterns, available_assets or resolved_fg))
            resolved_fg = [a for a in resolved_fg if a not in excluded]

        return resolved_fg

    @classmethod
    def _match_asset_patterns(
        cls,
        patterns: List[str],
        available_assets: Optional[List[str]] = None,
    ) -> List[str]:
        """Expand wildcard patterns or return exact names matching available shot assets."""
        import fnmatch

        if not patterns:
            return []

        matched = []
        for asset in available_assets:
            if not asset:
                continue
            asset_clean = str(asset).strip()
            asset_lower = asset_clean.lower()
            for pat in patterns:
                pat_clean = str(pat).strip()
                pat_lower = pat_clean.lower()
                if not pat_lower:
                    continue
                if pat_lower == asset_lower or fnmatch.fnmatch(asset_lower, pat_lower) or pat_lower in asset_lower:
                    if asset_clean not in matched:
                        matched.append(asset_clean)
                    break

        # Also preserve explicit non-wildcard patterns so direct Animation .blend collection names match
        for pat in patterns:
            pat_clean = str(pat).strip()
            if pat_clean and "*" not in pat_clean and "?" not in pat_clean:
                if pat_clean not in matched and pat_clean.lower() not in [m.lower() for m in matched]:
                    matched.append(pat_clean)

        return matched

    @classmethod
    def _discover_fg_yaml(
        cls,
        filepath: Dict[str, str],
        shot_data: Dict[str, Any],
    ) -> Optional[Path]:
        """Auto-detect if an FG configuration YAML file exists in shot or sequence folders."""
        candidate_names = [
            "fg_assets.yaml",
            "fg_assets.yml",
            "lighting_fg.yaml",
            "lighting_fg.yml",
            "batch_fg.yaml",
            "batch_fg.yml",
            "fg_map.yaml",
            "fg_map.yml",
            "fg.yaml",
            "fg.yml",
        ]

        search_dirs: List[Path] = []

        # 1. Directory of target version or final file
        for k in ["version", "final", "source"]:
            p_str = filepath.get(k)
            if p_str:
                p = Path(p_str)
                search_dirs.append(p.parent)
                search_dirs.append(p.parent.parent)

        # 2. Check candidate filenames in search directories
        for d in search_dirs:
            if d.is_dir():
                for cname in candidate_names:
                    cand = d / cname
                    if cand.is_file():
                        return cand

        return None

    @classmethod
    def prompt_batch_dialog(
        cls,
        selected_items: List[Any],
        parent: Optional[Any] = None,
        available_shots: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Open batch dialog to configure FG mapping for multiple shots."""
        try:
            from PySide6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return {}

            _, batch_dialog_cls = _get_lighting_dialog_classes()
            if batch_dialog_cls is not None:
                from PySide6.QtWidgets import QDialog
                dlg = batch_dialog_cls(selected_items=selected_items, available_shots=available_shots, parent=parent)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    return dlg.get_result()
                return None  # User clicked Cancel
        except Exception as e:
            logger.warning(f"Error in prompt_batch_dialog: {e}")
        return {}

    def script_builder(
        self,
        filepath: str,
        version_path: str,
        master_file: str,
        animation_file: str,
        setting_data: dict,
        collection_list: list,
        set_collection: dict,
        fg_assets: Optional[List[str]] = None,
    ) -> str:
        clean_fg_assets = [str(a).lower().strip() for a in (fg_assets or [])]

        tpl = Template(
            dedent(
                """
import bpy
from pathlib import Path

collections = $SET_COLLECTION
fg_assets = $FG_ASSETS
collection_list = $COLLECTION_LIST

master_file = "$FILEPATH"
if master_file and Path(master_file).is_file():
	bpy.ops.wm.open_mainfile(filepath=master_file)
else:
	bpy.ops.wm.read_factory_settings(use_empty=True)

def _unlink_collection_from(parent, target):
	for child in list(parent.children):
		if child == target:
			parent.children.unlink(child)
		else:
			_unlink_collection_from(child, target)		

def _force_remove_collection(name: str):
	coll = bpy.data.collections.get(name)
	if not coll:
		return
	for scene in bpy.data.scenes:
		_unlink_collection_from(scene.collection, coll)
	try:
		bpy.data.collections.remove(coll)
		print(f"Removed existing collection: {name}")
	except RuntimeError as e:
		print(f"[WARNING] Could not remove '{name}': {e}")

def ensure_collection(name: str, parent=None) -> bpy.types.Collection:
	coll = bpy.data.collections.get(name)
	if not coll:
		coll = bpy.data.collections.new(name)
		print(f"Created collection: {name}")
	if parent is None:
		parent = bpy.context.scene.collection
	if coll.name not in parent.children:
		parent.children.link(coll)
		print(f"Linked '{coll.name}' under '{parent.name}'")
	return coll

def is_asset_in_fg(coll_name: str, fg_list: list) -> bool:
	clean_name = coll_name.lower().strip()
	for fg_name in fg_list:
		if not fg_name:
			continue
		if fg_name == clean_name or clean_name.startswith(fg_name) or fg_name in clean_name:
			return True
	return False

def get_empty_groups_from_collection(collection_name: str):
	coll = bpy.data.collections.get(collection_name)
	if not coll:
		raise ValueError(f"Collection '{collection_name}' not found.")

	result = []

	def recurse(c: bpy.types.Collection):
		for obj in c.objects:
			if obj.type == 'EMPTY' and obj.name.endswith("_grp"):
				result.append(obj.name)
		for child in c.children:
			recurse(child)
	recurse(coll)
	return result

# Main Function
def link_animation():
	print("Animation file:", "$ANIMATION_FILE")
	anim_file = "$ANIMATION_FILE"
	if not anim_file or not Path(anim_file).is_file():
		print("[WARNING] Animation source file does not exist:", anim_file)
		return

	# 1. Ensure root scene collections: fg and bg
	fg_root = ensure_collection("fg")
	bg_root = ensure_collection("bg")

	# 2. Ensure sub-category parent collections: chr_fg, chr_bg, prp_fg, prp_bg, vhc_fg, vhc_bg
	cat_parents = {}
	for code, prefix in collection_list:
		if code in ["cam", "hdn", "ms", "set"] or not prefix:
			continue
		fg_cat_name = f"{code}_fg"
		bg_cat_name = f"{code}_bg"
		cat_parents[fg_cat_name] = ensure_collection(fg_cat_name, parent=fg_root)
		cat_parents[bg_cat_name] = ensure_collection(bg_cat_name, parent=bg_root)

	# 3. Discover desired collections from Animation library
	desired = {}
	with bpy.data.libraries.load(anim_file, link=True) as (data_from, data_to):
		for code, prefix in collection_list:
			if prefix is None:
				cam_coll = next((c for c in data_from.collections if c.lower() == "$CAMERA_COLLECTION".lower()), None)
				desired[code] = [cam_coll] if cam_coll else []
			else:
				names = [n for n in data_from.collections if n.startswith(prefix)]
				desired[code] = names

	# 4. Link all animated asset collections from library
	to_link = []
	for code, names in desired.items():
		if code == "cam":
			continue
		to_link.extend(names)

	to_link = [n for n in to_link if n not in bpy.data.collections]
	if to_link:
		with bpy.data.libraries.load(anim_file, link=True) as (data_from, data_to):
			data_to.collections = [n for n in to_link if n in data_from.collections]
			print(f"Linked collections: {data_to.collections}")

	bpy.context.view_layer.update()

	# 5. Place each loaded collection into corresponding _fg or _bg parent
	for code, child_names in desired.items():
		if code == "cam":
			continue

		fg_cat_name = f"{code}_fg"
		bg_cat_name = f"{code}_bg"
		fg_cat_parent = cat_parents.get(fg_cat_name)
		bg_cat_parent = cat_parents.get(bg_cat_name)

		for cname in child_names:
			col = bpy.data.collections.get(cname)
			if not col:
				col = next((c for c in bpy.data.collections
							if c.name == cname and c.library and
							bpy.path.abspath(c.library.filepath) == bpy.path.abspath(anim_file)), None)
			if not col:
				print(f"[WARNING] Expected linked collection missing: {cname}")
				continue

			# Check if selected as Foreground asset
			if is_asset_in_fg(cname, fg_assets):
				target_parent = fg_cat_parent
				target_label = fg_cat_name
			else:
				# Unselected or extra character in ANM not in shot assets goes into BG
				target_parent = bg_cat_parent
				target_label = bg_cat_name

			if target_parent and col.name not in target_parent.children:
				target_parent.children.link(col)
				# Unlink from scene root collection if directly attached
				if col.name in bpy.context.scene.collection.children:
					bpy.context.scene.collection.children.unlink(col)
				print(f"Linked '{cname}' under '{target_label}'")

	# 6. Camera handling
	link_mode = bool($METHOD)
	cam_names = next((v for k, v in desired.items() if k.lower() == "$CAMERA_COLLECTION".lower()), [])
	if cam_names:
		cam_name = cam_names[0]
		for c in [c for c in list(bpy.data.collections) if c.name == cam_name or c.name.startswith(cam_name + ".")]:
			for scene in bpy.data.scenes:
				_unlink_collection_from(scene.collection, c)
			try:
				bpy.data.collections.remove(c)
			except RuntimeError:
				pass

		try:
			bpy.data.orphans_purge(do_recursive=True)
		except Exception:
			pass

		with bpy.data.libraries.load(anim_file, link=link_mode) as (data_from, data_to):
			if cam_name in data_from.collections:
				data_to.collections = [cam_name]
			else:
				print(f"[WARNING] '{cam_name}' missing in library during {'link' if link_mode else 'append'}")
				return

		found = next((c for c in bpy.data.collections
					  if (c.name == cam_name or c.name.startswith(cam_name + "."))
					  and ((link_mode and c.library) or (not link_mode and not c.library))), None)

		if not found:
			print(f"[WARNING] Failed to {'link' if link_mode else 'append'} '{cam_name}'")
			return

		if not link_mode:
			other = bpy.data.collections.get(cam_name)
			if other and other is not found:
				try:
					bpy.data.collections.remove(other)
				except RuntimeError:
					pass
			if found.name != cam_name:
				try:
					found.name = cam_name
				except Exception:
					pass

		if found.name not in bpy.context.scene.collection.children.keys():
			bpy.context.scene.collection.children.link(found)

		print(f"[CAM] {'Linked' if link_mode else 'Appended'} '{cam_name}' as "
			  f"{'library' if link_mode else 'local'} collection '{found.name}'")

def select_only(obj):
	for o in bpy.context.view_layer.objects:
		o.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

def link_set_collection(collections_dict):
	bg_parent = ensure_collection("bg")
	for category_name, file_paths in collections_dict.items():
		if category_name in bpy.data.collections:
			category_collection = bpy.data.collections[category_name]
		else:
			category_collection = bpy.data.collections.new(category_name)
			bpy.context.scene.collection.children.link(category_collection)

		for asset_path_str in file_paths:
			asset_path = Path(asset_path_str)
			collection_name = asset_path.stem
			if category_name == "set":
				collection_name = f"{collection_name}_hi"
			with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
				if collection_name in data_from.collections:
					data_to.collections = [collection_name]
				else:
					print(f"Collection '{collection_name}' not found in {asset_path}")
					continue
     
			for linked_collection in data_to.collections:
				if linked_collection and linked_collection.name not in category_collection.children:
					category_collection.children.link(linked_collection)
					armatures = [obj for obj in linked_collection.all_objects if obj.type == 'ARMATURE']
					if not armatures:
						continue

					if linked_collection.name in bpy.data.collections:
						overridden_collection = bpy.data.collections[linked_collection.name]
						if overridden_collection.name not in [child.name for child in category_collection.children]:
							category_collection.children.link(overridden_collection)
						if overridden_collection.name in [child.name for child in bpy.context.scene.collection.children]:
							bpy.context.scene.collection.children.unlink(overridden_collection)

					bpy.context.view_layer.update()
				print(f"Linked collection '{linked_collection.name}' into '{category_name}'")

		if category_collection.name not in bg_parent.children:
			bg_parent.children.link(category_collection)
			if category_collection.name in bpy.context.scene.collection.children:
				bpy.context.scene.collection.children.unlink(category_collection)

link_animation()
link_set_collection(collections)

def update_camera():
	scene = bpy.data.scenes['Scene']
	cam_obj = next((obj for obj in scene.objects if obj.type == 'CAMERA'), None)
	if cam_obj:
		scene.camera = cam_obj

	active_camera = bpy.context.scene.camera
	if active_camera:
		active_camera.data.clip_end = 1000
		active_camera.data.dof.use_dof = True
		active_camera.data.dof.driver_remove("aperture_fstop")

def set_relative():
	bpy.context.preferences.filepaths.use_relative_paths = True
	bpy.ops.file.make_paths_relative()

update_camera()
set_relative()
print("All lighting operations completed successfully.")

settings = $SETTINGS
if settings.get("frame_out") is not None:
	bpy.context.scene.frame_end = settings["frame_out"]
if settings.get("frame_in") is not None:
	bpy.context.scene.frame_start = settings["frame_in"]
if settings.get("fps") is not None:
	bpy.context.scene.render.fps = settings["fps"]
res = settings.get("resolution") or [1920, 1080]
if len(res) >= 2:
	bpy.context.scene.render.resolution_x = res[0]
	bpy.context.scene.render.resolution_y = res[1]
bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
"""
            )
        )

        end_script = Template(
            dedent(
                """
# Save the modified Blender file
bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH_PROGRESS")
print("File saved as: $OUTPUT_PATH")
	
# Quit Blender
bpy.ops.wm.quit_blender()
"""
            )
        )
        script = tpl.substitute(
            FILEPATH=master_file,
            ANIMATION_FILE=animation_file,
            COLLECTION_LIST=collection_list,
            SET_COLLECTION=set_collection,
            FG_ASSETS=clean_fg_assets,
            CAMERA_COLLECTION="cam",
            METHOD=False,
            OUTPUT_PATH=filepath,
            SETTINGS=setting_data,
        )
        end_script = end_script.substitute(
            OUTPUT_PATH=filepath, OUTPUT_PATH_PROGRESS=version_path
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
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


if __name__ == "__main__":
    try:
        fg_yaml_arg = None
        filtered_args = []
        i = 1
        while i < len(sys.argv):
            if sys.argv[i] == "--fg-yaml" and i + 1 < len(sys.argv):
                fg_yaml_arg = sys.argv[i + 1]
                i += 2
            elif sys.argv[i].startswith("--fg-yaml="):
                fg_yaml_arg = sys.argv[i].split("=", 1)[1]
                i += 1
            else:
                filtered_args.append(sys.argv[i])
                i += 1

        shot_info = json.loads(filtered_args[0])
        current_dept = json.loads(filtered_args[1])
        asset_dept = json.loads(filtered_args[2])
        mastershot_data = json.loads(filtered_args[3])
        addon_data = json.loads(filtered_args[4])
        file_paths = json.loads(filtered_args[-1])

        builder = LightingBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            mastershots_data=mastershot_data,
            addons_data=addon_data,
            filepath=file_paths,
            fg_yaml=fg_yaml_arg,
            show_ui=False,
        )
        print(result)
    except Exception as e:
        print(f"Builder Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
