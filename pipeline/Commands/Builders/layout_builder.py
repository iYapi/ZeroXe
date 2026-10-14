"""Layout Builder Module for ZeroXe Pipeline.

Generates Blender scene files for Layout department with support for:
1. Clean scene generation from scratch using Kitsu asset casting and camera rig.
2. Sourcing from another shot (or custom .blend file) and matching casting:
   - Preserves all existing scene objects (never deletes existing elements).
   - Links missing characters/assets from Kitsu casting for the current shot with library overrides.
   - Configures timeline (frame_in, frame_out), FPS, render resolution, and simplify matching clean generation.
3. Interactive dialogs (LayoutDialog, LayoutBatchDialog) matching Compositing Builder.
"""

import configparser
import importlib.util
import inspect
import json
import logging
import os
import sys
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def _get_layout_dialog_classes() -> Tuple[Optional[type], Optional[type]]:
    """Dynamically import LayoutDialog and LayoutBatchDialog to prevent circular imports."""
    try:
        from .layout_dialog import LayoutDialog, LayoutBatchDialog
        return LayoutDialog, LayoutBatchDialog
    except (ImportError, ValueError):
        pass

    try:
        from layout_dialog import LayoutDialog, LayoutBatchDialog
        return LayoutDialog, LayoutBatchDialog
    except (ImportError, ValueError):
        pass

    try:
        from pipeline.Commands.Builders.layout_dialog import LayoutDialog, LayoutBatchDialog
        return LayoutDialog, LayoutBatchDialog
    except (ImportError, ValueError):
        pass

    try:
        dialog_path = Path(__file__).parent / "layout_dialog.py"
        if dialog_path.is_file():
            module_name = "pipeline_layout_dialog_dynamic"
            spec = importlib.util.spec_from_file_location(module_name, str(dialog_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "LayoutDialog", None), getattr(mod, "LayoutBatchDialog", None)
    except Exception:
        pass

    return None, None


class LayoutBuilder:
    """Builder for Layout department scene generation with clean and source-from-shot casting support."""

    @classmethod
    def resolve_sibling_shot_layout(
        cls,
        sibling_shot_name: str,
        shot_data: Dict[str, Any],
        current_department: Optional[Dict[str, Any]] = None,
        project_path: Optional[str] = None,
    ) -> Optional[Path]:
        """Resolve the Layout .blend file path for a sibling shot."""
        try:
            from .layout_dialog import _resolve_sibling_shot_layout_path
            return _resolve_sibling_shot_layout_path(
                sibling_shot_name=sibling_shot_name,
                shot_data=shot_data,
                current_department=current_department,
                project_path=project_path,
            )
        except Exception:
            try:
                from layout_dialog import _resolve_sibling_shot_layout_path
                return _resolve_sibling_shot_layout_path(
                    sibling_shot_name=sibling_shot_name,
                    shot_data=shot_data,
                    current_department=current_department,
                    project_path=project_path,
                )
            except Exception:
                pass

        # Direct PipelineService fallback
        try:
            from zeroxe.services.pipeline_service import PipelineService
            ep = shot_data.get("episode") or ""
            sq = shot_data.get("sequence") or ""
            proj = shot_data.get("project_name") or (shot_data.get("project") or {}).get("name")
            shot_res = PipelineService.resolve_shot(
                department="Layout",
                episode=ep,
                sequence=sq,
                shot=sibling_shot_name,
                project_name=proj if isinstance(proj, str) else None,
                project_path=project_path,
            )
            if shot_res and shot_res.master_path:
                m_path = Path(shot_res.master_path)
                if m_path.is_file():
                    return m_path
                versions = PipelineService.list_versions(
                    department="Layout",
                    episode=ep,
                    sequence=sq,
                    shot=sibling_shot_name,
                    project_name=proj if isinstance(proj, str) else None,
                    project_path=project_path,
                )
                if versions:
                    return Path(versions[-1][1])
                return m_path
        except Exception:
            pass

        return None

    @classmethod
    def prompt_batch_dialog(
        cls,
        selected_items: List[Any],
        parent: Optional[Any] = None,
        available_shots: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Open batch dialog allowing artists to configure clean vs source-shot strategy for multiple shots."""
        try:
            from PySide6.QtWidgets import QApplication, QDialog
            if QApplication.instance() is None:
                return {}

            _, batch_dialog_cls = _get_layout_dialog_classes()
            if batch_dialog_cls is not None:
                dlg = batch_dialog_cls(selected_items=selected_items, available_shots=available_shots, parent=parent)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    return dlg.get_result()
                return None  # Cancelled by user
        except Exception as e:
            logger.warning(f"Could not open LayoutBatchDialog: {e}")
        return {}

    def extract_data(
        self,
        shot_data: Dict[str, Any],
        current_department: Dict[str, Any],
        asset_department: Optional[Dict[str, Any]] = None,
        filepath: Optional[Dict[str, str]] = None,
        layout_mode: Optional[str] = None,
        source_shot: Optional[str] = None,
        source_file: Optional[Union[str, Path]] = None,
        show_ui: bool = True,
        project_path: Optional[str] = None,
        available_shots: Optional[List[str]] = None,
        setting_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Extract data and build the Layout DCC setup script."""
        # Handle legacy positional call: extract_data(asset_dept, current_dept, shot_info, file_paths)
        if isinstance(shot_data, dict) and "Asset" in shot_data and ("name" not in shot_data or "sequence" not in shot_data):
            asset_department, current_department, shot_data, filepath = (
                shot_data,
                current_department,
                asset_department or {},
                filepath or {},
            )

        file_paths = filepath or {}
        version_file = file_paths.get("version", "")
        final_file = file_paths.get("final", "")

        if version_file:
            Path(version_file).parent.mkdir(parents=True, exist_ok=True)
        if final_file:
            Path(final_file).parent.mkdir(parents=True, exist_ok=True)

        asset_dept = asset_department or {}
        asset_types = asset_dept.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in asset_dept:
            asset_types = asset_dept.get("asset_type", {})

        # Resolve project_path if missing
        if not project_path and version_file:
            fp_str = str(version_file).replace("\\", "/")
            for prod_token in ("/02_production/", "/01_pre_production/", "/01_preproduction/", "/03_post_production/"):
                if prod_token in fp_str:
                    project_path = fp_str.split(prod_token)[0]
                    break
        if not project_path and isinstance(shot_data, dict):
            project_path = shot_data.get("project_path") or (shot_data.get("project") or {}).get("path")

        # Resolve available_shots from shot_data if not passed directly
        resolved_available_shots = available_shots or (shot_data.get("available_shots") if isinstance(shot_data, dict) else None)

        # 1. Interactive Dialog UI (Single Shot)
        chosen_mode = (layout_mode or "").strip().lower()
        chosen_source_shot = source_shot
        chosen_source_file = source_file

        if not chosen_mode and show_ui and not os.environ.get("PYTEST_CURRENT_TEST"):
            dialog_cls, _ = _get_layout_dialog_classes()
            if dialog_cls is not None:
                try:
                    from PySide6.QtWidgets import QApplication, QDialog
                    if QApplication.instance() is not None:
                        dlg = dialog_cls(
                            shot_data=shot_data,
                            current_department=current_department,
                            available_shots=resolved_available_shots,
                            project_path=project_path,
                        )
                        if dlg.exec() == QDialog.DialogCode.Accepted:
                            res = dlg.get_result()
                            chosen_mode = res.get("layout_mode") or "clean"
                            chosen_source_shot = res.get("source_shot")
                            chosen_source_file = res.get("source_file")
                        else:
                            raise RuntimeError("Layout scene generation cancelled by user.")
                except ImportError:
                    pass
                except RuntimeError:
                    raise
                except Exception as e:
                    logger.warning(f"Could not open LayoutDialog: {e}")

        if not chosen_mode:
            chosen_mode = "clean"

        # 2. Extract shot metadata (keyframes, fps, resolution)
        shot_meta = shot_data.get("data") if isinstance(shot_data.get("data"), dict) else {}

        def safe_int(val, default):
            try:
                return int(val) if val is not None and str(val).strip() != "" else default
            except (ValueError, TypeError):
                return default

        frame_in = safe_int(shot_meta.get("frame_in") or shot_data.get("frame_in"), 1)
        frame_out = safe_int(shot_meta.get("frame_out") or shot_data.get("frame_out"), 100)
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

        # Resolve preset script path (e.g. playblast)
        dept_data = next(iter(current_department.values())) if current_department else {}
        preset_name = "playblast"
        preset_path = None
        if isinstance(dept_data, dict):
            preset_path = (dept_data.get("presets", {}).get(preset_name, {}) or {}).get("path")
            if not preset_path:
                preset_path = (dept_data.get("scripts", {}) or {}).get("playblast")

        resolved_settings = {
            "frame_in": frame_in,
            "frame_out": frame_out,
            "fps": fps,
            "resolution": resolution,
            "script_path": preset_path,
        }

        # 3. Gather Kitsu assets registered for this shot
        raw_assets = list(shot_data.get("assets", []) or [])
        shot_id = shot_data.get("id") or ""
        proj_id = shot_data.get("project_id") or ""
        if shot_id:
            try:
                from zeroxe.services.shot_service import ShotService
                live_assets = ShotService.get_assets_for_shot(shot_id, project_id=proj_id, force_refresh=True)
                if live_assets:
                    existing_ids = {a.get("id") for a in raw_assets if isinstance(a, dict) and a.get("id")}
                    existing_names = {a.get("name") for a in raw_assets if isinstance(a, dict) and a.get("name")}
                    for la in live_assets:
                        if la.get("id") not in existing_ids and la.get("name") not in existing_names:
                            raw_assets.append(la)
            except Exception:
                pass

        # Build asset type mapping (id -> (category_key, config))
        asset_type_map = {}
        for category_key, config in asset_types.items():
            if isinstance(config, dict):
                tid = config.get("id") or config.get("kitsu_id")
                if tid:
                    asset_type_map[str(tid)] = (category_key, config)

        # Categorize assets into collections dict
        categorized_assets: Dict[str, List[Dict[str, str]]] = {}
        clean_collections_dict: Dict[str, List[str]] = {}

        for a in raw_assets:
            if isinstance(a, dict):
                name = a.get("name", "").strip()
                type_id = str(a.get("entity_type_id", ""))
            elif hasattr(a, "name"):
                name = getattr(a, "name", "").strip()
                type_id = str(getattr(a, "entity_type_id", getattr(a, "asset_type_id", "")))
            else:
                continue

            if not name:
                continue

            category_key = ""
            config = {}
            if type_id in asset_type_map:
                category_key, config = asset_type_map[type_id]

            if not category_key:
                for k, cfg in asset_types.items():
                    if isinstance(cfg, dict):
                        prefix = cfg.get("prefix", "")
                        if prefix and name.startswith(prefix):
                            category_key = k
                            config = cfg
                            break

            if category_key.lower().startswith("ms_") or name.startswith("ms_") or name.startswith("LIT_") or name.startswith("COMP_"):
                continue

            code = config.get("code") or ("set" if name.startswith("s-") else ("chr" if name.startswith("c-") else ("prp" if name.startswith("p-") else "vhc")))
            prefix = config.get("prefix", "")
            base_dir = config.get("base_path") or ""
            proj_root = (project_path or "").rstrip("/\\")
            if proj_root and isinstance(base_dir, str):
                base_dir = base_dir.replace("@project_path@", proj_root)

            candidates = []
            if base_dir:
                base_p = Path(base_dir)
                candidates.append(base_p / name / f"{name}.blend")
                candidates.append(base_p / name / "final" / f"{name}.blend")
                if prefix and not name.startswith(prefix):
                    candidates.append(base_p / f"{prefix}{name}" / f"{prefix}{name}.blend")
                    candidates.append(base_p / f"{prefix}{name}" / "final" / f"{prefix}{name}.blend")
                if prefix and name.startswith(prefix):
                    clean_unprefixed = name[len(prefix):]
                    candidates.append(base_p / clean_unprefixed / f"{clean_unprefixed}.blend")
                    candidates.append(base_p / clean_unprefixed / "final" / f"{clean_unprefixed}.blend")

                existing_file = next((c for c in candidates if c.is_file()), None)
                file_path = str(existing_file) if existing_file else str(candidates[0])
            else:
                file_path = f"{name}.blend"

            if code not in categorized_assets:
                categorized_assets[code] = []
            categorized_assets[code].append({
                "name": name,
                "path": file_path,
                "category": category_key.lower(),
            })

            if code not in clean_collections_dict:
                clean_collections_dict[code] = []
            clean_collections_dict[code].append(file_path)

        # 4. Generate DCC script based on chosen mode
        if chosen_mode in ("source_shot", "custom"):
            resolved_source_file = chosen_source_file
            if not resolved_source_file and chosen_source_shot:
                resolved_sh_path = self.resolve_sibling_shot_layout(
                    sibling_shot_name=chosen_source_shot,
                    shot_data=shot_data,
                    current_department=current_department,
                    project_path=project_path,
                )
                if resolved_sh_path:
                    resolved_source_file = str(resolved_sh_path)

            if not resolved_source_file:
                logger.warning("No source file could be resolved for Layout; falling back to clean generation.")
                return self.build_clean_script(
                    filepath=final_file,
                    version_path=version_file,
                    collections=clean_collections_dict,
                    setting_data=resolved_settings,
                )

            return self.build_source_shot_script(
                source_file=resolved_source_file,
                filepath=final_file,
                version_path=version_file,
                kitsu_assets=categorized_assets,
                setting_data=resolved_settings,
            )

        # Default: Clean scene generation
        return self.build_clean_script(
            filepath=final_file,
            version_path=version_file,
            collections=clean_collections_dict,
            setting_data=resolved_settings,
        )

    def build_clean_script(
        self, filepath: str, version_path: str, collections: dict, setting_data: dict
    ) -> str:
        """Build Python script for clean Layout scene generation from scratch."""
        tpl = Template(
            dedent(
                """
import bpy
import os
import time
from pathlib import Path

_t0 = time.time()
print("=== [LAYOUT BUILDER] Starting Clean Scene Generation ===")

collections = $COLLECTIONS

# Clear all existing collections and objects before linking new ones
def clear_all():
	for obj in list(bpy.data.objects):
		bpy.data.objects.remove(obj, do_unlink=True)
	for collection in list(bpy.data.collections):
		bpy.data.collections.remove(collection)

clear_all()

def select_only(obj):
	for o in bpy.context.view_layer.objects:
		o.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

def link_collection(collections_dict):
	for category_name, file_paths in collections_dict.items():
		if category_name in bpy.data.collections:
			category_collection = bpy.data.collections[category_name]
		else:
			category_collection = bpy.data.collections.new(category_name)
			bpy.context.scene.collection.children.link(category_collection)

		for asset_path_str in file_paths:
			asset_path = Path(asset_path_str)
			asset_stem = asset_path.stem
			target_col_name = f"{asset_stem}_lo" if category_name == "set" else asset_stem

			if not asset_path.is_file():
				candidates = [
					asset_path,
					asset_path.parent / f"{asset_stem}.blend",
					asset_path.parent / "final" / f"{asset_stem}.blend",
				]
				found_path = next((p for p in candidates if p.is_file()), None)
				if found_path:
					asset_path = found_path
				else:
					print(f"[LAYOUT WARNING] Asset file not found on disk: {asset_path}")
					continue

			print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Loading '{target_col_name}' from {asset_path} -> '{category_name}'...")
			try:
				with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
					if target_col_name in data_from.collections:
						data_to.collections = [target_col_name]
					elif asset_stem in data_from.collections:
						data_to.collections = [asset_stem]
					else:
						match_col = next((c for c in data_from.collections if c.lower() == asset_stem.lower() or c.startswith(asset_stem)), None)
						if match_col:
							data_to.collections = [match_col]
						elif data_from.collections:
							data_to.collections = [data_from.collections[0]]
						else:
							print(f"[LAYOUT WARNING] Collection '{target_col_name}' not found in {asset_path}")
							continue

				for linked_collection in data_to.collections:
					if not linked_collection:
						continue
					if linked_collection.name not in category_collection.children:
						category_collection.children.link(linked_collection)

					armatures = [obj for obj in linked_collection.all_objects if obj.type == 'ARMATURE']
					if not armatures:
						print(f"[SKIP] '{linked_collection.name}' tidak punya Armature.")
					else:
						for arm in armatures:
							select_only(arm)
							bpy.context.view_layer.update()
							try:
								bpy.ops.object.make_override_library(collection=linked_collection.session_uid)
								break
							except Exception:
								try:
									bpy.ops.object.make_override_library()
									break
								except Exception:
									pass

					if linked_collection.name in bpy.data.collections:
						overridden_collection = bpy.data.collections[linked_collection.name]
						if overridden_collection.name not in [child.name for child in category_collection.children]:
							category_collection.children.link(overridden_collection)
						if overridden_collection.name in [child.name for child in bpy.context.scene.collection.children]:
							bpy.context.scene.collection.children.unlink(overridden_collection)

					bpy.context.view_layer.update()
					print(f"[LAYOUT] Linked collection '{linked_collection.name}' into '{category_name}'")
			except Exception as ex:
				print(f"[LAYOUT ERROR] Failed to link {asset_path}: {ex}")

link_collection(collections)

def add_camera_rig():
	cam_collection = bpy.data.collections.new("cam")
	bpy.context.scene.collection.children.link(cam_collection)
	bpy.ops.object.select_all(action='DESELECT')
	built = False
	try:
		if hasattr(bpy.ops.object, "build_camera_rig"):
			bpy.ops.object.build_camera_rig(mode='DOLLY')
			for obj in bpy.context.selected_objects:
				for col in list(obj.users_collection):
					col.objects.unlink(obj)
				cam_collection.objects.link(obj)
			built = True
	except Exception as e:
		print(f"[CAMERA RIG NOTE] Dolly rig error: {e}")

	if not built:
		try:
			bpy.ops.object.camera_add()
			cam_obj = bpy.context.active_object
			if cam_obj:
				cam_obj.name = "Camera"
				for col in list(cam_obj.users_collection):
					col.objects.unlink(cam_obj)
				cam_collection.objects.link(cam_obj)
				bpy.context.scene.camera = cam_obj
				print("[CAMERA RIG] Fallback standard camera created.")
		except Exception as ex:
			print(f"[CAMERA RIG ERROR] Failed to create camera: {ex}")

add_camera_rig()

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

bpy.context.scene.render.use_simplify = True
bpy.context.scene.render.simplify_subdivision = 1

try:
	bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
except Exception as e:
	print(f"[PURGE NOTE] {e}")

print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Saving initial version: $VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
"""
            )
        )
        end_tpl = Template(
            dedent(
                """
# Save final version and master copy after presets
print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Saving final version and master copy...")
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$FINAL_PATH", copy=True)
print(f"=== [LAYOUT BUILDER] Completed in {time.time()-_t0:.1f}s ===")
bpy.ops.wm.quit_blender()
"""
            )
        )

        script = tpl.substitute(
            COLLECTIONS=collections,
            SETTINGS=setting_data,
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    preset_code = f.read()
                    script = script + "\n\n# --- Preset Script Injection ---\n" + preset_code + "\n# --- End Preset ---\n\n"
            except Exception as e:
                logger.warning(f"Could not inject preset script: {e}")

        end_script = end_tpl.substitute(
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
        )
        script = script + end_script
        return script

    def build_source_shot_script(
        self,
        source_file: str,
        filepath: str,
        version_path: str,
        kitsu_assets: dict,
        setting_data: dict,
    ) -> str:
        """Build Python script that sources from another shot and matches casting with Kitsu."""
        tpl = Template(
            dedent(
                """
import bpy
import os
import time
from pathlib import Path

_t0 = time.time()
source_file = "$SOURCE_FILE"
print(f"=== [LAYOUT BUILDER] Opening source scene: {source_file} ===")
bpy.ops.wm.open_mainfile(filepath=source_file)
print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Source scene opened successfully.")

kitsu_assets = $KITSU_ASSETS

def get_existing_asset_names():
	existing = set()
	for col in bpy.data.collections:
		c_name = col.name.split(".")[0]
		existing.add(c_name.lower())
		if c_name.lower().endswith("_lo"):
			existing.add(c_name[:-3].lower())
		elif c_name.lower().endswith("_hi"):
			existing.add(c_name[:-3].lower())

	for lib in bpy.data.libraries:
		if lib.filepath:
			stem = Path(bpy.path.abspath(lib.filepath)).stem
			existing.add(stem.lower())
			if stem.lower().endswith("_lo"):
				existing.add(stem[:-3].lower())
			elif stem.lower().endswith("_hi"):
				existing.add(stem[:-3].lower())

	for obj in bpy.data.objects:
		if obj.instance_collection:
			inst_name = obj.instance_collection.name.split(".")[0]
			existing.add(inst_name.lower())

	return existing

def ensure_collection(col_name):
	if col_name in bpy.data.collections:
		col = bpy.data.collections[col_name]
	else:
		col = bpy.data.collections.new(col_name)
		bpy.context.scene.collection.children.link(col)
	return col

def select_only(obj):
	for o in bpy.context.view_layer.objects:
		o.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

existing_names = get_existing_asset_names()
print(f"[LAYOUT BUILDER] Detected {len(existing_names)} existing asset keys in source scene.")

# Compare Kitsu assets with scene assets:
# If asset exists in scene -> Keep it (preserved, not deleted).
# If asset exists in scene but not in Kitsu -> Keep it (preserved, like sync system).
# If asset does NOT exist in scene -> Link it into appropriate collection.
new_assets_to_link = {}
for cat_code, asset_list in kitsu_assets.items():
	for item in asset_list:
		asset_name = item.get("name", "").strip()
		if not asset_name:
			continue

		clean_name = asset_name.lower()
		target_col_name = f"{asset_name}_lo" if cat_code == "set" else asset_name

		unprefixed_name = clean_name
		for pref in ("c-", "p-", "s-", "v-", "chr_", "prp_", "set_", "vhc_"):
			if clean_name.startswith(pref):
				unprefixed_name = clean_name[len(pref):]
				break

		is_present = (
			clean_name in existing_names
			or unprefixed_name in existing_names
			or target_col_name.lower() in existing_names
			or f"{clean_name}_lo" in existing_names
			or f"{clean_name}_hi" in existing_names
		)

		if is_present:
			print(f"  [EXISTS] '{asset_name}' is already present in source scene. (Preserved)")
		else:
			print(f"  [MISSING] '{asset_name}' is NOT in scene -> Queued for linking into '{cat_code}'")
			if cat_code not in new_assets_to_link:
				new_assets_to_link[cat_code] = []
			new_assets_to_link[cat_code].append(item)

# Link missing assets
linked_assets_count = 0
for cat_code, items in new_assets_to_link.items():
	cat_col = ensure_collection(cat_code)

	for item in items:
		asset_name = item["name"]
		asset_path = Path(item["path"])
		coll_to_load = f"{asset_name}_lo" if cat_code == "set" else asset_name

		if not asset_path.is_file():
			candidates = [
				asset_path,
				asset_path.parent / f"{asset_name}.blend",
				asset_path.parent / "final" / f"{asset_name}.blend",
			]
			found_path = next((p for p in candidates if p.is_file()), None)
			if found_path:
				asset_path = found_path
			else:
				print(f"[LAYOUT WARNING] Asset file does not exist on disk: {asset_path}")
				continue

		print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Linking '{coll_to_load}' from {asset_path} -> Collection '{cat_code}'...")

		try:
			with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
				if coll_to_load in data_from.collections:
					data_to.collections = [coll_to_load]
				elif asset_name in data_from.collections:
					data_to.collections = [asset_name]
				else:
					match_col = next((c for c in data_from.collections if c.lower() == asset_name.lower() or c.startswith(asset_name)), None)
					if match_col:
						data_to.collections = [match_col]
					elif data_from.collections:
						data_to.collections = [data_from.collections[0]]
					else:
						print(f"[LAYOUT WARNING] Collection '{coll_to_load}' not found in {asset_path}")
						continue

			for linked_col in data_to.collections:
				if not linked_col:
					continue

				if linked_col.name not in cat_col.children:
					cat_col.children.link(linked_col)

				armatures = [obj for obj in linked_col.all_objects if obj.type == 'ARMATURE']
				if armatures:
					for arm in armatures:
						select_only(arm)
						bpy.context.view_layer.update()
						try:
							bpy.ops.object.make_override_library(collection=linked_col.session_uid)
							break
						except Exception:
							try:
								bpy.ops.object.make_override_library()
								break
							except Exception as err:
								print(f"[LAYOUT WARNING] Library override failed for {arm.name}: {err}")

				if linked_col.name in bpy.data.collections:
					over_col = bpy.data.collections[linked_col.name]
					if over_col.name not in cat_col.children:
						cat_col.children.link(over_col)
					if over_col.name in bpy.context.scene.collection.children:
						bpy.context.scene.collection.children.unlink(over_col)

				bpy.context.view_layer.update()
				linked_assets_count += 1
				print(f"[LAYOUT] Successfully linked '{linked_col.name}' into '{cat_code}'")

		except Exception as ex:
			print(f"[LAYOUT ERROR] Failed to link asset '{asset_name}': {ex}")

# Ensure camera rig exists
def ensure_camera_rig():
	has_cam = "cam" in bpy.data.collections or any(o.type == 'CAMERA' for o in bpy.data.objects)
	if not has_cam:
		cam_collection = bpy.data.collections.new("cam")
		bpy.context.scene.collection.children.link(cam_collection)
		bpy.ops.object.select_all(action='DESELECT')
		built = False
		try:
			if hasattr(bpy.ops.object, "build_camera_rig"):
				bpy.ops.object.build_camera_rig(mode='DOLLY')
				for obj in bpy.context.selected_objects:
					for col in list(obj.users_collection):
						col.objects.unlink(obj)
					cam_collection.objects.link(obj)
				built = True
		except Exception as e:
			print(f"[CAMERA RIG NOTE] Dolly rig error: {e}")

		if not built:
			try:
				bpy.ops.object.camera_add()
				cam_obj = bpy.context.active_object
				if cam_obj:
					cam_obj.name = "Camera"
					for col in list(cam_obj.users_collection):
						col.objects.unlink(cam_obj)
					cam_collection.objects.link(cam_obj)
					bpy.context.scene.camera = cam_obj
					print("[CAMERA RIG] Fallback standard camera created.")
			except Exception as ex:
				print(f"[CAMERA RIG ERROR] Failed to create camera: {ex}")

ensure_camera_rig()

# Configure Timeline, FPS, Resolution, Simplify matching clean generate
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

bpy.context.scene.render.use_simplify = True
bpy.context.scene.render.simplify_subdivision = 1

try:
	bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
except Exception as e:
	print(f"[PURGE NOTE] {e}")

# Save initial version so bpy.data.filepath is set for presets
print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Saving initial version: $VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
"""
            )
        )
        end_tpl = Template(
            dedent(
                """
# Save final version and master copy
print(f"[LAYOUT] [{time.time()-_t0:.1f}s] Saving final version and master copy...")
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$FINAL_PATH", copy=True)
print(f"=== [LAYOUT BUILDER] Completed in {time.time()-_t0:.1f}s ===")
bpy.ops.wm.quit_blender()
"""
            )
        )

        script = tpl.substitute(
            SOURCE_FILE=source_file,
            KITSU_ASSETS=kitsu_assets,
            SETTINGS=setting_data,
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    preset_code = f.read()
                    script = script + "\n\n# --- Preset Script Injection ---\n" + preset_code + "\n# --- End Preset ---\n\n"
            except Exception as e:
                logger.warning(f"Could not inject preset script: {e}")

        end_script = end_tpl.substitute(
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
        )
        script = script + end_script
        return script


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        file_paths = json.loads(sys.argv[-1])

        builder = LayoutBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            filepath=file_paths,
            show_ui=False,
        )
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
