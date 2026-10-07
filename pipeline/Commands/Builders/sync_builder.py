"""Sync Builder Module for ZeroXe Pipeline.

Synchronizes newly linked Kitsu shot assets (Characters, Props, Vehicles, Sets) into
working Layout and Animation scene files. Increments and saves a new version only if
new assets from Kitsu are missing in the Blender file. If all assets already exist or
the Blender file contains additional elements, existing assets are preserved and no
new version is generated.
"""

from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union
try:
    from versioning import VersioningSystem
except ImportError:
    try:
        from Commands.versioning import VersioningSystem
    except ImportError:
        try:
            from pipeline.Commands.versioning import VersioningSystem
        except ImportError:
            try:
                from ..versioning import VersioningSystem
            except (ImportError, ValueError):
                VersioningSystem = None


class SyncBuilder:
    """Builder for synchronizing Kitsu shot assets into Layout and Animation scene files."""

    def extract_data(
        self,
        shot_data: Dict[str, Any],
        current_department: Dict[str, Any],
        asset_department: Dict[str, Any],
        filepath: Dict[str, str],
        config_path: Optional[Union[str, Path]] = None,
        project_path: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Analyze shot assets and generate DCC synchronization script."""
        current_file = filepath.get("version") or filepath.get("final") or ""
        
        # Calculate target next version path
        next_ver_path = VersioningSystem.get_next_version_path(current_file)
        final_path = filepath.get("final") or VersioningSystem.get_master_path(current_file)

        # 1. Resolve asset types from configuration
        asset_types = asset_department.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in asset_department:
            asset_types = asset_department.get("asset_type", {})

        # 2. Gather shot assets from shot_data (or fetch on-demand if empty)
        raw_assets = shot_data.get("assets", []) or []
        if not raw_assets and shot_data.get("id"):
            try:
                import gazu
                raw_assets = gazu.asset.all_assets_for_shot(shot_data["id"]) or []
            except Exception:
                try:
                    from zeroxe.services.shot_service import ShotService
                    raw_assets = ShotService.get_assets_for_shot(shot_data["id"]) or []
                except Exception:
                    pass

        # Build asset type mapping (id -> config)
        asset_type_map = {}
        for category_key, config in asset_types.items():
            if isinstance(config, dict):
                tid = config.get("id") or config.get("kitsu_id")
                if tid:
                    asset_type_map[str(tid)] = (category_key, config)

        # 3. Build candidate collections dictionary
        collections_dict: Dict[str, List[Dict[str, str]]] = {}
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

            # Detect category key from name prefix if type_id mapping missing
            if not category_key:
                for k, cfg in asset_types.items():
                    if isinstance(cfg, dict):
                        prefix = cfg.get("prefix", "")
                        if prefix and name.startswith(prefix):
                            category_key = k
                            config = cfg
                            break

            # Filter out mastershot assets
            if category_key.lower().startswith("ms_") or name.startswith("ms_") or name.startswith("LIT_") or name.startswith("COMP_"):
                continue

            code = config.get("code") or ("set" if name.startswith("s-") else ("chr" if name.startswith("c-") else ("prp" if name.startswith("p-") else "vhc")))
            base_dir = config.get("base_path") or ""
            proj_root = (project_path or "").rstrip("/\\")
            if proj_root and isinstance(base_dir, str):
                base_dir = base_dir.replace("@project_path@", proj_root)

            file_path = str(Path(base_dir) / name / f"{name}.blend") if base_dir else f"{name}.blend"

            if code not in collections_dict:
                collections_dict[code] = []

            collections_dict[code].append({
                "name": name,
                "path": file_path,
                "category": category_key.lower(),
            })

        # 4. Department specific settings
        dept_data = next(iter(current_department.values())) if current_department else {}
        dept_name = str(next(iter(current_department.keys())) if current_department else "").lower()
        is_layout = "lay" in dept_name
        is_lighting = "light" in dept_name or "lgt" in dept_name

        script = self.script_builder(
            current_filepath=str(current_file),
            next_version_path=str(next_ver_path),
            final_filepath=str(final_path),
            kitsu_assets=collections_dict,
            is_layout=is_layout,
            is_lighting=is_lighting,
        )
        return script

    def script_builder(
        self,
        current_filepath: str,
        next_version_path: str,
        final_filepath: str,
        kitsu_assets: Dict[str, Any],
        is_layout: bool = False,
        is_lighting: bool = False,
    ) -> str:
        """Generate Blender Python script that performs asset synchronization."""
        tpl = Template(
            dedent(
                """
import bpy
import os
import sys
from pathlib import Path

kitsu_assets = $KITSU_ASSETS
current_file = "$CURRENT_FILE"
next_version_path = "$NEXT_VERSION_PATH"
final_filepath = "$FINAL_FILEPATH"
is_layout = $IS_LAYOUT
is_lighting = $IS_LIGHTING

print("=" * 60)
print(f"[SYNC] Starting Asset Sync for: {current_file}")
print("=" * 60)

# 1. Open current working file if exists
if current_file and Path(current_file).is_file():
	bpy.ops.wm.open_mainfile(filepath=current_file)
else:
	print(f"[SYNC] Current file not found on disk, creating new scene: {current_file}")
	bpy.ops.wm.read_factory_settings(use_empty=True)

def select_only(obj):
	for o in bpy.context.view_layer.objects:
		o.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

def ensure_collection(name: str, parent=None) -> bpy.types.Collection:
	coll = bpy.data.collections.get(name)
	if not coll:
		coll = bpy.data.collections.new(name)
		print(f"[SYNC] Created category collection: {name}")
	if parent is None:
		parent = bpy.context.scene.collection
	if coll.name not in parent.children:
		parent.children.link(coll)
	return coll

def get_existing_asset_names() -> set:
	existing = set()
	
	# Check all collections (by collection name and base name)
	for col in bpy.data.collections:
		c_name = col.name.strip()
		existing.add(c_name.lower())
		# Handle name without suffixes like _lo, _hi, .001
		base = c_name.split(".")[0].rstrip("_lo").rstrip("_hi")
		existing.add(base.lower())

	# Check libraries
	for lib in bpy.data.libraries:
		if lib.filepath:
			stem = Path(bpy.path.abspath(lib.filepath)).stem
			existing.add(stem.lower())

	# Check top-level objects
	for obj in bpy.data.objects:
		obj_base = obj.name.split(".")[0].split(":")[0]
		existing.add(obj_base.lower())

	return existing

existing_names = get_existing_asset_names()
print(f"[SYNC] Found {len(existing_names)} existing asset references in Blender scene.")

# 2. Identify new assets from Kitsu not yet present in Blender scene
new_assets_to_link = {}
total_kitsu_assets = 0

for cat_code, asset_list in kitsu_assets.items():
	for item in asset_list:
		total_kitsu_assets += 1
		asset_name = item.get("name", "").strip()
		if not asset_name:
			continue

		clean_name = asset_name.lower()
		target_col_name = f"{asset_name}_lo" if cat_code == "set" and not is_lighting else (f"{asset_name}_hi" if cat_code == "set" else asset_name)

		# Check if already present in scene
		is_present = (
			clean_name in existing_names
			or target_col_name.lower() in existing_names
			or any(clean_name == e or clean_name in e for e in existing_names)
		)

		if not is_present:
			if cat_code not in new_assets_to_link:
				new_assets_to_link[cat_code] = []
			new_assets_to_link[cat_code].append(item)

# 3. Evaluate Sync Decision
num_new_assets = sum(len(items) for items in new_assets_to_link.values())
print(f"[SYNC] Kitsu Total Assets: {total_kitsu_assets} | New Missing Assets to Link: {num_new_assets}")

if num_new_assets == 0:
	print("[SYNC] All Kitsu assets already exist in Blender scene. (Existing scene elements preserved).")
	print("[SYNC] NO NEW VERSION CREATED.")
else:
	print(f"[SYNC] Linking {num_new_assets} new asset(s) into scene...")

	for cat_code, items in new_assets_to_link.items():
		cat_col = ensure_collection(cat_code)

		for item in items:
			asset_name = item["name"]
			asset_path = Path(item["path"])
			coll_to_load = f"{asset_name}_lo" if cat_code == "set" and not is_lighting else (f"{asset_name}_hi" if cat_code == "set" else asset_name)

			if not asset_path.is_file():
				print(f"[SYNC WARNING] Asset file does not exist on disk: {asset_path}")
				continue

			print(f"[SYNC] Linking '{coll_to_load}' from {asset_path} -> '{cat_code}'...")

			try:
				with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
					if coll_to_load in data_from.collections:
						data_to.collections = [coll_to_load]
					elif asset_name in data_from.collections:
						data_to.collections = [asset_name]
					else:
						# Fallback to any collection starting with prefix
						match_col = next((c for c in data_from.collections if c.startswith(asset_name)), None)
						if match_col:
							data_to.collections = [match_col]
						else:
							print(f"[SYNC WARNING] Collection '{coll_to_load}' not found in {asset_path}")
							continue

				for linked_col in data_to.collections:
					if not linked_col:
						continue

					if linked_col.name not in cat_col.children:
						cat_col.children.link(linked_col)

					# Library override for armatures (character/prop animation)
					armatures = [obj for obj in linked_col.all_objects if obj.type == 'ARMATURE']
					if armatures:
						for arm in armatures:
							select_only(arm)
							bpy.context.view_layer.update()
							try:
								bpy.ops.object.make_override_library(collection=linked_col.session_uid)
							except Exception:
								try:
									bpy.ops.object.make_override_library()
								except Exception as err:
									print(f"[SYNC WARNING] Library override failed for {arm.name}: {err}")

					# Ensure overridden collection stays in category collection and not root
					if linked_col.name in bpy.data.collections:
						over_col = bpy.data.collections[linked_col.name]
						if over_col.name not in cat_col.children:
							cat_col.children.link(over_col)
						if over_col.name in bpy.context.scene.collection.children:
							bpy.context.scene.collection.children.unlink(over_col)

					bpy.context.view_layer.update()
					print(f"[SYNC] Successfully linked '{linked_col.name}' into '{cat_code}'")

			except Exception as ex:
				print(f"[SYNC ERROR] Failed to link asset '{asset_name}': {ex}")

	# Save to Next Incremental Version
	Path(next_version_path).parent.mkdir(parents=True, exist_ok=True)
	bpy.ops.wm.save_as_mainfile(filepath=next_version_path)
	print(f"[SYNC] Successfully saved next version: {next_version_path}")

	# Also update master / final file if defined
	if final_filepath:
		Path(final_filepath).parent.mkdir(parents=True, exist_ok=True)
		bpy.ops.wm.save_as_mainfile(filepath=final_filepath)
		print(f"[SYNC] Updated master file: {final_filepath}")

print("=" * 60)
print("[SYNC] Synchronization finished.")
print("=" * 60)
"""
            )
        )

        return tpl.substitute(
            KITSU_ASSETS=kitsu_assets,
            CURRENT_FILE=current_filepath,
            NEXT_VERSION_PATH=next_version_path,
            FINAL_FILEPATH=final_filepath,
            IS_LAYOUT=is_layout,
            IS_LIGHTING=is_lighting,
        )
