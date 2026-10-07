import bpy

# -----------------------------
# Konfigurasi grup collection
# -----------------------------
# Dipisah supaya parameter bake (khususnya clear_constraints) bisa berbeda
# antara CHR dan non-CHR (cam/prp/veh).
# collection cam adalah variable sementara sampai issue jari resolve, nanti bisa disatuin lagi ama non chr
COLLECTIONS_CHR = {"chr"}
COLLECTIONS_NON_CHR = {"prp", "veh"}
COLLECTIONS_CAM = {"cam"}
ALL_COLLECTIONS = COLLECTIONS_CHR | COLLECTIONS_NON_CHR | COLLECTIONS_CAM

# -----------------------------
# Helpers: LayerCollection lookup
# -----------------------------
def find_layer_collection(layer_collection, target_collection):
    if layer_collection.collection == target_collection:
        return layer_collection
    for child in layer_collection.children:
        found = find_layer_collection(child, target_collection)
        if found:
            return found
    return None

def get_layer_collections_for_names(view_layer, names):
    result = {}
    root = view_layer.layer_collection
    for name in names:
        col = bpy.data.collections.get(name)
        if not col:
            result[name] = (None, None)
            continue
        lc = find_layer_collection(root, col)
        result[name] = (col, lc)
    return result

COLLECTION_PREFIX = "c-"
TARGET_BONE_NAMES = {
    f"{base}{side}"
    for base in ("c_foot_ik", "c_arms_pole", "c_leg_pole", "c_hand_ik", "c_arm_fk", "c_stretch_arm", "c_stretch_leg", "c_head.x")
    for side in (".l", ".r")
}


def disable_control_constraints(prefix=COLLECTION_PREFIX, bone_names=TARGET_BONE_NAMES):
    target_collections = [
        c for c in bpy.data.collections
        if c.library is None and c.name.lower().startswith(prefix.lower())
    ]

    armatures = {}
    for col in target_collections:
        for obj in col.all_objects:  # termasuk object di nested child collection
            if obj.type == 'ARMATURE' and obj.library is None:
                armatures[obj.name] = obj

    disabled_count = 0
    for arm in armatures.values():
        if not arm.pose:
            continue
        for bone_name in bone_names:
            pbone = arm.pose.bones.get(bone_name)
            if not pbone:
                continue
            for con in pbone.constraints:
                con.enabled = False
                disabled_count += 1
                print(f"[OK] {arm.name} > {bone_name} > {con.name} ({con.type}) -> disabled")

    print(f"[SUMMARY] {len(armatures)} armature diproses, {disabled_count} constraint di-disable.")
    return disabled_count

# -----------------------------
# State snapshot / restore
# -----------------------------
def _snapshot_and_enable_subtree(layer_collection, payload):
    """
    Rekursif ke seluruh child LayerCollection (dan Collection datablock terkait)
    di bawah layer_collection.

    Ini fix untuk kasus: sebelumnya cuma collection paling atas ("chr", "cam",
    dst) yang di-force enable. Kalau ada sub-collection DI DALAM "chr" yang
    di-disable viewport secara individual (mis. collection karakter tertentu),
    armature di dalamnya tetap invisible walau collection "chr" sendiri sudah
    di-enable -> makanya nggak ikut ke-bake. Dengan rekursi ini, semua level
    di bawah "chr"/"cam"/"prp"/"veh" ikut di-enable sementara.
    """
    col = layer_collection.collection
    name = col.name

    if name not in payload["collection_states"]:
        payload["collection_states"][name] = {"col_hide_viewport": bool(col.hide_viewport)}
        col.hide_viewport = False

    if name not in payload["layer_states"]:
        payload["layer_states"][name] = {
            "exclude": bool(layer_collection.exclude),
            "layer_hide_viewport": bool(layer_collection.hide_viewport),
        }
        layer_collection.exclude = False
        layer_collection.hide_viewport = False

    for child in layer_collection.children:
        _snapshot_and_enable_subtree(child, payload)

def snapshot_and_enable(view_layer, collection_names):
    payload = {
        "layer_states": {},       # col_name -> dict(exclude=..., layer_hide_viewport=...)
        "collection_states": {},  # col_name -> dict(col_hide_viewport=...)
        "object_states": {},      # obj_name -> dict(hide_viewport=..., hide_get=...)
    }

    mapping = get_layer_collections_for_names(view_layer, collection_names)

    for name, (col, lc) in mapping.items():
        if col is None:
            print(f"[WARN] Collection not found: '{name}'")
            continue

        if lc is None:
            # Collection ada tapi tidak masuk View Layer aktif sama sekali.
            # Tetap catat & enable state datablock-nya, tapi tidak bisa rekursi
            # lewat LayerCollection karena memang tidak ada di view layer ini.
            if col.name not in payload["collection_states"]:
                payload["collection_states"][col.name] = {"col_hide_viewport": bool(col.hide_viewport)}
                col.hide_viewport = False
            print(f"[WARN] Collection '{name}' tidak ada di View Layer aktif.")
            continue

        # --- Rekursif enable seluruh subtree (top collection + semua nested child) ---
        _snapshot_and_enable_subtree(lc, payload)

    # Object-level hide (extra safety). col.all_objects sudah rekursif ke
    # nested collection, jadi ini tetap menjangkau semua armature di dalamnya.
    for name, (col, _lc) in mapping.items():
        if col is None:
            continue
        for obj in list(col.all_objects):
            if obj is None:
                print(f"[WARN] Found None object reference in collection '{name}', skipping.")
                continue
            obj_name = getattr(obj, "name", None)
            if not obj_name:
                print(f"[WARN] Found invalid object in collection '{name}', skipping.")
                continue

            if obj_name not in payload["object_states"]:
                payload["object_states"][obj_name] = {
                    "hide_viewport": bool(obj.hide_viewport),
                    "hide_get": bool(obj.hide_get()),
                }

            obj.hide_viewport = False
            obj.hide_set(False)

    view_layer.update()
    return payload

def restore_states(view_layer, payload):
    # Restore Collection datablock states
    for name, state in payload.get("collection_states", {}).items():
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        col.hide_viewport = state["col_hide_viewport"]

    # Restore LayerCollection states (termasuk semua nested child yang ikut
    # di-snapshot oleh _snapshot_and_enable_subtree)
    layer_states = payload.get("layer_states", {})
    mapping = get_layer_collections_for_names(view_layer, layer_states.keys())
    for name, state in layer_states.items():
        _col, lc = mapping.get(name, (None, None))
        if lc is None:
            continue
        lc.exclude = state["exclude"]
        lc.hide_viewport = state["layer_hide_viewport"]

    # Restore object states
    for obj_name, state in payload.get("object_states", {}).items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        obj.hide_viewport = state["hide_viewport"]
        obj.hide_set(state["hide_get"])

    view_layer.update()

# -----------------------------
# Baking logic
# -----------------------------
def get_armatures_from_collections(collection_names):
    armatures = []
    seen = set()
    for name in collection_names:
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in col.all_objects:
            if obj is None:
                continue
            if obj.type == 'ARMATURE' and obj.name not in seen:
                armatures.append(obj)
                seen.add(obj.name)
    return armatures

def bake_armature_pose(scene, obj, clear_constraints):
    view_layer = bpy.context.view_layer

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')

    if obj.name not in view_layer.objects:
        print(f"[SKIP] '{obj.name}' not in active View Layer objects (still excluded somewhere).")
        return

    obj.select_set(True)
    view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='POSE')
    for o in bpy.data.objects:
        if o.type == 'ARMATURE' and o.pose:
            is_target = (o == obj)
            for b in o.pose.bones:
            # .bone. nanti di hapus untuk blender 5.2 / tambah bone. setelah b. untuk blender 4.5
                b.select = is_target

    ctx = bpy.context
    override_kwargs = dict(
        active_object=obj,
        object=obj,
        selected_objects=[obj],
        selected_editable_objects=[obj],
    )

    with ctx.temp_override(**override_kwargs):
        bpy.ops.nla.bake(
            frame_start=scene.frame_start,
            frame_end=scene.frame_end,
            step=1,
            only_selected=True,
            visual_keying=True,
            clear_constraints=clear_constraints,
            clear_parents=True,
            use_current_action=True,
            bake_types={'POSE'},
        )

    bpy.ops.object.mode_set(mode='OBJECT')


def bake_collection_group(scene, collection_names, clear_constraints, label=""):
    """
    Bake semua armature dari sekumpulan collection dengan satu nilai
    clear_constraints yang seragam untuk grup itu.
    """
    label = label or ", ".join(sorted(collection_names))
    armatures = get_armatures_from_collections(collection_names)

    if not armatures:
        print(f"[INFO] Tidak ada armature ditemukan di collection: {label}")
        return 0

    print(f"[INFO] Baking {len(armatures)} armature ({label}), clear_constraints={clear_constraints}")
    for obj in armatures:
        print(f"[INFO] Baking: {obj.name}")
        bake_armature_pose(scene, obj, clear_constraints=clear_constraints)

    return len(armatures)

#
# def bake_chr(scene):
#     # CHR -> clear_constraints=False, constraint dipertahankan setelah bake
#     return bake_collection_group(scene, COLLECTIONS_CHR, clear_constraints=False, label="CHR")
#
# def bake_non_chr(scene):
#     # Non-CHR (cam/prp/veh) -> clear_constraints=True, constraint dihapus setelah bake
#     return bake_collection_group(scene, COLLECTIONS_NON_CHR, clear_constraints=True, label="NON-CHR")

# fungsi bake cam ini solusi sementara nanti usahain satuin ama non chr
def bake_cam(scene):
    # Non-CHR (cam/prp/veh) -> clear_constraints=True, constraint dihapus setelah bake
    return bake_collection_group(scene, COLLECTIONS_CAM, clear_constraints=True, label="CAM")

def main():
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    restore_payload = snapshot_and_enable(view_layer, ALL_COLLECTIONS)

    try:
        print(f"[INFO] Frame range: {scene.frame_start} - {scene.frame_end}, step=1")

        # fungsi bake char ama prop sementara di disable karena issue bake pada tangan banyak yang offset kecil kecil
        total_baked = 0
        # total_baked += bake_non_chr(scene)
        # total_baked += bake_chr(scene)
        total_baked += bake_cam(scene)

        if total_baked == 0:
            print("[INFO] No armatures found in any collection:", ", ".join(sorted(ALL_COLLECTIONS)))
        else:
            print("[DONE] Bake complete.")

    finally:
        restore_states(view_layer, restore_payload)
        print("[INFO] Restored collection/object visibility states.")

    # disable_control_constraints()


main()
