"""VFX / FX Department File Builder for ZeroXe Pipeline."""

import json
import logging
from pathlib import Path
from string import Template
import sys
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class VFXBuilder:
    """Builder for VFX / FX department shot files."""

    def extract_data(
        self,
        shot_data: Dict[str, Any],
        current_department: Dict[str, Any],
        asset_department: Dict[str, Any],
        mastershots_data: Optional[Dict[str, Any]] = None,
        addons_data: Optional[Dict[str, Any]] = None,
        filepath: Optional[Dict[str, str]] = None,
        project_path: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Create version folder and generate VFX Blender setup script."""
        file_paths = filepath or {}
        version_file = file_paths.get("version", "")
        if version_file:
            Path(version_file).parent.mkdir(parents=True, exist_ok=True)

        proj_root = (project_path or "").rstrip("/\\")

        # 1. Resolve animation source file
        animation_file = file_paths.get("source", "")

        # 2. Resolve preset
        dept_data = current_department
        if isinstance(current_department, dict) and len(current_department) == 1 and not ("code" in current_department):
            dept_data = next(iter(current_department.values()))

        preset_path = None
        if isinstance(dept_data, dict):
            presets = dept_data.get("presets", {})
            scripts = dept_data.get("scripts", {})
            raw_preset = (
                presets.get("preset", {}).get("path")
                if isinstance(presets.get("preset"), dict)
                else (presets.get("preset") or scripts.get("preset") or scripts.get("playblast"))
            )
            if raw_preset and isinstance(raw_preset, str):
                preset_path = raw_preset.replace("@project_path@", proj_root)

        shot_content = shot_data.get("data", {}) if isinstance(shot_data, dict) else {}
        frame_in = int(shot_content.get("frame_in") or shot_data.get("frame_in") or 1)
        frame_out = int(shot_content.get("frame_out") or shot_data.get("frame_out") or 100)
        fps = int(shot_content.get("fps") or shot_data.get("fps") or 24)
        res_str = str(shot_content.get("resolution") or shot_data.get("resolution") or "1920x1080")
        resolution = (
            [int(res.strip()) for res in res_str.split("x")] if "x" in res_str else [1920, 1080]
        )

        setting_data = {
            "frame_in": frame_in,
            "frame_out": frame_out,
            "fps": fps,
            "resolution": resolution,
            "script_path": preset_path,
        }

        return self.script_builder(
            filepath=file_paths.get("final", ""),
            version_path=file_paths.get("version", ""),
            animation_file=str(animation_file),
            collection_list=["chr", "prp", "cam"],
            setting_data=setting_data,
        )

    def script_builder(
        self,
        filepath: str,
        version_path: str,
        animation_file: str,
        collection_list: List[str],
        setting_data: Dict[str, Any],
    ) -> str:
        tpl = Template(
            dedent(
                """
import bpy
import os
from pathlib import Path

def ensure_parent_in_scene(name: str):
	parent = bpy.data.collections.get(name)
	if not parent:
		parent = bpy.data.collections.new(name)
		bpy.context.scene.collection.children.link(parent)
	elif parent.name not in bpy.context.scene.collection.children.keys():
		bpy.context.scene.collection.children.link(parent)
	return parent

def link_animation():
	anm_p = "$ANIMATION_FILE"
	if not os.path.isfile(anm_p):
		print(f"[SKIP] Animation source file not found: {anm_p}")
		return

	parent_coll = ensure_parent_in_scene("anm")
	for col_name in $COLLECTION_LIST:
		try:
			with bpy.data.libraries.load(anm_p, link=True) as (data_from, data_to):
				if col_name in data_from.collections:
					data_to.collections = [col_name]
				else:
					continue

			for linked in data_to.collections:
				if linked and linked.name not in parent_coll.children.keys():
					parent_coll.children.link(linked)
		except Exception as e:
			print(f"Error linking animation collection {col_name}: {e}")

def update_camera():
	scene = bpy.context.scene
	cam_obj = next((obj for obj in scene.objects if obj.type == 'CAMERA'), None)
	if cam_obj:
		scene.camera = cam_obj
		cam_obj.data.clip_end = 1000

def set_relative():
	try:
		bpy.context.preferences.filepaths.use_relative_paths = True
		bpy.ops.file.make_paths_relative()
	except Exception:
		pass

link_animation()
update_camera()
set_relative()

settings = $SETTINGS
bpy.context.scene.frame_end = settings["frame_out"]
bpy.context.scene.frame_start = settings["frame_in"]
bpy.context.scene.render.fps = settings["fps"]
if len(settings.get("resolution", [])) >= 2:
	bpy.context.scene.render.resolution_x = settings["resolution"][0]
	bpy.context.scene.render.resolution_y = settings["resolution"][1]

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
            ANIMATION_FILE=animation_file,
            COLLECTION_LIST=json.dumps(collection_list),
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
            SETTINGS=json.dumps(setting_data),
        )
        end_str = end_script.substitute(
            VERSION_PATH=version_path, FINAL_PATH=filepath
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    preset_code = f.read()
                    script = script + "\n\n" + preset_code + "\n\n"
            except Exception as e:
                logger.warning(f"Could not load preset {script_path}: {e}")

        script = script + "\n" + end_str
        return script


# Alias
FXBuilder = VFXBuilder


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        current_dept = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        asset_dept = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        mastershot_data = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        addon_data = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
        file_paths = json.loads(sys.argv[-1]) if len(sys.argv) > 6 else {}

        builder = VFXBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            mastershots_data=mastershot_data,
            addons_data=addon_data,
            filepath=file_paths,
        )
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
