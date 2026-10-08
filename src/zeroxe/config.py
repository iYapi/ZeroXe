import datetime
import json
import os
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Returns the base directory of the project/bundle."""
    if getattr(sys, "frozen", False):  # Bundled with PyInstaller
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


def get_app_version() -> str:
    """Returns application version based on compile/build date (YY.MM.DD)."""
    base_dir = get_base_dir()

    # 1. Check embedded build_info.json in bundle/project
    build_info_file = base_dir / "build_info.json"
    if build_info_file.is_file():
        try:
            data = json.loads(build_info_file.read_text(encoding="utf-8"))
            ver = data.get("version")
            if ver:
                return str(ver).strip()
        except Exception:
            pass

    # 2. In frozen binary, check binary executable mtime as compile date
    if getattr(sys, "frozen", False):
        try:
            exe_mtime = os.path.getmtime(sys.executable)
            dt = datetime.datetime.fromtimestamp(exe_mtime)
            return dt.strftime("%y.%m.%d")
        except Exception:
            pass

    # 3. Development runtime: format current date as YY.MM.DD
    return datetime.datetime.now().strftime("%y.%m.%d")


# Application Metadata
APP_NAME = "Zeroxe"
APP_VERSION = get_app_version()
ORGANIZATION_NAME = "ZeroxeOrg"
ORGANIZATION_DOMAIN = "zeroxe.org"
MAINTAINER = "iYapi"
MAINTAINER_WEB = "https://yapi.expiproject.com"

# Update Server Configuration
UPDATE_MANIFEST_URL = "https://github.com/iYapi/ZeroXe/blob/remake/version.json"


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
KITSU_API_URL = ""