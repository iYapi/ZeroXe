# ZeroXe Development Workflow & Cookbook

A practical step-by-step guide for creating new features, screens, and components in the **ZeroXe** project.

---

## Step-by-Step: Adding a New Screen / Feature

Follow these 6 steps whenever you create a new UI feature:

### Step 1: Design the UI in Qt Designer
1. Open Qt Designer (or use `pyside6-designer`).
2. Create a `Widget` (or `Dialog` / `MainWindow`).
3. Save the file into the `ui/` directory (e.g. `ui/settings.ui`).
4. **Naming Convention**: Give widgets clear `objectName` identifiers:
   - Buttons: `pushButton_apply`, `pushButton_exit`
   - Inputs: `lineEdit_search`, `comboBox_app`
   - Views: `listView_items`, `tableView_details`
   - Labels: `label_title`, `label_status`

---

### Step 2: Compile the UI to Python
Run the automated compiler script:

```bash
# One-time compilation of all .ui files:
python scripts/compile_ui.py

# OR during active design, run watch mode:
python scripts/compile_ui.py --watch
```

This generates `src/zeroxe/ui/ui_settings.py` containing the compiled `Ui_Form` class.

---

### Step 3: Define Data Models (`src/zeroxe/models/`)
Create a dataclass representing the data your feature handles:

```python
# src/zeroxe/models/settings_model.py
from dataclasses import dataclass

@dataclass
class AppSettings:
    default_project: str
    dcc_executable_path: str
    auto_check_update: bool = True
```

---

### Step 4: Implement the Service Layer (`src/zeroxe/services/`)
Create pure Python logic to fetch, save, or process data without importing Qt GUI widgets:

```python
# src/zeroxe/services/settings_service.py
from typing import List
from PySide6.QtCore import QSettings
from zeroxe import config
from zeroxe.utils.security import decrypt_string

class SettingsService:
    @classmethod
    def _settings(cls) -> QSettings:
        return QSettings(config.ORGANIZATION_NAME, config.APP_NAME)

    @classmethod
    def get_kitsu_password(cls) -> str:
        encrypted = cls._settings().value("kitsu/password_enc", "", type=str)
        return decrypt_string(encrypted)

    @classmethod
    def get_active_blender(cls) -> str:
        return cls._settings().value("software/active_blender", "", type=str)
```

---

### Step 5: Implement the Controller Layer (`src/zeroxe/controllers/`)
Create the Controller to wire signals, validate forms, open file dialogs, and call Services:

```python
# src/zeroxe/controllers/setting_controller.py
from PySide6.QtCore import QObject, QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox
from zeroxe import config
from zeroxe.utils.security import decrypt_string, encrypt_string

class SettingController(QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.settings = QSettings(config.ORGANIZATION_NAME, config.APP_NAME)

        self._bind_signals()
        self.load_settings()

    def _bind_signals(self):
        self.view.ui.pushButton_apply.clicked.connect(self.on_apply)
        self.view.software_ui.toolButton_locateBlender.clicked.connect(self.on_locate_blender)

    def load_settings(self):
        encrypted = self.settings.value("kitsu/password_enc", "", type=str)
        self.view.kitsu_ui.lineEdit_password.setText(decrypt_string(encrypted))

    def save_settings(self):
        raw_password = self.view.kitsu_ui.lineEdit_password.text().strip()
        self.settings.setValue("kitsu/password_enc", encrypt_string(raw_password))
        self.settings.sync()

    def on_apply(self):
        self.save_settings()
        QMessageBox.information(self.view, "Settings", "Settings saved successfully.")

    def on_locate_blender(self):
        file_path, _ = QFileDialog.getOpenFileName(self.view, "Locate Blender")
        if file_path:
            self.view.software_ui.lineEdit_kitsuUrl.setText(file_path)
```

---

### Step 6: Implement the View Layer (`src/zeroxe/views/`)
Create the `QWidget` container, assemble any child pages, and attach the Controller:

```python
# src/zeroxe/views/settings_view.py
from typing import Optional
from PySide6.QtWidgets import QWidget, QStackedWidget
from zeroxe.controllers.setting_controller import SettingController
from zeroxe.ui.ui_settings import Ui_Form

class SettingsView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        # Attach Controller
        self.controller = SettingController(self)
```

---

## Best Practices & Patterns

### 1. Storing Entity Objects in Qt Items (`Qt.ItemDataRole.UserRole`)
Never rely on string matching to retrieve data when an item in `QListView` is clicked:

```python
# ✅ GOOD: Store domain entity in UserRole
item = QStandardItem(project.name)
item.setData(project, Qt.ItemDataRole.UserRole)
self.model.appendRow(item)

# Retrieval in slot:
def on_selected(self, current, previous):
    if current.isValid():
        project_obj = current.data(Qt.ItemDataRole.UserRole)
        print(project_obj.id, project_obj.name)
```

---

### 2. Instant Search with `QSortFilterProxyModel`
Never manually rebuild your list on every keystroke in search bars:

```python
# ✅ GOOD: Proxy model automatically handles fast filtering
self.source_model = QStandardItemModel(self)
self.proxy_model = QSortFilterProxyModel(self)
self.proxy_model.setSourceModel(self.source_model)
self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

self.ui.listView_items.setModel(self.proxy_model)

# Wire search box directly to proxy:
self.ui.lineEdit_search.textChanged.connect(self.proxy_model.setFilterFixedString)
```

---

### 3. Clean CLI & Build Commands

```bash
# Run application
python -m zeroxe.main
# Or via uv
uv run zeroxe

# Run automated tests
pytest

# Run specific path generator test
python test/test_shot_path.py

# Test Pipeline CLI endpoint directly
python -m pipeline.Commands.main shot-path --dept Layout --ep ep998 --sq sq01 --sh sh0020 --json

# Compile all UI files
python scripts/compile_ui.py

# Watch UI files during Designer workflow
python scripts/compile_ui.py --watch

# Build standalone desktop executable (PyInstaller)
python scripts/build_executable.py --onedir

# Build AppImage for local system
./scripts/build_appimage.sh

# Build 100% portable AppImage for all Linux distros (via Ubuntu 22.04 container)
./scripts/build_appimage_docker.sh
```

---

### 4. Testing & Environment Configuration (`.env`)

For headless test scripts (e.g. `test/test_kitsu_service.py`):
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure your local test credentials:
   ```env
   KITSU_HOST=http://192.168.99.38:8080/api
   KITSU_EVENT_HOST=http://192.168.99.38:8080
   KITSU_EMAIL=user@example.com
   KITSU_PASSWORD=your_password
   ```
3. Test files will automatically load `.env` at runtime.

---

### 5. Linux GLIBC & AppImage Compatibility Rule
> [!IMPORTANT]
> Linux shared libraries (GLIBC) are backward-compatible, but **not forward-compatible**.
> If you build an AppImage directly on a cutting-edge host system (e.g. Arch Linux / Fedora with GLIBC 2.44), the generated AppImage will fail on older distributions (Ubuntu 22.04/24.04, Debian 12) with:
> `ImportError: /lib64/libm.so.6: version 'GLIBC_2.44' not found`
>
> **Solution**: Always use `./scripts/build_appimage_docker.sh` to package production AppImages against an Ubuntu 22.04 LTS (GLIBC 2.35) baseline so it runs across all Linux distributions.

