import sys
import json
from pathlib import Path
from textwrap import dedent
from string import Template


class LightingBuilder:
    def extract_data(
        self,
        shot_data,
        current_department,
        asset_department,
        mastershots_data,
        addons_data,
        filepath,
    ):
        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)
        
        # Get lit mastershot path
        relative_assets = {}
        asset_types = asset_department.get("Asset", {}).get("asset_type", {})
        shot_assets_content = shot_data.get("assets", [])
        asset_type_map = {config["id"]: (category_key, config) for category_key, config in asset_types.items()}
        
        lit_mastershot_name = ""
        lit_mastershot_base_path = ""

        for asset in shot_assets_content:
            asset_type_id = asset.get("entity_type_id")
            if asset_type_id in asset_type_map:
                category_key, config = asset_type_map[asset_type_id]
                if category_key.lower() == "set":
                    if category_key not in relative_assets:
                        relative_assets[category_key] = {
                            "assets": [],
                            "base_path": config.get("base_path"),
                            "prefix": config.get("prefix"),
                            "code": config.get("code"),
                        }
                    relative_assets[category_key]["assets"].append(asset["name"])
                elif category_key.lower().startswith("ms_"):
                    if category_key.lower() == "ms_lit":
                        lit_mastershot_name = asset.get("name", "")
                        lit_mastershot_base_path = config.get("base_path", "")
                    if category_key in asset_types:
                        del asset_types[category_key]
        
        lit_mastershot_file = (
            Path(lit_mastershot_base_path)
            / lit_mastershot_name
            / f"{lit_mastershot_name}.blend"
        )

        # Construct collection dict
        collections_dict = {}
        for category, data in relative_assets.items():
            paths = []
            base_dir = Path(data["base_path"])

            for asset in data["assets"]:
                filename = f"{asset}.blend"
                full_path = base_dir / asset / filename

                # Convert back to string for Blender's libraries.load
                paths.append(str(full_path))

            collections_dict[data["code"]] = paths

        # Get preset
        dept_data = next(iter(current_department.values()))
        preset_name = "preset"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")

        # Get addon preset
        addon_preset_path = (
            addons_data.get("addons", {})
            .get("ops_blp", {})
            .get("base_path", "")
        )
        addon_preset_file = Path(addon_preset_path) / f"{lit_mastershot_name}.json"

        # Collection list
        collection_list = [
            (config.get("code"), config.get("prefix"))
            for config in asset_types.values()
            if config.get("code") not in ["ms", "set"] and not config.get("code", "").startswith("ms")
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
            "ops_blp": str(addon_preset_file),
            "script_path": preset_path,
        }

        lighting_script = self.script_builder(
            filepath=filepath["final"],
            version_path=filepath["version"],
            master_file=str(lit_mastershot_file),
            animation_file=filepath["source"],
            setting_data=setting_data,
            collection_list=collection_list,
            set_collection=collections_dict
        )
        return lighting_script

    def script_builder(
        self,
        filepath: str,
        version_path: str,
        master_file: str,
        animation_file: str,
        setting_data: dict,
        collection_list: list,
        set_collection: list,
    ):
        tpl = Template(
            dedent(
                """
import bpy
from pathlib import Path

collections = $SET_COLLECTION
							  
bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

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

def ensure_parent_in_scene(name: str) -> bpy.types.Collection:
	if name.lower() != "$CAMERA_COLLECTION".lower():
		_force_remove_collection(name)
		parent = bpy.data.collections.new(name)
		bpy.context.scene.collection.children.link(parent)
		print(f"Created and linked parent collection: {name}")
		return parent


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
	
# Main Fucntion
def link_animation():
	# Link the animation file
	link_whole = $LINK_WHOLE
	print("Animation file:", "$ANIMATION_FILE")
	parents = {}
	for name, prefix in $COLLECTION_LIST:
		if name.lower() == "$CAMERA_COLLECTION".lower():
			_force_remove_collection("$CAMERA_COLLECTION")
			continue
		parents[name] = ensure_parent_in_scene(name)

	desired = {}
	with bpy.data.libraries.load("$ANIMATION_FILE", link=True) as (data_from, data_to):
		for parent_name, prefix in $COLLECTION_LIST:
			if prefix is None:
				cam_coll = next((c for c in data_from.collections if c.lower() == "$CAMERA_COLLECTION".lower()), None)
				if cam_coll:
					desired[parent_name] = [cam_coll]
				else:
					desired[parent_name] = []
				print("[WARNING] '$CAMERA_COLLECTION' not found in library")
			else:
				names = [n for n in data_from.collections if n.startswith(prefix)]
				desired[parent_name] = names

	to_link = []
	for parent_name, names in desired.items():
		if parent_name.lower() == "$CAMERA_COLLECTION".lower():
			continue
		if link_whole:
			if desired[parent_name]:
				_force_remove_collection(parent_name)
				to_link.append(parent_name)
		else:
			to_link.extend(names)

	to_link = [n for n in to_link if n not in bpy.data.collections]

	if to_link:
		with bpy.data.libraries.load("$ANIMATION_FILE", link=True) as (data_from, data_to):
			data_to.collections = [n for n in to_link if n in data_from.collections]
			print(f"linked: {data_to.collections}")
	bpy.context.view_layer.update()
	root_col = bpy.context.scene.collection

	fg_parent = ensure_parent_in_scene("fg")
	for parent_name, child_names in desired.items():
		if parent_name.lower() == "$CAMERA_COLLECTION".lower():
			continue

		if link_whole:
			col = bpy.data.collections.get(parent_name)
			if not col:
				print(f"[WARNING] Expected linked collection missing: {parent_name}")
				continue

			if not (col.library and bpy.path.abspath(col.library.filepath) == bpy.path.abspath("$ANIMATION_FILE")):
				col = next((c for c in bpy.data.collections
							if c.name == parent_name and c.library and
							bpy.path.abspath(c.library.filepath) == bpy.path.abspath("$ANIMATION_FILE")), None)
				if not col:
					print(f"[WARNING] (Parent) No valid linked collection found for: {parent_name}")
					continue

			if col.name not in root_col.children:
				root_col.children.link(col)
				print(f"Linked '{parent_name}' under '{root_col.name}'")

			continue

		parent = parents.get(parent_name)
		if not parent:
			print(f"[WARNING] Local parent collection not found: {parent_name}")
			continue

		for cname in child_names:
			col = bpy.data.collections.get(cname)
			if not col:
				print(f"[WARNING] Expected linked collection missing: {cname}")
				continue

			if not (col.library and bpy.path.abspath(col.library.filepath) == bpy.path.abspath("$ANIMATION_FILE")):
				col = next((c for c in bpy.data.collections
							if c.name == cname and c.library and
							bpy.path.abspath(c.library.filepath) == bpy.path.abspath("$ANIMATION_FILE")), None)
				if not col:
					print(f"[WARNING] No valid linked collection found for: {cname}")
					continue

			if col.name not in parent.children:
				parent.children.link(col)
				print(f"Linked '{cname}' under '{parent_name}'")

		if parent.name not in fg_parent.children:
			fg_parent.children.link(parent)
			bpy.context.scene.collection.children.unlink(parent)

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

		with bpy.data.libraries.load("$ANIMATION_FILE", link=link_mode) as (data_from, data_to):
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
	bg_parent = ensure_parent_in_scene("bg")
	for category_name, file_paths in collections_dict.items():
		# Create or get top-level category collection
		if category_name in bpy.data.collections:
			category_collection = bpy.data.collections[category_name]
		else:
			category_collection = bpy.data.collections.new(category_name)
			bpy.context.scene.collection.children.link(category_collection)

		# Link collections from each .blend file
		for asset_path_str in file_paths:
			asset_path = Path(asset_path_str)

			# Collection name = stem of file (filename without extension)
			collection_name = asset_path.stem  # e.g., "c-bahlil"
			if category_name == "set":
				collection_name = f"{collection_name}_hi"
			# Load collection from the blend file
			with bpy.data.libraries.load(str(asset_path), link=True) as (data_from, data_to):
				if collection_name in data_from.collections:
					data_to.collections = [collection_name]  # Only load this collection
				else:
					print(f"Collection '{collection_name}' not found in {asset_path}")
					continue
     
			# Link the loaded collection into the category collection
			for linked_collection in data_to.collections:
				if linked_collection and linked_collection.name not in category_collection.children:
					category_collection.children.link(linked_collection)
					armatures = [obj for obj in linked_collection.all_objects if obj.type == 'ARMATURE']

					if not armatures:
						print(f"[SKIP] '{linked_collection.name}' tidak punya Armature.")
						continue

					# Ensure the overridden collection remains in the category collection and remove it from the root
					if linked_collection.name in bpy.data.collections:
						overridden_collection = bpy.data.collections[linked_collection.name]
						if overridden_collection.name not in [child.name for child in category_collection.children]:
							category_collection.children.link(overridden_collection)
							print(f"Kept overridden collection '{overridden_collection.name}' in category '{category_collection.name}'")

						# Remove the overridden collection from the root collection
						if overridden_collection.name in [child.name for child in bpy.context.scene.collection.children]:
							bpy.context.scene.collection.children.unlink(overridden_collection)
							print(f"Removed overridden collection '{overridden_collection.name}' from root collection")

					bpy.context.view_layer.update()
				print(f"Linked collection '{linked_collection.name}' into '{category_name}'")

		if category_collection.name not in bg_parent.children:
			bg_parent.children.link(category_collection)
			bpy.context.scene.collection.children.unlink(category_collection)

link_set_collection(collections)

def update_camera():
	# Update camera settings
	scene = bpy.data.scenes['Scene']

	cam_obj = next((obj for obj in scene.objects if obj.type == 'CAMERA'), None)

	if cam_obj:
		scene.camera = cam_obj
	else:
		print("cam not found")

	active_camera = bpy.context.scene.camera
	if active_camera:
		active_camera.data.clip_end = 1000
		active_camera.data.dof.use_dof = True
		active_camera.data.dof.driver_remove("aperture_fstop")
		print(f"Camera '{active_camera.name}' settings updated: DOF disabled, clip_end set to 1000")
	else:
		print("No active camera found in the scene.")

def set_relative():
	# Make all file paths relative
	bpy.context.preferences.filepaths.use_relative_paths = True
	bpy.ops.file.make_paths_relative()
						 
# Execute functions
link_animation()
update_camera()
set_relative()
print("All operations completed successfully.")

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
            CAMERA_COLLECTION="cam",
            METHOD=False,
            LINK_WHOLE=False,
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
    # 1. Capture arguments from subprocess
    # We expect JSON strings for the dictionaries
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        mastershot_data = json.loads(sys.argv[4])
        addon_data = json.loads(sys.argv[5])
        file_paths = json.loads(sys.argv[-1])

        # 2. Run the logic
        builder = LightingBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            mastershots_data=mastershot_data,
            addons_data=addon_data,
            filepath=file_paths,
        )

        # 3. Print the result so the subprocess can "catch" it
        print(result)

    except Exception as e:
        print(f"Builder Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
