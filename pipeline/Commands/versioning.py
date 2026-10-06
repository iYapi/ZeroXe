"""Versioning System Module for ZeroXe Pipeline.

Provides pattern-based path resolution for master and version files,
and automated DCC script generation (Up Version, Up Master) with preset integration.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from string import Template
import sys
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class VersioningSystem:
    """Core Versioning System for ZeroXe Pipeline DCC files."""

    @staticmethod
    def get_master_path(filepath: Union[str, Path]) -> str:
        """Extract master file path from either a version path or an existing master path.

        Examples:
            '/path/to/shot/progress/mdt_ep998_sq01_sh0020_lay_v002.blend' -> '/path/to/shot/mdt_ep998_sq01_sh0020_lay.blend'
            '/path/to/shot/mdt_ep998_sq01_sh0020_lay.blend' -> '/path/to/shot/mdt_ep998_sq01_sh0020_lay.blend'
            '/path/to/asset/progress/c-hero_v001.blend' -> '/path/to/asset/c-hero.blend'
        """
        p = Path(filepath).resolve()
        parent = p.parent
        ext = p.suffix
        stem = p.stem

        # Remove version suffix like _v001, _v02, .v003, -v001
        master_stem = re.sub(r"[_.\-]v\d+$", "", stem, flags=re.IGNORECASE)
        master_filename = f"{master_stem}{ext}"

        # If file is inside a version directory (e.g. 'progress', 'version', 'versions', 'work', 'wip')
        if parent.name.lower() in ("progress", "version", "versions", "work", "wip"):
            master_dir = parent.parent
        else:
            master_dir = parent

        return str(master_dir / master_filename)

    @staticmethod
    def get_next_version_path(
        filepath: Union[str, Path],
        version_folder: str = "progress",
        version_format: str = "v{version:03d}",
    ) -> str:
        """Calculate the next incremental version file path.

        Scans the version folder for existing versions (e.g. v001, v002) and returns
        the next highest version path (e.g. v003). If none exists, returns v001.
        """
        p = Path(filepath).resolve()
        parent = p.parent
        ext = p.suffix or ".blend"
        stem = p.stem

        # Base stem without any version suffix
        base_stem = re.sub(r"[_.\-]v\d+$", "", stem, flags=re.IGNORECASE)

        # Determine version directory and base directory
        if parent.name.lower() == version_folder.lower():
            ver_dir = parent
            base_dir = parent.parent
        else:
            base_dir = parent
            ver_dir = base_dir / version_folder

        existing_versions: List[int] = []
        pattern = re.compile(rf"^{re.escape(base_stem)}[_.\-]v(\d+){re.escape(ext)}$", re.IGNORECASE)

        search_dirs = [ver_dir]
        if base_dir.is_dir() and base_dir != ver_dir:
            search_dirs.append(base_dir)

        for d in search_dirs:
            if d.is_dir():
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() == ext.lower():
                        m = pattern.match(f.name)
                        if m:
                            try:
                                existing_versions.append(int(m.group(1)))
                            except ValueError:
                                pass

        if existing_versions:
            next_ver_num = max(existing_versions) + 1
        else:
            cur_m = re.search(r"[_.\-]v(\d+)$", stem, flags=re.IGNORECASE)
            if cur_m:
                next_ver_num = int(cur_m.group(1)) + 1
            else:
                next_ver_num = 1

        version_str = version_format.format(version=next_ver_num)
        version_filename = f"{base_stem}_{version_str}{ext}"
        return str(ver_dir / version_filename)

    @staticmethod
    def up_version(filepath: str) -> Tuple[str, str]:
        """Generate Blender automation script and target version path for Up Version action."""
        tpl = Template(dedent("""
			import bpy

			bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

			bpy.ops.wm.save_as_mainfile(filepath="$VERSION_PATH", copy=True)

			bpy.ops.wm.quit_blender()
			""").strip())

        version_path = VersioningSystem.get_next_version_path(filepath)

        script = tpl.substitute(
            FILEPATH=filepath,
            VERSION_PATH=version_path,
        )
        return script, version_path

    @staticmethod
    def up_master(filepath: str, setting_data: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """Generate Blender automation script and target master path for Up Master action.

        Applies preset script code configured for the department if present in setting_data.
        """
        start_script = Template(dedent("""
import bpy

bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

bpy.ops.wm.save_as_mainfile(filepath="$MASTER_PATH")
		""").strip())
        end_script = Template(dedent("""
bpy.ops.wm.save_as_mainfile(filepath="$MASTER_PATH")

bpy.ops.wm.quit_blender()
        """).strip())
        master_path = VersioningSystem.get_master_path(filepath)

        script = start_script.substitute(
            FILEPATH=filepath,
            MASTER_PATH=master_path,
        )
        end_script = end_script.substitute(
            MASTER_PATH=master_path,
        )
        if setting_data and setting_data.get("script"):
            script_path = setting_data.get("script")
            if script_path and Path(script_path).is_file():
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        preset_code = f.read()
                        script = script + "\n\n" + preset_code
                except Exception as e:
                    logger.warning(f"Could not read preset script from {script_path}: {e}")

        script = script + "\n\n" + end_script
        return script, master_path


def up_version(filepath: str) -> Tuple[str, str]:
    """Module-level shortcut for VersioningSystem.up_version."""
    return VersioningSystem.up_version(filepath)


def up_master(filepath: str, setting_data: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """Module-level shortcut for VersioningSystem.up_master."""
    return VersioningSystem.up_master(filepath, setting_data=setting_data)


def get_master_path(filepath: Union[str, Path]) -> str:
    """Module-level shortcut for VersioningSystem.get_master_path."""
    return VersioningSystem.get_master_path(filepath)


def get_next_version_path(
    filepath: Union[str, Path],
    version_folder: str = "progress",
    version_format: str = "v{version:03d}",
) -> str:
    """Module-level shortcut for VersioningSystem.get_next_version_path."""
    return VersioningSystem.get_next_version_path(
        filepath=filepath,
        version_folder=version_folder,
        version_format=version_format,
    )
