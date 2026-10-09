"""Notification Service and Kitsu Real-Time Event Listener.

Provides native OS desktop notifications via QSystemTrayIcon, a Notification Menu
with recent notification history, and listens to real-time Kitsu WebSocket events
specifically filtered for the logged-in user in a dedicated background QThread.
"""

from datetime import datetime
import logging
import os
import time
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
)

import gazu
from zeroxe import config
from zeroxe.api.gazu_client import init_kitsu, is_kitsu_configured, is_kitsu_connected

logger = logging.getLogger(__name__)


def get_current_user_id() -> Optional[str]:
    """Retrieve the ID of the currently authenticated Kitsu user."""
    try:
        if not is_kitsu_connected():
            return None
        user = gazu.client.get_current_user()
        if user and isinstance(user, dict):
            return str(user.get("id") or "")
    except Exception as e:
        logger.debug(f"Could not retrieve current user: {e}")
    return None


def is_event_relevant_to_user(
    event_name: str, data: Any, current_user_id: Optional[str]
) -> bool:
    """Determine if a Kitsu event should be notified to the current user.

    Filters:
    1. Ignores self-actions (if the current user triggered the update/comment).
    2. For 'notification:new': checks if recipient is the current user.
    3. For 'task:update', 'comment:new', 'task:new', 'preview:new': checks if
       the task is assigned to the current user or mentions the current user.

    Args:
        event_name: The event type name.
        data: The enriched event payload dictionary.
        current_user_id: The ID of the currently logged-in user.

    Returns:
        bool: True if relevant, False to filter out.
    """
    if not current_user_id or not isinstance(data, dict):
        # Fallback if no user ID is resolvable (e.g. offline tests)
        return True

    current_uid_str = str(current_user_id).strip()

    # 1. Ignore actions performed by the current user themselves
    author_id = (
        data.get("person_id")
        or data.get("user_id")
        or data.get("author_id")
        or data.get("created_by")
        or (data.get("person", {}).get("id") if isinstance(data.get("person"), dict) else None)
    )
    if author_id and str(author_id).strip() == current_uid_str:
        return False

    # 2. For direct in-app notifications ('notification:new')
    if event_name == "notification:new":
        recipient_id = (
            data.get("recipient_id")
            or data.get("target_id")
            or data.get("person_id")
            or (data.get("person", {}).get("id") if isinstance(data.get("person"), dict) else None)
        )
        if recipient_id and str(recipient_id).strip() == current_uid_str:
            return True

        activity = data.get("activity") if isinstance(data.get("activity"), dict) else {}
        activity_target = activity.get("recipient_id") or activity.get("person_id")
        if activity_target and str(activity_target).strip() == current_uid_str:
            return True

        # If no explicit recipient field is in notification, accept
        if not recipient_id and not activity_target:
            return True
        return False

    # 3. For task updates, comments, new tasks, previews: check task assignees
    task = data.get("task")
    assignee_ids = []

    if isinstance(task, dict):
        assignees = task.get("assignees") or task.get("persons") or []
        for a in assignees:
            if isinstance(a, dict) and a.get("id"):
                assignee_ids.append(str(a["id"]).strip())
            elif isinstance(a, str):
                assignee_ids.append(str(a).strip())

        if task.get("assignee_id"):
            assignee_ids.append(str(task.get("assignee_id")).strip())

    # Also check top-level assignees in payload
    top_assignees = data.get("assignees") or []
    for a in top_assignees:
        if isinstance(a, dict) and a.get("id"):
            assignee_ids.append(str(a["id"]).strip())
        elif isinstance(a, str):
            assignee_ids.append(str(a).strip())

    if current_uid_str in assignee_ids:
        return True

    return False


def hydrate_kitsu_event(event_name: str, data: Any) -> dict:
    """Enrich raw Socket.IO event payloads by resolving IDs via Gazu API/cache.

    Kitsu Socket.IO events often deliver minimal database dictionaries (e.g. {'task_id': '...',
    'task_status_id': '...'} or {'task': {'id': '...'}}). This helper resolves names for task,
    entity, project, task_status, and author person so notifications display full context.
    """
    if not isinstance(data, dict):
        return {}

    enriched = dict(data)
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    if inner:
        for k, v in inner.items():
            enriched.setdefault(k, v)

    # 1. Resolve Task ID
    task_id = (
        enriched.get("task_id")
        or (enriched.get("task") if isinstance(enriched.get("task"), str) else None)
        or (enriched.get("task", {}).get("id") if isinstance(enriched.get("task"), dict) else None)
        or (enriched.get("activity", {}).get("task_id") if isinstance(enriched.get("activity"), dict) else None)
        or (enriched.get("id") if event_name.startswith("task:") else None)
    )

    if task_id and isinstance(task_id, str):
        try:
            task_full = gazu.task.get_task(task_id)
            if task_full and isinstance(task_full, dict):
                for key in [
                    "project_name",
                    "project_code",
                    "project_short_name",
                    "entity_name",
                    "sequence_name",
                    "episode_name",
                    "sequence_id",
                    "episode_id",
                    "sequence",
                    "episode",
                    "parent_id",
                    "task_type_name",
                    "task_type_id",
                    "task_status_name",
                    "name",
                    "task_status_id",
                    "entity_type_name",
                    "entity_id",
                    "project_id",
                    "assignees",
                ]:
                    if task_full.get(key) and not enriched.get(key):
                        enriched[key] = task_full[key]

                if isinstance(task_full.get("sequence"), dict) and not enriched.get("sequence_name"):
                    enriched["sequence_name"] = task_full["sequence"].get("name", "")
                if isinstance(task_full.get("episode"), dict) and not enriched.get("episode_name"):
                    enriched["episode_name"] = task_full["episode"].get("name", "")

                if not isinstance(enriched.get("task"), dict) or not enriched["task"].get("task_type_name"):
                    enriched["task"] = task_full

                last_comment = task_full.get("last_comment")
                if isinstance(last_comment, dict):
                    if not enriched.get("text") and last_comment.get("text"):
                        enriched.setdefault("comment_text", last_comment["text"])
                    if not enriched.get("person_id") and last_comment.get("person_id"):
                        enriched.setdefault("person_id", last_comment["person_id"])
        except Exception as e:
            logger.debug(f"Could not hydrate task {task_id}: {e}")

    # 2. Resolve Status ID
    task_status_id = (
        enriched.get("task_status_id")
        or (enriched.get("task", {}).get("task_status_id") if isinstance(enriched.get("task"), dict) else None)
        or (enriched.get("activity", {}).get("task_status_id") if isinstance(enriched.get("activity"), dict) else None)
    )
    if task_status_id and isinstance(task_status_id, str):
        try:
            status_obj = gazu.task.get_task_status(task_status_id)
            if status_obj and isinstance(status_obj, dict):
                enriched["task_status_name"] = status_obj.get("name", "")
                enriched["task_status"] = status_obj
        except Exception as e:
            logger.debug(f"Could not hydrate task_status {task_status_id}: {e}")

    # 3. Resolve Person ID
    person_id = (
        enriched.get("person_id")
        or enriched.get("user_id")
        or enriched.get("author_id")
        or enriched.get("created_by")
        or (enriched.get("person") if isinstance(enriched.get("person"), str) else None)
        or (enriched.get("person", {}).get("id") if isinstance(enriched.get("person"), dict) else None)
        or (enriched.get("activity", {}).get("person_id") if isinstance(enriched.get("activity"), dict) else None)
    )
    if person_id and isinstance(person_id, str) and (not isinstance(enriched.get("person"), dict) or not enriched["person"].get("first_name")):
        try:
            person_obj = gazu.person.get_person(person_id)
            if person_obj and isinstance(person_obj, dict):
                enriched["person"] = person_obj
        except Exception as e:
            logger.debug(f"Could not hydrate person {person_id}: {e}")

    # 4. Resolve Comment ID
    comment_id = (
        enriched.get("comment_id")
        or (enriched.get("id") if event_name.startswith("comment:") else None)
        or (enriched.get("activity", {}).get("comment_id") if isinstance(enriched.get("activity"), dict) else None)
    )
    if comment_id and isinstance(comment_id, str) and not enriched.get("text") and not enriched.get("comment"):
        try:
            comment_obj = gazu.task.get_comment(comment_id)
            if comment_obj and isinstance(comment_obj, dict):
                enriched["text"] = comment_obj.get("text", "")
                if not enriched.get("person") and comment_obj.get("person_id"):
                    p_obj = gazu.person.get_person(comment_obj["person_id"])
                    if p_obj:
                        enriched["person"] = p_obj
                if not enriched.get("task_id") and comment_obj.get("task_id"):
                    t_full = gazu.task.get_task(comment_obj["task_id"])
                    if t_full:
                        enriched["task"] = t_full
                        for key in [
                            "project_name",
                            "project_code",
                            "project_short_name",
                            "entity_name",
                            "sequence_name",
                            "episode_name",
                            "sequence_id",
                            "episode_id",
                            "entity_id",
                            "project_id",
                            "task_id",
                            "task_type_name",
                            "task_status_name",
                            "assignees",
                        ]:
                            if t_full.get(key) and not enriched.get(key):
                                enriched[key] = t_full[key]

                        if isinstance(t_full.get("sequence"), dict) and not enriched.get("sequence_name"):
                            enriched["sequence_name"] = t_full["sequence"].get("name", "")
                        if isinstance(t_full.get("episode"), dict) and not enriched.get("episode_name"):
                            enriched["episode_name"] = t_full["episode"].get("name", "")
        except Exception as e:
            logger.debug(f"Could not hydrate comment {comment_id}: {e}")

    # 5. Resolve Entity ID (and hierarchy: sequence, episode)
    entity_id = (
        enriched.get("entity_id")
        or (enriched.get("entity", {}).get("id") if isinstance(enriched.get("entity"), dict) else None)
        or enriched.get("shot_id")
        or enriched.get("asset_id")
    )
    if entity_id and isinstance(entity_id, str):
        if not enriched.get("entity_name") or not enriched.get("sequence_name") or not enriched.get("episode_name"):
            try:
                ent = gazu.entity.get_entity(entity_id)
                if ent and isinstance(ent, dict):
                    if not enriched.get("entity_name"):
                        enriched["entity_name"] = ent.get("name", "")
                    if not enriched.get("entity"):
                        enriched["entity"] = ent

                    if ent.get("sequence_name") and not enriched.get("sequence_name"):
                        enriched["sequence_name"] = ent["sequence_name"]
                    if ent.get("episode_name") and not enriched.get("episode_name"):
                        enriched["episode_name"] = ent["episode_name"]
                    if isinstance(ent.get("sequence"), dict) and not enriched.get("sequence_name"):
                        enriched["sequence_name"] = ent["sequence"].get("name", "")
                    if isinstance(ent.get("episode"), dict) and not enriched.get("episode_name"):
                        enriched["episode_name"] = ent["episode"].get("name", "")

                    # For shots, parent is sequence, and sequence parent is episode
                    parent_id = ent.get("parent_id") or ent.get("sequence_id")
                    if parent_id and isinstance(parent_id, str) and not enriched.get("sequence_name"):
                        try:
                            parent_ent = gazu.entity.get_entity(parent_id)
                            if parent_ent and isinstance(parent_ent, dict):
                                enriched.setdefault("sequence_name", parent_ent.get("name", ""))
                                ep_id = parent_ent.get("parent_id") or parent_ent.get("episode_id")
                                if ep_id and isinstance(ep_id, str) and not enriched.get("episode_name"):
                                    ep_ent = gazu.entity.get_entity(ep_id)
                                    if ep_ent and isinstance(ep_ent, dict):
                                        enriched.setdefault("episode_name", ep_ent.get("name", ""))
                        except Exception as err:
                            logger.debug(f"Could not hydrate parent sequence {parent_id}: {err}")
            except Exception as e:
                logger.debug(f"Could not hydrate entity {entity_id}: {e}")

    # 5b. Direct sequence_id / episode_id resolution fallback
    if enriched.get("sequence_id") and isinstance(enriched.get("sequence_id"), str) and not enriched.get("sequence_name"):
        try:
            seq_obj = gazu.entity.get_entity(enriched["sequence_id"])
            if seq_obj and isinstance(seq_obj, dict):
                enriched["sequence_name"] = seq_obj.get("name", "")
                if seq_obj.get("parent_id") and not enriched.get("episode_name"):
                    ep_obj = gazu.entity.get_entity(seq_obj["parent_id"])
                    if ep_obj and isinstance(ep_obj, dict):
                        enriched["episode_name"] = ep_obj.get("name", "")
        except Exception as e:
            logger.debug(f"Could not hydrate sequence_id {enriched.get('sequence_id')}: {e}")

    if enriched.get("episode_id") and isinstance(enriched.get("episode_id"), str) and not enriched.get("episode_name"):
        try:
            ep_obj = gazu.entity.get_entity(enriched["episode_id"])
            if ep_obj and isinstance(ep_obj, dict):
                enriched["episode_name"] = ep_obj.get("name", "")
        except Exception as e:
            logger.debug(f"Could not hydrate episode_id {enriched.get('episode_id')}: {e}")

    # 6. Resolve Project ID if project_code or project_name still missing
    project_id = (
        enriched.get("project_id")
        or (enriched.get("project", {}).get("id") if isinstance(enriched.get("project"), dict) else None)
    )
    if project_id and isinstance(project_id, str) and not enriched.get("project_code"):
        try:
            proj = gazu.project.get_project(project_id)
            if proj and isinstance(proj, dict):
                enriched["project_name"] = proj.get("name", "")
                enriched["project_code"] = proj.get("code", "") or proj.get("short_name", "")
                if not enriched.get("project"):
                    enriched["project"] = proj
        except Exception as e:
            logger.debug(f"Could not hydrate project {project_id}: {e}")

    return enriched


def parse_kitsu_event(event_name: str, data: Any) -> Tuple[str, str]:
    """Extract a user-friendly title and message from a Kitsu Socket.IO event payload.

    Args:
        event_name: The event identifier (e.g., 'notification:new', 'comment:new', 'task:update').
        data: The payload dictionary or value sent by Kitsu server.

    Returns:
        Tuple[str, str]: (Title, Message Body)
    """
    if not isinstance(data, dict):
        val_str = str(data) if data else "New event received."
        if len(val_str) > 200:
            val_str = val_str[:197] + "..."
        return f"Kitsu: {event_name}", val_str

    # 1. Author / Sender resolution
    person_obj = data.get("person") or data.get("user") or data.get("author")
    author_name = ""
    if isinstance(person_obj, dict):
        first_name = str(person_obj.get("first_name", "")).strip()
        last_name = str(person_obj.get("last_name", "")).strip()
        author_name = f"{first_name} {last_name}".strip() or str(
            person_obj.get("name") or person_obj.get("email") or ""
        ).strip()
    elif person_obj:
        author_name = str(person_obj).strip()

    # 2. Context resolution (Project / Episode / Sequence / Entity / Task)
    task_obj = data.get("task")
    task_type_obj = data.get("task_type") or (
        task_obj.get("task_type") if isinstance(task_obj, dict) else None
    )

    # 2a. Resolve task type / department name (e.g. "Lighting", "Modeling", "Animation")
    task_type_name = ""
    if isinstance(task_type_obj, dict):
        task_type_name = str(
            task_type_obj.get("name") or task_type_obj.get("short_name") or ""
        ).strip()
    elif task_type_obj:
        task_type_name = str(task_type_obj).strip()

    if not task_type_name:
        task_type_name = str(
            (task_obj.get("task_type_name") if isinstance(task_obj, dict) else "")
            or data.get("task_type_name")
            or ""
        ).strip()

    # 2b. Resolve sub-task / stream name (e.g. "main", "retake_01")
    subtask_name = ""
    if isinstance(task_obj, dict):
        subtask_name = str(task_obj.get("name") or "").strip()
    elif task_obj and not task_type_name:
        subtask_name = str(task_obj).strip()
    if not subtask_name:
        subtask_name = str(data.get("task_name") or "").strip()

    # 2c. Prioritize task type (e.g. "Lighting") over default stream name "main"
    if task_type_name:
        if subtask_name and subtask_name.lower() not in ("main", task_type_name.lower()):
            task_name = f"{task_type_name} ({subtask_name})"
        else:
            task_name = task_type_name
    elif subtask_name and subtask_name.lower() != "main":
        task_name = subtask_name
    else:
        task_name = ""

    entity_obj = data.get("entity") or data.get("shot") or data.get("asset")
    if isinstance(entity_obj, dict):
        entity_name = (
            str(entity_obj.get("name") or "")
            or str(data.get("entity_name") or data.get("shot_name") or data.get("asset_name") or "")
        ).strip()
    elif entity_obj:
        entity_name = str(entity_obj).strip()
    else:
        entity_name = str(data.get("entity_name") or data.get("shot_name") or data.get("asset_name") or "").strip()

    # 2d. Resolve Episode and Sequence
    ep_val = (
        data.get("episode")
        or data.get("episode_name")
        or (data.get("entity", {}).get("episode") if isinstance(data.get("entity"), dict) else None)
        or (data.get("task", {}).get("episode") if isinstance(data.get("task"), dict) else None)
    )
    if isinstance(ep_val, dict):
        episode_name = str(ep_val.get("name") or "").strip()
    elif ep_val:
        episode_name = str(ep_val).strip()
    else:
        episode_name = ""

    seq_val = (
        data.get("sequence")
        or data.get("sequence_name")
        or (data.get("entity", {}).get("sequence") if isinstance(data.get("entity"), dict) else None)
        or (data.get("task", {}).get("sequence") if isinstance(data.get("task"), dict) else None)
    )
    if isinstance(seq_val, dict):
        sequence_name = str(seq_val.get("name") or "").strip()
    elif seq_val:
        sequence_name = str(seq_val).strip()
    else:
        sequence_name = ""

    project_obj = data.get("project")
    project_label = ""
    if isinstance(project_obj, dict):
        project_label = str(
            project_obj.get("code")
            or project_obj.get("short_name")
            or data.get("project_code")
            or data.get("project_short_name")
            or project_obj.get("name")
            or data.get("project_name")
            or ""
        ).strip()
    elif project_obj:
        project_label = str(project_obj).strip()
    else:
        project_label = str(
            data.get("project_code")
            or data.get("project_short_name")
            or data.get("project_name")
            or ""
        ).strip()

    context_parts = []
    if project_label:
        context_parts.append(project_label)

    # Add Episode if present
    if episode_name:
        if (
            not entity_name.lower().startswith(f"{episode_name.lower()}_")
            and entity_name.lower() != episode_name.lower()
        ):
            context_parts.append(episode_name)

    # Add Sequence if present
    if sequence_name:
        if (
            not entity_name.lower().startswith(f"{sequence_name.lower()}_")
            and entity_name.lower() != sequence_name.lower()
            and f"_{sequence_name.lower()}_" not in entity_name.lower()
        ):
            context_parts.append(sequence_name)

    if entity_name:
        context_parts.append(entity_name)

    if task_name:
        context_parts.append(task_name)

    context_str = " | ".join(context_parts)

    # 3. Event-specific formatting
    if event_name == "comment:new":
        title = f"New Comment ({context_str})" if context_str else "New Kitsu Comment"
        raw_text = (
            data.get("text")
            or data.get("comment")
            or data.get("content")
            or "A new comment was posted."
        )
        text = str(raw_text).strip()
        if len(text) > 250:
            text = text[:247] + "..."
        message = f"{author_name}: {text}" if author_name else text
        return title, message

    elif event_name == "task:update":
        status_name = ""
        status_obj = data.get("task_status") or data.get("status")
        if isinstance(status_obj, dict):
            status_name = str(status_obj.get("name") or "").strip()
        elif status_obj:
            status_name = str(status_obj).strip()
        else:
            status_name = str(data.get("task_status_name") or data.get("status_name") or "").strip()

        title = f"Task Updated ({context_str})" if context_str else "Kitsu Task Updated"
        comment_text = str(
            data.get("comment_text") or data.get("text") or data.get("comment") or ""
        ).strip()

        if status_name:
            if author_name:
                if comment_text:
                    message = f"{author_name} changed status to '{status_name}': {comment_text}"
                else:
                    message = f"{author_name} changed status to: {status_name}"
            else:
                if comment_text:
                    message = f"Status changed to '{status_name}': {comment_text}"
                else:
                    message = f"Status changed to: {status_name}"
        elif comment_text:
            message = f"{author_name}: {comment_text}" if author_name else comment_text
        else:
            message = f"Task '{context_str or 'details'}' was updated."

        if len(message) > 250:
            message = message[:247] + "..."
        return title, message

    elif event_name == "notification:new":
        title = f"Kitsu Notification ({context_str})" if context_str else "New Kitsu Notification"
        activity = data.get("activity") if isinstance(data.get("activity"), dict) else {}
        raw_text = (
            data.get("text")
            or data.get("comment")
            or activity.get("comment")
            or activity.get("action")
            or data.get("data")
        )
        text = str(raw_text).strip() if raw_text else "You have a new in-app notification."
        if len(text) > 250:
            text = text[:247] + "..."
        if author_name and not text.startswith(author_name):
            message = f"{author_name}: {text}"
        else:
            message = text
        return title, message

    elif event_name == "task:new":
        title = f"New Task Assigned ({context_str})" if context_str else "New Kitsu Task"
        message = f"New task created: {task_name or context_str or 'Task'}"
        if author_name:
            message = f"{author_name} assigned: {message}"
        return title, message

    elif event_name in ("preview:new", "preview:file:new"):
        title = f"New Preview Uploaded ({context_str})" if context_str else "New Preview on Kitsu"
        rev = data.get("revision") or data.get("version")
        message = f"New preview (v{rev}) uploaded" if rev else "A new preview was uploaded."
        if author_name:
            message = f"{author_name}: {message}"
        return title, message

    else:
        title = f"Kitsu: {event_name} ({context_str})" if context_str else f"Kitsu Event: {event_name}"
        raw_text = data.get("text") or data.get("message") or str(data)
        text = str(raw_text).strip()
        if len(text) > 200:
            text = text[:197] + "..."
        message = f"{author_name}: {text}" if author_name else text
        return title, message


class KitsuNotificationWorker(QThread):
    """Background worker QThread that runs the Gazu Socket.IO event loop."""

    notification_received = Signal(str, str, int, dict)  # (title, message, icon_type_value, raw_payload)
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_running = True
        self._event_client = None

    def run(self) -> None:
        """Worker execution loop."""
        logger.info("Starting Kitsu notification worker thread...")

        while self._is_running:
            # 1. Verify authentication
            if not is_kitsu_connected():
                if is_kitsu_configured():
                    logger.debug("Attempting to authenticate Kitsu for notification worker...")
                    success, msg = init_kitsu()
                    if not success:
                        logger.debug(f"Kitsu auth failed in worker: {msg}")
                else:
                    logger.debug("Kitsu is not configured. Waiting before rechecking...")

                # If still not connected, wait before rechecking
                for _ in range(50):
                    if not self._is_running:
                        return
                    time.sleep(0.1)
                continue

            # 2. Initialize Socket.IO event client
            try:
                logger.info("Initializing gazu.events client...")
                event_client = gazu.events.init()
                self._event_client = event_client
            except Exception as e:
                logger.warning(f"Could not connect to Kitsu event stream: {e}")
                self.error_occurred.emit(str(e))
                for _ in range(50):
                    if not self._is_running:
                        return
                    time.sleep(0.1)
                continue

            # 3. Bind event listeners with user filtering
            def make_handler(evt_name: str):
                def handler(data: Any):
                    try:
                        logger.debug(f"Kitsu raw event [{evt_name}]: {data}")
                        enriched = hydrate_kitsu_event(evt_name, data)

                        # Filter: only show notifications relevant to the logged-in user
                        current_uid = get_current_user_id()
                        if not is_event_relevant_to_user(evt_name, enriched, current_uid):
                            logger.debug(
                                f"Event [{evt_name}] filtered out: not relevant to current user {current_uid}"
                            )
                            return

                        title, message = parse_kitsu_event(evt_name, enriched)
                        info_icon = int(QSystemTrayIcon.MessageIcon.Information.value)
                        self.notification_received.emit(title, message, info_icon, enriched)
                    except Exception as err:
                        logger.error(f"Error handling event '{evt_name}': {err}", exc_info=True)

                return handler

            supported_events = [
                "notification:new",
                "comment:new",
                "task:update",
                "task:new",
                "preview:new",
                "preview:file:new",
            ]

            for evt in supported_events:
                try:
                    gazu.events.add_listener(event_client, evt, make_handler(evt))
                except Exception as err:
                    logger.warning(f"Failed to add listener for '{evt}': {err}")

            self.connected.emit()
            logger.info("Connected and listening for Kitsu events.")

            # 4. Run event client (blocking wait loop)
            try:
                gazu.events.run_client(event_client)
            except Exception as e:
                if self._is_running:
                    logger.warning(f"Kitsu event stream connection lost: {e}")
                    self.disconnected.emit()
            finally:
                if self._is_running:
                    # Short pause before reconnection attempt
                    for _ in range(30):
                        if not self._is_running:
                            break
                        time.sleep(0.1)

        logger.info("Kitsu notification worker stopped.")

    def stop(self) -> None:
        """Safely terminate the background event client and thread."""
        self._is_running = False
        if self._event_client is not None:
            try:
                logger.debug("Disconnecting gazu event client...")
                self._event_client.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting event client: {e}")
            self._event_client = None

        self.quit()
        if not self.wait(1500):
            logger.warning("Worker thread did not stop in time; terminating.")
            self.terminate()
            self.wait(500)


class NotificationServiceSignals(QObject):
    """Signals for NotificationService events."""

    history_updated = Signal()
    notification_added = Signal(dict)


class NotificationService:
    """Centralized service for managing Desktop OS Notifications and Kitsu listeners."""

    signals = NotificationServiceSignals()

    _tray_icon: Optional[QSystemTrayIcon] = None
    _worker: Optional[KitsuNotificationWorker] = None
    _parent_window = None
    _history: List[dict] = []
    _notification_menu: Optional[QMenu] = None

    @classmethod
    def initialize(cls, parent_window=None) -> Optional[QSystemTrayIcon]:
        """Initialize the QSystemTrayIcon and attach to parent window if available."""
        if cls._tray_icon is not None:
            if parent_window is not None:
                cls._parent_window = parent_window
            return cls._tray_icon

        cls._parent_window = parent_window

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("System tray is not available in current environment; running without system tray.")
            return None

        try:
            # Check system tray support
            tray = QSystemTrayIcon(parent_window)
            cls._tray_icon = tray

            # Set default tray icon
            icon = cls._create_default_icon()
            tray.setIcon(icon)
            tray.setToolTip(f"{config.APP_NAME} - Production Hub")

            # Build Context Menu with dynamic Notifications submenu
            menu = QMenu()
            restore_action = menu.addAction(f"Show {config.APP_NAME}")
            if parent_window is not None:
                restore_action.triggered.connect(cls._restore_window)

            menu.addSeparator()

            # Dynamic Notification History Menu
            cls._notification_menu = menu.addMenu("Notifications (0)")
            cls._rebuild_notification_menu()

            menu.addSeparator()
            quit_action = menu.addAction("Quit")
            app_inst = QApplication.instance()
            if app_inst:
                quit_action.triggered.connect(app_inst.quit)

            tray.setContextMenu(menu)

            # Wire activation and click events
            tray.activated.connect(cls._on_tray_activated)
            tray.messageClicked.connect(cls._on_message_clicked)

            tray.show()
            logger.info("NotificationService initialized with QSystemTrayIcon.")
            return tray
        except Exception as e:
            logger.warning(f"Could not initialize system tray icon: {e}")
            cls._tray_icon = None
            return None

    @classmethod
    def _create_default_icon(cls) -> QIcon:
        """Resolve a suitable application icon for system tray notification."""
        # 1. Check local assets if present
        for candidate in [
            config.ASSETS_DIR / "icons" / "icon.png",
            config.ASSETS_DIR / "icons" / "zeroxe.png",
            config.ASSETS_DIR / "icon.png",
            config.ASSETS_DIR / "zeroxe.png",
            config.BASE_DIR / "assets" / "icons" / "icon.png",
            config.BASE_DIR / "assets" / "icons" / "zeroxe.png",
            config.BASE_DIR / "assets" / "icon.png",
        ]:
            if candidate.is_file():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon

        # 2. Check standard Qt application style icon
        app = QApplication.instance()
        if app and app.style():
            std_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            if not std_icon.isNull():
                return std_icon

        # 3. Fallback: generate a clean high-contrast stylized Z icon pixmap
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 32, 32, 6, 6)

        painter.setPen(QColor("#ffffff"))
        font = QFont("Sans-Serif", 16, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, 32, 32, Qt.AlignmentFlag.AlignCenter, "Z")
        painter.end()
        return QIcon(pixmap)

    @classmethod
    def _restore_window(cls) -> None:
        """Bring the main application window to the foreground."""
        if cls._parent_window is not None:
            cls._parent_window.showNormal()
            cls._parent_window.raise_()
            cls._parent_window.activateWindow()

    @classmethod
    def _on_tray_activated(cls, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle user clicking or double-clicking the tray icon."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            cls._restore_window()

    @classmethod
    def _on_message_clicked(cls) -> None:
        """Handle user clicking on an active notification bubble to pop open its details."""
        cls._restore_window()
        if cls._history:
            latest = cls._history[0]
            cls.show_notification_detail_dialog(latest)

    @classmethod
    def show_notification_detail_dialog(cls, item: dict, parent=None) -> None:
        """Pop open a clean detail dialog for a specific notification from the notification menu."""
        title = item.get("title", "Kitsu Notification")
        message = item.get("message", "")
        timestamp = item.get("timestamp", "")

        p = parent or cls._parent_window
        dialog = QDialog(p)
        dialog.setWindowTitle(f"Notification: {title}")
        dialog.resize(440, 240)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)

        header_label = QLabel(f"<b>{title}</b>")
        header_label.setWordWrap(True)
        header_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(header_label)

        if timestamp:
            time_label = QLabel(f"<span style='color: gray; font-size: 11px;'>Received at {timestamp}</span>")
            layout.addWidget(time_label)

        text_edit = QTextEdit()
        text_edit.setPlainText(message)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.close)
        layout.addWidget(btn_box)

        dialog.exec()

    @classmethod
    def _rebuild_notification_menu(cls) -> None:
        """Refresh the notifications submenu in the tray."""
        if cls._notification_menu is None:
            return

        cls._notification_menu.clear()
        count = len(cls._history)
        cls._notification_menu.setTitle(f"Notifications ({count})")

        if not cls._history:
            empty_action = cls._notification_menu.addAction("No recent notifications")
            empty_action.setEnabled(False)
            return

        for item in cls._history[:15]:
            ts = item.get("timestamp", "")
            title = item.get("title", "")
            msg = item.get("message", "")
            preview = f"[{ts}] {title}: {msg}"
            if len(preview) > 55:
                preview = preview[:52] + "..."

            action = cls._notification_menu.addAction(preview)
            action.triggered.connect(
                lambda checked=False, it=item: cls.show_notification_detail_dialog(it)
            )

        cls._notification_menu.addSeparator()
        clear_action = cls._notification_menu.addAction("Clear Notifications")
        clear_action.triggered.connect(cls.clear_notifications)

    @classmethod
    def clear_notifications(cls) -> None:
        """Clear stored notification history."""
        cls._history.clear()
        cls._rebuild_notification_menu()
        cls.signals.history_updated.emit()

    @classmethod
    def get_notifications(cls) -> List[dict]:
        """Return the list of recent notifications."""
        return list(cls._history)

    @classmethod
    def show_notification(
        cls,
        title: str,
        message: str,
        icon_type: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        msecs: int = 5000,
        force: bool = False,
        raw_payload: Optional[dict] = None,
    ) -> None:
        """Display a native OS notification and pop it into the Notification Menu.

        Args:
            title: Notification header.
            message: Notification content text.
            icon_type: QSystemTrayIcon.MessageIcon type.
            msecs: Duration in milliseconds before auto-dismissal.
            force: If True, bypass notification enable setting.
            raw_payload: Optional raw/enriched Kitsu event data.
        """
        from zeroxe.services.settings_service import SettingsService

        if not force and not SettingsService.get_kitsu_notification_enabled():
            logger.debug(f"Notification skipped (disabled in settings): [{title}] {message}")
            return

        logger.info(f"OS Notification: [{title}] {message}")

        # 1. Record in notification history (most recent first)
        now_str = datetime.now().strftime("%H:%M:%S")
        record = {
            "title": title,
            "message": message,
            "timestamp": now_str,
            "raw": raw_payload or {},
        }
        cls._history.insert(0, record)
        if len(cls._history) > 50:
            cls._history.pop()

        cls._rebuild_notification_menu()
        cls.signals.history_updated.emit()
        cls.signals.notification_added.emit(record)

        # 2. Native OS System Notification (pops in OS notification center / tray)
        if cls._tray_icon is not None and QSystemTrayIcon.isSystemTrayAvailable():
            try:
                cls._tray_icon.showMessage(title, message, icon_type, msecs)
            except Exception as e:
                logger.debug(f"Failed to display OS system notification: {e}")

    @classmethod
    def start_kitsu_listener(cls) -> None:
        """Start or restart the background Kitsu real-time event worker."""
        cls.stop_kitsu_listener()

        from zeroxe.services.settings_service import SettingsService

        if not SettingsService.get_kitsu_notification_enabled():
            logger.info("Kitsu notifications are disabled in settings. Listener will not start.")
            return

        logger.info("Launching Kitsu Notification Worker...")
        worker = KitsuNotificationWorker()
        cls._worker = worker

        def on_received(title: str, message: str, icon_val: int, raw_payload: dict):
            icon_enum = QSystemTrayIcon.MessageIcon(icon_val)
            cls.show_notification(title, message, icon_enum, raw_payload=raw_payload)

        worker.notification_received.connect(on_received)
        worker.start()

    @classmethod
    def stop_kitsu_listener(cls) -> None:
        """Stop and terminate the background Kitsu worker thread if active."""
        if cls._worker is not None:
            logger.info("Stopping Kitsu Notification Worker...")
            try:
                cls._worker.stop()
            except Exception as e:
                logger.warning(f"Exception stopping worker: {e}")
            cls._worker = None

    @classmethod
    def is_kitsu_listener_running(cls) -> bool:
        """Return True if the background worker thread is currently alive."""
        return bool(cls._worker and cls._worker.isRunning())

    @classmethod
    def shutdown(cls) -> None:
        """Cleanup tray icon and stop worker thread upon application exit."""
        cls.stop_kitsu_listener()
        if cls._tray_icon is not None:
            try:
                cls._tray_icon.hide()
            except Exception:
                pass
            cls._tray_icon = None
        cls._notification_menu = None
        cls._parent_window = None
