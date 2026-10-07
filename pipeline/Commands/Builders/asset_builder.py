"""Asset Department File Builder for ZeroXe Pipeline.

Constructs initial asset scene collections based on asset prefix/type rules
and saves both master and initial progress version files.
"""

import json
import logging
import os
from pathlib import Path
from string import Template
import sys
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class AssetBuilder:
    """Builder for Asset department files (Character, Props, Set, Vehicle, etc.)."""

    def extract_data(
        self,
        filepath: Union[Dict[str, str], str],
        asset_data: Optional[Dict[str, Any]] = None,
        current_department: Optional[Dict[str, Any]] = None,
        shot_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Create version directory and generate Blender setup script for an asset."""
        if isinstance(filepath, dict):
            final_path = filepath.get("final") or filepath.get("master") or ""
            version_path = filepath.get("version") or filepath.get("version_path") or ""
        else:
            final_path = str(filepath)
            version_path = kwargs.get("version_path") or kwargs.get("version") or ""

        # Auto-resolve missing paths if one is provided
        if not version_path and final_path:
            try:
                from versioning import VersioningSystem
                version_path = VersioningSystem.get_version_path(final_path, version=1)
            except Exception:
                try:
                    from Commands.versioning import VersioningSystem
                    version_path = VersioningSystem.get_version_path(final_path, version=1)
                except Exception:
                    try:
                        from pipeline.Commands.versioning import VersioningSystem
                        version_path = VersioningSystem.get_version_path(final_path, version=1)
                    except Exception:
                        pass

        if not final_path and version_path:
            try:
                from versioning import VersioningSystem
                final_path = VersioningSystem.get_master_path(version_path)
            except Exception:
                try:
                    from Commands.versioning import VersioningSystem
                    final_path = VersioningSystem.get_master_path(version_path)
                except Exception:
                    try:
                        from pipeline.Commands.versioning import VersioningSystem
                        final_path = VersioningSystem.get_master_path(version_path)
                    except Exception:
                        pass

        if version_path:
            try:
                Path(version_path).parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if final_path:
            try:
                Path(final_path).parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

        return self.script_builder(
            filepath=final_path,
            init_version_path=version_path,
            asset_data=asset_data or shot_data,
            current_department=current_department,
        )


    def script_builder(
        self,
        filepath: str,
        init_version_path: str,
        asset_data: Optional[Dict[str, Any]] = None,
        current_department: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate Blender python script for building initial asset scene collections."""
        norm_file_path = str(Path(filepath).as_posix()) if filepath else ""
        norm_version_path = str(Path(init_version_path).as_posix()) if init_version_path else norm_file_path

        tpl = Template(dedent("""
            import bpy
            import os

            bpy.ops.wm.read_factory_settings(use_empty=True)

            file_path = "$FILE_PATH"
            init_version_path = "$INIT_VERSION_PATH"

            b = os.path.splitext(os.path.basename(file_path))[0]
            is_s = b.startswith("s-")
            sub_b = b if is_s else (b[2:] if len(b) > 2 and b[1] == "-" else b)
            sfxs = ["_hi", "_lo"] if is_s else ["_grp_mdl", "_grp_rig"]

            r = bpy.data.collections.new(b)
            bpy.context.scene.collection.children.link(r)
            for s in sfxs:
                r.children.link(bpy.data.collections.new(f"{sub_b}{s}"))

            bpy.ops.wm.save_as_mainfile(filepath=file_path)
            if init_version_path and init_version_path != file_path:
                bpy.ops.wm.save_as_mainfile(filepath=init_version_path)
            bpy.ops.wm.quit_blender()
        """).strip())

        return tpl.substitute(
            FILE_PATH=norm_file_path,
            INIT_VERSION_PATH=norm_version_path,
        )


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1].startswith("{"):
            shot_info = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
            current_dept = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            asset_dept = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
            file_paths = json.loads(sys.argv[-1]) if len(sys.argv) > 4 else {}

            builder = AssetBuilder()
            result = builder.extract_data(filepath=file_paths, asset_data=shot_info, current_department=current_dept)
            print(result)
        elif len(sys.argv) > 1:
            file_path = sys.argv[1]
            ver_path = sys.argv[2] if len(sys.argv) > 2 else ""
            builder = AssetBuilder()
            result = builder.extract_data(filepath={"final": file_path, "version": ver_path})
            print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
