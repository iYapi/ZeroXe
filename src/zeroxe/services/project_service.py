"""Project Service.

Fetches project data from Kitsu via Gazu and maps to Project domain models.
"""

from typing import List, Optional
import gazu
from zeroxe.models.project_model import Project


class ProjectService:
    @staticmethod
    def get_all_projects() -> List[Project]:
        """Fetch all projects from Kitsu and map to Project model objects."""
        raw_projects = gazu.project.all_projects()
        return [Project.from_kitsu(p) for p in raw_projects]

    @staticmethod
    def get_open_projects() -> List[Project]:
        """Fetch all open/active projects from Kitsu and map to Project model objects."""
        raw_projects = gazu.project.all_open_projects()
        return [Project.from_kitsu(p) for p in raw_projects]

    @staticmethod
    def get_project_by_id(project_id: str) -> Optional[Project]:
        """Fetch a single project by its ID."""
        raw_project = gazu.project.get_project(project_id)
        if raw_project:
            return Project.from_kitsu(raw_project)
        return None