import bpy
import os

#=========================variables=========================

blend_path = bpy.data.filepath
output_comp_node = bpy.data.node_groups["Compositing Node Tree"].nodes["File Output Comp"]
input_char = bpy.data.images["Char Image Sequence"]
input_set = bpy.data.images["Set Image Sequence"]
input_sky = bpy.data.images["Sky Image Sequence"]
input_matte = bpy.data.images["Matte Image Sequence"]
# input_gobos = bpy.data.images["Gobos Image Sequence"]
node_char = bpy.data.node_groups["Char Image Sequence"].nodes["Char Image Sequence"]
node_set = bpy.data.node_groups["Set Image Sequence"].nodes["Set Image Sequence"]
node_sky = bpy.data.node_groups["Sky Image Sequence"].nodes["Sky Image Sequence"]
node_matte = bpy.data.node_groups["Matte Image Sequence"].nodes["Matte Image Sequence"]
# node_gobos = bpy.data.node_groups["Compositing Node Tree"].nodes["Gobos Image Sequence"]
scenes = bpy.data.scenes["Scene"]

setting_data = $SETTINGS
if setting_data:
    total_frame = setting_data["frame_out"] - setting_data["frame_in"] + 1
# -----------------------------
# Main setup
# -----------------------------

def set_node_output_path():
    # Ambil nama file tanpa extension
    filename = os.path.splitext(os.path.basename(blend_path))[0]

    # Pisahkan berdasarkan underscore
    parts = filename.split("_")

    if len(parts) == 5:
        project, ep, sq, sh, stage = parts
        version = "v001"

    elif len(parts) == 6:
        project, ep, sq, sh, stage, version = parts

    else:
        raise Exception("Format nama file tidak sesuai standar.")

    output_comp_node.directory = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/{stage}/"
    output_comp_node.file_name = "" # ini untuk socket kedua, default di set ke null saja
    output_comp_node.file_output_items[0].name = f"{project}_{ep}_{sq}_{sh}_{stage}_####.png"

    input_char.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/char/{project}_{ep}_{sq}_{sh}_char_0101.exr"
    input_set.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/set/{project}_{ep}_{sq}_{sh}_set_0101.exr"
    input_sky.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/sky/{project}_{ep}_{sq}_{sh}_sky_0101.png"
    input_matte.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/matte/{project}_{ep}_{sq}_{sh}_matte_0101.png"
    # input_gobos.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/render/gobos/{project}_{ep}_{sq}_{sh}_gobos_0101.png"
    #scenes.render.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/playblast/{stage}/{project}_{ep}_{sq}_{sh}_{stage}_{version}.mov"


def set_char_node():
    #setting node untuk sky image sequence
    input_char.source = "SEQUENCE"
    node_char.frame_duration = total_frame      #Total frame sesuai dari kitsu
    node_char.frame_start = 101                  #Frame start static 101
    node_char.frame_offset = 100
    node_char.use_cyclic = False
    node_char.use_auto_refresh = True

def set_set_node():
    #setting node untuk sky image sequence
    input_set.source = "SEQUENCE"
    node_set.frame_duration = total_frame      #Total frame sesuai dari kitsu
    node_set.frame_start = 101                  #Frame start static 101
    node_set.frame_offset = 100
    node_set.use_cyclic = False
    node_set.use_auto_refresh = True

def set_sky_node():
    #setting node untuk sky image sequence
    input_sky.source = "SEQUENCE"
    node_sky.frame_duration = total_frame      #Total frame sesuai dari kitsu
    node_sky.frame_start = 101                  #Frame start static 101
    node_sky.frame_offset = 100
    node_sky.use_cyclic = False
    node_sky.use_auto_refresh = True

def set_matte_node():
    #setting node untuk sky image sequence
    input_matte.source = "SEQUENCE"
    node_matte.frame_duration = total_frame      #Total frame sesuai dari kitsu
    node_matte.frame_start = 101                  #Frame start static 101
    node_matte.frame_offset = 100
    node_matte.use_cyclic = False
    node_matte.use_auto_refresh = True

# def set_gobos_node():
#     #setting node untuk sky image sequence
#     input_gobos.source = "SEQUENCE"
#     node_gobos.frame_duration = total_frame      #Total frame sesuai dari kitsu
#     node_gobos.frame_start = 101                  #Frame start static 101
#     node_gobos.frame_offset = 100
#     node_gobos.use_cyclic = False
#     node_gobos.use_auto_refresh = True

scenes.frame_start = 101
scenes.frame_end = 100 + total_frame

# Jalankan
set_node_output_path()
set_char_node()
set_set_node()
set_sky_node()
set_matte_node()
# set_gobos_node()
bpy.ops.file.make_paths_relative()
