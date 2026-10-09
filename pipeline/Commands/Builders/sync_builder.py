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

        # Deduce project_path from current_file if missing
        if not project_path and current_file:
            fp_str = str(current_file).replace("\\", "/")
            for prod_token in ("/02_production/", "/01_pre_production/", "/01_preproduction/", "/03_post_production/"):
                if prod_token in fp_str:
                    project_path = fp_str.split(prod_token)[0]
                    break

        # 1. Resolve asset types from configuration
        asset_types = asset_department.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in asset_department:
            asset_types = asset_department.get("asset_type", {})

        # 2. Gather shot assets from shot_data and Kitsu live query
        raw_assets = list(shot_data.get("assets", []) or [])
        shot_id = shot_data.get("id") or ""
        proj_id = shot_data.get("project_id") or ""
        if shot_id:
            try:
                from zeroxe.services.shot_service import ShotService
                live_assets = ShotService.get_assets_for_shot(shot_id, project_id=proj_id, force_refresh=True)
                if live_assets:
                    # Merge live assets, avoiding duplicates by id or name
                    existing_ids = {a.get("id") for a in raw_assets if isinstance(a, dict) and a.get("id")}
                    existing_names = {a.get("name") for a in raw_assets if isinstance(a, dict) and a.get("name")}
                    for la in live_assets:
                        if la.get("id") not in existing_ids and la.get("name") not in existing_names:
                            raw_assets.append(la)
            except Exception:
                try:
                    import gazu
                    gazu_assets = gazu.asset.all_assets_for_shot(shot_id) or []
                    if gazu_assets and not raw_assets:
                        raw_assets = gazu_assets
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
            prefix = config.get("prefix", "")
            base_dir = config.get("base_path") or ""
            proj_root = (project_path or "").rstrip("/\\")
            if proj_root and isinstance(base_dir, str):
                base_dir = base_dir.replace("@project_path@", proj_root)

            # Robust candidate paths on disk (with prefix, without prefix, direct)
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

print("=" * 70)
print("[SYNC] ZeroXe DCC Asset Synchronization")
print(f" Target File      : {current_file}")
print(f" Next Version Path: {next_version_path}")
print(f" Master File Path : {final_filepath}")
print("=" * 70)

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
	
	# 1. Check all collections (exact collection name, stem, and clean name without suffixes)
	for col in bpy.data.collections:
		c_name = col.name.strip()
		existing.add(c_name.lower())
		base = c_name.split(".")[0]
		existing.add(base.lower())
		if base.lower().endswith("_lo"):
			existing.add(base[:-3].lower())
		elif base.lower().endswith("_hi"):
			existing.add(base[:-3].lower())

	# 2. Check linked libraries (filepath stems)
	for lib in bpy.data.libraries:
		if lib.filepath:
			stem = Path(bpy.path.abspath(lib.filepath)).stem
			existing.add(stem.lower())
			if stem.lower().endswith("_lo"):
				existing.add(stem[:-3].lower())
			elif stem.lower().endswith("_hi"):
				existing.add(stem[:-3].lower())

	# 3. Check direct library objects
	for obj in bpy.data.objects:
		if obj.instance_collection:
			inst_name = obj.instance_collection.name.split(".")[0]
			existing.add(inst_name.lower())

	return existing

# --- SECTION 1: KITSU ASSETS ---
print("\\n=== [1/4] KITSU ASSETS REGISTERED FOR SHOT ===")
total_kitsu_assets = 0
for cat_code, asset_list in kitsu_assets.items():
	print(f" Category: [{cat_code}] ({len(asset_list)} asset(s))")
	for item in asset_list:
		total_kitsu_assets += 1
		a_name = item.get("name", "")
		a_path = item.get("path", "")
		exists_str = "FOUND ON DISK" if Path(a_path).is_file() else "MISSING ON DISK"
		print(f"  • {a_name} -> {a_path} [{exists_str}]")
if total_kitsu_assets == 0:
	print("  (No casting or assets linked in Kitsu for this shot)")

# --- SECTION 2: BLENDER SCENE CONTENTS ---
print("\\n=== [2/4] CURRENT BLENDER SCENE CONTENTS ===")
print(f" Collections in Scene ({len(bpy.data.collections)}):")
for col in bpy.data.collections:
	print(f"  • Collection: '{col.name}' (Objects: {len(col.objects)})")

print(f" Linked Libraries in Scene ({len(bpy.data.libraries)}):")
for lib in bpy.data.libraries:
	print(f"  • Library: '{lib.filepath}' (name='{lib.name}')")

print(f" Objects in Scene ({len(bpy.data.objects)}):")
for obj in bpy.data.objects:
	if obj.instance_collection:
		print(f"  • Instance: '{obj.name}' -> Collection: '{obj.instance_collection.name}'")
	elif obj.library:
		print(f"  • Library Obj: '{obj.name}' (type={obj.type}, lib={obj.library.name})")

existing_names = get_existing_asset_names()
print(f" Registered Existing Asset Keys ({len(existing_names)}):")
for k in sorted(existing_names):
	print(f"  - '{k}'")

# --- SECTION 3: COMPARISON & DECISION ---
print("\\n=== [3/4] SYNC ASSET COMPARISON & DECISION ===")
new_assets_to_link = {}

for cat_code, asset_list in kitsu_assets.items():
	for item in asset_list:
		asset_name = item.get("name", "").strip()
		if not asset_name:
			continue

		clean_name = asset_name.lower()
		target_col_name = f"{asset_name}_lo" if cat_code == "set" and not is_lighting else (f"{asset_name}_hi" if cat_code == "set" else asset_name)

		# Extract unprefixed base name (e.g. c-hero -> hero)
		unprefixed_name = clean_name
		for pref in ("c-", "p-", "s-", "v-", "chr_", "prp_", "set_", "vhc_"):
			if clean_name.startswith(pref):
				unprefixed_name = clean_name[len(pref):]
				break

		# Exact matching check
		is_present = (
			clean_name in existing_names
			or unprefixed_name in existing_names
			or target_col_name.lower() in existing_names
			or f"{clean_name}_lo" in existing_names
			or f"{clean_name}_hi" in existing_names
		)

		if is_present:
			print(f"  [EXISTS] '{asset_name}' is already present in scene. (Preserved)")
		else:
			print(f"  [MISSING] '{asset_name}' is NOT in scene -> Queued for linking into '{cat_code}'")
			if cat_code not in new_assets_to_link:
				new_assets_to_link[cat_code] = []
			new_assets_to_link[cat_code].append(item)

# --- SECTION 4: LINKING & VERSIONING ---
num_new_assets = sum(len(items) for items in new_assets_to_link.values())
print("\\n=== [4/4] SYNC EXECUTION SUMMARY ===")
print(f" Total Kitsu Assets    : {total_kitsu_assets}")
print(f" Missing Assets to Link: {num_new_assets}")

if num_new_assets == 0:
	print("\\n[SYNC] All Kitsu assets already exist in Blender scene. (Existing scene elements preserved).")
	print("[SYNC] NO NEW VERSION CREATED.")
else:
	print(f"\\n[SYNC] Linking {num_new_assets} new asset(s) into scene...")
	linked_assets_count = 0

	for cat_code, items in new_assets_to_link.items():
		cat_col = ensure_collection(cat_code)

		for item in items:
			asset_name = item["name"]
			asset_path = Path(item["path"])
			coll_to_load = f"{asset_name}_lo" if cat_code == "set" and not is_lighting else (f"{asset_name}_hi" if cat_code == "set" else asset_name)

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
					print(f"[SYNC WARNING] Asset file does not exist on disk: {asset_path}")
					continue

			print(f"[SYNC] Linking '{coll_to_load}' from {asset_path} -> Collection '{cat_code}'...")

			try:
				with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
					if coll_to_load in data_from.collections:
						data_to.collections = [coll_to_load]
					elif asset_name in data_from.collections:
						data_to.collections = [asset_name]
					else:
						# Fallback to collection matching name or unprefixed name
						match_col = next((c for c in data_from.collections if c.lower() == asset_name.lower() or c.startswith(asset_name)), None)
						if match_col:
							data_to.collections = [match_col]
						elif data_from.collections:
							data_to.collections = [data_from.collections[0]]
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
					linked_assets_count += 1
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

print("=" * 70)
print("[SYNC] Synchronization finished.")
print("=" * 70)
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
