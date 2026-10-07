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
except Exception:
    try:
        from Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
    except Exception:
        try:
            from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult
        except Exception:
            ShotPathGenerator = None
            ShotPathResult = None

try:
    from Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
except Exception:
    try:
        from Commands.Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
    except Exception:
        try:
            from pipeline.Commands.Paths.asset_path_generator import AssetPathGenerator, AssetPathResult
        except Exception:
            AssetPathGenerator = None
            AssetPathResult = None

try:
    from Locks.lock_manager import LockManager
except Exception:
    try:
        from Commands.Locks.lock_manager import LockManager
    except Exception:
        try:
            from pipeline.Commands.Locks.lock_manager import LockManager
        except Exception:
            LockManager = None

try:
    from versioning import VersioningSystem, get_master_path, get_next_version_path, get_version_path, up_master, up_version
except Exception:
    try:
        from Commands.versioning import VersioningSystem, get_master_path, get_next_version_path, get_version_path, up_master, up_version
    except Exception:
        try:
            from pipeline.Commands.versioning import VersioningSystem, get_master_path, get_next_version_path, get_version_path, up_master, up_version
        except Exception:
            VersioningSystem = None
            get_master_path = None
            get_next_version_path = None
            get_version_path = None
            up_master = None
            up_version = None

try:
    from feature_registry import (
        PipelineFeatureResult,
        execute_feature,
        list_available_features,
        register_feature,
    )
except Exception:
    try:
        from Commands.feature_registry import (
            PipelineFeatureResult,
            execute_feature,
            list_available_features,
            register_feature,
        )
    except Exception:
        try:
            from pipeline.Commands.feature_registry import (
                PipelineFeatureResult,
                execute_feature,
                list_available_features,
                register_feature,
            )
        except Exception:
            PipelineFeatureResult = None
            execute_feature = None
            list_available_features = None
            register_feature = None

try:
    from Builders.builder_factory import BuilderFactory, BuilderResult
except Exception:
    try:
        from Commands.Builders.builder_factory import BuilderFactory, BuilderResult
    except Exception:
        try:
            from pipeline.Commands.Builders.builder_factory import BuilderFactory, BuilderResult
        except Exception:
            BuilderFactory = None
            BuilderResult = None

# Default pipeline configuration location (relative to this Commands folder)
DEFAULT_PIPELINE_YAML = _pipeline_root / "pipeline.yaml"

_GENERATOR_CACHE: Dict[str, Any] = {}
_ASSET_GENERATOR_CACHE: Dict[str, Any] = {}
_LOCK_MANAGER_CACHE: Dict[str, Any] = {}


def get_generator(config_path: Optional[Union[str, Path]] = None) -> Any:
    """Create or return cached ShotPathGenerator initialized with pipeline.yaml."""
    cfg = Path(config_path) if config_path else DEFAULT_PIPELINE_YAML
    key = str(cfg.resolve())
    if key not in _GENERATOR_CACHE:
        if ShotPathGenerator is None:
            raise ImportError("ShotPathGenerator module could not be loaded.")
        _GENERATOR_CACHE[key] = ShotPathGenerator(config=cfg)
    return _GENERATOR_CACHE[key]
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
# Versioning and Up Version / Up Master APIs
# ==============================================================================
def resolve_master_path(filepath: Union[str, Path]) -> str:
    """Resolve master path for a given DCC file path."""
    if get_master_path:
        return get_master_path(filepath)
    from versioning import VersioningSystem
    return VersioningSystem.get_master_path(filepath)


def resolve_next_version_path(
    filepath: Union[str, Path],
    version_folder: str = "progress",
) -> str:
    """Resolve next incremental version path for a given DCC file path."""
    if get_next_version_path:
        return get_next_version_path(filepath, version_folder=version_folder)
    from versioning import VersioningSystem
    return VersioningSystem.get_next_version_path(filepath, version_folder=version_folder)


def generate_up_version_script(filepath: str) -> Tuple[str, str]:
    """Generate Blender script and version path for Up Version action."""
    if up_version:
        return up_version(filepath)
    from versioning import VersioningSystem
    return VersioningSystem.up_version(filepath)


def generate_up_master_script(
    filepath: str,
    setting_data: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Generate Blender script and master path for Up Master action."""
    if up_master:
        return up_master(filepath, setting_data=setting_data)
    from versioning import VersioningSystem
    return VersioningSystem.up_master(filepath, setting_data=setting_data)


def generate_asset_builder_script(
    filepath: str,
    department: str = "Asset",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    setting_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Tuple[str, str]:
    """Generate Blender script and version path for an asset using pipeline AssetBuilder."""
    cfg = config_path or DEFAULT_PIPELINE_YAML
    if BuilderFactory:
        res = BuilderFactory.generate_asset_script(
            filepath=filepath,
            department=department,
            config_path=cfg,
            project_path=project_path,
            setting_data=setting_data,
            **kwargs,
        )
        return res.script, res.target_version_path
    from versioning import VersioningSystem
    return "import bpy", VersioningSystem.get_version_path(filepath, version=1)


def generate_builder_script(
    filepath: str,
    department: str = "Layout",
    shot_data: Optional[Dict[str, Any]] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    setting_data: Optional[Dict[str, Any]] = None,
    builder_mode: str = "previous",
    **kwargs: Any,
) -> Tuple[str, str]:
    """Generate Blender script and version path using pipeline modular builder."""
    dept_clean = (department or "").lower().strip()
    if dept_clean in ("asset", "assets"):
        return generate_asset_builder_script(
            filepath=filepath,
            department=department,
            config_path=config_path,
            project_path=project_path,
            setting_data=setting_data,
            **kwargs,
        )

    cfg = config_path or DEFAULT_PIPELINE_YAML
    if BuilderFactory:
        res = BuilderFactory.generate_shot_script(
            filepath=filepath,
            department=department,
            shot_data=shot_data,
            config_path=cfg,
            project_path=project_path,
            setting_data=setting_data,
            builder_mode=builder_mode,
            **kwargs,
        )
        return res.script, res.target_version_path
    from versioning import VersioningSystem
    return "import bpy", VersioningSystem.get_version_path(filepath, version=1)



# ==============================================================================
# Dynamic Pipeline Features Discovery and Dispatch APIs
# ==============================================================================
def list_features(
    department: Optional[str] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
) -> List[str]:
    """Dynamically list all available pipeline features for the department and project."""
    cfg = config_path or DEFAULT_PIPELINE_YAML
    if list_available_features:
        return list_available_features(
            department=department,
            config_path=cfg,
            project_path=project_path,
        )
    return ["Generate", "Up Version", "Up Master"]


def run_pipeline_feature(
    feature_name: str,
    filepath: str,
    department: Optional[str] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    setting_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Execute a registered pipeline feature dynamically."""
    cfg = config_path or DEFAULT_PIPELINE_YAML
    if execute_feature:
        return execute_feature(
            feature_name=feature_name,
            filepath=filepath,
            department=department,
            config_path=cfg,
            project_path=project_path,
            setting_data=setting_data,
            **kwargs,
        )

    # Fallback to direct handlers
    clean_name = feature_name.lower().replace("_", " ")
    if clean_name in ("generate",):
        script, ver_path = generate_builder_script(
            filepath=filepath,
            department=department or "Layout",
            config_path=cfg,
            project_path=project_path,
            setting_data=setting_data,
            **kwargs,
        )
        return {
            "success": True,
            "message": f"Generated builder script for {ver_path}",
            "target_path": ver_path,
            "script": script,
        }
    elif clean_name in ("sync", "sync assets", "sync_assets"):
        if execute_feature:
            return execute_feature(
                feature_name="Sync",
                filepath=filepath,
                department=department,
                config_path=cfg,
                project_path=project_path,
                setting_data=setting_data,
                **kwargs,
            )
    elif clean_name in ("up version", "up_version"):
        script, ver_path = generate_up_version_script(filepath)
        return {
            "success": True,
            "message": f"Generated Up Version for {ver_path}",
            "target_path": ver_path,
            "script": script,
        }
    elif clean_name in ("up master", "up_master"):
        script, mst_path = generate_up_master_script(filepath, setting_data=setting_data)
        return {
            "success": True,
            "message": f"Generated Up Master for {mst_path}",
            "target_path": mst_path,
            "script": script,
        }

    return {"success": False, "message": f"Feature '{feature_name}' not recognized."}


# ==============================================================================
# CLI Interface
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="ZeroXe Pipeline Command Line Tool")
    parser.add_argument("--config", "-c", type=Path, default=None, help="Path to pipeline.yaml")

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate initial DCC scene file using pipeline builder")
    gen_parser.add_argument("--file", "-f", required=True, help="Input DCC file path or target shot file path")
    gen_parser.add_argument("--dept", "-d", default="Layout", help="Department name (e.g. Layout, Animation)")
    gen_parser.add_argument("--mode", "-m", default="previous", help="Builder resolution mode (e.g. previous, scan)")
    gen_parser.add_argument("--shot-data", default="{}", help="JSON string of shot data / metadata")
    gen_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # list-features command
    list_feat_parser = subparsers.add_parser("list-features", help="List all available pipeline features")
    list_feat_parser.add_argument("--dept", "-d", default="", help="Filter by department (e.g. Animation)")
    list_feat_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # execute-feature command
    exec_feat_parser = subparsers.add_parser("execute-feature", help="Execute a pipeline feature dynamically")
    exec_feat_parser.add_argument("--name", "-n", required=True, help="Feature name (e.g. 'Up Version', 'Up Master')")
    exec_feat_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    exec_feat_parser.add_argument("--dept", "-d", default="", help="Department name")
    exec_feat_parser.add_argument("--preset", "-p", default="", help="Path to preset python script")
    exec_feat_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # up-version command
    up_ver_parser = subparsers.add_parser("up-version", help="Generate Up Version script for a DCC file")
    up_ver_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    up_ver_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # up-master command
    up_mst_parser = subparsers.add_parser("up-master", help="Generate Up Master script for a DCC file")
    up_mst_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    up_mst_parser.add_argument("--preset", "-p", default="", help="Path to preset python script to embed")
    up_mst_parser.add_argument("--json", action="store_true", help="Output result as JSON")

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

    if args.command == "generate":
        shot_data = {}
        if getattr(args, "shot_data", None):
            try:
                shot_data = json.loads(args.shot_data)
            except Exception:
                pass

        script, ver_path = generate_builder_script(
            filepath=args.file,
            department=args.dept,
            shot_data=shot_data,
            config_path=args.config,
            builder_mode=getattr(args, "mode", "previous"),
        )
        if args.json:
            print(json.dumps({"version_path": ver_path, "script": script}, indent=2))
        else:
            print(f"Target Version Path: {ver_path}")
            print("Generated Script:\n" + script)

    elif args.command == "list-features":
        features = list_features(department=args.dept, config_path=args.config)
        if args.json:
            print(json.dumps({"features": features}, indent=2))
        else:
            print("Available Pipeline Features:")
            for f in features:
                print(f" - {f}")

    elif args.command == "execute-feature":
        setting_data = {"script": args.preset} if args.preset else None
        res = run_pipeline_feature(
            feature_name=args.name,
            filepath=args.file,
            department=args.dept,
            config_path=args.config,
            setting_data=setting_data,
        )
        if hasattr(res, "success"):
            output = {
                "success": res.success,
                "message": res.message,
                "target_path": res.target_path,
                "script": res.script,
            }
        elif isinstance(res, dict):
            output = res
        else:
            output = {"result": str(res)}

        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print(f"Result: {output}")

    elif args.command == "up-version":
        script, version_path = generate_up_version_script(args.file)
        if args.json:
            print(json.dumps({"version_path": version_path, "script": script}, indent=2))
        else:
            print(f"Target Version Path: {version_path}")
            print("Generated Script:\n" + script)

    elif args.command == "up-master":
        setting_data = {"script": args.preset} if args.preset else None
        script, master_path = generate_up_master_script(args.file, setting_data=setting_data)
        if args.json:
            print(json.dumps({"master_path": master_path, "script": script}, indent=2))
        else:
            print(f"Target Master Path: {master_path}")
            print("Generated Script:\n" + script)

    elif args.command == "shot-path":
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
