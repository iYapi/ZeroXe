import sys
import json
from pathlib import Path
from textwrap import dedent


class BlockingAnimationBuilder:
    """
    OPTION A: source = Blocking shot that this animation is based on.

    filepath['source'] is expected to already point at this shot's Blocking
    blend (e.g. .../03_blocking/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_blk.blend),
    which matches the department config: Animation.source == "Blocking".
    """

    # Fixed asset-library config for this project (base_path/prefix/collection code
    # per asset type). Kept as a constant here instead of a new CLI argument so the
    # script's input contract (shot_info, current_department, filepath) is unchanged.
    ASSET_TYPES = {
        "CHAR": {
            "field": "char",
            "code": "chr",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/01_char/",
        },
        "PROPS": {
            "field": "prop",
            "code": "prp",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/02_prop/",
        },
        "SET": {
            "field": "set",
            "code": "set",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/03_set/",
        },
        "VEHICLE": {
            "field": "vehicle",
            "code": "vhc",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/04_vehicle/",
        },
    }

    def _get_required_assets(self, shot_data):
        """
        Build a dict of assets that MUST be linked/overridden in the generated
        shot file, based on the shot's own data (char/prop/set/vehicle).
        """
        required = {}
        shot_fields = (shot_data or {}).get("data", {}) or {}

        for type_key, type_cfg in self.ASSET_TYPES.items():
            raw_value = shot_fields.get(type_cfg["field"])
            if not raw_value:
                continue

            base_path = type_cfg["base_path"]
            collection_code = type_cfg["code"]

            for name in [n.strip() for n in str(raw_value).split(",") if n.strip()]:
                blend_path = f"{base_path}{name}/mdt_{name}_{collection_code}.blend"
                required[name] = {"collection": collection_code, "filepath": blend_path}

        return required

    def _build_sync_script(self, required_assets):
        """
        Build the Blender-side python snippet that:
          1. Removes any linked/overridden asset that is no longer required.
          2. Links + library-overrides every required asset that isn't already
             present, placing it inside the collection matching its asset type
             (chr / prp / set / vhc).
        """
        required_json = json.dumps(required_assets)

        return dedent(f"""
            import bpy

            REQUIRED_ASSETS = {required_json}

            def _get_or_create_collection(name):
                col = bpy.data.collections.get(name)
                if col is None:
                    col = bpy.data.collections.new(name)
                    bpy.context.scene.collection.children.link(col)
                return col

            def _instanced_collection_name(obj):
                if obj.instance_type == 'COLLECTION' and obj.instance_collection:
                    return obj.instance_collection.name
                return None

            # --- 1. remove assets that are linked but no longer required ---
            for obj in list(bpy.data.objects):
                asset_name = _instanced_collection_name(obj)
                if asset_name and asset_name not in REQUIRED_ASSETS:
                    stale_collection = obj.instance_collection
                    stale_library = stale_collection.library if stale_collection else None
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if stale_collection and stale_collection.users == 0:
                        bpy.data.collections.remove(stale_collection)
                    if stale_library and stale_library.users_id == 0:
                        bpy.data.libraries.remove(stale_library)

            for col in list(bpy.data.collections):
                if col.override_library and col.name not in REQUIRED_ASSETS:
                    bpy.data.collections.remove(col)

            for lib in list(bpy.data.libraries):
                if lib.users_id == 0:
                    bpy.data.libraries.remove(lib)

            # --- 2. link + override any required asset that is still missing ---
            existing_names = set()
            for obj in bpy.data.objects:
                name = _instanced_collection_name(obj)
                if name:
                    existing_names.add(name)
            for col in bpy.data.collections:
                if col.override_library:
                    existing_names.add(col.name)

            for asset_name, info in REQUIRED_ASSETS.items():
                if asset_name in existing_names:
                    continue

                target_collection = _get_or_create_collection(info["collection"])

                with bpy.data.libraries.load(info["filepath"], link=True) as (data_from, data_to):
                    if asset_name in data_from.collections:
                        data_to.collections = [asset_name]
                    else:
                        data_to.collections = list(data_from.collections)

                for linked_collection in data_to.collections:
                    if linked_collection is None:
                        continue

                    instance_obj = bpy.data.objects.new(linked_collection.name, None)
                    instance_obj.instance_type = 'COLLECTION'
                    instance_obj.instance_collection = linked_collection
                    target_collection.objects.link(instance_obj)

                    linked_collection.override_hierarchy_create(
                        bpy.context.scene, bpy.context.view_layer
                    )
        """)

    def extract_data(self, shot_data, current_department, filepath):
        # Entry data
        # region Example Data
        # shot_data = {
        #     "name": "sh0020",
        #     "data": {
        #         "set": "s-sekolah",
        #         "char": "c-baha",
        #         "prop": "p-dagangan,p-leupeut_single",
        #     },
        # }
        # current_department = {
        #     "Animation": {
        #         "code": "anm",
        #         "source": "Blocking",
        #         "presets": {"playblast": {"path": "/mnt/I/.../mdt_preset_playblast.py"}},
        #     }
        # }
        # filepath = {
        #     "source": "/mnt/I/.../03_blocking/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_blk.blend",
        #     "version": "/mnt/I/.../04_animation/.../progress/mdt_ep998_sq01_sh0020_anm_v001.blend",
        #     "final": "/mnt/I/.../04_animation/.../mdt_ep998_sq01_sh0020_anm.blend",
        # }
        # endregion

        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)

        # Copy from source (Blocking blend for this same shot)
        start_script = (
            f"import bpy; import os; "
            f"bpy.ops.wm.open_mainfile(filepath='{filepath['source']}'); "
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}');"
        )
        end_script = (
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['final']}'); "
            f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}')"
        )

        # Sync linked assets (unlink/remove what's no longer needed, link+override what's missing)
        required_assets = self._get_required_assets(shot_data)
        sync_script = self._build_sync_script(required_assets)

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
        file_paths = json.loads(sys.argv[-1])

        builder = BlockingAnimationBuilder()
        result = builder.extract_data(shot_info, current_dept, file_paths)

        print(result)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
