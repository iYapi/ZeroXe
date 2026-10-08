# ZeroXe Notification & Kitsu Real-Time Event System Guide

This guide explains the architecture, background worker, user filtering rules, system tray integration, and settings of the **Notification System** (`src/zeroxe/services/notification_service.py`) in **ZeroXe**.

---

## 1. Overview & Architecture

The ZeroXe Notification System provides native OS desktop alerts and a centralized in-app notification history menu. It listens in real-time to Kitsu Socket.IO / WebSocket events, resolving missing context and filtering out irrelevant notifications.

```mermaid
flowchart TD
    Kitsu["Kitsu Server (WebSockets / Socket.IO)"] -->|Event Streams| Worker["KitsuNotificationWorker (Dedicated QThread)"]
    Worker --> Hydrate["Event Hydration (hydrate_kitsu_event)"]
    Hydrate --> Filter["User Filtering (is_event_relevant_to_user)"]
    Filter --> Parser["Payload Parser (parse_kitsu_event)"]
    Parser --> Service["NotificationService"]
    
    Service --> TrayBubble["OS Native Notification (QSystemTrayIcon)"]
    Service --> TrayMenu["System Tray Context Menu (Recent Notifications)"]
    Service --> MenuBar["Main Window Menubar (&Notifications Menu)"]
    Service --> Dialog["Detail Dialog (show_notification_detail_dialog)"]
    
    Settings["SettingsService (kitsu/notification_enabled)"] -.->|Toggle On/Off| Service
    Settings -.->|Start/Stop Worker| Worker
```

---

## 2. Key Features

1. **Native OS Notifications**: Displays popups via `QSystemTrayIcon.showMessage()` in the user's OS notification center with application icon branding.
2. **Real-Time Background Listener**: Runs `KitsuNotificationWorker` on a non-blocking background `QThread` using `gazu.events` (Socket.IO).
3. **Smart User Filtering**:
   - **Ignores Self-Actions**: If the current logged-in user posts a comment, changes a status, or creates a task, no self-notification is triggered.
   - **Direct Notifications**: For `notification:new`, only shows events targeted to the current user's ID.
   - **Task Updates & Comments**: Only notifies if the task is assigned to the current user.
4. **Data Hydration**: Kitsu Socket.IO events often carry minimal IDs (`task_id`, `person_id`, `project_id`). The hydrator queries the Gazu API/cache to resolve full project codes, entity names, task types, author names, and status names.
5. **Project Code & Task Type Formatting**:
   - Uses **Project Code / Short Name** (e.g. `MDT` instead of full name `MELANGKAH DARI TIMUR`).
   - Prioritizes **Task Type / Department** (e.g. `Lighting`, `Animation`) over internal sub-task stream names (`"main"`).
   - Example Header: `New Comment (MDT | sq01_sh010 | Lighting)`
6. **Notification History & Detail Viewer**:
   - Stores the 50 most recent notifications.
   - Viewable from both the **System Tray Menu** and the **Main Window Menu Bar** (`&Notifications`).
   - Clicking any notification opens a detail popup displaying timestamp, sender, and full comment body.
   - Includes a **`Clear Notifications`** option.

---

## 3. Supported Kitsu Event Types

| Event Identifier | Description | Formatted Output Example |
| :--- | :--- | :--- |
| `comment:new` | A note/comment posted on a task | `New Comment (MDT \| sq01_sh010 \| Lighting)`<br>`Jane Doe: Please adjust rim light.` |
| `task:update` | Status change on an assigned task | `Task Updated (MDT \| Hero_Prop \| Modeling)`<br>`Bob Lead changed status to 'Approved'` |
| `notification:new` | Direct in-app Kitsu notification | `Kitsu Notification (MDT \| sq01_sh010 \| Lighting)`<br>`Director Lee: Assigned you to shot.` |
| `task:new` | New task assigned to user | `New Task Assigned (MDT \| sh050 \| Layout)`<br>`Prod Mgr assigned: New task created: Layout` |
| `preview:new` | New preview/version uploaded | `New Preview Uploaded (MDT \| sh010 \| Comp)`<br>`Artist One: New preview (v2) uploaded` |

---

## 4. Configuration & Settings

### In Settings UI
Navigate to **`Edit > Settings > Kitsu`**:
- Check/uncheck **`Notification:`** (`checkBox_notification`).
- Clicking **`Apply`** or **`OK`** immediately starts or stops the background `KitsuNotificationWorker` without restarting the application.

### Settings Persistence
Saved in `QSettings`:
- Key: `kitsu/notification_enabled` (`bool`)

---

## 5. Python API Reference

```python
from zeroxe.services.notification_service import NotificationService

# Initialize tray icon with parent window
NotificationService.initialize(main_window)

# Start real-time background listener
NotificationService.start_kitsu_listener()

# Trigger custom notification
NotificationService.show_notification(
    title="Render Complete",
    message="Frame range 101-200 finished rendering.",
)

# Access history
history = NotificationService.get_notifications()

# Clean shutdown
NotificationService.shutdown()
```
