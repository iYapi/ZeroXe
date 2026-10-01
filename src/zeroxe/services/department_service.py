"""Department Service.

Fetches department data from Kitsu via Gazu and maps to Department domain models.
"""

import logging
from typing import List, Optional
import gazu
from zeroxe.models.department_model import Department

logger = logging.getLogger(__name__)


class DepartmentService:
    @staticmethod
    def get_all_departments() -> List[Department]:
        """Fetch all departments from Kitsu and map to department model objects."""
        try:
            raw_departments = gazu.person.all_departments() or []
            return [
                Department.from_kitsu(p)
                for p in raw_departments
                if isinstance(p, dict) or hasattr(p, "get")
            ]
        except Exception as e:
            logger.error(f"Failed to fetch departments: {e}")
            return []

    @staticmethod
    def get_department_by_id(department_id: str) -> Optional[Department]:
        """Fetch a single department by its ID."""
        try:
            raw_department = gazu.person.get_department(department_id)
            if raw_department:
                return Department.from_kitsu(raw_department)
        except Exception as e:
            logger.error(f"Failed to fetch department by id {department_id}: {e}")
        return None

    @staticmethod
    def get_department_by_name(department_name: str) -> Optional[Department]:
        """Fetch a single department by its name."""
        try:
            raw_department = gazu.person.get_department_by_name(department_name)
            if raw_department:
                return Department.from_kitsu(raw_department)
        except Exception as e:
            logger.error(f"Failed to fetch department by name {department_name}: {e}")
        return None