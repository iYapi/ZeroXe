import os
import sys
from pathlib import Path

# Application Metadata
APP_NAME = "Zeroxe"
APP_VERSION = "1.0.0"
ORGANIZATION_NAME = "ZeroxeOrg"
ORGANIZATION_DOMAIN = "zeroxe.org"
MAINTAINER = "iYapi"
MAINTAINER_WEB = "https://yapi.expiproject.com"

# Update Server Configuration
UPDATE_MANIFEST_URL = "https://github.com/iYapi/ZeroXe/blob/remake/version.json"

# Dynamic Path Resolution
def get_base_dir() -> Path:
    """Returns the base directory of the project/bundle."""
    if getattr(sys, "frozen", False):  # Bundled with PyInstaller
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


def get_user_data_dir() -> Path:
    """Returns a writable directory for user scripts and logs across OS platforms."""
    home = Path.home()
    if sys.platform.startswith("linux"):
        data_dir = home / ".local" / "share" / APP_NAME.lower()
    elif sys.platform == "darwin":
        data_dir = home / "Library" / "Application Support" / APP_NAME
    else:
        data_dir = Path(os.getenv("APPDATA", home)) / APP_NAME

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# Paths for Editable Logic & Bundled Assets
BASE_DIR = get_base_dir()
USER_DATA_DIR = get_user_data_dir()

SCRIPTS_DIR = USER_DATA_DIR / "scripts"
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_SCRIPT_PATH = SCRIPTS_DIR / "active_task.py"

ASSETS_DIR = BASE_DIR / "assets"