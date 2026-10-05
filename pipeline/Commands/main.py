"""Modular Entrypoint for ZeroXe Pipeline Commands.

Provides unified Python API and CLI interface for Qt app integration,
path generation for shots & assets, lock management, and builder dispatching.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure sibling directories (Paths, Locks, Builders) and pipeline root can be resolved
_current_dir = Path(__file__).resolve().parent
_pipeline_root = _current_dir.parent

for _p in [str(_pipeline_root), str(_current_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
    from Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
except ImportError:
    try:
        from Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
        from Commands.Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
    except ImportError:
        try:
            from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
            from pipeline.Commands.Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
        except ImportError:
            from .Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
            from .Paths.asset_path_generator import AssetPathGenerator, AssetPathResult

try:
    from Locks.lock_manager import LockManager
except ImportError:
    try:
        from Commands.Locks.lock_manager import LockManager
    except ImportError:
        try:
            from pipeline.Commands.Locks.lock_manager import LockManager
        except ImportError:
            from .Locks.lock_manager import LockManager

# Default pipeline configuration location (relative to this Commands folder)
DEFAULT_PIPELINE_YAML = _pipeline_root / "pipeline.yaml"

_GENERATOR_CACHE: Dict[str, ShotPathGenerator] = {}
_ASSET_GENERATOR_CACHE: Dict[str, AssetPathGenerator] = {}
_LOCK_MANAGER_CACHE: Dict[str, LockManager] = {}


def get_generator(config_path: Optional[Union[str, Path]] = None) -> ShotPathGenerator:
    """Create or return cached ShotPathGenerator initialized with pipeline.yaml."""
    cfg = Path(config_path) if config_path else DEFAULT_PIPELINE_YAML
    key = str(cfg.resolve())
    if key not in _GENERATOR_CACHE:
        _GENERATOR_CACHE[key] = ShotPathGenerator(config=cfg)
    return _GENERATOR_CACHE[key]


def get_asset_generator(config_path: Optional[Union[str, Path]] = None) -> AssetPathGenerator:
    """Create or return cached AssetPathGenerator initialized with pipeline.yaml."""
    cfg = Path(config_path) if config_path else DEFAULT_PIPELINE_YAML
    key = str(cfg.resolve())
    if key not in _ASSET_GENERATOR_CACHE:
        _ASSET_GENERATOR_CACHE[key] = AssetPathGenerator(config=cfg)
    return _ASSET_GENERATOR_CACHE[key]


def get_lock_manager(config_path: Optional[Union[str, Path]] = None) -> LockManager:
    """Create or return cached LockManager."""
    cfg = Path(config_path) if config_path else DEFAULT_PIPELINE_YAML
    key = str(cfg.resolve())
    if key not in _LOCK_MANAGER_CACHE:
        _LOCK_MANAGER_CACHE[key] = LockManager(pipeline_root=cfg.parent)
    return _LOCK_MANAGER_CACHE[key]


def clear_generator_cache() -> None:
    """Clear in-memory generator, lock manager, and config caches."""
    _GENERATOR_CACHE.clear()
    _ASSET_GENERATOR_CACHE.clear()
    _LOCK_MANAGER_CACHE.clear()


# ==============================================================================
# Shot Path Resolution APIs
# ==============================================================================
def resolve_shot_paths(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_number: int = 1,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> ShotPathResult:
    """Resolve master path and version path for a given shot."""
    generator = get_generator(config_path)
    return generator.generate_shot_paths(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_number=version_number,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def list_shot_versions(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> List[Tuple[int, Path]]:
    """List existing versions for a shot."""
    generator = get_generator(config_path)
    return generator.list_existing_versions(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def get_next_shot_version(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> int:
    """Get the next version number for a shot."""
    generator = get_generator(config_path)
    return generator.get_next_version_number(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


# ==============================================================================
# Asset Path Resolution APIs
# ==============================================================================
def resolve_asset_paths(
    asset_type: str,
    asset_name: str,
    department: str = "",
    version_number: int = 1,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> AssetPathResult:
    """Resolve master path and version path for a given asset."""
    generator = get_asset_generator(config_path)
    return generator.generate_asset_paths(
        asset_type=asset_type,
        asset_name=asset_name,
        department=department,
        version_number=version_number,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def list_asset_versions(
    asset_type: str,
    asset_name: str,
    department: str = "",
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> List[Tuple[int, Path]]:
    """List existing versions for an asset."""
    generator = get_asset_generator(config_path)
    return generator.list_existing_versions(
        asset_type=asset_type,
        asset_name=asset_name,
        department=department,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def get_next_asset_version(
    asset_type: str,
    asset_name: str,
    department: str = "",
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> int:
    """Get the next version number for an asset."""
    generator = get_asset_generator(config_path)
    return generator.get_next_version_number(
        asset_type=asset_type,
        asset_name=asset_name,
        department=department,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


# ==============================================================================
# Lock and Version History APIs
# ==============================================================================
def build_entity_key(
    department: str,
    episode: str = "",
    sequence: str = "",
    shot: str = "",
    task: str = "",
    asset_type: str = "",
    asset_name: str = "",
) -> str:
    """Construct standard entity key for shot or asset."""
    if asset_name:
        clean_at = asset_type.strip().lower()
        clean_an = asset_name.strip().lower().replace(" ", "_")
        clean_dept = department.strip().lower() or task.strip().lower()
        if clean_dept and clean_dept not in ("asset", "none"):
            return f"asset_{clean_at}_{clean_an}_{clean_dept}"
        return f"asset_{clean_at}_{clean_an}"

    return LockManager.build_entity_key(
        department=department, episode=episode, sequence=sequence, shot=shot, task=task
    )


def check_lock(
    entity_key: str,
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check if an entity is currently locked."""
    mgr = get_lock_manager(config_path)
    return mgr.check_lock(entity_key=entity_key, project_path=project_path, config_path=config_path)


def acquire_lock(
    entity_key: str,
    kitsu_id: str,
    name: str,
    email: str = "",
    workstation: Optional[str] = None,
    working_file: str = "",
    current_version: str = "",
    project_name: str = "",
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
    force: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Acquire lock on a shot/asset and record OPEN_FILE in history log."""
    mgr = get_lock_manager(config_path)
    return mgr.acquire_lock(
        entity_key=entity_key,
        kitsu_id=kitsu_id,
        name=name,
        email=email,
        workstation=workstation,
        working_file=working_file,
        current_version=current_version,
        project_name=project_name,
        project_path=project_path,
        config_path=config_path,
        force=force,
    )


def release_lock(
    entity_key: str,
    kitsu_id: str = "",
    name: str = "",
    workstation: Optional[str] = None,
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Release lock on file close and record CLOSE_FILE in history log."""
    mgr = get_lock_manager(config_path)
    return mgr.release_lock(
        entity_key=entity_key,
        kitsu_id=kitsu_id,
        name=name,
        workstation=workstation,
        project_path=project_path,
        config_path=config_path,
    )


def force_unlock(
    entity_key: str,
    kitsu_id: str,
    name: str,
    reason: str = "Lead forced unlock",
    workstation: Optional[str] = None,
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Force unlock an entity and record FORCE_UNLOCK in history log."""
    mgr = get_lock_manager(config_path)
    return mgr.force_unlock(
        entity_key=entity_key,
        kitsu_id=kitsu_id,
        name=name,
        reason=reason,
        workstation=workstation,
        project_path=project_path,
        config_path=config_path,
    )


def record_version(
    entity_key: str,
    kitsu_id: str,
    name: str,
    version: str,
    file_path: str,
    comment: str = "",
    file_size_mb: float = 0.0,
    workstation: Optional[str] = None,
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Record a newly saved version in history log."""
    mgr = get_lock_manager(config_path)
    return mgr.record_version(
        entity_key=entity_key,
        kitsu_id=kitsu_id,
        name=name,
        version=version,
        file_path=file_path,
        comment=comment,
        file_size_mb=file_size_mb,
        workstation=workstation,
        project_path=project_path,
        config_path=config_path,
    )


def get_history(
    entity_key: str,
    project_path: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Get history JSON for an entity."""
    mgr = get_lock_manager(config_path)
    return mgr.get_history(entity_key=entity_key, project_path=project_path, config_path=config_path)


# ==============================================================================
# CLI Interface
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="ZeroXe Pipeline Command Line Tool")
    parser.add_argument("--config", "-c", type=Path, default=None, help="Path to pipeline.yaml")

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # shot-path command
    shot_parser = subparsers.add_parser("shot-path", help="Resolve master and version paths for a shot")
    shot_parser.add_argument("--dept", "-d", required=True, help="Department name or code (e.g. Layout, lay)")
    shot_parser.add_argument("--ep", "-e", required=True, help="Episode (e.g. ep998)")
    shot_parser.add_argument("--sq", "-s", required=True, help="Sequence (e.g. sq01)")
    shot_parser.add_argument("--sh", required=True, help="Shot (e.g. sh0020)")
    shot_parser.add_argument("--ver", "-v", type=int, default=1, help="Version number (default: 1)")
    shot_parser.add_argument("--ver-folder", default="progress", help="Version folder name (default: progress)")
    shot_parser.add_argument("--mount", help="Override project mount root path")
    shot_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # asset-path command
    asset_parser = subparsers.add_parser("asset-path", help="Resolve master and version paths for an asset")
    asset_parser.add_argument("--type", "-t", required=True, help="Asset type (e.g. CHAR, PROPS, SET, VEHICLE)")
    asset_parser.add_argument("--name", "-n", required=True, help="Asset name (e.g. Hero_Char, c-hero)")
    asset_parser.add_argument("--dept", "-d", default="", help="Department/task name (e.g. Model, Texture)")
    asset_parser.add_argument("--ver", "-v", type=int, default=1, help="Version number (default: 1)")
    asset_parser.add_argument("--ver-folder", default="progress", help="Version folder name (default: progress)")
    asset_parser.add_argument("--mount", help="Override project mount root path")
    asset_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # lock command
    lock_parser = subparsers.add_parser("lock", help="Check or acquire lock")
    lock_parser.add_argument("--key", "-k", required=True, help="Entity key (e.g. ep998_sq01_sh0010_anm)")
    lock_parser.add_argument("--kitsu-id", default="", help="Kitsu user ID")
    lock_parser.add_argument("--name", default="", help="User name")
    lock_parser.add_argument("--check", action="store_true", help="Only check lock status")

    args = parser.parse_args()

    if args.command == "shot-path":
        result = resolve_shot_paths(
            department=args.dept,
            episode=args.ep,
            sequence=args.sq,
            shot=args.sh,
            version_number=args.ver,
            version_folder=args.ver_folder,
            config_path=args.config,
            project_path=args.mount,
        )

        if args.json:
            output = {
                "master_path": str(result.master_path),
                "version_path": str(result.version_path),
                "shot_dir": str(result.shot_dir),
                "version_dir": str(result.version_dir),
                "file_name": result.file_name,
                "version_file_name": result.version_file_name,
                "version_number": result.version_number,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Master Path : {result.master_path}")
            print(f"Version Path: {result.version_path}")
            print(f"Shot Dir    : {result.shot_dir}")
            print(f"Version Dir : {result.version_dir}")

    elif args.command == "asset-path":
        result = resolve_asset_paths(
            asset_type=args.type,
            asset_name=args.name,
            department=args.dept,
            version_number=args.ver,
            version_folder=args.ver_folder,
            config_path=args.config,
            project_path=args.mount,
        )

        if args.json:
            output = {
                "master_path": str(result.master_path),
                "version_path": str(result.version_path),
                "asset_dir": str(result.asset_dir),
                "version_dir": str(result.version_dir),
                "file_name": result.file_name,
                "version_file_name": result.version_file_name,
                "version_number": result.version_number,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Master Path : {result.master_path}")
            print(f"Version Path: {result.version_path}")
            print(f"Asset Dir   : {result.asset_dir}")
            print(f"Version Dir : {result.version_dir}")

    elif args.command == "lock":
        if args.check:
            is_locked, data = check_lock(args.key, config_path=args.config)
            print(json.dumps({"is_locked": is_locked, "data": data}, indent=2))
        else:
            success, msg, data = acquire_lock(
                entity_key=args.key,
                kitsu_id=args.kitsu_id,
                name=args.name,
                config_path=args.config,
            )
            print(json.dumps({"success": success, "message": msg, "data": data}, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
