import os
import sys
import json
import hashlib
import urllib.request
from packaging import version
from zeroxe import config

class UpdateService:
    @staticmethod
    def get_remote_manifest(url: str, timeout: int = 5) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "ZeroxeUpdater/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def is_newer_version(remote_version: str, current_version: str) -> bool:
        return version.parse(remote_version) > version.parse(current_version)

    @staticmethod
    def download_file(url: str, target_path: str, progress_callback=None) -> None:
        def reporthook(block_num, block_size, total_size):
            if progress_callback and total_size > 0:
                percent = int((block_num * block_size * 100) / total_size)
                progress_callback(min(percent, 100))

        urllib.request.urlretrieve(url, target_path, reporthook=reporthook)

    @staticmethod
    def verify_sha256(filepath: str, expected_hash: str) -> bool:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest().lower() == expected_hash.lower()

    @staticmethod
    def replace_and_restart(new_binary_path: str) -> None:
        current_executable = os.path.abspath(sys.argv[0])
        os.chmod(new_binary_path, 0o755)
        os.replace(new_binary_path, current_executable)
        os.execv(current_executable, sys.argv)