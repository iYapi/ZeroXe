"""Department Service.

Fetches department data from Kitsu via Gazu and maps to Department domain models.
"""

from typing import List, Optional
import gazu
from zeroxe.models.department_model import Department


class DepartmentService:
    @staticmethod
    def get_all_departments() -> List[Department]:
        """Fetch all departments from Kitsu and map to department model objects."""
        raw_departments = gazu.person.all_departments()
        return [Department.from_kitsu(p) for p in raw_departments]

    @staticmethod
    def get_department_by_id(department_id: str) -> Optional[Department]:
        """Fetch a single department by its ID."""
        raw_department = gazu.person.get_department(department_id)
        if raw_department:
            return Department.from_kitsu(raw_department)
        return None

    @staticmethod
    def get_department_by_name(department_name: str) -> Optional[Department]:
        """Fetch a single department by its name."""
        raw_department = gazu.person.get_department_by_name(department_name)
        if raw_department:
            return Department.from_kitsu(raw_department)
        return None