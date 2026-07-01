import re
from pathlib import Path
from app.config import Settings
from app.utils.file_manager import FileManager
from app.utils.json_manager import JsonManager


class VersioningSystem:
    @staticmethod
    def get_version_folder(path: str | Path):
        return Path(path) / Settings.VERSIONING_FOLDER

    @staticmethod
    def get_version_log_folder(path: str | Path):
        return Path(path) / Settings.VERSIONING_LOG_FOLDER / "logs"

    @staticmethod
    def get_version_log_file(path: str | Path):
        return Path(path) / Settings.VERSIONING_LOG_FOLDER / "log.json"

    @staticmethod
    def get_version_files(path: str):
        p = Path(path)
        if not p.exists():
            return []
        ignore_list = [".blend1", ".tmp"]
        pattern = re.compile(rf"{re.escape(Settings.VERSIONING_STARTWITH)}\d+", re.IGNORECASE)
        return [f.name for f in p.iterdir() if f.is_file() and pattern.search(f.name) and f.suffix.lower() not in ignore_list]

    @staticmethod
    def get_version_files_number(path: str):
        filenames = VersioningSystem.get_version_files(path)
        version_numbers = []
        pattern = rf"{re.escape(Settings.VERSIONING_STARTWITH)}\d+"
        for name in filenames:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                version_numbers.append(match.group())
        return version_numbers

    @staticmethod
    def get_version_info_list(path: str):
        base_p = Path(path)
        filenames = VersioningSystem.get_version_files(path)
        results = []
        pattern = rf"{re.escape(Settings.VERSIONING_STARTWITH)}\d+"
        for name in filenames:
            match = re.search(pattern, name, re.IGNORECASE)
            version_str = match.group() if match else "unknown"
            results.append({
                "version": version_str,
                "filename": name,
                "full_path": str(base_p / name)
            })
        return results

    @staticmethod
    def get_version_files_with_date(path: str):
        files = VersioningSystem.get_version_files(path)
        files_with_date = []
        for file in files:
            files_with_date.append(
                (file, FileManager.get_file_last_modified(str(Path(path) / file)))
            )
        return files_with_date

    @staticmethod
    def get_version_file_with_date(path: str):
        file = VersioningSystem.get_latest_version(path)
        if not file:
            return None
        return (file, FileManager.get_file_last_modified(str(Path(path) / file)))

    @staticmethod
    def get_latest_version(path: str):
        files = VersioningSystem.get_version_files(path)
        if not files:
            return None
        return max(files)

    @staticmethod
    def get_latest_version_path(path: str):
        latest_version = VersioningSystem.get_latest_version(path)
        if not latest_version:
            return None
        return VersioningSystem.get_version_folder(path) / latest_version

    @staticmethod
    def get_next_version(path: str):
        latest_version = VersioningSystem.get_latest_version(path)
        if not latest_version:
            return None
        pattern = rf"(.*?){re.escape(Settings.VERSIONING_STARTWITH)}(\d+)(\.[^.]+)$"
        match = re.search(pattern, latest_version, re.IGNORECASE)

        if match:
            prefix = match.group(1)
            v_marker = Settings.VERSIONING_STARTWITH
            number_str = match.group(2)
            extension = match.group(3)
            padding = len(number_str)
            next_number = int(number_str) + 1
            next_number_str = str(next_number).zfill(padding)
            return f"{prefix}{v_marker}{next_number_str}{extension}"
        return None

    @staticmethod
    def get_next_version_path(path: str):
        path_obj = Path(path)
        next_version = VersioningSystem.get_next_version(str(path_obj.parent))
        if not next_version:
            return None
        return path_obj.parent / next_version

    @staticmethod
    def get_master_path(version_path: str | Path):
        version_path = Path(version_path)
        parent_dir = version_path.parent.parent
        extension = version_path.suffix
        pattern = rf"{re.escape(Settings.VERSIONING_STARTWITH)}\d+(\.[^.]+)?$"
        master_name = re.sub(pattern, "", version_path.name, flags=re.IGNORECASE)
        master_name = f"{master_name.rstrip('_')}{extension}"
        return parent_dir / master_name

    @staticmethod
    def get_init_version(master_path: str, version_number: int = 1, padding: int = 3):
        path_obj = Path(master_path)
        base_name = path_obj.stem
        extension = path_obj.suffix
        version_str = str(version_number).zfill(padding)
        return f"{base_name}_{Settings.VERSIONING_STARTWITH}{version_str}{extension}"

    @staticmethod
    def get_init_version_path(master_path: str, version_number: int = 1, padding: int = 3):
        path_obj = Path(master_path)
        version_dir = VersioningSystem.get_version_folder(str(path_obj.parent))    
        base_name = path_obj.stem
        extension = path_obj.suffix
        version_str = str(version_number).zfill(padding)
        filename = f"{base_name}_{Settings.VERSIONING_STARTWITH}{version_str}{extension}"
        return version_dir / filename

    @staticmethod
    def init_log(base_path: str, file_path: str, locked: bool, timestamp: float, author: str):
        file_name = Path(file_path).stem

        if not file_name:
            return

        log_folder = VersioningSystem.get_version_log_folder(base_path)
        log_folder.mkdir(parents=True, exist_ok=True)
        log_file = log_folder / f"{file_name}.json"
        JsonManager.save_json(
            str(log_file),
            {
                "file": file_name,
                "file_path": file_path,
                "locked": locked,
                "logs": [
                    {"log": 1, "date": timestamp, "author": author, "locked": locked}
                ],
            },
        )

    @staticmethod
    def update_log(base_path: str, file_path: str, locked: bool, timestamp: float, author: str):
        file_name = Path(file_path).stem

        if not file_name:
            return

        log_folder = VersioningSystem.get_version_log_folder(base_path)
        log_file = log_folder / f"{file_name}.json"
        if not log_file.exists():
            return None
        log_data = JsonManager.load_json(str(log_file))
        next_log_id = len(log_data.get("logs", [])) + 1
        log_data["locked"] = locked
        log_data["logs"].append({"log": next_log_id, "date": timestamp, "author": author, "locked": locked})
        JsonManager.update_json(str(log_file), log_data)

    @staticmethod
    def get_latest_log(base_path: str, file_path: str | None  = None):
        target = file_path or base_path
        file_name = Path(target).stem

        if not file_name:
            return None

        log_folder = VersioningSystem.get_version_log_folder(base_path)
        log_file = log_folder / f"{file_name}.json"
        if not log_file.exists():
            return None
        log_data = JsonManager.load_json(str(log_file))
        logs = log_data.get("logs", [])
        if not logs:
            return None
        return logs[-1]