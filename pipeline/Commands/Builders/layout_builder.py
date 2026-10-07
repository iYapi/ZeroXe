import configparser
import sys
import json
from pathlib import Path
from textwrap import dedent
from string import Template


class LayoutBuilder:
    def extract_data(self, asset_department, current_department, shot_data, filepath):
        # Create parent folder
        Path(filepath["version"]).parent.mkdir(parents=True, exist_ok=True)

        # Get all asset list by asset type
        relative_assets = {}
        asset_types = asset_department["Asset"]["asset_type"]
        shot_assets_content = shot_data.get("assets", [])
        # Build lookup mapping for O(1) access
        asset_type_map = {
            config["id"]: (category_key, config)
            for category_key, config in asset_types.items()
        }

        for category_key, config in asset_type_map.values():
            if not category_key.startswith("MS_"):
                relative_assets[category_key] = {
                    "assets": [],
                    "base_path": config.get("base_path"),
                    "prefix": config.get("prefix"),
                    "code": config.get("code"),
                }
        for asset in shot_assets_content:
            asset_type_id = asset.get("entity_type_id")
            if asset_type_id in asset_type_map:
                category_key, _ = asset_type_map[asset_type_id]
                if category_key in relative_assets:
                    relative_assets[category_key]["assets"].append(asset["name"])

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
        preset_name = "playblast"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")

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
            "script_path": preset_path,
        }

        layout_script = self.script_builder(
            filepath=filepath["final"],
            version_path=filepath["version"],
            collections=collections_dict,
            setting_data=setting_data,
        )
        return layout_script

    def script_builder(
        self, filepath: str, version_path: str, collections: dict, setting_data: dict
    ):
        tpl = Template(
            dedent(
                """
import bpy
import os
from pathlib import Path

collections = $COLLECTIONS

# Clear all existing collections and objects before linking new ones
def clear_all():
	# Remove all objects
	for obj in bpy.data.objects:
		bpy.data.objects.remove(obj, do_unlink=True)

	# Remove all collections
	for collection in bpy.data.collections:
		bpy.data.collections.remove(collection)

clear_all()

def select_only(obj):
	for o in bpy.context.view_layer.objects:
		o.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

def link_collection(collections_dict):
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
				collection_name = f"{collection_name}_lo"

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

					# Override the entire collection
					for arm in armatures:
						select_only(arm)  # Ensure the object is active and selected
						bpy.context.view_layer.update()  # Update the context

						try:
							bpy.ops.object.make_override_library(collection=linked_collection.session_uid)
						except Exception:
							bpy.ops.object.make_override_library()

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

link_collection(collections)

def add_camera_rig():
	# Create new collection named "cam"
	cam_collection = bpy.data.collections.new("cam")
	bpy.context.scene.collection.children.link(cam_collection)

	# Deselect all objects
	bpy.ops.object.select_all(action='DESELECT')

	# Build camera rig (Dolly type)for python_cmd in ("python", "python3"):
	bpy.ops.object.build_camera_rig(mode='DOLLY')
 
	# Function to get object + all children recursively
	def get_children_recursive(obj):
		objs = [obj]
		for child in obj.children:
			objs.extend(get_children_recursive(child))
		return objs

	# Collect all selected objects and their children
	objects_to_move = []
	for obj in bpy.context.selected_objects:
		objects_to_move.extend(get_children_recursive(obj))

	# Remove duplicates (in case of shared hierarchy)
	objects_to_move = list(set(objects_to_move))

	# Move to cam collection
	for obj in objects_to_move:
		for col in obj.users_collection:
			col.objects.unlink(obj)
		cam_collection.objects.link(obj)

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

bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")

		"""
            )
        )
        end_script = Template(
            dedent(
                """
bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$FINAL_PATH", copy=True)

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
        end_script = end_script.substitute(
            VERSION_PATH=version_path, FINAL_PATH=filepath
        )
        script_path = setting_data.get("script_path")
        if script_path:
            with open(script_path, "r") as f:
                preset_code = f.read()
                script = script + "\n\n" + preset_code + "\n\n"
        script = script + end_script
        return script


if __name__ == "__main__":
    # 1. Capture arguments from subprocess
    # We expect JSON strings for the dictionaries
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        # mastershot_dept = json.loads(sys.argv[4])
        file_paths = json.loads(sys.argv[-1])

        # 2. Run the logic
        builder = LayoutBuilder()
        result = builder.extract_data(asset_dept, current_dept, shot_info, file_paths)

        # 3. Print the result so the subprocess can "catch" it
        print(result)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
