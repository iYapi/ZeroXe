"""Project Service.

Fetches project data from Kitsu via Gazu and maps to Project domain models.
"""

import logging
from typing import List, Optional
import gazu
from zeroxe.models.project_model import Project

logger = logging.getLogger(__name__)


class ProjectService:
    @staticmethod
    def get_all_projects() -> List[Project]:
        """Fetch all projects from Kitsu and map to Project model objects."""
        try:
            raw_projects = gazu.project.all_projects() or []
            return [
                Project.from_kitsu(p)
                for p in raw_projects
                if isinstance(p, dict) or hasattr(p, "get")
            ]
        except Exception as e:
            logger.error(f"Failed to fetch projects: {e}")
            return []

    @staticmethod
    def get_open_projects() -> List[Project]:
        """Fetch all open/active projects from Kitsu and map to Project model objects."""
        try:
            raw_projects = gazu.project.all_open_projects() or []
            return [
                Project.from_kitsu(p)
                for p in raw_projects
                if isinstance(p, dict) or hasattr(p, "get")
            ]
        except Exception as e:
            logger.error(f"Failed to fetch open projects: {e}")
            return []

    @staticmethod
    def get_project_by_id(project_id: str) -> Optional[Project]:
        """Fetch a single project by its ID."""
        try:
            raw_project = gazu.project.get_project(project_id)
            if raw_project:
                return Project.from_kitsu(raw_project)
        except Exception as e:
            logger.error(f"Failed to fetch project by id {project_id}: {e}")
        return None