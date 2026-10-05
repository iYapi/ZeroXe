"""Lock Service for ZeroXe Application.

Connects UI controllers with pipeline lock management and version logging.
Resolves user identity (Kitsu ID, Full Name, Email, Workstation) and monitors DCC processes.
"""

from dataclasses import dataclass
import getpass
import logging
from pathlib import Path
import platform
import socket
from typing import Any, Dict, Optional, Tuple, Union

from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class UserIdentity:
    """Represents current active user identity."""

    kitsu_id: str
    name: str
    email: str
    workstation: str


class LockService:
    """Manages file locking and version logging from the ZeroXe application."""

    _cached_user: Optional[UserIdentity] = None

    @classmethod
    def get_current_user(cls) -> UserIdentity:
        """Resolve current user identity from Kitsu or fallback to local environment."""
        kitsu_id = ""
        user_name = ""
        user_email = SettingsService.get_kitsu_email()
        workstation = socket.gethostname() or platform.node() or "Workstation"

        try:
            import gazu

            # Attempt to fetch currently authenticated user from Kitsu/Gazu
            curr = getattr(gazu.client, "get_current_user", None)
            user_data = curr() if callable(curr) else None
            if user_data and isinstance(user_data, dict):
                kitsu_id = str(user_data.get("id", ""))
                first_name = str(user_data.get("first_name", "")).strip()
                last_name = str(user_data.get("last_name", "")).strip()
                full_name = f"{first_name} {last_name}".strip()
                user_name = full_name or str(user_data.get("name", "")) or user_email
                if user_data.get("email"):
                    user_email = user_data.get("email")
        except Exception as e:
            logger.debug(f"Could not retrieve user info from Kitsu: {e}")

        # Fallback to email username or OS username if not logged into Kitsu
        if not user_name:
            if user_email and "@" in user_email:
                user_name = user_email.split("@")[0].replace(".", " ").title()
            else:
                user_name = getpass.getuser()

        return UserIdentity(
            kitsu_id=kitsu_id,
            name=user_name,
            email=user_email,
            workstation=workstation,
        )

    @classmethod
    def build_entity_key(
        cls,
        department: str,
        episode: str,
        sequence: str,
        shot: str,
        task: str = "",
        project_name: Optional[str] = None,
    ) -> str:
        """Construct standard entity key."""
        module = PipelineService.load_pipeline_module(project_name=project_name)
        if module and hasattr(module, "build_entity_key"):
            return module.build_entity_key(
                department=department,
                episode=episode,
                sequence=sequence,
                shot=shot,
                task=task,
            )

        # Fallback direct formatting
        ep = episode.strip().lower()
        seq = sequence.strip().lower()
        sh = shot.strip().lower()
        dept = department.strip().lower()

        if seq.startswith(f"{ep}_"):
            seq_part = seq
        else:
            seq_part = f"{ep}_{seq}" if ep else seq

        if sh.startswith(f"{seq_part}_"):
            shot_part = sh
        elif sh.startswith(f"{ep}_"):
            shot_part = sh
        else:
            shot_part = f"{seq_part}_{sh}" if seq_part else sh

        suffix = task.strip().lower() or dept
        return f"{shot_part}_{suffix}".replace(" ", "_").replace("/", "_")

    @classmethod
    def check_lock(
        cls,
        entity_key: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if an entity is locked."""
        config_path = PipelineService.get_active_pipeline_yaml_path(project_name=project_name)
        module = PipelineService.load_pipeline_module(project_name=project_name)
        if module and hasattr(module, "check_lock"):
            return module.check_lock(
                entity_key=entity_key,
                project_path=project_path,
                config_path=config_path,
            )

        # Fallback to local LockManager
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Locks.lock_manager import LockManager

                mgr = LockManager(pipeline_root=config_path.parent)
                return mgr.check_lock(
                    entity_key=entity_key,
                    project_path=project_path,
                    config_path=config_path,
                )
            except Exception as e:
                logger.warning(f"Fallback LockManager check_lock error: {e}")

        return False, None

    @classmethod
    def acquire_lock(
        cls,
        entity_key: str,
        working_file: str = "",
        current_version: str = "",
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Acquire lock on shot/asset."""
        user = cls.get_current_user()
        config_path = PipelineService.get_active_pipeline_yaml_path(project_name=project_name)
        module = PipelineService.load_pipeline_module(project_name=project_name)

        if module and hasattr(module, "acquire_lock"):
            return module.acquire_lock(
                entity_key=entity_key,
                kitsu_id=user.kitsu_id,
                name=user.name,
                email=user.email,
                workstation=user.workstation,
                working_file=working_file,
                current_version=current_version,
                project_name=project_name or "",
                project_path=project_path,
                config_path=config_path,
                force=force,
            )

        # Fallback to local LockManager
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Locks.lock_manager import LockManager

                mgr = LockManager(pipeline_root=config_path.parent)
                return mgr.acquire_lock(
                    entity_key=entity_key,
                    kitsu_id=user.kitsu_id,
                    name=user.name,
                    email=user.email,
                    workstation=user.workstation,
                    working_file=working_file,
                    current_version=current_version,
                    project_name=project_name or "",
                    project_path=project_path,
                    config_path=config_path,
                    force=force,
                )
            except Exception as e:
                logger.error(f"Fallback LockManager acquire_lock error: {e}")
                return False, f"Lock acquisition error: {e}", None

        return True, "Lock module bypassed", None

    @classmethod
    def release_lock(
        cls,
        entity_key: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Release lock on file close."""
        user = cls.get_current_user()
        config_path = PipelineService.get_active_pipeline_yaml_path(project_name=project_name)
        module = PipelineService.load_pipeline_module(project_name=project_name)

        if module and hasattr(module, "release_lock"):
            return module.release_lock(
                entity_key=entity_key,
                kitsu_id=user.kitsu_id,
                name=user.name,
                workstation=user.workstation,
                project_path=project_path,
                config_path=config_path,
            )

        # Fallback to local LockManager
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Locks.lock_manager import LockManager

                mgr = LockManager(pipeline_root=config_path.parent)
                return mgr.release_lock(
                    entity_key=entity_key,
                    kitsu_id=user.kitsu_id,
                    name=user.name,
                    workstation=user.workstation,
                    project_path=project_path,
                    config_path=config_path,
                )
            except Exception as e:
                logger.warning(f"Fallback LockManager release_lock error: {e}")

        return True, "Lock released"

    @classmethod
    def force_unlock(
        cls,
        entity_key: str,
        reason: str = "Lead forced unlock",
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Force unlock an entity."""
        user = cls.get_current_user()
        config_path = PipelineService.get_active_pipeline_yaml_path(project_name=project_name)
        module = PipelineService.load_pipeline_module(project_name=project_name)

        if module and hasattr(module, "force_unlock"):
            return module.force_unlock(
                entity_key=entity_key,
                kitsu_id=user.kitsu_id,
                name=user.name,
                reason=reason,
                workstation=user.workstation,
                project_path=project_path,
                config_path=config_path,
            )

        # Fallback to local LockManager
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Locks.lock_manager import LockManager

                mgr = LockManager(pipeline_root=config_path.parent)
                return mgr.force_unlock(
                    entity_key=entity_key,
                    kitsu_id=user.kitsu_id,
                    name=user.name,
                    reason=reason,
                    workstation=user.workstation,
                    project_path=project_path,
                    config_path=config_path,
                )
            except Exception as e:
                logger.error(f"Fallback LockManager force_unlock error: {e}")
                return False, f"Force unlock error: {e}", None

        return True, "Force unlock completed", None

    @classmethod
    def get_history(
        cls,
        entity_key: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve history data for an entity."""
        config_path = PipelineService.get_active_pipeline_yaml_path(project_name=project_name)
        module = PipelineService.load_pipeline_module(project_name=project_name)

        if module and hasattr(module, "get_history"):
            return module.get_history(
                entity_key=entity_key,
                project_path=project_path,
                config_path=config_path,
            )

        # Fallback to local LockManager
        if config_path and config_path.is_file():
            try:
                from pipeline.Commands.Locks.lock_manager import LockManager

                mgr = LockManager(pipeline_root=config_path.parent)
                return mgr.get_history(
                    entity_key=entity_key,
                    project_path=project_path,
                    config_path=config_path,
                )
            except Exception as e:
                logger.warning(f"Fallback LockManager get_history error: {e}")

        return {"versions": [], "activity_log": []}

