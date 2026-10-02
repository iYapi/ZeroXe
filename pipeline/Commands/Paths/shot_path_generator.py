"""Shot Path Generator Module.

Pattern-based generator for shot master and version file paths.
Configurable version formatting and pipeline placeholder resolution.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

# ==============================================================================
# Configurable Formatting Templates
# ==============================================================================
# Change VERSION_FORMAT here to adjust version string formatting (e.g. "v{version:03d}" -> v001)
DEFAULT_VERSION_FORMAT = "v{version:03d}"
DEFAULT_FILE_EXTENSION = ".blend"
DEFAULT_VERSION_FOLDER = "progress"


@dataclass
class ShotPathResult:
    """Encapsulates resolved shot path information."""

    master_path: Path
    version_path: Path
    shot_dir: Path
    version_dir: Path
    file_name: str
    version_file_name: str
    version_number: int


# Global in-memory cache for parsed YAML configs to avoid redundant disk/NAS reads
_YAML_CONFIG_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


class ShotPathGenerator:
    """Generates and resolves pipeline paths for shots."""

    def __init__(
        self,
        config: Optional[Union[Dict[str, Any], str, Path]] = None,
        version_format: str = DEFAULT_VERSION_FORMAT,
        default_extension: str = DEFAULT_FILE_EXTENSION,
    ):
        self.version_format = version_format
        self.default_extension = default_extension
        self.config: Dict[str, Any] = {}

        if config is not None:
            self.load_config(config)

    def load_config(self, config_source: Union[Dict[str, Any], str, Path]) -> None:
        """Load configuration dictionary or from YAML file path with fast caching."""
        if isinstance(config_source, dict):
            self.config = config_source
        else:
            path = Path(config_source)
            if path.is_file():
                resolved_key = str(path.resolve())
                try:
                    mtime = path.stat().st_mtime
                    cached = _YAML_CONFIG_CACHE.get(resolved_key)
                    if cached and cached[0] == mtime:
                        self.config = cached[1]
                        return

                    with open(path, "r", encoding="utf-8") as f:
                        loaded = yaml.safe_load(f) or {}
                        _YAML_CONFIG_CACHE[resolved_key] = (mtime, loaded)
                        self.config = loaded
                except Exception:
                    with open(path, "r", encoding="utf-8") as f:
                        self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}

    def get_project_path(self, platform_name: Optional[str] = None) -> str:
        """Resolve project mount root path for current OS platform."""
        global_cfg = self.config.get("global", {})
        mounts = global_cfg.get("mounts", {})

        if platform_name:
            return mounts.get(platform_name, "")

        if sys.platform.startswith("linux"):
            return mounts.get("linux", "")
        elif sys.platform.startswith("win32"):
            return mounts.get("windows", "")
        elif sys.platform.startswith("darwin"):
            return mounts.get("darwin", "")
        return mounts.get("linux", "")

    def get_project_code(self) -> str:
        """Retrieve project code (e.g. 'mdt')."""
        global_cfg = self.config.get("global", {})
        return str(global_cfg.get("code", "")).lower()

    def get_department_info(self, department_name_or_code: str) -> Tuple[str, Dict[str, Any]]:
        """Look up department configuration by name or short code with flexible matching."""
        departments = self.config.get("departments", {})
        if not departments:
            return department_name_or_code, {}

        # 1. Direct name match (e.g. 'Layout')
        if department_name_or_code in departments:
            return department_name_or_code, departments[department_name_or_code]

        # 2. Case-insensitive and normalized match (e.g. 'layout', '3d layout', 'lay')
        target_lower = department_name_or_code.lower().strip()
        target_clean = target_lower.replace(" ", "").replace("_", "")

        for dept_name, info in departments.items():
            dept_lower = dept_name.lower().strip()
            dept_clean = dept_lower.replace(" ", "").replace("_", "")
            code_lower = str(info.get("code", "")).lower().strip()
            code_clean = code_lower.replace(" ", "").replace("_", "")

            if (
                dept_lower == target_lower
                or dept_clean == target_clean
                or code_lower == target_lower
                or code_clean == target_clean
            ):
                return dept_name, info

        # 3. Substring matching (e.g. '3D Layout' contains 'layout')
        for dept_name, info in departments.items():
            dept_lower = dept_name.lower().strip()
            code_lower = str(info.get("code", "")).lower().strip()
            if (dept_lower and (dept_lower in target_lower or target_lower in dept_lower)) or (
                code_lower and (code_lower in target_lower or target_lower in code_lower)
            ):
                return dept_name, info

        # 4. Fallback to first configured department
        first_key = next(iter(departments.keys()))
        return first_key, departments[first_key]

    def resolve_base_path(self, raw_path: str, project_path: Optional[str] = None) -> str:
        """Replace @project_path@ placeholder with actual mount path."""
        proj_root = (project_path if project_path is not None else self.get_project_path()).rstrip("/\\")
        resolved = raw_path.replace("@project_path@", proj_root)
        return resolved

    @staticmethod
    def normalize_tokens(episode: str, sequence: str, shot: str) -> Tuple[str, str, str, str, str]:
        """Normalize and clean episode, sequence, shot tokens into standard naming parts.

        Returns:
            Tuple[ep_clean, sq_clean, sh_clean, seq_folder, shot_folder]
        """
        ep_clean = episode.strip().lower()

        # Handle sequence prefix (e.g. 'ep998_sq01' vs 'sq01')
        seq_input = sequence.strip().lower()
        if seq_input.startswith(f"{ep_clean}_"):
            sq_clean = seq_input[len(ep_clean) + 1 :]
            seq_folder = seq_input
        else:
            sq_clean = seq_input
            seq_folder = f"{ep_clean}_{sq_clean}" if ep_clean else sq_clean

        # Handle shot prefix (e.g. 'ep998_sq01_sh0020' vs 'sh0020')
        shot_input = shot.strip().lower()
        if shot_input.startswith(f"{seq_folder}_"):
            sh_clean = shot_input[len(seq_folder) + 1 :]
            shot_folder = shot_input
        elif shot_input.startswith(f"{ep_clean}_"):
            sh_clean = shot_input.split("_")[-1]
            shot_folder = f"{seq_folder}_{sh_clean}"
        else:
            sh_clean = shot_input
            shot_folder = f"{seq_folder}_{sh_clean}" if seq_folder else sh_clean

        return ep_clean, sq_clean, sh_clean, seq_folder, shot_folder

    def format_version(self, version_number: int) -> str:
        """Format version number according to configured version_format."""
        return self.version_format.format(version=version_number)

    def generate_shot_paths(
        self,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        version_number: int = 1,
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        project_code: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> ShotPathResult:
        """Generate master path, version path, and directories for a given shot."""
        ext = extension or self.default_extension
        if not ext.startswith("."):
            ext = f".{ext}"

        proj_code = (project_code or self.get_project_code() or "proj").lower()
        _, dept_info = self.get_department_info(department)
        dept_code = dept_info.get("code", department.lower()[:3])
        raw_base = dept_info.get("base_path", "")

        resolved_base = self.resolve_base_path(raw_base, project_path=project_path)
        ep_clean, _, _, seq_folder, shot_folder = self.normalize_tokens(episode, sequence, shot)

        # Directory structure: base_path / ep998 / ep998_sq01 / ep998_sq01_sh0020
        base_dir = Path(resolved_base)
        shot_dir = base_dir / ep_clean / seq_folder / shot_folder
        version_dir = shot_dir / version_folder

        # File names
        # Master: mdt_ep998_sq01_sh0020_lay.blend
        file_base = f"{proj_code}_{shot_folder}_{dept_code}"
        master_file_name = f"{file_base}{ext}"
        master_path = shot_dir / master_file_name

        # Version: mdt_ep998_sq01_sh0020_lay_v001.blend
        version_str = self.format_version(version_number)
        version_file_name = f"{file_base}_{version_str}{ext}"
        version_path = version_dir / version_file_name

        return ShotPathResult(
            master_path=master_path,
            version_path=version_path,
            shot_dir=shot_dir,
            version_dir=version_dir,
            file_name=master_file_name,
            version_file_name=version_file_name,
            version_number=version_number,
        )

    def list_existing_versions(
        self,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> List[Tuple[int, Path]]:
        """List existing version files in the version directory, sorted by version number.

        Returns list of (version_number, file_path) tuples.
        """
        ext = extension or self.default_extension
        if not ext.startswith("."):
            ext = f".{ext}"

        res = self.generate_shot_paths(
            department=department,
            episode=episode,
            sequence=sequence,
            shot=shot,
            version_folder=version_folder,
            project_path=project_path,
            extension=ext,
        )

        search_dirs: List[Path] = []
        if res.version_dir.is_dir():
            search_dirs.append(res.version_dir)
        if res.shot_dir.is_dir() and res.shot_dir != res.version_dir:
            search_dirs.append(res.shot_dir)

        if not search_dirs:
            return []

        versions: List[Tuple[int, Path]] = []
        seen_numbers = set()

        # Compile matching regexes
        base_no_ext = res.file_name[:-len(ext)] if res.file_name.lower().endswith(ext.lower()) else res.file_name
        specific_pattern = re.compile(rf"^{re.escape(base_no_ext)}_v(\d+){re.escape(ext)}$", re.IGNORECASE)
        generic_pattern = re.compile(rf"(?:^|[_.\-])[vV](\d+){re.escape(ext)}$", re.IGNORECASE)

        for d in search_dirs:
            for f in d.iterdir():
                if f.is_file() and f.name.lower().endswith(ext.lower()):
                    # Avoid adding master file as a version if it happens to match
                    if f.resolve() == res.master_path.resolve():
                        continue

                    # Try specific pattern first
                    m = specific_pattern.search(f.name)
                    if not m:
                        m = generic_pattern.search(f.name)

                    if m:
                        try:
                            ver_num = int(m.group(1))
                            if ver_num not in seen_numbers:
                                seen_numbers.add(ver_num)
                                versions.append((ver_num, f))
                        except ValueError:
                            continue

        versions.sort(key=lambda x: x[0])
        return versions


    def get_next_version_number(
        self,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> int:
        """Find the highest existing version number and return next (highest + 1)."""
        existing = self.list_existing_versions(
            department=department,
            episode=episode,
            sequence=sequence,
            shot=shot,
            version_folder=version_folder,
            project_path=project_path,
            extension=extension,
        )
        if not existing:
            return 1
        return existing[-1][0] + 1
