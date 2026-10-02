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
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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

        # 1. Match specifically requested project if provided
        if project_name:
            if project_name in projects and isinstance(projects[project_name], dict):
                pipe_path = projects[project_name].get("pipeline_path")
                if pipe_path and Path(pipe_path).is_file():
                    return Path(pipe_path)

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

        # 2. Match first configured project with valid pipeline_path
        for p_info in projects.values():
            if isinstance(p_info, dict):
                pipe_path = p_info.get("pipeline_path")
                if pipe_path and Path(pipe_path).is_file():
                    return Path(pipe_path)

        logger.warning(
            f"No valid pipeline_path found in zeroxe_map.yaml for project: '{project_name}'."
        )
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

        reason = cls._get_pipeline_error_reason(project_name=project_name)
        raise FileNotFoundError(reason)
