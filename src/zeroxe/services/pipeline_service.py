"""Pipeline Service.

Bridges the ZeroXe desktop application (controllers and views)
with the pipeline path resolution and command modules.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pipeline.Commands.main import (
    DEFAULT_PIPELINE_YAML,
    ShotPathResult,
    get_next_shot_version,
    list_shot_versions,
    resolve_shot_paths,
)
from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class PipelineService:
    """Service for resolving pipeline paths and executing pipeline commands."""

    @staticmethod
    def get_active_pipeline_yaml_path() -> Path:
        """Resolve active pipeline.yaml path from NAS zeroxe_map or default project pipeline."""
        # 1. Try resolving via zeroxe_map.yaml in NAS setting
        zeroxe_map = SettingsService.get_zeroxe_map()
        if zeroxe_map:
            projects = zeroxe_map.get("project", {})
            for p_info in projects.values():
                if isinstance(p_info, dict):
                    pipe_path = p_info.get("pipeline_path")
                    if pipe_path and Path(pipe_path).is_file():
                        return Path(pipe_path)

        # 2. Fallback to local replicated pipeline.yaml
        if DEFAULT_PIPELINE_YAML.is_file():
            return DEFAULT_PIPELINE_YAML

        # 3. Fallback to workspace root pipeline/pipeline.yaml
        root_pipe = Path(__file__).resolve().parent.parent.parent.parent / "pipeline" / "pipeline.yaml"
        if root_pipe.is_file():
            return root_pipe

        return DEFAULT_PIPELINE_YAML

    @classmethod
    def resolve_shot(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        version_number: int = 1,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> ShotPathResult:
        """Resolve shot master path and version path using current NAS version folder setting."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path()

        return resolve_shot_paths(
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

    @classmethod
    def list_versions(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> List[Tuple[int, Path]]:
        """List existing version files for a shot."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path()

        return list_shot_versions(
            department=department,
            episode=episode,
            sequence=sequence,
            shot=shot,
            version_folder=version_folder,
            config_path=config_path,
            project_path=project_path,
            extension=extension,
        )

    @classmethod
    def get_next_version(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        project_path: Optional[str] = None,
        extension: str = ".blend",
    ) -> int:
        """Get the next version number for a shot."""
        version_folder = SettingsService.get_version_folder() or "progress"
        config_path = cls.get_active_pipeline_yaml_path()

        return get_next_shot_version(
            department=department,
            episode=episode,
            sequence=sequence,
            shot=shot,
            version_folder=version_folder,
            config_path=config_path,
            project_path=project_path,
            extension=extension,
        )
