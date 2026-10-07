import bpy

bpy.ops.file.pack_all()
bpy.ops.file.unpack_all(method='USE_LOCAL')
bpy.data.scenes["Scene"].render.use_texture_cache = True
bpy.ops.render.generate_texture_cache(generate_sequences=True)
