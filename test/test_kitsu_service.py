import os
from pathlib import Path
import gazu

from zeroxe.api.gazu_client import init_kitsu
from zeroxe.services import asset_service
from zeroxe.services.project_service import ProjectService
from zeroxe.services.department_service import DepartmentService
from zeroxe.services.shot_service import ShotService
from zeroxe.services.asset_service import AssetService

# Auto-load .env file from project root if it exists
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        with open(_env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

PRINTOUT = True

kitsu_host = os.getenv("KITSU_HOST", "http://localhost:8080/api")
kitsu_email = os.getenv("KITSU_EMAIL", "user@example.com")
kitsu_password = os.getenv("KITSU_PASSWORD", "password")

gazu.set_host(kitsu_host)
gazu.log_in(kitsu_email, kitsu_password)

project_service = ProjectService()
department_service = DepartmentService()
shot_service = ShotService()
asset_service = AssetService()

# Project
def test_get_all_projects() -> None:
    projects = project_service.get_all_projects()
    if PRINTOUT:
        print(projects)

def test_get_project_by_id() -> None:
    project = project_service.get_project_by_id("be1f0090-4796-406a-a4f6-c2341e9d85bd")
    if PRINTOUT:
        print(project)

# Department
def test_get_departments() -> None:
    departments = department_service.get_all_departments()
    if PRINTOUT:
        print(departments)

def test_get_department_by_id() -> None:
    department = department_service.get_department_by_id("54958da3-33d0-404d-a6e8-d4a58b9a0137")
    if PRINTOUT:
        print(department)

def test_get_department_by_name() -> None:
    department = department_service.get_department_by_name("Layout")
    if PRINTOUT:
        print(department)

# Shot
def test_get_episodes_by_project_id() -> None:
    episodes = shot_service.get_episodes_by_project_id("0f029a6d-603e-4d6d-8217-902e2e32f274")
    if PRINTOUT:
        print(episodes)

def test_get_sequences_by_episode_id() -> None:
    sequences = shot_service.get_sequences_by_episode_id("6f577fed-48fa-488d-9aba-bd6ccb4fd2e7")
    if PRINTOUT:
        print(sequences)

def test_get_shots_by_episode_id() -> None:
    shots = shot_service.get_shots_by_episode_id("6f577fed-48fa-488d-9aba-bd6ccb4fd2e7")
    if PRINTOUT:
        print(shots)

def test_get_assets_for_shot() -> None:
    assets = gazu.asset.all_assets_for_shot("cdd16d87-0608-4b8b-b05c-8d4e570a90c5")
    if PRINTOUT:
        print(assets)

# Asset
def test_get_assets_by_project_id() -> None:
    assets = asset_service.get_assets_by_project_id("0f029a6d-603e-4d6d-8217-902e2e32f274")
    if PRINTOUT:
        print(assets)

def test_get_asset_types_by_project_id() -> None:
    asset_types = asset_service.get_asset_types_by_project_id("0f029a6d-603e-4d6d-8217-902e2e32f274")
    if PRINTOUT:
        print(asset_types)