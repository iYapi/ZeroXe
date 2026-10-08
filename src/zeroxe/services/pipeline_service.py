"""Pipeline Service.

Bridges the ZeroXe desktop application (controllers and views)
with external pipeline path resolution and command modules.

Uses dynamic module loading via `importlib.util` to load the external pipeline entrypoint
strictly from NAS or the configured pipeline_path in zeroxe_map.yaml.

No local pipeline dependencies or static package requirements.
Includes dynamic cache invalidation when settings or map files change.
"""

from dataclasses import dataclass
import importlib.util
import logging
from pathlib import Path
import re
from string import Template
import subprocess
import sys
import tempfile
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import yaml

from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)






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



class PipelineService:
    """High-performance service for resolving pipeline paths and executing pipeline commands."""

    _cached_modules: Dict[str, Any] = {}
    _cached_pipeline_yaml_paths: Dict[Optional[str], Optional[Path]] = {}
    _cached_entrypoints: Dict[Optional[str], Optional[Path]] = {}
    _cached_resolvers: Dict[str, Tuple[Callable, Callable, Callable]] = {}
    _cached_map_path_value: Optional[str] = None
    _cached_map_mtime: Optional[float] = None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all in-memory pipeline path, module, and function caches."""
        cls._cached_modules.clear()
        cls._cached_pipeline_yaml_paths.clear()
        cls._cached_entrypoints.clear()
        cls._cached_resolvers.clear()

    @classmethod
    def _validate_cache_freshness(cls) -> None:
        """Automatically invalidate cache if the configured map path string changed."""
        current_map_path = SettingsService.get_zeroxe_map_path()
        if current_map_path != cls._cached_map_path_value:
            cls.clear_cache()
            cls._cached_map_path_value = current_map_path


    @classmethod
    def _get_pipeline_error_reason(cls, project_name: Optional[str] = None) -> str:
        """Diagnose why pipeline could not be loaded to produce a clear error message."""
        map_path = SettingsService.get_zeroxe_map_path()
        if not map_path:
            return "zeroxe_map.yaml path is not configured. Please set the zeroxe_map path in Settings -> NAS."

        map_file = Path(map_path)
        if not map_file.is_file():
            return (
                f"zeroxe_map.yaml file not found at: '{map_path}'. "
                "Please check your NAS connection or update the path in Settings -> NAS."
            )

        zeroxe_map = SettingsService.get_zeroxe_map()
        if not zeroxe_map or "project" not in zeroxe_map:
            return f"zeroxe_map.yaml at '{map_path}' is empty or missing the 'project' configuration section."

        projects = zeroxe_map.get("project", {})
        if not projects:
            return f"No projects are configured in zeroxe_map.yaml at '{map_path}'."

        if project_name:
            target_lower = project_name.lower()
            matched = False
            for p_key, p_info in projects.items():
                if isinstance(p_info, dict):
                    if (
                        p_key.lower() == target_lower
                        or str(p_info.get("code", "")).lower() == target_lower
                        or str(p_info.get("name", "")).lower() == target_lower
                    ):
                        matched = True
                        pipe_path = p_info.get("pipeline_path")
                        if not pipe_path:
                            return f"Project '{project_name}' in zeroxe_map.yaml has no 'pipeline_path' configured."
                        if not Path(pipe_path).is_file():
                            return (
                                f"pipeline.yaml for project '{project_name}' not found at: '{pipe_path}'. "
                                "Please verify the NAS path in zeroxe_map.yaml."
                            )
            if not matched:
                avail = ", ".join(projects.keys())
                return f"Project '{project_name}' was not found in zeroxe_map.yaml (configured projects: {avail})."

        pipe_yaml = cls.get_active_pipeline_yaml_path(project_name=project_name)
        if not pipe_yaml or not pipe_yaml.is_file():
            return "The 'pipeline.yaml' specified in zeroxe_map.yaml could not be found or does not exist on disk."

        entrypoint = cls.get_pipeline_entrypoint(project_name=project_name)
        if not entrypoint or not entrypoint.is_file():
            return f"Pipeline entrypoint 'Commands/main.py' not found in pipeline directory: '{pipe_yaml.parent}'."

        return f"Could not load external pipeline module from '{map_path}'."

    @classmethod
    def get_active_pipeline_yaml_path(cls, project_name: Optional[str] = None) -> Optional[Path]:
        """Resolve active pipeline.yaml path strictly from zeroxe_map.yaml."""
        cls._validate_cache_freshness()

        if project_name in cls._cached_pipeline_yaml_paths:
            return cls._cached_pipeline_yaml_paths[project_name]

        path = cls._resolve_pipeline_yaml_path(project_name=project_name)
        cls._cached_pipeline_yaml_paths[project_name] = path
        return path

    @classmethod
    def _resolve_pipeline_yaml_path(cls, project_name: Optional[str] = None) -> Optional[Path]:
        """Internal uncached resolution of pipeline.yaml path from zeroxe_map.yaml."""
        zeroxe_map = SettingsService.get_zeroxe_map()
        if not zeroxe_map:
            logger.warning("zeroxe_map.yaml is empty or could not be loaded from NAS settings.")
            return None

        projects = zeroxe_map.get("project", {})
        if not projects:
            logger.warning("No projects defined in zeroxe_map.yaml.")
            return None

        # 1. Match specifically requested project (by key, code, or name)
        if project_name:
            if project_name in projects and isinstance(projects[project_name], dict):
                pipe_path = projects[project_name].get("pipeline_path")
                if pipe_path and Path(pipe_path).is_file():
                    return Path(pipe_path)
                elif pipe_path:
                    logger.warning(f"Project '{project_name}' pipeline_path does not exist: {pipe_path}")
                    return None

            target_lower = project_name.lower()
            for p_key, p_info in projects.items():
                if isinstance(p_info, dict):
                    if (
                        p_key.lower() == target_lower
                        or str(p_info.get("code", "")).lower() == target_lower
                        or str(p_info.get("name", "")).lower() == target_lower
                    ):
                        pipe_path = p_info.get("pipeline_path")
                        if pipe_path and Path(pipe_path).is_file():
                            return Path(pipe_path)
                        elif pipe_path:
                            logger.warning(f"Project '{project_name}' pipeline_path does not exist: {pipe_path}")
                            return None

            logger.info(
                f"No pipeline configuration found in zeroxe_map.yaml for project: '{project_name}'."
            )
            return None

        # 2. If project_name is None, match first configured project with valid pipeline_path (for shot/asset path fallback)
        for p_info in projects.values():
            if isinstance(p_info, dict):
                pipe_path = p_info.get("pipeline_path")
                if pipe_path and Path(pipe_path).is_file():
                    return Path(pipe_path)

        return None

    @classmethod
    def get_pipeline_entrypoint(cls, project_name: Optional[str] = None) -> Optional[Path]:
        """Locate Commands/main.py corresponding to active pipeline on NAS with caching."""
        cls._validate_cache_freshness()

        if project_name in cls._cached_entrypoints:
            return cls._cached_entrypoints[project_name]

        entrypoint = cls._resolve_pipeline_entrypoint(project_name=project_name)
        cls._cached_entrypoints[project_name] = entrypoint
        return entrypoint

    @classmethod
    def _resolve_pipeline_entrypoint(cls, project_name: Optional[str] = None) -> Optional[Path]:
        """Internal uncached resolution of Commands/main.py entrypoint from active pipeline.yaml."""
        pipeline_yaml = cls.get_active_pipeline_yaml_path(project_name=project_name)
        if not pipeline_yaml:
            return None

        pipeline_dir = pipeline_yaml.parent
        # Look for pipeline_dir / Commands / main.py
        cmd_main = pipeline_dir / "Commands" / "main.py"
        if cmd_main.is_file():
            return cmd_main

        # Look for pipeline_dir / main.py
        direct_main = pipeline_dir / "main.py"
        if direct_main.is_file():
            return direct_main

        logger.warning(f"Commands/main.py entrypoint not found in pipeline directory: {pipeline_dir}")
        return None

    @classmethod
    def load_pipeline_module(cls, project_name: Optional[str] = None) -> Optional[Any]:
        """Dynamically load external pipeline main entrypoint via importlib.util with zero-overhead caching."""
        cls._validate_cache_freshness()

        entrypoint = cls.get_pipeline_entrypoint(project_name=project_name)
        if not entrypoint or not entrypoint.is_file():
            map_path = SettingsService.get_zeroxe_map_path() or "Not configured"
            logger.warning(
                f"Pipeline entrypoint not found for project '{project_name}' (zeroxe_map_path: {map_path})."
            )
            return None

        entry_str = str(entrypoint.resolve())
        if entry_str in cls._cached_modules:
            return cls._cached_modules[entry_str]

        try:
            # Ensure pipeline root and commands folder are in sys.path for internal imports
            cmd_dir = entrypoint.parent
            pipe_root = cmd_dir.parent
            for p in [str(pipe_root), str(cmd_dir)]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            module_name = f"zeroxe_external_pipeline_{entrypoint.parent.parent.name}_{entrypoint.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(entrypoint))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                cls._cached_modules[entry_str] = module

                # Cache direct callables for ultra-fast dispatch
                resolve_fn = getattr(module, "resolve_shot_paths", None)
                list_fn = getattr(module, "list_shot_versions", None)
                next_fn = getattr(module, "get_next_shot_version", None)
                if resolve_fn and list_fn and next_fn:
                    cls._cached_resolvers[entry_str] = (resolve_fn, list_fn, next_fn)

                return module
        except Exception as e:
            logger.error(f"Failed to dynamically load pipeline module at {entrypoint}: {e}")

        return None

    @classmethod
    def get_pipeline_handlers(
        cls, project_name: Optional[str] = None
    ) -> Optional[Tuple[Callable, Callable, Callable]]:
        """Retrieve cached function handlers (resolve, list, next) for maximum speed."""
        cls._validate_cache_freshness()

        entrypoint = cls.get_pipeline_entrypoint(project_name=project_name)
        if not entrypoint:
            return None

        entry_str = str(entrypoint.resolve())
        if entry_str in cls._cached_resolvers:
            return cls._cached_resolvers[entry_str]

        module = cls.load_pipeline_module(project_name=project_name)
        if module:
            return cls._cached_resolvers.get(entry_str)
        return None

    @classmethod
    def resolve_shot(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        version_number: int = 1,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> ShotPathResult:
        """Resolve shot master path and version path with optimized handler execution."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        handlers = cls.get_pipeline_handlers(project_name=project_name)

        if handlers:
            resolve_fn, _, _ = handlers
            res = resolve_fn(
                department=department,
                episode=episode,
                sequence=sequence,
                shot=shot,
                version_number=version_number,
                version_folder=version_folder,
                config_path=config_path,
                project_path=project_path,
                extension=extension,
            )
            return ShotPathResult(
                master_path=Path(res.master_path),
                version_path=Path(res.version_path),
                shot_dir=Path(res.shot_dir),
                version_dir=Path(res.version_dir),
                file_name=res.file_name,
                version_file_name=res.version_file_name,
                version_number=res.version_number,
            )

        # Fallback to direct ShotPathGenerator
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator

                gen = ShotPathGenerator(config=config_path)
                res = gen.generate_shot_paths(
                    department=department,
                    episode=episode,
                    sequence=sequence,
                    shot=shot,
                    version_number=version_number,
                    version_folder=version_folder,
                    project_path=project_path,
                    extension=extension,
                )
                return ShotPathResult(
                    master_path=Path(res.master_path),
                    version_path=Path(res.version_path),
                    shot_dir=Path(res.shot_dir),
                    version_dir=Path(res.version_dir),
                    file_name=res.file_name,
                    version_file_name=res.version_file_name,
                    version_number=res.version_number,
                )
            except Exception as e:
                logger.warning(f"Fallback ShotPathGenerator error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    @classmethod
    def list_versions(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> List[Tuple[int, Path]]:
        """List existing version files for a shot with optimized handler execution."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        handlers = cls.get_pipeline_handlers(project_name=project_name)

        if handlers:
            _, list_fn, _ = handlers
            raw_list = list_fn(
                department=department,
                episode=episode,
                sequence=sequence,
                shot=shot,
                version_folder=version_folder,
                config_path=config_path,
                project_path=project_path,
                extension=extension,
            )
            return [(int(v_num), Path(v_p)) for v_num, v_p in raw_list]

        # Fallback to direct ShotPathGenerator
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator

                gen = ShotPathGenerator(config=config_path)
                raw_list = gen.list_existing_versions(
                    department=department,
                    episode=episode,
                    sequence=sequence,
                    shot=shot,
                    version_folder=version_folder,
                    project_path=project_path,
                    extension=extension,
                )
                return [(int(v_num), Path(v_p)) for v_num, v_p in raw_list]
            except Exception as e:
                logger.warning(f"Fallback ShotPathGenerator list error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    @classmethod
    def get_next_version(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> int:
        """Get the next version number for a shot with optimized handler execution."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        handlers = cls.get_pipeline_handlers(project_name=project_name)

        if handlers:
            _, _, next_fn = handlers
            return int(
                next_fn(
                    department=department,
                    episode=episode,
                    sequence=sequence,
                    shot=shot,
                    version_folder=version_folder,
                    config_path=config_path,
                    project_path=project_path,
                    extension=extension,
                )
            )

        # Fallback to direct ShotPathGenerator
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator

                gen = ShotPathGenerator(config=config_path)
                return int(
                    gen.get_next_version_number(
                        department=department,
                        episode=episode,
                        sequence=sequence,
                        shot=shot,
                        version_folder=version_folder,
                        project_path=project_path,
                        extension=extension,
                    )
                )
            except Exception as e:
                logger.warning(f"Fallback ShotPathGenerator get_next error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    # --------------------------------------------------------------------------
    # Asset Path Resolution
    # --------------------------------------------------------------------------
    @classmethod
    def resolve_asset(
        cls,
        asset_type: str,
        asset_name: str,
        department: str = "",
        version_number: int = 1,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> AssetPathResult:
        """Resolve asset master path and version path from pipeline.yaml."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)

        # 1. Try external module if available
        module = cls.load_pipeline_module(project_name=project_name)
        if module and hasattr(module, "resolve_asset_paths"):
            try:
                res = module.resolve_asset_paths(
                    asset_type=asset_type,
                    asset_name=asset_name,
                    department=department,
                    version_number=version_number,
                    version_folder=version_folder,
                    config_path=config_path,
                    project_path=project_path,
                    extension=extension,
                )
                return AssetPathResult(
                    master_path=Path(res.master_path),
                    version_path=Path(res.version_path),
                    asset_dir=Path(res.asset_dir),
                    version_dir=Path(res.version_dir),
                    file_name=res.file_name,
                    version_file_name=res.version_file_name,
                    version_number=res.version_number,
                )
            except Exception as e:
                logger.warning(f"External module resolve_asset_paths failed: {e}")

        # 2. Built-in AssetPathGenerator fallback
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.asset_path_generator import AssetPathGenerator

                gen = AssetPathGenerator(config=config_path)
                res = gen.generate_asset_paths(
                    asset_type=asset_type,
                    asset_name=asset_name,
                    department=department,
                    version_number=version_number,
                    version_folder=version_folder,
                    project_path=project_path,
                    extension=extension,
                )
                return AssetPathResult(
                    master_path=Path(res.master_path),
                    version_path=Path(res.version_path),
                    asset_dir=Path(res.asset_dir),
                    version_dir=Path(res.version_dir),
                    file_name=res.file_name,
                    version_file_name=res.version_file_name,
                    version_number=res.version_number,
                )
            except Exception as e:
                logger.error(f"AssetPathGenerator fallback error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    @classmethod
    def list_asset_versions(
        cls,
        asset_type: str,
        asset_name: str,
        department: str = "",
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> List[Tuple[int, Path]]:
        """List existing version files for an asset."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)

        # 1. Try external module if available
        module = cls.load_pipeline_module(project_name=project_name)
        if module and hasattr(module, "list_asset_versions"):
            try:
                raw_list = module.list_asset_versions(
                    asset_type=asset_type,
                    asset_name=asset_name,
                    department=department,
                    version_folder=version_folder,
                    config_path=config_path,
                    project_path=project_path,
                    extension=extension,
                )
                return [(int(v_num), Path(v_p)) for v_num, v_p in raw_list]
            except Exception as e:
                logger.warning(f"External module list_asset_versions failed: {e}")

        # 2. Built-in AssetPathGenerator fallback
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.asset_path_generator import AssetPathGenerator

                gen = AssetPathGenerator(config=config_path)
                raw_list = gen.list_existing_versions(
                    asset_type=asset_type,
                    asset_name=asset_name,
                    department=department,
                    version_folder=version_folder,
                    project_path=project_path,
                    extension=extension,
                )
                return [(int(v_num), Path(v_p)) for v_num, v_p in raw_list]
            except Exception as e:
                logger.error(f"AssetPathGenerator list fallback error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    @classmethod
    def get_next_asset_version(
        cls,
        asset_type: str,
        asset_name: str,
        department: str = "",
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> int:
        """Get the next version number for an asset."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)

        # 1. Try external module if available
        module = cls.load_pipeline_module(project_name=project_name)
        if module and hasattr(module, "get_next_asset_version"):
            try:
                return int(
                    module.get_next_asset_version(
                        asset_type=asset_type,
                        asset_name=asset_name,
                        department=department,
                        version_folder=version_folder,
                        config_path=config_path,
                        project_path=project_path,
                        extension=extension,
                    )
                )
            except Exception as e:
                logger.warning(f"External module get_next_asset_version failed: {e}")

        # 2. Built-in AssetPathGenerator fallback
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Paths.asset_path_generator import AssetPathGenerator

                gen = AssetPathGenerator(config=config_path)
                return int(
                    gen.get_next_version_number(
                        asset_type=asset_type,
                        asset_name=asset_name,
                        department=department,
                        version_folder=version_folder,
                        project_path=project_path,
                        extension=extension,
                    )
                )
            except Exception as e:
                logger.error(f"AssetPathGenerator get_next fallback error: {e}")

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)

    # --------------------------------------------------------------------------
    # Versioning and Up Version / Up Master DCC Automation
    # --------------------------------------------------------------------------
    @classmethod
    def get_department_script(
        cls,
        department: str,
        script_key: str = "up_master",
        project_name: Optional[str] = None,
    ) -> Optional[str]:
        """Look up configured script preset path for a department in pipeline.yaml."""
        pipe_yaml = cls.get_active_pipeline_yaml_path(project_name=project_name)
        if not pipe_yaml or not pipe_yaml.is_file():
            return None

        try:
            with open(pipe_yaml, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            departments = cfg.get("departments", {})
            dept_info = departments.get(department)
            if not dept_info:
                # Case-insensitive / code lookup
                for d_name, d_val in departments.items():
                    if isinstance(d_val, dict):
                        if (
                            d_name.lower() == department.lower()
                            or d_val.get("code", "").lower() == department.lower()
                        ):
                            dept_info = d_val
                            break

            if not dept_info or not isinstance(dept_info, dict):
                return None

            scripts = dept_info.get("scripts", {})
            if not scripts or not isinstance(scripts, dict):
                return None

            raw_path = scripts.get(script_key)
            if not raw_path:
                return None

            # Resolve project mount path
            global_cfg = cfg.get("global", {})
            mounts = global_cfg.get("mounts", {})
            if sys.platform.startswith("linux"):
                proj_root = mounts.get("linux", "")
            elif sys.platform.startswith("win32"):
                proj_root = mounts.get("windows", "")
            elif sys.platform.startswith("darwin"):
                proj_root = mounts.get("darwin", "")
            else:
                proj_root = mounts.get("linux", "")

            resolved_path = raw_path.replace("@project_path@", proj_root.rstrip("/\\"))
            return resolved_path
        except Exception as e:
            logger.warning(f"Failed to read department script from {pipe_yaml}: {e}")
            return None

    @classmethod
    def execute_blender_script(
        cls,
        script: str,
        blender_path: Optional[str] = None,
        timeout: int = 180,
    ) -> Tuple[bool, str]:
        """Execute a Python script in background headless Blender instance.

        Returns (success: bool, output_log: str).
        """
        active_blender = blender_path or SettingsService.get_active_blender()
        if not active_blender or not Path(active_blender).is_file():
            return False, "Blender executable path is not configured or does not exist."

        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(script)
                tmp_file = Path(f.name)

            proc = subprocess.run(
                [active_blender, "-b", "--python", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            success = (proc.returncode == 0)
            if "Traceback (most recent call last):" in output or "Error: Python:" in output:
                success = False
            return success, output
        except subprocess.TimeoutExpired:
            return False, f"Blender execution timed out after {timeout} seconds."
        except Exception as e:
            return False, f"Failed to execute Blender script: {e}"
        finally:
            if tmp_file and tmp_file.is_file():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass

    @classmethod
    def list_features(
        cls,
        department: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> List[str]:
        """Dynamically query all available features for the project from external pipeline."""
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        if not config_path:
            return []

        module = cls.load_pipeline_module(project_name=project_name)

        if module and hasattr(module, "list_features"):
            try:
                features = module.list_features(department=department, config_path=config_path)
                if features:
                    return list(features)
            except Exception as e:
                logger.warning(f"External module list_features failed: {e}")

        if module and hasattr(module, "list_available_features"):
            try:
                features = module.list_available_features(department=department, config_path=config_path)
                if features:
                    return list(features)
            except Exception as e:
                logger.warning(f"External module list_available_features failed: {e}")

        return []

    @classmethod
    def execute_feature(
        cls,
        feature_name: str,
        filepath: str,
        department: Optional[str] = None,
        project_name: Optional[str] = None,
        setting_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Tuple[bool, str, Optional[str]]:
        """Send feature execution request directly to the external pipeline loaded via zeroxe_map.yaml.

        Returns (success: bool, message: str, target_path: Optional[str]).
        """
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        module = cls.load_pipeline_module(project_name=project_name)

        if not module:
            err = cls._get_pipeline_error_reason(project_name=project_name)
            return False, f"External pipeline module not loaded: {err}", None

        result = None
        if hasattr(module, "run_pipeline_feature"):
            try:
                result = module.run_pipeline_feature(
                    feature_name=feature_name,
                    filepath=filepath,
                    department=department,
                    config_path=config_path,
                    setting_data=setting_data,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(f"External module run_pipeline_feature error: {e}")

        if result is None and hasattr(module, "execute_feature"):
            try:
                result = module.execute_feature(
                    feature_name=feature_name,
                    filepath=filepath,
                    department=department,
                    config_path=config_path,
                    setting_data=setting_data,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(f"External module execute_feature error: {e}")

        if result is None:
            return False, f"Feature '{feature_name}' could not be executed by the external pipeline.", None

        script = getattr(result, "script", None) if hasattr(result, "script") else (result.get("script") if isinstance(result, dict) else None)
        target_path = getattr(result, "target_path", None) if hasattr(result, "target_path") else (result.get("target_path") if isinstance(result, dict) else None)
        is_success = getattr(result, "success", True) if hasattr(result, "success") else (result.get("success", True) if isinstance(result, dict) else True)
        msg = getattr(result, "message", "") if hasattr(result, "message") else (result.get("message", "") if isinstance(result, dict) else "")

        if not is_success:
            return False, msg or f"Pipeline feature '{feature_name}' returned failure.", target_path

        # If pipeline generated a DCC script, execute it headlessly via Blender if available
        if script:
            if target_path:
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            final_p = getattr(result, "data", {}).get("final_path") if hasattr(result, "data") else None
            if final_p:
                Path(final_p).parent.mkdir(parents=True, exist_ok=True)

            active_blender = SettingsService.get_active_blender()
            if not active_blender or not Path(active_blender).is_file():
                return True, msg or f"Script generated successfully for '{feature_name}'", target_path

            dcc_success, dcc_output = cls.execute_blender_script(script)
            if not dcc_success:
                return False, f"Blender execution error:\n\n{dcc_output}", target_path

            # Verify that the target file exists on disk
            if target_path and not Path(target_path).is_file():
                return False, f"Blender completed but target file was not created:\n{target_path}\n\nBlender Log:\n{dcc_output}", target_path

            return True, msg or f"Successfully executed '{feature_name}'", target_path

        # If feature was executed completely within pipeline
        return is_success, msg or f"Successfully executed '{feature_name}'", target_path

    @classmethod
    def prompt_batch_parameters(
        cls,
        department: str,
        action: str,
        selected_items: List[Any],
        parent: Optional[Any] = None,
        project_name: Optional[str] = None,
        available_shots: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Prompt for department-specific batch parameters (e.g. FG YAML, Comp Mastershot) or confirmation.

        Returns:
            Dict[str, Any] of extra kwargs to pass to execute_feature, or None if the user cancelled.
        """
        config_path = cls.get_active_pipeline_yaml_path(project_name=project_name)
        try:
            from pipeline.Commands.Builders.builder_factory import BuilderFactory
            return BuilderFactory.prompt_batch_parameters(
                department=department,
                action=action,
                selected_items=selected_items,
                parent=parent,
                project_name=project_name,
                config_path=config_path,
                available_shots=available_shots,
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"Error in prompt_batch_parameters: {e}")
            return {}



