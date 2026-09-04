import os
from zeroxe import config
from zeroxe.services.update_service import UpdateService

class UpdateAPI:
    @staticmethod
    def check_for_updates() -> tuple[bool, dict]:
        """
        Checks if an update is available.
        Returns: (has_update: bool, manifest_data: dict)
        """
        manifest = UpdateService.get_remote_manifest(config.UPDATE_MANIFEST_URL)
        remote_ver = manifest.get("version", "0.0.0")
        has_update = UpdateService.is_newer_version(remote_ver, config.APP_VERSION)
        return has_update, manifest

    @staticmethod
    def download_update(download_url: str, target_path: str, progress_callback=None) -> str:
        """Downloads the binary to target_path with a progress callback(percent: int)."""
        UpdateService.download_file(download_url, target_path, progress_callback)
        return target_path

    @staticmethod
    def verify_integrity(file_path: str, expected_sha256: str) -> bool:
        """Returns True if the file hash matches."""
        return UpdateService.verify_sha256(file_path, expected_sha256)

    @staticmethod
    def install_and_restart(file_path: str) -> None:
        """Replaces the running executable and restarts."""
        UpdateService.replace_and_restart(file_path)