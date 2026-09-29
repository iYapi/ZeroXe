# ZeroXe Development Workflow & Cookbook

A practical step-by-step guide for creating new features, screens, and components in the **ZeroXe** project.

---

## Step-by-Step: Adding a New Screen / Tab

Follow these 5 steps whenever you create a new UI feature:

### Step 1: Design the UI in Qt Designer
1. Open Qt Designer (or use `.venv/bin/pyside6-designer`).
2. Create a `Widget` (or `Dialog` / `MainWindow`).
3. Save the file into the `ui/` directory (e.g. `ui/settings.ui`).
4. **Naming Convention**: Give widgets clear `objectName` identifiers:
   - Buttons: `pushButton_save`, `pushButton_cancel`
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

This generates `src/zeroxe/ui/ui_settings.py` containing the `Ui_Form` class.

---

### Step 3: Define Data Models (`src/zeroxe/models/`)
Create a dataclass representing the data your screen handles:

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

### Step 4: Implement the Service / Logic Layer (`src/zeroxe/services/`)
Create pure Python logic to fetch, save, or process data:

```python
# src/zeroxe/services/settings_service.py
import json
from pathlib import Path
from zeroxe.models.settings_model import AppSettings

class SettingsService:
    CONFIG_PATH = Path.home() / ".zeroxe" / "config.json"

    @classmethod
    def load_settings(cls) -> AppSettings:
        if not cls.CONFIG_PATH.exists():
            return AppSettings(default_project="", dcc_executable_path="")
        with open(cls.CONFIG_PATH, "r") as f:
            data = json.load(f)
            return AppSettings(**data)

    @classmethod
    def save_settings(cls, settings: AppSettings) -> bool:
        cls.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.CONFIG_PATH, "w") as f:
            json.dump(settings.__dict__, f, indent=2)
        return True
```

---

### Step 5: Implement the View Layer (`src/zeroxe/views/`)
Create the view widget that inherits from `QWidget`, sets up `Ui_Form`, and connects user interactions:

```python
# src/zeroxe/views/settings_view.py
from PySide6.QtWidgets import QWidget, QMessageBox
from zeroxe.ui.ui_settings import Ui_Form
from zeroxe.services.settings_service import SettingsService

class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        # Connect signals
        self.ui.pushButton_save.clicked.connect(self._on_save_clicked)

        # Load initial values
        self._load_values()

    def _load_values(self):
        settings = SettingsService.load_settings()
        self.ui.lineEdit_project.setText(settings.default_project)
        self.ui.checkBox_update.setChecked(settings.auto_check_update)

    def _on_save_clicked(self):
        # Read from UI and pass to Service
        pass
```

---

### Step 6: Register into Main Window (`src/zeroxe/views/main_view.py`)
Add your new view to the main tab widget or navigation bar:

```python
from zeroxe.views.launcher_view import LauncherView
from zeroxe.views.settings_view import SettingsView

class MainView(QMainWindow):
    def _setup_ui(self):
        self.tab_widget = QTabWidget(self)
        
        self.launcher_view = LauncherView(self)
        self.settings_view = SettingsView(self)
        
        self.tab_widget.addTab(self.launcher_view, "Launcher")
        self.tab_widget.addTab(self.settings_view, "Settings")
        
        self.setCentralWidget(self.tab_widget)
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
uv run python -m zeroxe.main

# Compile all UI files
python scripts/compile_ui.py

# Watch UI files during Designer workflow
python scripts/compile_ui.py --watch

# Build standalone desktop executable (PyInstaller)
uv run python scripts/build_executable.py --onedir

# Build AppImage for local system
./scripts/build_appimage.sh

# Build 100% portable AppImage for all Linux distros (via Ubuntu 22.04 container)
./scripts/build_appimage_docker.sh
```

---

### 4. Linux GLIBC & AppImage Compatibility Rule
> [!IMPORTANT]
> Linux shared libraries (GLIBC) are backward-compatible, but **not forward-compatible**.
> If you build an AppImage directly on a cutting-edge host system (e.g. Arch Linux / Fedora with GLIBC 2.44), the generated AppImage will fail on older distributions (Ubuntu 22.04/24.04, Debian 12) with:
> `ImportError: /lib64/libm.so.6: version 'GLIBC_2.44' not found`
>
> **Solution**: Always use `./scripts/build_appimage_docker.sh` to package production AppImages against an Ubuntu 22.04 LTS (GLIBC 2.35) baseline so it runs across all Linux distributions.

