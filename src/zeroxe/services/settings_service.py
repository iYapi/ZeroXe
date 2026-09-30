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
