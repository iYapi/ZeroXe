import bpy
import os

#=========================variables=========================
blend_path = bpy.data.filepath
scenes = bpy.data.scenes["Scene"]

path_preview = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Preview"]
# subpath_preview = path_preview.file_slots[0]
path_char = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Char"]
path_set = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Set"]
path_sky = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Sky"]
# subpath_sky = path_sky.file_slots[0]
path_matte = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Matte"]
# subpath_matte = path_matte.file_slots[0]

# -----------------------------
# Helpers
# -----------------------------
def find_layer_collection(lc, target_col):
    if lc.collection == target_col:
        return lc
    for child in lc.children:
        found = find_layer_collection(child, target_col)
        if found:
            return found
    return None

def find_layer_collection_path(lc, target_col, path=None):
    if path is None:
        path = []
    path.append(lc)

    if lc.collection == target_col:
        return path

    for child in lc.children:
        found = find_layer_collection_path(child, target_col, path.copy())
        if found is not None:
            return found

    return None

def get_view_layer(scene, name):
    vl = scene.view_layers.get(name)
    if vl is None:
        raise ValueError(f"View Layer '{name}' tidak ditemukan")
    return vl


def get_collection(name):
    col = bpy.data.collections.get(name)
    if col is not None:
        return col
    for suffix in ["_fg", "_bg"]:
        variant = bpy.data.collections.get(f"{name}{suffix}")
        if variant is not None:
            return variant
    return None

def traverse_layer_collections(root_lc):
    stack = [root_lc]
    while stack:
        lc = stack.pop()
        yield lc
        stack.extend(reversed(lc.children))

def reset_layer(root_lc, *, exclude=False, holdout=False, indirect=False):
    for lc in traverse_layer_collections(root_lc):
        lc.exclude = exclude
        lc.holdout = holdout
        lc.indirect_only = indirect

def set_flags_on_collection(view_layer, collection_name, *, exclude=None, holdout=None, indirect=None, recursive=True):
    # Find all matching target collections (handles 'chr' -> 'chr_fg', 'chr_bg')
    targets = []
    direct_col = bpy.data.collections.get(collection_name)
    if direct_col is not None:
        targets.append(direct_col)
    else:
        for suffix in ["_fg", "_bg"]:
            variant = bpy.data.collections.get(f"{collection_name}{suffix}")
            if variant is not None:
                targets.append(variant)

    if not targets:
        print(f"[PRESET] Notice: Collection '{collection_name}' not present in scene, skipping flag assignment.")
        return

    def apply_flags(layer_col):
        if exclude is not None:
            layer_col.exclude = exclude
        if holdout is not None:
            layer_col.holdout = holdout
        if indirect is not None:
            layer_col.indirect_only = indirect

    def recurse(layer_col):
        apply_flags(layer_col)
        for child in layer_col.children:
            recurse(child)

    for target_col in targets:
        lc = find_layer_collection(view_layer.layer_collection, target_col)
        if lc is not None:
            if recursive:
                recurse(lc)
            else:
                apply_flags(lc)
        else:
            print(f"[PRESET] Notice: Collection '{target_col.name}' not found in View Layer '{view_layer.name}'.")

# -----------------------------
# Main setup
# -----------------------------
def setup_view_layers():
    scene = bpy.context.scene

    vl_preview = scene.view_layers.get("PREVIEW")
    vl_char    = scene.view_layers.get("CHAR")
    vl_set     = scene.view_layers.get("SET")
    vl_sky     = scene.view_layers.get("SKY")
    vl_matte   = scene.view_layers.get("MATTE")

    # 1) PREVIEW: semua ON, tidak holdout, tidak indirect
    if vl_preview:
        reset_layer(vl_preview.layer_collection, exclude=False, holdout=False, indirect=False)

    # 2) CHAR: FG ON, BG & set di holdout
    if vl_char:
        reset_layer(vl_char.layer_collection, exclude=False, holdout=False, indirect=False)
        set_flags_on_collection(vl_char, "sky", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_char, "matte", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_char, "cam", holdout=False, indirect=False, exclude=False)
        
        # Foreground layers: rendered directly
        set_flags_on_collection(vl_char, "fg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "chr_fg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "prp_fg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "vhc_fg", holdout=False, indirect=False, exclude=False)
        
        # Background layers & set: holdout matte occluders
        set_flags_on_collection(vl_char, "bg", holdout=True, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "chr_bg", holdout=True, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "prp_bg", holdout=True, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "vhc_bg", holdout=True, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "set", holdout=True, indirect=False, exclude=False)

        # Legacy fallback
        set_flags_on_collection(vl_char, "chr", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "prp", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_char, "vhc", holdout=False, indirect=False, exclude=False)

    # 3) SET: FG di indirect, BG & set di render
    if vl_set:
        reset_layer(vl_set.layer_collection, exclude=False, holdout=False, indirect=False)
        set_flags_on_collection(vl_set, "sky", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "matte", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "cam", holdout=False, indirect=False, exclude=False)
        
        # Foreground layers: indirect bounce lighting only
        set_flags_on_collection(vl_set, "fg", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "chr_fg", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "prp_fg", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "vhc_fg", holdout=False, indirect=True, exclude=False)
        
        # Background layers & set: rendered
        set_flags_on_collection(vl_set, "bg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_set, "chr_bg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_set, "prp_bg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_set, "vhc_bg", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_set, "set", holdout=False, indirect=False, exclude=False)

        # Legacy fallback
        set_flags_on_collection(vl_set, "chr", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "prp", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "vhc", holdout=False, indirect=True, exclude=False)
        set_flags_on_collection(vl_set, "Fill_Light", indirect=True, holdout=False, exclude=True)

    # 4) SKY: semua OFF kecuali "cam" dan "sky"
    if vl_sky:
        reset_layer(vl_sky.layer_collection, exclude=True, holdout=False, indirect=False)
        set_flags_on_collection(vl_sky, "sky", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_sky, "cam", holdout=False, indirect=False, exclude=False)

    # 5) MATTE: semua OFF kecuali "cam" dan "matte"
    if vl_matte:
        reset_layer(vl_matte.layer_collection, exclude=True, holdout=False, indirect=False)
        set_flags_on_collection(vl_matte, "matte", holdout=False, indirect=False, exclude=False)
        set_flags_on_collection(vl_matte, "cam", holdout=False, indirect=False, exclude=False)

    print("View Layers configured: PREVIEW, CHAR, SET, SKY, MATTE")

def set_node_output_path():
    # Ambil nama file tanpa extension
    filename = os.path.splitext(os.path.basename(blend_path))[0]

    # Pisahkan berdasarkan underscore
    parts = filename.split("_")

    if len(parts) != 5:
        raise Exception("Format nama file tidak sesuai standar.")

    project, ep, sq, sh, stage = parts

    path_preview.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/preview/"
    path_preview.file_name = ""
    path_preview.file_output_items[0].name = f"{project}_{ep}_{sq}_{sh}_preview_####.png"

    path_char.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/char/"
    path_char.file_name = f"{project}_{ep}_{sq}_{sh}_char_####.exr"

    path_set.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/set/"
    path_set.file_name = f"{project}_{ep}_{sq}_{sh}_set_####.exr"

    path_sky.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/sky/"
    path_sky.file_name = ""
    path_sky.file_output_items[0].name = f"{project}_{ep}_{sq}_{sh}_sky_####.png"

    path_matte.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/matte/"
    path_matte.file_name = ""
    path_matte.file_output_items[0].name = f"{project}_{ep}_{sq}_{sh}_matte_####.png"

    #scenes.render.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/playblast/{stage}/{project}_{ep}_{sq}_{sh}_{stage}_{version}.mov"

# Jalankan
setup_view_layers()
set_node_output_path()

def setup_tp_light():
    try:
        settings = $SETTINGS

        # Init 3 point light
        character_collections = []
        for coll_key in ["chr_fg", "chr", "chr_bg"]:
            c_parent = bpy.data.collections.get(coll_key)
            if c_parent:
                character_collections.extend([
                    coll.name for coll in c_parent.children
                    if coll.name.lower().startswith("c-") and coll.name not in character_collections
                ])

        def set_active_layer_collection(view_layer, target_coll_name):
            def recurse(layer_coll):
                if layer_coll.collection.name == target_coll_name:
                    view_layer.active_layer_collection = layer_coll
                    return True
                for child in layer_coll.children:
                    if recurse(child):
                        return True
                return False

            recurse(view_layer.layer_collection)

        view_layer = bpy.context.view_layer

        for coll_name in character_collections:
            coll = bpy.data.collections.get(coll_name)
            if not coll:
                print(f"Skipping '{coll_name}': collection not found.")
                continue

            set_active_layer_collection(view_layer, coll_name)

            active = view_layer.active_layer_collection.collection
            if active.name != coll_name:
                print(f"Skipping '{coll_name}': could not set as active layer collection.")
                continue

            result = bpy.ops.bls.append_blend()
            print(f"'{coll_name}' → {result}")

        # Set preset
        bpy.ops.blp.import_lighting_preset(filepath=settings.get("ops_blp", ""))
        print(f"Lighting preset applied from: {settings.get('ops_blp', '')}")
    except Exception as e:
        print(f"Error accessing settings: {e}")
        return
try:
    cam = bpy.context.scene.camera
    cam.data.dof.use_dof = False
    cam.data.clip_end = 10000
except Exception as e:
        print(f"Error accessing settings: {e}")

# setup_tp_light()
