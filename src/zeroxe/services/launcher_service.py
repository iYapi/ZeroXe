"""Mock Data Service for Launcher Prototype.

Pure Python logic & data processing with zero Qt dependency.
Easy to replace with Gazu / SQLite / REST API in production.
"""

from typing import Any, Dict, List, Optional


class LauncherService:
    # ---------------------------------------------------------
    # Mock Data Store
    # ---------------------------------------------------------
    MOCK_PROJECTS = [
        {"id": "proj-01", "name": "Orion", "code": "CPK"},
        {"id": "proj-02", "name": "Oregon", "code": "SSF"},
        {"id": "proj-03", "name": "Olaf", "code": "ATC"},
    ]

    MOCK_DEPARTMENTS = ["concept", "modeling", "rigging", "animation", "fx", "lighting", "comp"]

    MOCK_CATEGORIES = {
        "Shot": ["All", "ep101", "ep102", "ep103"],
        "Asset": ["All", "char", "prop", "set", "vhc"],
    }

    MOCK_ITEMS = {
        "proj-01": {
            "Shot": [
                {"id": "s101", "name": "sq01_sh0010", "type": "Shot", "category": "ep101", "status": "WIP"},
                {"id": "s102", "name": "sq01_sh0020", "type": "Shot", "category": "ep101", "status": "Review"},
                {"id": "s103", "name": "sq01_sh0030", "type": "Shot", "category": "ep102", "status": "Approved"},
                {"id": "s104", "name": "sq01_sh0030", "type": "Shot", "category": "ep103", "status": "WIP"},
            ],
            "Asset": [
                {"id": "a101", "name": "c-char01", "type": "Asset", "category": "char", "status": "WIP"},
                {"id": "a102", "name": "c-hero_female", "type": "Asset", "category": "char", "status": "Approved"},
                {"id": "a103", "name": "p-laser_gun", "type": "Asset", "category": "prop", "status": "Ready"},
                {"id": "a104", "name": "p-holo_phone", "type": "Asset", "category": "prop", "status": "WIP"},
                {"id": "a105", "name": "s-cyber_alley", "type": "Asset", "category": "set", "status": "WIP"},
                {"id": "a106", "name": "v-flying_car", "type": "Asset", "category": "vhc", "status": "Approved"},
            ],
        },
        "proj-02": {
            "Shot": [
                {"id": "s201", "name": "sq01_sh0010", "type": "Shot", "category": "ep101", "status": "WIP"},
                {"id": "s202", "name": "sq01_sh0020", "type": "Shot", "category": "ep101", "status": "WIP"},
                {"id": "s203", "name": "sq01_sh0030", "type": "Shot", "category": "ep102", "status": "Review"},
            ],
            "Asset": [
                {"id": "a201", "name": "c-astronaut", "type": "Asset", "category": "char", "status": "Review"},
                {"id": "a202", "name": "c-alien_creature", "type": "Asset", "category": "char", "status": "WIP"},
                {"id": "a203", "name": "p-scanner_device", "type": "Asset", "category": "prop", "status": "Ready"},
                {"id": "a204", "name": "s-command_deck", "type": "Asset", "category": "set", "status": "Approved"},
                {"id": "a205", "name": "v-mothership", "type": "Asset", "category": "vhc", "status": "Approved"},
            ],
        },
        "proj-03": {
            "Shot": [
                {"id": "s301", "name": "sq01_sh0010", "type": "Shot", "category": "ep101", "status": "Approved"},
                {"id": "s302", "name": "sq01_sh0020", "type": "Shot", "category": "ep101", "status": "WIP"},
            ],
            "Asset": [
                {"id": "a301", "name": "v-supercar_body", "type": "Asset", "category": "vhc", "status": "Approved"},
                {"id": "a302", "name": "v-wheel_rim", "type": "Asset", "category": "vhc", "status": "Approved"},
                {"id": "a303", "name": "p-fuel_nozzle", "type": "Asset", "category": "prop", "status": "Approved"},
                {"id": "a304", "name": "s-race_track", "type": "Asset", "category": "set", "status": "Approved"},
            ],
        },
    }

    MOCK_VERSIONS = {
        "s101": ["Master", "v001", "v002", "v003"],
        "s102": ["Master", "v001", "v002"],
        "s103": ["Master", "v001"],
        "s104": ["Master", "v001"],
        "a101": ["Master", "v001", "v002", "v003", "v004"],
        "a102": ["Master", "v001", "v002"],
        "a103": ["Master", "v001"],
        "a104": ["Master", "v001"],
        "a105": ["Master", "v001", "v002"],
        "a106": ["Master", "v001", "v002"],
        "a107": ["Master", "v001"],
    }

    MOCK_FEATURES = [
        "Generate",
        "Generate (from previous)",
        "Generate (from next)",
        "Up Master",
        "Up Version",
    ]

    # ---------------------------------------------------------
    # Data Processing / Fetch Methods
    # ---------------------------------------------------------
    @classmethod
    def get_projects(cls) -> List[Dict[str, Any]]:
        """Return list of available projects."""
        return cls.MOCK_PROJECTS

    @classmethod
    def get_departments(cls, project_id: str) -> List[str]:
        """Return departments available for project."""
        return cls.MOCK_DEPARTMENTS

    @classmethod
    def get_categories(cls, item_type: str) -> List[str]:
        """Return category options based on type (Episode list for Shots, Asset types for Assets)."""
        return cls.MOCK_CATEGORIES.get(item_type, ["All"])

    @classmethod
    def get_items(
        cls, project_id: str, item_type: str, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return shots or assets for the specified project and optional category."""
        project_data = cls.MOCK_ITEMS.get(project_id, {})
        items = project_data.get(item_type, [])

        if category and category != "All":
            items = [item for item in items if item.get("category") == category]

        return items

    @classmethod
    def get_versions(cls, item_id: str) -> List[str]:
        """Return versions for the selected item."""
        return cls.MOCK_VERSIONS.get(item_id, ["Master", "v001"])

    @classmethod
    def get_applications(cls) -> List[str]:
        """Return available DCC action features."""
        return cls.MOCK_FEATURES

    @classmethod
    def get_metadata(cls, item_data: Dict[str, Any], version: str, dept: str) -> Dict[str, str]:
        """Process and format metadata table for display."""
        return {
            "Item Name": item_data.get("name", "N/A"),
            "Item Type": item_data.get("type", "N/A"),
            "Category": item_data.get("category", "N/A"),
            "Department": dept or "General",
            "Version": version or "Master",
            "Status": item_data.get("status", "WIP"),
            "Author": "iyapi",
            "Resolution": "1920x1080 (HD)",
            "Frame Range": "1001-1120 (120 frames)",
            "Path": f"/projects/production/{item_data.get('name', '')}/{version}",
        }

    @classmethod
    def execute_action(cls, app_name: str, item_name: str, version: str) -> str:
        """Simulate launching or executing an application action."""
        msg = f"[Launcher] Executing '{app_name}' on '{item_name}' ({version})..."
        print(msg)
        return msg
