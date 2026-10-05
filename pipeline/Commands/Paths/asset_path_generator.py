"""Asset Path Generator Module.

Pattern-based generator for asset master and version file paths using pipeline.yaml asset_type configurations.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

DEFAULT_VERSION_FORMAT = "v{version:03d}"
DEFAULT_FILE_EXTENSION = ".blend"
DEFAULT_VERSION_FOLDER = "progress"


@dataclass
class AssetPathResult:
    """Encapsulates resolved asset path information."""

    master_path: Path
    version_path: Path
    asset_dir: Path
    version_dir: Path
    file_name: str
    version_file_name: str
    version_number: int


_YAML_CONFIG_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


class AssetPathGenerator:
    """Generates and resolves pipeline paths for assets based on asset_type in pipeline.yaml."""

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

    def get_asset_type_info(self, asset_type_name_or_code: str) -> Tuple[str, Dict[str, Any]]:
        """Look up asset_type configuration by name, key, or short code with flexible matching."""
        asset_types = self.config.get("asset_type", {})
        if not asset_types:
            return asset_type_name_or_code, {}

        # 1. Direct key match (e.g. 'CHAR', 'PROPS')
        if asset_type_name_or_code in asset_types:
            return asset_type_name_or_code, asset_types[asset_type_name_or_code]

        target_lower = asset_type_name_or_code.lower().strip()
        target_clean = target_lower.replace(" ", "").replace("_", "").replace("-", "")

        for at_name, info in asset_types.items():
            at_lower = at_name.lower().strip()
            at_clean = at_lower.replace(" ", "").replace("_", "").replace("-", "")
            code_lower = str(info.get("code", "")).lower().strip()
            code_clean = code_lower.replace(" ", "").replace("_", "").replace("-", "")
            prefix_lower = str(info.get("prefix", "")).lower().strip().replace("-", "").replace("_", "")

            if (
                at_lower == target_lower
                or at_clean == target_clean
                or code_lower == target_lower
                or code_clean == target_clean
                or (prefix_lower and prefix_lower == target_clean)
            ):
                return at_name, info

        # 2. Substring matching (e.g. 'character' contains 'char')
        for at_name, info in asset_types.items():
            at_lower = at_name.lower().strip()
            code_lower = str(info.get("code", "")).lower().strip()
            if (at_lower and (at_lower in target_lower or target_lower in at_lower)) or (
                code_lower and (code_lower in target_lower or target_lower in code_lower)
            ):
                return at_name, info

        # 3. Fallback to first configured asset_type
        first_key = next(iter(asset_types.keys()))
        return first_key, asset_types[first_key]

    def resolve_base_path(self, raw_path: str, project_path: Optional[str] = None) -> str:
        """Replace @project_path@ placeholder with actual mount path."""
        proj_root = (project_path if project_path is not None else self.get_project_path()).rstrip("/\\")
        return raw_path.replace("@project_path@", proj_root)

    def format_version(self, version_number: int) -> str:
        """Format version number according to configured version_format."""
        return self.version_format.format(version=version_number)

    def generate_asset_paths(
        self,
        asset_type: str,
        asset_name: str,
        department: str = "",
        version_number: int = 1,
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        project_code: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> AssetPathResult:
        """Generate master path, version path, and directories for an asset."""
        ext = extension or self.default_extension
        if not ext.startswith("."):
            ext = f".{ext}"

        proj_code = (project_code or self.get_project_code() or "proj").lower()
        _, at_info = self.get_asset_type_info(asset_type)
        at_code = str(at_info.get("code", asset_type.lower()[:3])).lower()
        raw_base = at_info.get("base_path", "")
        prefix = str(at_info.get("prefix", "")).lower()

        resolved_base = self.resolve_base_path(raw_base, project_path=project_path)
        base_dir = Path(resolved_base)

        # Normalize asset folder name (apply prefix if not present)
        clean_name = asset_name.strip().lower()
        if prefix and not clean_name.startswith(prefix):
            asset_folder = f"{prefix}{clean_name}"
        else:
            asset_folder = clean_name

        # Directory structure: base_path / <asset_folder> (e.g. 01_char / c-hero_char)
        asset_dir = base_dir / asset_folder
        version_dir = asset_dir / version_folder

        # File naming convention (no project code for assets, e.g. c-hero_char.blend):
        file_base = asset_folder

        master_file_name = f"{file_base}{ext}"
        master_path = asset_dir / master_file_name

        version_str = self.format_version(version_number)
        version_file_name = f"{file_base}_{version_str}{ext}"
        version_path = version_dir / version_file_name

        return AssetPathResult(
            master_path=master_path,
            version_path=version_path,
            asset_dir=asset_dir,
            version_dir=version_dir,
            file_name=master_file_name,
            version_file_name=version_file_name,
            version_number=version_number,
        )

    def list_existing_versions(
        self,
        asset_type: str,
        asset_name: str,
        department: str = "",
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> List[Tuple[int, Path]]:
        """List existing version files in the asset version directory."""
        ext = extension or self.default_extension
        if not ext.startswith("."):
            ext = f".{ext}"

        res = self.generate_asset_paths(
            asset_type=asset_type,
            asset_name=asset_name,
            department=department,
            version_folder=version_folder,
            project_path=project_path,
            extension=ext,
        )

        search_dirs: List[Path] = []
        if res.version_dir.is_dir():
            search_dirs.append(res.version_dir)
        if res.asset_dir.is_dir() and res.asset_dir != res.version_dir:
            search_dirs.append(res.asset_dir)

        if not search_dirs:
            return []

        versions: List[Tuple[int, Path]] = []
        seen_numbers = set()

        base_no_ext = res.file_name[:-len(ext)] if res.file_name.lower().endswith(ext.lower()) else res.file_name
        specific_pattern = re.compile(rf"^{re.escape(base_no_ext)}_v(\d+){re.escape(ext)}$", re.IGNORECASE)
        generic_pattern = re.compile(rf"(?:^|[_.\-])[vV](\d+){re.escape(ext)}$", re.IGNORECASE)

        for d in search_dirs:
            for f in d.iterdir():
                if f.is_file() and f.name.lower().endswith(ext.lower()):
                    if f.resolve() == res.master_path.resolve():
                        continue

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
        asset_type: str,
        asset_name: str,
        department: str = "",
        version_folder: str = DEFAULT_VERSION_FOLDER,
        project_path: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> int:
        """Find the highest existing version number and return next (highest + 1)."""
        existing = self.list_existing_versions(
            asset_type=asset_type,
            asset_name=asset_name,
            department=department,
            version_folder=version_folder,
            project_path=project_path,
            extension=extension,
        )
        if not existing:
            return 1
        return existing[-1][0] + 1
