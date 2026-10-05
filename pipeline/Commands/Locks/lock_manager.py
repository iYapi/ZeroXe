"""Lock and Version History Management Module for ZeroXe Pipeline.

Manages cooperative application locks in `00_pipeline/locks/` and
chronological version/audit history logs in `00_pipeline/history/`.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import socket
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def get_current_iso_timestamp() -> str:
    """Return current timestamp in ISO 8601 format with local timezone offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_workstation_name() -> str:
    """Get computer / workstation hostname or node name."""
    try:
        return socket.gethostname() or platform.node() or "Unknown-Workstation"
    except Exception:
        return "Unknown-Workstation"


class LockManager:
    """Handles file/shot locks and version history in 00_pipeline directory."""

    def __init__(self, pipeline_root: Optional[Union[str, Path]] = None):
        self._pipeline_root = Path(pipeline_root) if pipeline_root else None

    def resolve_pipeline_dir(
        self,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Resolve the 00_pipeline directory on disk/mount."""
        if self._pipeline_root and self._pipeline_root.is_dir():
            if self._pipeline_root.name == "00_pipeline":
                return self._pipeline_root
            candidate = self._pipeline_root / "00_pipeline"
            if candidate.is_dir() or self._pipeline_root.name.startswith("2026") or self._pipeline_root.parent.name.startswith("2026"):
                return candidate

        # 1. Check if project_path is provided
        if project_path:
            p_path = Path(project_path)
            candidate = p_path / "00_pipeline"
            if candidate.is_dir():
                return candidate
            if p_path.name == "00_pipeline":
                return p_path
            return candidate

        # 2. Check if config_path is provided (e.g. pipeline.yaml inside 00_pipeline or pipeline/)
        if config_path:
            c_path = Path(config_path).resolve()
            # If pipeline.yaml is inside 00_pipeline/
            if c_path.parent.name == "00_pipeline":
                return c_path.parent
            # If pipeline.yaml is inside pipeline/ or project_root/
            if (c_path.parent / "00_pipeline").is_dir():
                return c_path.parent / "00_pipeline"
            if (c_path.parent.parent / "00_pipeline").is_dir():
                return c_path.parent.parent / "00_pipeline"
            return c_path.parent / "00_pipeline"

        # 3. Fallback to current module's pipeline root
        module_dir = Path(__file__).resolve().parent
        fallback_pipeline_root = module_dir.parent.parent
        return fallback_pipeline_root / "00_pipeline"

    def get_locks_dir(
        self,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Get or create the 00_pipeline/locks directory."""
        pipe_dir = self.resolve_pipeline_dir(project_path=project_path, config_path=config_path)
        locks_dir = pipe_dir / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        return locks_dir

    def get_history_dir(
        self,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Get or create the 00_pipeline/history directory."""
        pipe_dir = self.resolve_pipeline_dir(project_path=project_path, config_path=config_path)
        history_dir = pipe_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir

    @staticmethod
    def build_entity_key(
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        task: str = "",
    ) -> str:
        """Construct standard entity key for shot task (e.g. ep998_sq01_sh0010_anm)."""
        ep = episode.strip().lower()
        seq = sequence.strip().lower()
        sh = shot.strip().lower()
        dept = department.strip().lower()

        # Clean sequence prefix if needed
        if seq.startswith(f"{ep}_"):
            seq_part = seq
        else:
            seq_part = f"{ep}_{seq}" if ep else seq

        # Clean shot prefix if needed
        if sh.startswith(f"{seq_part}_"):
            shot_part = sh
        elif sh.startswith(f"{ep}_"):
            shot_part = sh
        else:
            shot_part = f"{seq_part}_{sh}" if seq_part else sh

        suffix = task.strip().lower() or dept
        return f"{shot_part}_{suffix}".replace(" ", "_").replace("/", "_")

    # --------------------------------------------------------------------------
    # Lock Operations
    # --------------------------------------------------------------------------
    def get_lock_file_path(
        self,
        entity_key: str,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Get the path to the .lock.json file for a given entity."""
        locks_dir = self.get_locks_dir(project_path=project_path, config_path=config_path)
        return locks_dir / f"{entity_key}.lock.json"

    def check_lock(
        self,
        entity_key: str,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if an entity is currently locked.

        Returns:
            Tuple[is_locked, lock_data_dict]
        """
        lock_file = self.get_lock_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )
        if not lock_file.is_file():
            return False, None

        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return True, data
        except Exception as e:
            logger.warning(f"Failed to read lock file '{lock_file}': {e}")
            return False, None

    def acquire_lock(
        self,
        entity_key: str,
        kitsu_id: str,
        name: str,
        email: str = "",
        workstation: Optional[str] = None,
        working_file: str = "",
        current_version: str = "",
        project_name: str = "",
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
        force: bool = False,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Acquire a lock on a shot/asset.

        Returns:
            Tuple[success: bool, message: str, active_lock_data: Optional[Dict]]
        """
        lock_file = self.get_lock_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        # Check existing lock
        is_locked, existing_data = self.check_lock(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        ws = workstation or get_workstation_name()
        now_str = get_current_iso_timestamp()

        if is_locked and existing_data and not force:
            existing_kitsu_id = str(existing_data.get("kitsu_id", ""))
            existing_name = str(existing_data.get("name", ""))
            existing_ws = str(existing_data.get("workstation", ""))

            # If locked by the exact same user on the exact same workstation, allow re-entry
            if (
                (kitsu_id and existing_kitsu_id == kitsu_id)
                or (name and existing_name.lower() == name.lower())
            ) and (existing_ws == ws):
                # Update timestamp and continue
                existing_data["last_heartbeat"] = now_str
                try:
                    with open(lock_file, "w", encoding="utf-8") as f:
                        json.dump(existing_data, f, indent=2)
                except Exception:
                    pass
                return True, "Lock refreshed by current user", existing_data

            msg = (
                f"Locked by {existing_name or 'another artist'} "
                f"(Kitsu ID: {existing_kitsu_id or 'N/A'}) on workstation '{existing_ws}' "
                f"since {existing_data.get('locked_at', 'unknown time')}."
            )
            return False, msg, existing_data

        # Create lock record
        lock_data = {
            "entity_key": entity_key,
            "status": "LOCKED",
            "kitsu_id": kitsu_id,
            "name": name,
            "email": email,
            "workstation": ws,
            "pid": os.getpid(),
            "locked_at": now_str,
            "working_file": working_file,
            "current_version": current_version,
            "project": project_name,
        }

        try:
            # Atomic write to temporary file first
            temp_lock = lock_file.with_suffix(".tmp")
            with open(temp_lock, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
            temp_lock.replace(lock_file)
        except Exception as e:
            logger.error(f"Failed to write lock file '{lock_file}': {e}")
            return False, f"Failed to acquire lock: {e}", None

        # Append to history log
        self._append_history_event(
            entity_key=entity_key,
            action="OPEN_FILE",
            kitsu_id=kitsu_id,
            name=name,
            workstation=ws,
            details=f"Opened file {working_file} ({current_version})",
            project_path=project_path,
            config_path=config_path,
            project_name=project_name,
            master_file=working_file,
            current_version=current_version,
        )

        return True, "Lock successfully acquired", lock_data

    def release_lock(
        self,
        entity_key: str,
        kitsu_id: str = "",
        name: str = "",
        workstation: Optional[str] = None,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, str]:
        """Release an existing lock upon file close."""
        lock_file = self.get_lock_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        ws = workstation or get_workstation_name()

        if lock_file.is_file():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to delete lock file '{lock_file}': {e}")
                return False, f"Failed to release lock: {e}"

        # Append CLOSE_FILE event to history log
        self._append_history_event(
            entity_key=entity_key,
            action="CLOSE_FILE",
            kitsu_id=kitsu_id,
            name=name,
            workstation=ws,
            details="Released lock on file close",
            project_path=project_path,
            config_path=config_path,
        )

        return True, "Lock released"

    def force_unlock(
        self,
        entity_key: str,
        kitsu_id: str,
        name: str,
        reason: str = "Lead forced unlock",
        workstation: Optional[str] = None,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Force unlock an entity regardless of who owns the lock."""
        lock_file = self.get_lock_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        is_locked, existing_data = self.check_lock(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        prev_owner = "Unknown"
        prev_kitsu = ""
        prev_ws = ""
        if existing_data:
            prev_owner = existing_data.get("name", "Unknown")
            prev_kitsu = existing_data.get("kitsu_id", "")
            prev_ws = existing_data.get("workstation", "")

        if lock_file.is_file():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to delete lock file on force unlock '{lock_file}': {e}")
                return False, f"Failed to force unlock: {e}", existing_data

        ws = workstation or get_workstation_name()

        # Record FORCE_UNLOCK in history log
        self._append_history_event(
            entity_key=entity_key,
            action="FORCE_UNLOCK",
            kitsu_id=kitsu_id,
            name=name,
            workstation=ws,
            details=f"Force unlocked by {name} (Kitsu: {kitsu_id}). Previous owner: {prev_owner} (Kitsu: {prev_kitsu}, WS: {prev_ws}). Reason: {reason}",
            project_path=project_path,
            config_path=config_path,
        )

        return True, f"Successfully force-unlocked. Previous holder: {prev_owner}", existing_data

    # --------------------------------------------------------------------------
    # Version & History Operations
    # --------------------------------------------------------------------------
    def get_history_file_path(
        self,
        entity_key: str,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Get the path to the _history.json file for a given entity."""
        history_dir = self.get_history_dir(project_path=project_path, config_path=config_path)
        return history_dir / f"{entity_key}_history.json"

    def get_history(
        self,
        entity_key: str,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Load history log JSON for an entity."""
        hist_file = self.get_history_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )
        if not hist_file.is_file():
            return {
                "meta": {
                    "entity_key": entity_key,
                    "latest_version": "",
                    "last_updated": get_current_iso_timestamp(),
                },
                "versions": [],
                "activity_log": [],
            }

        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read history file '{hist_file}': {e}")
            return {
                "meta": {"entity_key": entity_key, "error": str(e)},
                "versions": [],
                "activity_log": [],
            }

    def record_version(
        self,
        entity_key: str,
        kitsu_id: str,
        name: str,
        version: str,
        file_path: str,
        comment: str = "",
        file_size_mb: float = 0.0,
        workstation: Optional[str] = None,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> bool:
        """Record a new saved version in the history JSON."""
        ws = workstation or get_workstation_name()
        now_str = get_current_iso_timestamp()

        hist_data = self.get_history(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        # 1. Update metadata
        meta = hist_data.setdefault("meta", {})
        meta["entity_key"] = entity_key
        meta["latest_version"] = version
        meta["last_updated"] = now_str

        # 2. Append or update version record
        versions: List[Dict[str, Any]] = hist_data.setdefault("versions", [])
        # Check if version entry already exists
        existing_ver = next((v for v in versions if v.get("version") == version), None)
        if existing_ver:
            existing_ver["kitsu_id"] = kitsu_id
            existing_ver["author"] = name
            existing_ver["created_at"] = now_str
            existing_ver["file_path"] = file_path
            existing_ver["comment"] = comment
            existing_ver["file_size_mb"] = file_size_mb
        else:
            versions.append(
                {
                    "version": version,
                    "file_path": file_path,
                    "kitsu_id": kitsu_id,
                    "author": name,
                    "created_at": now_str,
                    "comment": comment,
                    "file_size_mb": file_size_mb,
                }
            )

        # 3. Append to activity_log
        activity_log: List[Dict[str, Any]] = hist_data.setdefault("activity_log", [])
        activity_log.append(
            {
                "timestamp": now_str,
                "action": "SAVE_VERSION",
                "kitsu_id": kitsu_id,
                "user": name,
                "workstation": ws,
                "details": f"Saved version {version}. {comment}".strip(),
            }
        )

        return self._save_history(
            entity_key=entity_key,
            data=hist_data,
            project_path=project_path,
            config_path=config_path,
        )

    def _append_history_event(
        self,
        entity_key: str,
        action: str,
        kitsu_id: str,
        name: str,
        workstation: str,
        details: str,
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
        project_name: str = "",
        master_file: str = "",
        current_version: str = "",
    ) -> None:
        """Internal helper to append an entry to activity_log in history JSON."""
        now_str = get_current_iso_timestamp()
        hist_data = self.get_history(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )

        meta = hist_data.setdefault("meta", {})
        meta["entity_key"] = entity_key
        meta["last_updated"] = now_str
        if project_name:
            meta["project"] = project_name
        if master_file:
            meta["master_file"] = master_file
        if current_version:
            meta["latest_version"] = current_version

        activity_log: List[Dict[str, Any]] = hist_data.setdefault("activity_log", [])
        activity_log.append(
            {
                "timestamp": now_str,
                "action": action,
                "kitsu_id": kitsu_id,
                "user": name,
                "workstation": workstation,
                "details": details,
            }
        )

        self._save_history(
            entity_key=entity_key,
            data=hist_data,
            project_path=project_path,
            config_path=config_path,
        )

    def _save_history(
        self,
        entity_key: str,
        data: Dict[str, Any],
        project_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> bool:
        """Write history data atomically."""
        hist_file = self.get_history_file_path(
            entity_key=entity_key, project_path=project_path, config_path=config_path
        )
        try:
            temp_file = hist_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(hist_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save history file '{hist_file}': {e}")
            return False
