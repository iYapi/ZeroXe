import re
import sys
import json
from pathlib import Path
from textwrap import dedent


class BlockingAnimationBuilder:
    SHOT_NUMBER_STEP = 10

    @staticmethod
    def _replace_shot_token(path_component, current_name, prev_name):
        parts = path_component.split("_")
        replaced = False
        new_parts = []
        for part in parts:
            if part == current_name:
                new_parts.append(prev_name)
                replaced = True
            else:
                new_parts.append(part)
        return "_".join(new_parts), replaced

    def _resolve_scan_source(self, filepath, direction="previous"):
        final_path = Path(filepath["final"])

        current_folder = final_path.parent
        parent_folder = current_folder.parent

        folders = sorted(
            p for p in parent_folder.iterdir()
            if p.is_dir()
        )

        try:
            index = folders.index(current_folder)
        except ValueError:
            return filepath.get("source", ""), "current-folder-not-found"

        if direction == "previous":
            if index == 0:
                return filepath.get("source", ""), "no-previous-folder"
            target_folder = folders[index - 1]

        elif direction == "next":
            if index >= len(folders) - 1:
                return filepath.get("source", ""), "no-next-folder"
            target_folder = folders[index + 1]

        else:
            return filepath.get("source", ""), "invalid-direction"

        # Replace the current shot folder name inside the blend filename
        blend_name = final_path.name.replace(current_folder.name, target_folder.name)

        blend_file = target_folder / blend_name

        return str(blend_file), "resolved-by-scan"

    def _get_required_assets(self, shot_data, asset_types):
        required = {}
        assets = (shot_data or {}).get("assets", []) or []

        type_by_id = {type_cfg["id"]: type_cfg for type_cfg in asset_types.values()}

        for asset in assets:
            type_cfg = type_by_id.get(asset.get("entity_type_id"))
            if not type_cfg:
                continue  # not CHAR/PROPS/SET/VEHICLE, e.g. a mastershot comp/lit asset

            name = asset.get("name")
            if not name:
                continue

            base_path = type_cfg["base_path"]
            collection_code = type_cfg["code"]
            blend_path = f"{base_path}{name}/{name}.blend"
            required[name] = {"collection": collection_code, "filepath": blend_path}

        return required

    def _build_sync_script(self, required_assets, setting_data):
        required_json = json.dumps(required_assets)

        return dedent(f"""
            import bpy
            import os

            REQUIRED_ASSETS = {required_json}

            if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            def _norm(path):
                if not path:
                    return path
                return os.path.normcase(os.path.normpath(bpy.path.abspath(path)))

            REQUIRED_PATHS = {{_norm(info["filepath"]) for info in REQUIRED_ASSETS.values()}}

            def _get_or_create_collection(name):
                col = bpy.data.collections.get(name)
                if col is None:
                    col = bpy.data.collections.new(name)
                    bpy.context.scene.collection.children.link(col)
                return col

            def _select_only(obj):
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj

            # --- 1. link + override any required asset not already present ---
            existing_paths = {{_norm(lib.filepath) for lib in bpy.data.libraries}}

            for asset_name, info in REQUIRED_ASSETS.items():
                if _norm(info["filepath"]) in existing_paths:
                    continue  # already linked/overridden from this exact file, leave it

                category_collection = _get_or_create_collection(info["collection"])

                with bpy.data.libraries.load(info["filepath"], link=True) as (data_from, data_to):
                    if asset_name in data_from.collections:
                        data_to.collections = [asset_name]
                    else:
                        data_to.collections = list(data_from.collections)

                # Link the loaded collection into the category collection
                for linked_collection in data_to.collections:
                    if not linked_collection:
                        continue

                    if linked_collection.name not in category_collection.children:
                        category_collection.children.link(linked_collection)

                    armatures = [obj for obj in linked_collection.all_objects if obj.type == 'ARMATURE']
                    if not armatures:
                        print(f"[SKIP] '{{linked_collection.name}}' tidak punya Armature.")
                        continue

                    # Override the entire collection
                    for arm in armatures:
                        _select_only(arm)  # Ensure the object is active and selected
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
                            print(f"Kept overridden collection '{{overridden_collection.name}}' in category '{{category_collection.name}}'")
                        # Remove the overridden collection from the root collection
                        if overridden_collection.name in [child.name for child in bpy.context.scene.collection.children]:
                            bpy.context.scene.collection.children.unlink(overridden_collection)
                            print(f"Removed overridden collection '{{overridden_collection.name}}' from root collection")

                    bpy.context.view_layer.update()
                    print(f"Linked collection '{{linked_collection.name}}' into '{{category_collection.name}}'")

            # --- 2. list EVERY linked library in the file, unlink whatever
            #        this shot's asset list no longer needs ---
            for lib in list(bpy.data.libraries):
                norm_fp = _norm(lib.filepath)
                if norm_fp in REQUIRED_PATHS:
                    continue  # still needed for this shot, keep

                # remove local override wrappers first -- do_unlink on the
                # library only clears references FROM these, it won't delete
                # the (local) override collection/object itself
                for obj in [o for o in bpy.data.objects
                            if o.library == lib
                            or (o.instance_collection and o.instance_collection.library == lib)]:
                    bpy.data.objects.remove(obj, do_unlink=True)

                for col in [c for c in bpy.data.collections
                            if c.library == lib
                            or (c.override_library and c.override_library.reference
                                and c.override_library.reference.library == lib)]:
                    bpy.data.collections.remove(col)

                # do_unlink=True unlinks EVERY remaining datablock sourced
                # from this library (meshes, armatures, materials, actions,
                # ...), not just top-level objects/collections, then removes
                # the library itself.
                bpy.data.libraries.remove(lib, do_unlink=True)

            # final sweep: purge any orphan data left behind by the unlinks
            # above, and drop any library that still ended up with 0 users
            bpy.data.orphans_purge(do_local_ids=False, do_linked_ids=True, do_recursive=True)
            for lib in list(bpy.data.libraries):
                if lib.users_id == 0:
                    bpy.data.libraries.remove(lib)
                    
            settings = {setting_data}
            bpy.context.scene.frame_end = settings["frame_out"]
            bpy.context.scene.frame_start = settings["frame_in"]
            bpy.context.scene.render.fps = settings["fps"]
            bpy.context.scene.render.resolution_x = settings["resolution"][0]
            bpy.context.scene.render.resolution_y = settings["resolution"][1]
            
            bpy.context.scene.render.use_simplify = True
            bpy.context.scene.render.simplify_subdivision = 1
            
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
        """)

    def extract_data(self, asset_department, shot_data, current_department, filepath, builder_type):
        # Entry data
        # region Example Data
        # shot_data = {
        #     "name": "sh0020",
        #     "assets": [
        #         {"name": "c-baha", "entity_type_id": "3810b978-8a0f-46d7-8ac9-51243507fc3a"},   # CHAR
        #         {"name": "p-dagangan", "entity_type_id": "4f34e37a-a6a3-4571-857f-212434f82e3a"}, # PROPS
        #         {"name": "s-sekolah", "entity_type_id": "44b7cabe-af80-4784-bb32-5c3cf7b05f4a"},  # SET
        #         # entries with other entity_type_id (e.g. MS_COMP/MS_LIT) are ignored
        #     ],
        # }
        # current_department = {
        #     "Animation": {
        #         "code": "anm",
        #         "presets": {"playblast": {"path": "/mnt/I/.../mdt_preset_playblast.py"}},
        #     }
        # }
        # filepath = {
        #     "source": "<fallback only, used if previous shot can't be resolved>",
        #     "version": "/mnt/I/.../04_animation/ep998/ep998_sq01/ep998_sq01_sh0020/progress/mdt_ep998_sq01_sh0020_anm_v001.blend",
        #     "final": "/mnt/I/.../04_animation/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_anm.blend",
        # }
        # -> resolved source becomes:
        #    /mnt/I/.../04_animation/ep998/ep998_sq01/ep998_sq01_sh0010/mdt_ep998_sq01_sh0010_anm.blend
        # endregion

        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)

        # Resolve the actual source: previous shot's animation file (falls back
        # to filepath['source'] only when there's genuinely no previous shot)
        source_path, source_reason = self._resolve_scan_source(filepath, builder_type)

        start_script = (
            f"# source-resolution: {source_reason}\n"
            f"import bpy; import os; "
            f"bpy.ops.wm.open_mainfile(filepath='{source_path}'); "
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}');"
        )
        end_script = (
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['final']}'); "
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}')"
        )

        # Get preset
        dept_data = next(iter(current_department.values()))
        preset_name = "playblast"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")

        # Construct shot metadata
        frame_in = int(shot_data.get("data", {}).get("frame_in", "0"))
        frame_out = int(shot_data.get("data", {}).get("frame_out", "0"))
        fps = int(shot_data.get("data", {}).get("fps", "24"))
        res_str = str(shot_data.get("data", {}).get("resolution", "1920x1080"))
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

        # Sync linked assets (unlink/remove what's no longer needed, link+override what's missing)
        asset_types = asset_department["Asset"]["asset_type"]
        required_assets = self._get_required_assets(shot_data, asset_types)
        sync_script = self._build_sync_script(required_assets, setting_data)

        # Apply preset
        dept_data = next(iter(current_department.values()))
        preset_name = "playblast"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")
        if preset_path:
            with open(preset_path, "r") as f:
                preset_code = f.read()
        else:
            preset_code = ""

        create_script = "\n\n".join(
            part for part in [start_script, sync_script, preset_code, end_script] if part
        )

        return create_script


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        builder_mode = str(sys.argv[-2])
        file_paths = json.loads(sys.argv[-1])

        builder = BlockingAnimationBuilder()
        result = builder.extract_data(asset_dept, shot_info, current_dept, file_paths, builder_mode)

        print(result)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
