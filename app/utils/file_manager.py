import shutil
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict


class FileManager:
    @staticmethod
    def get_file_last_modified(path: str):
        return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def scan_project_file_recursive(root_path: str, file_extension=None):
        root_path = Path(root_path)
        if not root_path.exists() or not root_path.is_dir():
            raise ValueError(f"The path {root_path} is not a valid directory.")

            # gather files
        if file_extension:
            files = list(root_path.rglob(f"*.{file_extension}"))
        else:
            files = list(root_path.rglob("*"))

            # regex: capture show/ep/seq/shot/div/version
        pat = re.compile(
            r"^(?P<show>[a-z0-9]+)_ep(?P<ep>\d+)_sq(?P<seq>\d+)_sh(?P<shot>\d+)_(?P<div>[a-z]+)_v(?P<ver>\d+)\.\w+$",
            re.IGNORECASE
        )

        grouped = defaultdict(list)

        for f in files:
            if not f.is_file():
                continue
            m = pat.match(f.name)
            if not m:
                continue

            key = (
                m.group("ep"),
                m.group("seq"),
                m.group("shot"),
                m.group("div").lower()
            )
            ver = int(m.group("ver"))
            grouped[key].append((ver, f))

        # pick latest version per group
        latest = {}
        for key, versions in grouped.items():
            latest[key] = max(versions, key=lambda x: x[0])[1]  # keep file with max version

        print(latest)

        return latest

    @staticmethod
    def copy_file(src: str, destination: str) -> str:
        src_path = Path(src)
        dest_dir = Path(destination)

        if not src_path.is_file():
            raise FileNotFoundError(f"Source file not found: {src_path}")

        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / src_path.name
        shutil.copy2(src_path, dest_path)

        return str(dest_path)