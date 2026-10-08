"""Notification View Component.

Pure PySide6 presentation widget for displaying real-time notification history.
Binds to zeroxe.ui.ui_notification.Ui_Form and synchronizes with NotificationService.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QWidget,
)

from zeroxe.services.notification_service import NotificationService
from zeroxe.ui.ui_notification import Ui_Form


class NotificationView(QWidget):
    """Notification tab view displaying recent notification history."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self._init_model()
        self._setup_view()
        self._connect_signals()
        self.refresh_notifications()

    def _init_model(self) -> None:
        """Initialize the item model for the notification list."""
        self.model = QStandardItemModel(self)
        self.ui.listView_notification.setModel(self.model)

    def _setup_view(self) -> None:
        """Configure list view properties and context menu."""
        self.ui.listView_notification.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.ui.listView_notification.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.ui.listView_notification.customContextMenuRequested.connect(
            self._show_context_menu
        )
        self.ui.listView_notification.doubleClicked.connect(
            self._on_item_double_clicked
        )

    def _connect_signals(self) -> None:
        """Connect to NotificationService signals for live updates."""
        NotificationService.signals.history_updated.connect(
            self.refresh_notifications
        )

    def refresh_notifications(self) -> None:
        """Reload the list of notifications from NotificationService."""
        self.model.clear()
        notifications = NotificationService.get_notifications()

        if not notifications:
            placeholder = QStandardItem("No notifications")
            placeholder.setEnabled(False)
            self.model.appendRow(placeholder)
            return

        for item in notifications:
            title = item.get("title", "Notification")
            message = item.get("message", "")
            ts = item.get("timestamp", "")

            display_text = f"[{ts}] {title}\n  {message}" if ts else f"{title}\n  {message}"
            list_item = QStandardItem(display_text)
            list_item.setData(item, Qt.ItemDataRole.UserRole)
            self.model.appendRow(list_item)

    def _on_item_double_clicked(self, index) -> None:
        """Open detail dialog when user double-clicks a notification."""
        item = self.model.itemFromIndex(index)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            NotificationService.show_notification_detail_dialog(data, parent=self)

    def _show_context_menu(self, pos) -> None:
        """Show right-click context menu on notification list."""
        index = self.ui.listView_notification.indexAt(pos)
        menu = QMenu(self)

        if index.isValid():
            item = self.model.itemFromIndex(index)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(data, dict):
                action_view = menu.addAction("View Details")
                action_view.triggered.connect(
                    lambda: NotificationService.show_notification_detail_dialog(
                        data, parent=self
                    )
                )
                menu.addSeparator()

        action_clear = menu.addAction("Clear Notifications")
        action_clear.triggered.connect(NotificationService.clear_notifications)

        action_refresh = menu.addAction("Refresh")
        action_refresh.triggered.connect(self.refresh_notifications)

        menu.exec(self.ui.listView_notification.viewport().mapToGlobal(pos))
