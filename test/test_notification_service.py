"""Tests for NotificationService and Kitsu Real-Time Notification worker."""

import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from zeroxe.services.notification_service import (
    NotificationService,
    KitsuNotificationWorker,
    parse_kitsu_event,
)
from zeroxe.services.settings_service import SettingsService


class TestNotificationParser(unittest.TestCase):
    """Test suite for Kitsu event payload parsing into OS notifications."""

    def test_parse_comment_new_with_full_metadata(self):
        payload = {
            "text": "Please adjust the rim light on character.",
            "person": {"first_name": "Jane", "last_name": "Doe"},
            "project": {"name": "ProjectAlpha", "code": "PA"},
            "entity": {"name": "sq01_sh010"},
            "task": {"name": "Lighting"},
        }
        title, message = parse_kitsu_event("comment:new", payload)
        self.assertIn("PA | sq01_sh010 | Lighting", title)
        self.assertEqual(message, "Jane Doe: Please adjust the rim light on character.")

    def test_parse_project_code_precedence(self):
        # Code should be prioritized over full name
        payload = {
            "project": {"name": "Melangkah Dari Timur", "code": "MDT"},
            "entity": {"name": "sh010"},
            "task": {"name": "Animation"},
        }
        title, _ = parse_kitsu_event("task:new", payload)
        self.assertIn("MDT | sh010 | Animation", title)

    def test_parse_project_short_name(self):
        payload = {
            "project": {"name": "ZeroXe Production", "short_name": "ZRX"},
            "entity": {"name": "prop_sword"},
        }
        title, _ = parse_kitsu_event("task:new", payload)
        self.assertIn("ZRX | prop_sword", title)

    def test_parse_task_type_priority_over_main(self):
        # Kitsu tasks have name="main" and task_type_name="Lighting".
        # We must display "Lighting", not "main".
        payload = {
            "project": {"code": "MDT"},
            "entity": {"name": "sq01_sh010"},
            "task": {"name": "main", "task_type_name": "Lighting"},
        }
        title, _ = parse_kitsu_event("task:update", payload)
        self.assertEqual(title, "Task Updated (MDT | sq01_sh010 | Lighting)")

    def test_parse_task_type_with_custom_subtask_name(self):
        payload = {
            "project": {"code": "MDT"},
            "entity": {"name": "sq01_sh010"},
            "task": {"name": "retake_01", "task_type_name": "Lighting"},
        }
        title, _ = parse_kitsu_event("task:update", payload)
        self.assertEqual(title, "Task Updated (MDT | sq01_sh010 | Lighting (retake_01))")

    def test_parse_project_fallback_to_name_if_no_code(self):
        payload = {
            "project": {"name": "ProjectAlpha"},
            "entity": {"name": "sq01_sh010"},
            "task": {"task_type_name": "Lighting"},
        }
        title, _ = parse_kitsu_event("comment:new", payload)
        self.assertIn("ProjectAlpha | sq01_sh010 | Lighting", title)

    def test_parse_comment_new_minimal(self):
        payload = {"text": "Simple note"}
        title, message = parse_kitsu_event("comment:new", payload)
        self.assertEqual(title, "New Kitsu Comment")
        self.assertEqual(message, "Simple note")

    def test_parse_task_update_with_status_and_author(self):
        payload = {
            "task_status": {"name": "Approved"},
            "person": {"first_name": "Bob", "last_name": "Lead"},
            "entity": {"name": "Hero_Prop"},
            "task": {"name": "Modeling"},
        }
        title, message = parse_kitsu_event("task:update", payload)
        self.assertIn("Hero_Prop | Modeling", title)
        self.assertEqual(message, "Bob Lead changed status to: Approved")

    def test_parse_task_update_without_author(self):
        payload = {
            "task_status_name": "In Progress",
            "task_type_name": "Animation",
            "entity_name": "sh020",
        }
        title, message = parse_kitsu_event("task:update", payload)
        self.assertIn("sh020 | Animation", title)
        self.assertEqual(message, "Status changed to: In Progress")

    def test_parse_notification_new_activity(self):
        payload = {
            "activity": {"comment": "Assigned you to scene cleanup."},
            "person": {"first_name": "Director", "last_name": "Lee"},
        }
        title, message = parse_kitsu_event("notification:new", payload)
        self.assertEqual(title, "New Kitsu Notification")
        self.assertEqual(message, "Director Lee: Assigned you to scene cleanup.")

    def test_parse_task_new(self):
        payload = {
            "task_name": "Layout",
            "entity_name": "sh050",
            "person": {"first_name": "Prod", "last_name": "Mgr"},
        }
        title, message = parse_kitsu_event("task:new", payload)
        self.assertIn("sh050 | Layout", title)
        self.assertIn("Prod Mgr assigned", message)

    def test_parse_preview_new(self):
        payload = {
            "revision": 2,
            "entity": {"name": "sh010"},
            "task": {"name": "Comp"},
            "person": {"first_name": "Artist", "last_name": "One"},
        }
        title, message = parse_kitsu_event("preview:new", payload)
        self.assertIn("sh010 | Comp", title)
        self.assertIn("Artist One: New preview (v2) uploaded", message)

    def test_parse_non_dict_payload(self):
        title, message = parse_kitsu_event("custom:ping", "Server ping OK")
        self.assertEqual(title, "Kitsu: custom:ping")
        self.assertEqual(message, "Server ping OK")

    def test_parse_long_text_truncation(self):
        long_str = "x" * 500
        payload = {"text": long_str}
        title, message = parse_kitsu_event("comment:new", payload)
        self.assertTrue(len(message) <= 250)
        self.assertTrue(message.endswith("..."))

    def test_parse_with_episode_and_sequence(self):
        payload = {
            "project": {"code": "MDT"},
            "episode": "ep998",
            "sequence": "sq01",
            "entity": {"name": "sh010"},
            "task": {"name": "Lighting"},
            "text": "Review note",
        }
        title, _ = parse_kitsu_event("comment:new", payload)
        self.assertEqual(title, "New Comment (MDT | ep998 | sq01 | sh010 | Lighting)")

    def test_parse_with_sequence_only(self):
        payload = {
            "project": {"code": "MDT"},
            "sequence": "sq02",
            "entity": {"name": "sh030"},
            "task": {"name": "Animation"},
        }
        title, _ = parse_kitsu_event("task:new", payload)
        self.assertEqual(title, "New Task Assigned (MDT | sq02 | sh030 | Animation)")

    def test_parse_with_episode_and_composite_shot_name(self):
        # Sequence name is already in entity name (sq01_sh010), so sq01 is not duplicated
        payload = {
            "project": {"code": "MDT"},
            "episode": "ep998",
            "sequence": "sq01",
            "entity": {"name": "sq01_sh010"},
            "task": {"name": "Lighting"},
        }
        title, _ = parse_kitsu_event("task:update", payload)
        self.assertEqual(title, "Task Updated (MDT | ep998 | sq01_sh010 | Lighting)")


class TestEventHydration(unittest.TestCase):
    """Test suite for resolving raw Kitsu event IDs via Gazu."""

    @patch("gazu.task.get_task")
    @patch("gazu.task.get_task_status")
    @patch("gazu.person.get_person")
    def test_hydrate_task_update_with_ids(self, mock_get_person, mock_get_status, mock_get_task):
        from zeroxe.services.notification_service import hydrate_kitsu_event

        mock_get_task.return_value = {
            "id": "task-001",
            "name": "Animation",
            "task_type_name": "Animation",
            "entity_name": "sq01_sh010",
            "sequence_name": "sq01",
            "episode_name": "ep998",
            "project_name": "ZeroXeProject",
            "project_code": "ZRX",
            "task_status_name": "WIP",
            "task_status_id": "status-002",
        }
        mock_get_status.return_value = {"id": "status-002", "name": "Approved"}
        mock_get_person.return_value = {
            "id": "person-003",
            "first_name": "Alice",
            "last_name": "Lead",
        }

        raw_event = {
            "task_id": "task-001",
            "task_status_id": "status-002",
            "person_id": "person-003",
        }

        enriched = hydrate_kitsu_event("task:update", raw_event)
        title, message = parse_kitsu_event("task:update", enriched)

        self.assertEqual(title, "Task Updated (ZRX | ep998 | sq01_sh010 | Animation)")
        self.assertEqual(message, "Alice Lead changed status to: Approved")

    @patch("gazu.entity.get_entity")
    @patch("gazu.task.get_comment")
    @patch("gazu.task.get_task")
    @patch("gazu.person.get_person")
    def test_hydrate_hierarchy_via_parent_entity(self, mock_get_person, mock_get_task, mock_get_comment, mock_get_entity):
        from zeroxe.services.notification_service import hydrate_kitsu_event

        mock_get_comment.return_value = {
            "id": "comment-001",
            "text": "Great lighting pass!",
            "task_id": "task-001",
            "person_id": "person-002",
        }
        mock_get_task.return_value = {
            "id": "task-001",
            "name": "Lighting",
            "task_type_name": "Lighting",
            "entity_id": "shot-001",
            "project_name": "ZeroXeProject",
            "project_code": "ZRX",
        }
        mock_get_person.return_value = {
            "id": "person-002",
            "first_name": "Bob",
            "last_name": "Reviewer",
        }

        def mock_entity_lookup(entity_id):
            if entity_id == "shot-001":
                return {"id": "shot-001", "name": "sh020", "parent_id": "seq-001"}
            elif entity_id == "seq-001":
                return {"id": "seq-001", "name": "sq02", "parent_id": "ep-001"}
            elif entity_id == "ep-001":
                return {"id": "ep-001", "name": "ep998"}
            return {}

        mock_get_entity.side_effect = mock_entity_lookup

        raw_event = {"comment_id": "comment-001"}
        enriched = hydrate_kitsu_event("comment:new", raw_event)
        title, message = parse_kitsu_event("comment:new", enriched)

        self.assertEqual(title, "New Comment (ZRX | ep998 | sq02 | sh020 | Lighting)")
        self.assertEqual(message, "Bob Reviewer: Great lighting pass!")

    @patch("gazu.task.get_comment")
    @patch("gazu.task.get_task")
    @patch("gazu.person.get_person")
    def test_hydrate_comment_new_with_ids(self, mock_get_person, mock_get_task, mock_get_comment):
        from zeroxe.services.notification_service import hydrate_kitsu_event

        mock_get_comment.return_value = {
            "id": "comment-001",
            "text": "Great lighting pass!",
            "task_id": "task-001",
            "person_id": "person-002",
        }
        mock_get_task.return_value = {
            "id": "task-001",
            "name": "Lighting",
            "task_type_name": "Lighting",
            "entity_name": "sq01_sh020",
            "project_name": "ZeroXeProject",
            "project_code": "ZRX",
        }
        mock_get_person.return_value = {
            "id": "person-002",
            "first_name": "Bob",
            "last_name": "Reviewer",
        }

        raw_event = {"comment_id": "comment-001"}
        enriched = hydrate_kitsu_event("comment:new", raw_event)
        title, message = parse_kitsu_event("comment:new", enriched)

        self.assertEqual(title, "New Comment (ZRX | sq01_sh020 | Lighting)")
        self.assertEqual(message, "Bob Reviewer: Great lighting pass!")


class TestUserFiltering(unittest.TestCase):
    """Test suite for filtering Kitsu events specifically for the logged-in user."""

    def test_ignore_self_actions(self):
        from zeroxe.services.notification_service import is_event_relevant_to_user

        event_data = {
            "person_id": "user-current-123",
            "task": {"assignees": [{"id": "user-current-123"}]},
        }
        # Self-action should be ignored
        self.assertFalse(is_event_relevant_to_user("task:update", event_data, "user-current-123"))

    def test_assigned_task_update_is_relevant(self):
        from zeroxe.services.notification_service import is_event_relevant_to_user

        event_data = {
            "person_id": "lead-456",
            "task": {
                "id": "task-001",
                "assignees": [{"id": "user-current-123"}, {"id": "other-789"}],
            },
        }
        self.assertTrue(is_event_relevant_to_user("task:update", event_data, "user-current-123"))

    def test_unassigned_task_update_is_filtered_out(self):
        from zeroxe.services.notification_service import is_event_relevant_to_user

        event_data = {
            "person_id": "lead-456",
            "task": {
                "id": "task-999",
                "assignees": [{"id": "other-user-789"}],
            },
        }
        self.assertFalse(is_event_relevant_to_user("task:update", event_data, "user-current-123"))

    def test_direct_notification_recipient(self):
        from zeroxe.services.notification_service import is_event_relevant_to_user

        # Notification addressed to current user
        notif_for_me = {"person_id": "lead-456", "recipient_id": "user-current-123"}
        self.assertTrue(is_event_relevant_to_user("notification:new", notif_for_me, "user-current-123"))

        # Notification addressed to someone else
        notif_for_other = {"person_id": "lead-456", "recipient_id": "other-user-789"}
        self.assertFalse(is_event_relevant_to_user("notification:new", notif_for_other, "user-current-123"))


class TestNotificationMenuAndHistory(unittest.TestCase):
    """Test suite for notification history tracking and detail dialog."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        NotificationService.shutdown()

    def tearDown(self):
        NotificationService.shutdown()

    def test_notification_history_and_clear(self):
        widget = QWidget()
        NotificationService.initialize(widget)

        self.assertEqual(len(NotificationService.get_notifications()), 0)
        NotificationService.show_notification("Notif 1", "Message 1", force=True)
        NotificationService.show_notification("Notif 2", "Message 2", force=True)

        history = NotificationService.get_notifications()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["title"], "Notif 2")
        self.assertEqual(history[1]["title"], "Notif 1")

        NotificationService.clear_notifications()
        self.assertEqual(len(NotificationService.get_notifications()), 0)


class TestNotificationService(unittest.TestCase):
    """Test suite for NotificationService and QSystemTrayIcon interaction."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        NotificationService.shutdown()

    def tearDown(self):
        NotificationService.shutdown()

    def test_initialize_and_show_notification(self):
        widget = QWidget()
        tray = NotificationService.initialize(widget)
        self.assertIsNotNone(tray)
        self.assertIsInstance(tray, QSystemTrayIcon)
        self.assertFalse(tray.icon().isNull())

        # Test show_notification call when enabled
        with patch.object(SettingsService, "get_kitsu_notification_enabled", return_value=True), \
             patch.object(tray, "showMessage") as mock_show:
            NotificationService.show_notification("Test Title", "Test Body")
            mock_show.assert_called_once()
            args, _ = mock_show.call_args
            self.assertEqual(args[0], "Test Title")
            self.assertEqual(args[1], "Test Body")

    def test_show_notification_suppressed_when_disabled(self):
        widget = QWidget()
        tray = NotificationService.initialize(widget)

        with patch.object(SettingsService, "get_kitsu_notification_enabled", return_value=False), \
             patch.object(tray, "showMessage") as mock_show:
            NotificationService.show_notification("Test Title", "Test Body")
            mock_show.assert_not_called()

            # Forced notification still shows
            NotificationService.show_notification("Forced Title", "Forced Body", force=True)
            mock_show.assert_called_once()

    def test_listener_start_and_stop_when_enabled(self):
        with patch.object(SettingsService, "get_kitsu_notification_enabled", return_value=True), \
             patch("zeroxe.services.notification_service.is_kitsu_connected", return_value=False), \
             patch("zeroxe.services.notification_service.is_kitsu_configured", return_value=False):
            NotificationService.start_kitsu_listener()
            self.assertTrue(NotificationService.is_kitsu_listener_running())
            NotificationService.stop_kitsu_listener()
            self.assertFalse(NotificationService.is_kitsu_listener_running())

    def test_listener_does_not_start_when_disabled(self):
        with patch.object(SettingsService, "get_kitsu_notification_enabled", return_value=False):
            NotificationService.start_kitsu_listener()
            self.assertFalse(NotificationService.is_kitsu_listener_running())

    def test_worker_stop_cleanly(self):
        worker = KitsuNotificationWorker()
        mock_client = MagicMock()
        mock_client.connected = True
        worker._event_client = mock_client

        worker.stop()
        mock_client.disconnect.assert_called_once()
        self.assertFalse(worker._is_running)


class TestSettingsServiceNotification(unittest.TestCase):
    """Test suite for notification settings persistence."""

    def test_get_set_notification_enabled(self):
        # Save original state
        orig = SettingsService.get_kitsu_notification_enabled()
        try:
            SettingsService.set_kitsu_notification_enabled(False)
            self.assertFalse(SettingsService.get_kitsu_notification_enabled())

            SettingsService.set_kitsu_notification_enabled(True)
            self.assertTrue(SettingsService.get_kitsu_notification_enabled())
        finally:
            SettingsService.set_kitsu_notification_enabled(orig)


if __name__ == "__main__":
    unittest.main()
