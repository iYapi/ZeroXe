"""Settings Service.

Provides centralized, strongly typed access to user configuration and decrypted credentials.
"""

from typing import List
from PySide6.QtCore import QSettings
from zeroxe import config
from zeroxe.utils.security import decrypt_string


class SettingsService:
    @classmethod
    def _settings(cls) -> QSettings:
        return QSettings(config.ORGANIZATION_NAME, config.APP_NAME)

    # ------------------------------------------------------------------
    # Kitsu Configuration & Credentials
    # ------------------------------------------------------------------
    @classmethod
    def get_kitsu_url(cls) -> str:
        return cls._settings().value("kitsu/url", config.KITSU_API_URL, type=str)

    @classmethod
    def get_kitsu_email(cls) -> str:
        return cls._settings().value("kitsu/email", "", type=str)

    @classmethod
    def get_kitsu_password(cls) -> str:
        """Retrieve and decrypt stored Kitsu password."""
        encrypted_pwd = cls._settings().value("kitsu/password_enc", "", type=str)
        return decrypt_string(encrypted_pwd)

    @classmethod
    def get_kitsu_notification_enabled(cls) -> bool:
        """Check if Kitsu OS desktop notifications are enabled."""
        val = cls._settings().value("kitsu/notification_enabled", True)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    @classmethod
    def set_kitsu_notification_enabled(cls, enabled: bool) -> None:
        """Persist whether Kitsu OS notifications should be active."""
        cls._settings().setValue("kitsu/notification_enabled", bool(enabled))
        cls._settings().sync()

    # ------------------------------------------------------------------
    # Software Configuration
    # ------------------------------------------------------------------
    @classmethod
    def get_active_blender(cls) -> str:
        return cls._settings().value("software/active_blender", "", type=str)

    @classmethod
    def get_blender_paths(cls) -> List[str]:
        return cls._settings().value("software/blender_paths", [], type=list)

    @classmethod
    def get_pureref_path(cls) -> str:
        return cls._settings().value("software/pureref_path", "", type=str)

    # ------------------------------------------------------------------
    # NAS Configuration
    # ------------------------------------------------------------------
    @classmethod
    def get_zeroxe_map_path(cls) -> str:
        from pathlib import Path

        if cls._settings().contains("nas/zeroxe_map_path"):
            return cls._settings().value("nas/zeroxe_map_path", "", type=str)

        # Default fallback to standard NAS or local workspace zeroxe_map.yaml if not configured
        if Path("/mnt/I/zeroxe_map.yaml").is_file():
            return "/mnt/I/zeroxe_map.yaml"
        if Path("zeroxe_map.yaml").is_file():
            return str(Path("zeroxe_map.yaml").resolve())

        return ""

    @classmethod
    def set_zeroxe_map_path(cls, path: str) -> None:
        cls._settings().setValue("nas/zeroxe_map_path", path)
        cls._settings().sync()



    @classmethod
    def get_version_folder(cls) -> str:
        return cls._settings().value("nas/version_folder", "progress", type=str)

    @classmethod
    def set_version_folder(cls, folder: str) -> None:
        cls._settings().setValue("nas/version_folder", folder)
        cls._settings().sync()

    @classmethod
    def get_zeroxe_map(cls) -> dict:
        """Load and parse the YAML file from zeroxe_map_path."""
        map_path = cls.get_zeroxe_map_path()
        if not map_path:
            return {}
        try:
            import yaml
            from pathlib import Path

            path = Path(map_path)
            if path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Failed to load zeroxe map from {map_path}: {e}")
        return {}

