import re
import sys
import json
from pathlib import Path
from textwrap import dedent


class BlockingAnimationBuilder:
    """
    OPTION B: source = the PREVIOUS shot's own Animation file in the same
    sequence, instead of this shot's Blocking file.

    Example: current shot "sh0020" -> source becomes shot "sh0010"'s final
    animation blend (same episode/sequence, same department/code).

    Useful when a shot should inherit continuity (character position, props
    in hand, camera framing, etc.) directly from the shot right before it,
    rather than starting fresh from Blocking.
    """

    # How much the numeric part of the shot name decreases to find the
    # "previous" shot. Matches this project's shot numbering convention
    # (sh0010, sh0020, sh0030, ...).
    SHOT_NUMBER_STEP = 10

    # Fixed asset-library config for this project (id/code/base_path per asset
    # type, taken from the project config's Asset.asset_type section). Kept as
    # a constant here instead of a new CLI argument so the script's input
    # contract (shot_info, current_department, filepath) is unchanged.
    #
    # "id" is the entity_type_id used on each entry inside shot_data['assets']
    # -- that's how we know which bucket (chr/prp/set/vhc) an asset belongs to.
    ASSET_TYPES = {
        "CHAR": {
            "id": "3810b978-8a0f-46d7-8ac9-51243507fc3a",
            "code": "chr",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/01_char/",
        },
        "PROPS": {
            "id": "4f34e37a-a6a3-4571-857f-212434f82e3a",
            "code": "prp",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/02_prop/",
        },
        "SET": {
            "id": "44b7cabe-af80-4784-bb32-5c3cf7b05f4a",
            "code": "set",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/03_set/",
        },
        "VEHICLE": {
            "id": "5a1b1c9f-12f2-493a-91af-dbc6fcfe9461",
            "code": "vhc",
            "base_path": "/mnt/I/20260222_melangkah_dari_timur/02_production/01_asset/04_vehicle/",
        },
        # MS_COMP / MS_LIT intentionally NOT included -- this builder doesn't
        # link mastershot comp/lit assets, per earlier instruction.
    }

    @staticmethod
    def _replace_shot_token(path_component, current_name, prev_name):
        """
        Replace `current_name` with `prev_name` only when it appears as an
        EXACT underscore-delimited token (e.g. the "sh0020" in
        "ep998_sq01_sh0020" or "mdt_ep998_sq01_sh0020_anm"). This guarantees
        the department code token ("anm", "blk", ...) is never touched, even
        if it happened to share characters with the shot name.

        Returns (new_component, was_replaced).
        """
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

    def _resolve_previous_shot_source(self, shot_data, filepath):
        """
        Derive the source blend path by swapping this shot's name TOKEN for
        the previous shot's name token, inside both the parent folder name
        and the filename of this shot's own (Animation) final-file path:

          .../04_animation/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_anm.blend
          ->
          .../04_animation/ep998/ep998_sq01/ep998_sq01_sh0010/mdt_ep998_sq01_sh0010_anm.blend

        Because filepath['final'] is always this shot's ANIMATION target
        (never Blocking), and only the exact "shNNNN" token is swapped, the
        resolved path always stays in the Animation department ("_anm.blend")
        -- it can never resolve to a "_blk.blend" file.

        Falls back to filepath['source'] (which your pipeline sets to the
        Blocking file) ONLY when there genuinely is no previous shot to
        source from:
          - the shot name has no trailing number, or
          - this is already the first shot in the sequence (prev <= 0), or
          - the shot-name token isn't found in the final path at all
            (unexpected naming -> fail safe rather than guess).

        A "# source-resolution: ..." comment is embedded in the returned
        script marker so it's obvious in the generated code which case fired
        -- no more silent fallbacks.
        """
        current_name = (shot_data or {}).get("name", "") or ""
        match = re.match(r"^(.*?)(\d+)$", current_name)
        if not match:
            return filepath.get("source", ""), "no-trailing-number-in-shot-name"

        prefix, digits = match.groups()
        width = len(digits)
        prev_number = int(digits) - self.SHOT_NUMBER_STEP
        if prev_number <= 0:
            # first shot in the sequence, no previous shot to source from
            return filepath.get("source", ""), "first-shot-in-sequence"

        prev_name = f"{prefix}{str(prev_number).zfill(width)}"

        final_path = Path(filepath.get("final", ""))
        new_folder, folder_replaced = self._replace_shot_token(final_path.parent.name, current_name, prev_name)
        new_stem, stem_replaced = self._replace_shot_token(final_path.stem, current_name, prev_name)

        if not (folder_replaced and stem_replaced):
            # shot-name token wasn't found where expected -> don't guess, fail safe
            return filepath.get("source", ""), "shot-token-not-found-in-final-path"

        resolved = final_path.parent.with_name(new_folder) / f"{new_stem}{final_path.suffix}"
        return str(resolved), "resolved-from-previous-shot"

    def _get_required_assets(self, shot_data):
        """
        Build a dict of assets that MUST be linked/overridden in the generated
        shot file, based on shot_data['assets'] -- the actual list of asset
        entities cast to this shot. Each entry looks like:

            {"name": "c-baha", "entity_type_id": "3810b978-...", ...}

        `entity_type_id` is matched against ASSET_TYPES[*]['id'] to know which
        bucket (chr/prp/set/vhc) the asset belongs to. Assets whose type isn't
        one of CHAR/PROPS/SET/VEHICLE (e.g. MS_COMP/MS_LIT mastershots) are
        skipped -- this builder doesn't link those.
        """
        required = {}
        assets = (shot_data or {}).get("assets", []) or []

        type_by_id = {type_cfg["id"]: type_cfg for type_cfg in self.ASSET_TYPES.values()}

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

    def _build_sync_script(self, required_assets):
        """
        Build the Blender-side python snippet that:
          1. Links + library-overrides every required asset that isn't already
             present, placing it inside the collection matching its asset type
             (chr / prp / set / vhc).
          2. Lists EVERY linked library (.blend file) currently in the shot
             file and removes/unlinks any that this shot's asset list no
             longer needs -- regardless of where the library lives, so
             nothing stale is left behind.

        Matching is done by the asset's SOURCE LIBRARY FILEPATH, not by
        collection/object name. Names can drift (Blender renames on conflict,
        e.g. "c-baha.001", or the asset was linked by a different tool that
        used its own naming), but the filepath the data was linked from is
        stable -- so this is the only reliable way to know whether an
        already-linked asset is still the one this shot actually needs.
        """
        required_json = json.dumps(required_assets)

        return dedent(f"""
            import bpy
            import os

            REQUIRED_ASSETS = {required_json}

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
        """)

    def extract_data(self, shot_data, current_department, filepath):
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
        source_path, source_reason = self._resolve_previous_shot_source(shot_data, filepath)

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

        # Sync linked assets     (unlink/remove what's no longer needed, link+override what's missing)
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