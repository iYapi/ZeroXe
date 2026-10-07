"""Editing Department File Builder for ZeroXe Pipeline."""

import json
import logging
from pathlib import Path
import shutil
from string import Template
import sys
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class EditingBuilder:
    """Builder for Editing department files."""

    def extract_data(
        self,
        filepath: Dict[str, str],
        shot_data: Optional[Dict[str, Any]] = None,
        current_department: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Ensure folder structure for editing project."""
        final_p = filepath.get("final") or filepath.get("version") or ""
        if final_p:
            full_path = Path(final_p)
            try:
                episode_path = full_path.parents[2]
                (episode_path / "progress").mkdir(parents=True, exist_ok=True)
                sequence_path = full_path.parents[1]
                if sequence_path.exists() and sequence_path.is_dir():
                    try:
                        shutil.rmtree(sequence_path)
                    except Exception:
                        pass
            except Exception:
                pass

            if filepath.get("version"):
                Path(filepath["version"]).parent.mkdir(parents=True, exist_ok=True)

        return self.script_builder(
            filepath=filepath.get("final", ""),
            version_path=filepath.get("version", ""),
        )

    def script_builder(self, filepath: str, version_path: str) -> str:
        tpl = Template(
            dedent(
                """
import bpy

bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$FINAL_PATH", copy=True)
bpy.ops.wm.quit_blender()
"""
            )
        )
        return tpl.substitute(FINAL_PATH=filepath, VERSION_PATH=version_path)


# Alias
EditBuilder = EditingBuilder


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        current_dept = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        asset_dept = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        mastershot_data = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        addon_data = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
        file_paths = json.loads(sys.argv[-1]) if len(sys.argv) > 6 else {}

        builder = EditingBuilder()
        result = builder.extract_data(filepath=file_paths)
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
