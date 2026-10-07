"""Animatic / 2D Department File Builder for ZeroXe Pipeline."""

import json
from pathlib import Path
from string import Template
import sys
from textwrap import dedent
from typing import Any, Dict, Optional


class AnimaticBuilder:
    """Builder for 2D / Animatic department files."""

    def extract_data(
        self,
        filepath: Dict[str, str],
        shot_data: Optional[Dict[str, Any]] = None,
        current_department: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Create version folder and generate Blender setup script."""
        version_path = filepath.get("version", "")
        final_path = filepath.get("final", "")

        if version_path:
            Path(version_path).parent.mkdir(parents=True, exist_ok=True)

        return self.script_builder(
            filepath=final_path,
            version_path=version_path,
            shot_data=shot_data,
            current_department=current_department,
        )

    def script_builder(
        self,
        filepath: str,
        version_path: str,
        shot_data: Optional[Dict[str, Any]] = None,
        current_department: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate Blender python script."""
        shot_info = shot_data or {}
        shot_content = shot_info.get("data", {}) if isinstance(shot_info.get("data"), dict) else {}

        frame_in = int(shot_content.get("frame_in") or shot_info.get("frame_in") or 1)
        frame_out = int(shot_content.get("frame_out") or shot_info.get("frame_out") or 100)
        fps = int(shot_content.get("fps") or shot_info.get("fps") or 24)
        res_str = str(shot_content.get("resolution") or shot_info.get("resolution") or "1920x1080")
        resolution = (
            [int(res.strip()) for res in res_str.split("x")] if "x" in res_str else [1920, 1080]
        )

        tpl = Template(dedent("""
            import bpy

            # Clear existing objects if any
            for obj in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            for col in bpy.data.collections:
                bpy.data.collections.remove(col)

            # Scene settings
            bpy.context.scene.frame_start = $FRAME_IN
            bpy.context.scene.frame_end = $FRAME_OUT
            bpy.context.scene.render.fps = $FPS
            bpy.context.scene.render.resolution_x = $RES_X
            bpy.context.scene.render.resolution_y = $RES_Y

            bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
            bpy.ops.wm.save_as_mainfile(filepath="$FINAL_PATH", copy=True)
            bpy.ops.wm.quit_blender()
        """).strip())

        return tpl.substitute(
            FRAME_IN=frame_in,
            FRAME_OUT=frame_out,
            FPS=fps,
            RES_X=resolution[0],
            RES_Y=resolution[1] if len(resolution) > 1 else 1080,
            VERSION_PATH=version_path,
            FINAL_PATH=filepath,
        )


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        current_dept = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        asset_dept = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        file_paths = json.loads(sys.argv[-1]) if len(sys.argv) > 4 else {}

        builder = AnimaticBuilder()
        result = builder.extract_data(filepath=file_paths, shot_data=shot_info, current_department=current_dept)
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
