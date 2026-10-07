import bpy
import os

#=========================variables=========================

blend_path = bpy.data.filepath
scenes = bpy.data.scenes["Scene"]

#====================Name split=============================

# Ambil nama file tanpa extension
filename = os.path.splitext(os.path.basename(blend_path))[0]

# Pisahkan berdasarkan underscore
parts = filename.split("_")

if len(parts) != 6:
    raise Exception("Format nama file tidak sesuai standar.")

project, ep, sq, sh, stage, version = parts

# Template path
#output_path = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/playblast/{stage}/{project}_{ep}_{sq}_{sh}_{stage}_{version}.mov"
#stamp_text = f"{project}_{ep}_{sq}_{sh}_{stage}_{version}"

# Set ke render filepath
#scenes.render.filepath = output_path
#scenes.render.stamp_note_text = stamp_text

print("Render path berhasil di-set:")


#===================Format playblast===================

scenes.render.resolution_x = 2560
scenes.render.resolution_y = 1080
scenes.render.resolution_percentage = 85
scenes.render.use_border = False
scenes.render.fps = 24
#ganti meida type ke "FFMPEG" untuk blender di bawah 5, "VIDEO" untuk blender 5 ke atas
scenes.render.image_settings.media_type = "VIDEO"
scenes.render.ffmpeg.format = "QUICKTIME"
scenes.render.ffmpeg.codec = "PRORES"
scenes.render.ffmpeg.audio_codec = "AAC"
scenes.render.filepath = f"/mnt/K/20260222_melangkah_dari_timur/{ep}/{ep}_{sq}/{ep}_{sq}_{sh}/playblast/{stage}/{project}_{ep}_{sq}_{sh}_{stage}_{version}.mov"

#======================Metadata======================

scenes.render.use_stamp_date = True
scenes.render.use_stamp_time = False
scenes.render.use_stamp_render_time = False
scenes.render.use_stamp_frame = True
scenes.render.use_stamp_camera = False
scenes.render.use_stamp_lens = True
scenes.render.use_stamp_scene = False
scenes.render.use_stamp_filename = False
#Note
scenes.render.use_stamp_note = True
scenes.render.stamp_note_text = f"{project}_{ep}_{sq}_{sh}_{stage}_{version}"
#Burn Into Image
scenes.render.use_stamp = True
scenes.render.stamp_font_size = 13
scenes.render.stamp_foreground = (0.799238, 0.715663, 0, 1)
scenes.render.stamp_background = (0, 0, 0, 0.15)
