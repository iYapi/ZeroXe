"""Unit tests for NotificationView and UI integration."""

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from zeroxe.services.notification_service import NotificationService
from zeroxe.views.main_view import MainView
from zeroxe.views.notification_view import NotificationView


class TestNotificationView(unittest.TestCase):
    """Test suite for NotificationView component."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        NotificationService.shutdown()
        NotificationService.clear_notifications()

    def tearDown(self):
        NotificationService.shutdown()
        NotificationService.clear_notifications()

    def test_notification_view_initialization_empty(self):
        """Test that NotificationView initializes with an empty placeholder when no notifications exist."""
        view = NotificationView()
        self.assertIsNotNone(view.ui.listView_notification)
        self.assertEqual(view.model.rowCount(), 1)
        item = view.model.item(0)
        self.assertEqual(item.text(), "No notifications")
        self.assertFalse(item.isEnabled())

    def test_notification_view_populates_items(self):
        """Test that NotificationView displays notifications in chronological order."""
        NotificationService.show_notification("Task Updated", "Lighting is WIP", force=True)
        NotificationService.show_notification("New Comment", "Looks great!", force=True)

        view = NotificationView()
        self.assertEqual(view.model.rowCount(), 2)

        first_item = view.model.item(0)
        self.assertIn("New Comment", first_item.text())
        self.assertIn("Looks great!", first_item.text())

        second_item = view.model.item(1)
        self.assertIn("Task Updated", second_item.text())
        self.assertIn("Lighting is WIP", second_item.text())

    def test_notification_view_auto_updates_on_new_notification(self):
        """Test that NotificationView updates in real-time when a new notification is emitted."""
        view = NotificationView()
        self.assertEqual(view.model.rowCount(), 1)  # placeholder

        NotificationService.show_notification("Realtime Title", "Realtime Message", force=True)
        self.assertEqual(view.model.rowCount(), 1)
        self.assertIn("Realtime Title", view.model.item(0).text())

    def test_notification_view_auto_updates_on_clear(self):
        """Test that NotificationView resets to placeholder when notifications are cleared."""
        NotificationService.show_notification("Item 1", "Msg 1", force=True)
        view = NotificationView()
        self.assertEqual(view.model.rowCount(), 1)
        self.assertIn("Item 1", view.model.item(0).text())

        NotificationService.clear_notifications()
        self.assertEqual(view.model.rowCount(), 1)
        self.assertEqual(view.model.item(0).text(), "No notifications")

    def test_notification_double_click_opens_dialog(self):
        """Test double-clicking an item invokes show_notification_detail_dialog."""
        NotificationService.show_notification("Detail Item", "Detailed info", force=True)
        view = NotificationView()
        index = view.model.index(0, 0)

        with patch.object(NotificationService, "show_notification_detail_dialog") as mock_dlg:
            view._on_item_double_clicked(index)
            mock_dlg.assert_called_once()
            called_item = mock_dlg.call_args[0][0]
            self.assertEqual(called_item["title"], "Detail Item")

    def test_main_view_contains_notification_tab(self):
        """Test that MainView includes Launcher, Notification, and Logs tabs."""
        with patch.object(NotificationService, "start_kitsu_listener"):
            main_view = MainView()
            self.assertEqual(main_view.tab_widget.count(), 3)
            self.assertEqual(main_view.tab_widget.tabText(0), "Launcher")
            self.assertEqual(main_view.tab_widget.tabText(1), "Notification")
            self.assertEqual(main_view.tab_widget.tabText(2), "Logs")
            self.assertIsInstance(main_view.notification_view, NotificationView)


if __name__ == "__main__":
    unittest.main()
