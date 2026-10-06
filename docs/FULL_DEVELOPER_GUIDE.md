# ZeroXe Complete Developer & Pipeline Guide

A comprehensive guide for developers and pipeline technical directors (TDs) to modify the ZeroXe desktop codebase, extend the client application, and add or customize pipeline features.

---

## Table of Contents

1. [Architectural Overview & System Boundaries](#1-architectural-overview--system-boundaries)
2. [Modifying the Desktop Codebase (`src/zeroxe/`)](#2-modifying-the-desktop-codebase-srczeroxe)
   - [A. Adding or Modifying UI (Qt Designer)](#a-adding-or-modifying-ui-qt-designer)
   - [B. Implementing Controllers & Event Flow](#b-implementing-controllers--event-flow)
   - [C. Creating or Updating Services](#c-creating-or-updating-services)
   - [D. Background Async Workers (`QThread`)](#d-background-async-workers-qthread)
   - [E. Working with Local Settings & Security](#e-working-with-local-settings--security)
3. [Adding & Customizing Pipeline Features (`pipeline/`)](#3-adding--customizing-pipeline-features-pipeline)
   - [A. How the Dynamic Pipeline Bridge Works](#a-how-the-dynamic-pipeline-bridge-works)
   - [B. Step-by-Step: Adding a New Feature with `@register_feature`](#b-step-by-step-adding-a-new-feature-with-register_feature)
   - [C. Department Filtering & Preset Scripts](#c-department-filtering--preset-scripts)
   - [D. Customizing Path Resolution Rules](#d-customizing-path-resolution-rules)
   - [E. Customizing Cooperative File Locks & History](#e-customizing-cooperative-file-locks--history)
4. [Deployment & Server/NAS Sync](#4-deployment--servernas-sync)
5. [Testing & Quality Assurance](#5-testing--quality-assurance)
6. [Packaging & AppImage Builds](#6-packaging--appimage-builds)
7. [Troubleshooting & Common Questions](#7-troubleshooting--common-questions)

---

## 1. Architectural Overview & System Boundaries

ZeroXe separates the **Desktop Client** from the **External Pipeline**:

```
+-------------------------------------------------------------------------+
| ZeroXe Desktop Client (PySide6 / Qt 6)                                  |
|                                                                         |
|  [Qt Designer UI] -> [Views] <-> [Controllers] -> [Services]            |
|                                                          |              |
|                                              (Dynamic Dispatch)         |
+----------------------------------------------------------|--------------+
                                                           |
                                                           v
+-------------------------------------------------------------------------+
| External Pipeline (NAS / Shared Storage / Local Repo)                   |
|                                                                         |
|  zeroxe_map.yaml -> pipeline.yaml -> Commands/main.py                   |
|                                            ├── feature_registry.py      |
|                                            ├── versioning.py            |
|                                            ├── Paths/                   |
|                                            └── Locks/                   |
+-------------------------------------------------------------------------+
```

### Separation Rules:
- **`src/zeroxe/` (Client App)**: Pure presentation, signal routing, asynchronous thread management, and generic pipeline invocation. It **never** contains hardcoded feature names, versioning logic, or DCC scripts.
- **`pipeline/Commands/` (Pipeline)**: Single source of truth for versioning, DCC automation scripts, path generation, and file locking. Can be edited on the NAS to update all studio artists instantly without rebuilding the client app.

---

## 2. Modifying the Desktop Codebase (`src/zeroxe/`)

### A. Adding or Modifying UI (Qt Designer)

1. Open Qt Designer (or `pyside6-designer`).
2. Edit or create the `.ui` file in `ui/` (e.g. `ui/launcher.ui` or `ui/my_new_dialog.ui`).
3. Follow strict naming conventions:
   - Push Buttons: `pushButton_myAction`
   - Line Edits: `lineEdit_search`
   - Combo Boxes: `comboBox_category`
   - List Views: `listView_items`
   - Check Boxes: `checkBox_multiSelect`
4. Compile the UI to Python:
   ```bash
   # One-time compilation
   python scripts/compile_ui.py

   # Or run watch mode while actively editing in Qt Designer
   python scripts/compile_ui.py --watch
   ```
5. The generated file appears in `src/zeroxe/ui/ui_launcher.py`. **Never edit `src/zeroxe/ui/ui_*.py` directly.**

---

### B. Implementing Controllers & Event Flow

Controllers live in `src/zeroxe/controllers/` and inherit from `QObject`. They connect UI signals to actions, validate form inputs, and call services.

```python
# src/zeroxe/controllers/my_feature_controller.py
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QMessageBox
from zeroxe.services.pipeline_service import PipelineService

class MyFeatureController(QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._bind_signals()

    def _bind_signals(self) -> None:
        self.view.ui.pushButton_execute.clicked.connect(self.on_execute_clicked)

    def on_execute_clicked(self) -> None:
        selected_file = self.view.get_selected_filepath()
        if not selected_file:
            QMessageBox.warning(self.view, "Selection Required", "Please select a file first.")
            return

        success, msg, target_path = PipelineService.execute_feature(
            feature_name="Up Version",
            filepath=selected_file,
            department="Layout",
            project_name="MyProject",
        )

        if success:
            QMessageBox.information(self.view, "Success", f"Operation succeeded:\n{target_path}")
        else:
            QMessageBox.critical(self.view, "Execution Failed", msg)
```

#### Best Practices for List & Tree Views:
- **Use `Qt.ItemDataRole.UserRole`**: Always store Python objects (e.g. `Shot`, `Asset`, `Project`) directly on `QStandardItem.setData(obj, Qt.ItemDataRole.UserRole)`.
- **Fast Search Filtering**: Attach a `QSortFilterProxyModel` to your `QStandardItemModel` and connect `lineEdit.textChanged` to `proxy_model.setFilterFixedString`.

---

### C. Creating or Updating Services

Services in `src/zeroxe/services/` contain pure business logic with **no GUI imports** (`QWidget`, `QMessageBox`, etc.). This allows 100% headless testing via `pytest`.

```python
# src/zeroxe/services/custom_service.py
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class CustomService:
    @classmethod
    def process_data(cls, input_path: str) -> bool:
        p = Path(input_path)
        if not p.is_file():
            logger.error(f"File not found: {input_path}")
            return False
        # Perform computation or file I/O
        return True
```

---

### D. Background Async Workers (`QThread`)

Never perform network requests (Kitsu/Gazu API), large file downloads, or long-running disk scans on the main GUI thread.

```python
# src/zeroxe/services/workers.py
from PySide6.QtCore import QThread, Signal

class DataFetchWorker(QThread):
    finished = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id

    def run(self):
        try:
            # Network request or heavy computation
            data = FetchService.fetch_all_shots(self.project_id)
            self.finished.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))
```

In the Controller:
```python
def load_data_async(self, project_id: str):
    self.worker = DataFetchWorker(project_id)
    self.worker.finished.connect(self.on_data_loaded)
    self.worker.error_occurred.connect(self.on_data_error)
    self.worker.start()
```

---

### E. Working with Local Settings & Security

ZeroXe stores settings in `QSettings` via [`SettingsService`](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/src/zeroxe/services/settings_service.py).
Sensitive tokens and passwords must be encrypted using [`src/zeroxe/utils/security.py`](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/src/zeroxe/utils/security.py):

```python
from zeroxe.services.settings_service import SettingsService
from zeroxe.utils.security import encrypt_string, decrypt_string

# Saving encrypted password
raw_pass = "secret_password"
encrypted = encrypt_string(raw_pass)
SettingsService._settings().setValue("kitsu/password_enc", encrypted)

# Retrieving decrypted password
enc_val = SettingsService._settings().value("kitsu/password_enc", "", type=str)
plain_pass = decrypt_string(enc_val)
```

---

## 3. Adding & Customizing Pipeline Features (`pipeline/`)

### A. How the Dynamic Pipeline Bridge Works

When the user selects a project in the UI:
1. `LauncherController` queries `PipelineService.list_features(department, project_name)`.
2. `PipelineService` reads `zeroxe_map.yaml` -> resolves `projects[project_name].pipeline_path` -> locates `Commands/main.py`.
3. `PipelineService` dynamically loads `Commands/main.py` using Python's `importlib.util`.
4. `Commands/main.py` queries `feature_registry.py` and returns the registered features.
5. When the user executes an action, `PipelineService.execute_feature()` sends the request directly to the external pipeline and headlessly runs the returned Blender/DCC script.

---

### B. Step-by-Step: Adding a New Feature with `@register_feature`

To add a new pipeline feature (e.g. **Export Alembic Cache** or **Render Viewport**):

#### Step 1: Open `pipeline/Commands/feature_registry.py`
Add your feature function and annotate it with `@register_feature`:

```python
# pipeline/Commands/feature_registry.py
from textwrap import dedent
from Commands.feature_registry import register_feature, PipelineFeatureResult

@register_feature(
    name="Export Alembic",
    description="Export animated geometry to ABC cache",
    departments=["animation", "cfx"],  # Set to None to allow all departments
    order=25,                           # Priority in dropdown menu
)
def handle_export_alembic(
    filepath: str,
    department: str = None,
    **kwargs,
) -> PipelineFeatureResult:
    if not filepath:
        return PipelineFeatureResult(success=False, message="No working file path provided.")

    abc_output_path = filepath.replace(".blend", ".abc")

    # Generate headless Blender automation script
    script = dedent(f"""
        import bpy

        bpy.ops.wm.open_mainfile(filepath="{filepath}")

        # Select exportable objects
        bpy.ops.object.select_all(action='SELECT')

        # Export Alembic
        bpy.ops.wm.alembic_export(
            filepath="{abc_output_path}",
            start=1,
            end=100,
            selected=True,
        )

        bpy.ops.wm.quit_blender()
    """).strip()

    return PipelineFeatureResult(
        success=True,
        message=f"Export Alembic script generated:\n{abc_output_path}",
        target_path=abc_output_path,
        script=script,
        data={"action": "export_alembic", "output": abc_output_path},
    )
```

#### Step 2: Test via CLI
Verify the feature directly from your terminal:
```bash
# List features
python pipeline/Commands/main.py list-features --dept animation --json

# Execute feature
python pipeline/Commands/main.py execute-feature \
  --name "Export Alembic" \
  --file "/path/to/shot_anm_v001.blend" \
  --dept "Animation" \
  --json
```

#### Step 3: Run in ZeroXe UI
Launch ZeroXe. When you select the **Animation** department, **`Export Alembic`** will automatically appear in the feature dropdown!
- It works immediately for single execution.
- It works immediately for multi-select batch execution (<kbd>Shift</kbd>/<kbd>Ctrl</kbd> selection).

---

### C. Department Filtering & Preset Scripts

In `pipeline.yaml`, you can configure custom department scripts and presets:

```yaml
# pipeline.yaml
global:
  code: mdt
  mounts:
    linux: /mnt/projects/mdt
    windows: Z:/projects/mdt
    darwin: /Volumes/projects/mdt

departments:
  Animation:
    code: anm
    scripts:
      up_master: "@project_path@/00_pipeline/scripts/anm_master_bake.py"
      playblast: "@project_path@/00_pipeline/scripts/anm_playblast.py"

  Lighting:
    code: lgt
    scripts:
      up_master: "@project_path@/00_pipeline/scripts/lgt_cleanup.py"
```

When `Up Master` runs in the Animation department, ZeroXe automatically resolves `@project_path@`, reads `anm_master_bake.py`, and embeds that code into the published master file.

---

### D. Customizing Path Resolution Rules

Path patterns for shots and assets are defined in:
- [`pipeline/Commands/Paths/shot_path_generator.py`](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/pipeline/Commands/Paths/shot_path_generator.py)
- [`pipeline/Commands/Paths/asset_path_generator.py`](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/pipeline/Commands/Paths/asset_path_generator.py)

#### Shot Pattern Variables:
- `{project_code}`: Project code from `pipeline.yaml` (e.g. `mdt`)
- `{episode}`: Episode name (e.g. `ep998`)
- `{sequence}`: Sequence name (e.g. `sq01`)
- `{shot}`: Shot name (e.g. `sh0020`)
- `{department_code}`: Department abbreviation (e.g. `lay`, `anm`, `lgt`)
- `{version_folder}`: Progress/version directory (e.g. `progress`)
- `{version}`: Formatted version string (e.g. `v001`, `v002`)

---

### E. Customizing Cooperative File Locks & History

Cooperative file locking and version audit logging live in [`pipeline/Commands/Locks/lock_manager.py`](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/pipeline/Commands/Locks/lock_manager.py):
- Locks are saved as JSON files in `<project_root>/00_pipeline/locks/<entity_key>.json`.
- Version history audit logs are stored in `<project_root>/00_pipeline/history/<entity_key>.json`.
- Automatic lock release occurs when the artist exits the DCC software.

---

## 4. Deployment & Server/NAS Sync

When you are ready to push pipeline updates to the studio:

1. **Deploy to NAS**:
   Copy updated files from `pipeline/Commands/` to your server's pipeline folder:
   ```bash
   cp pipeline/Commands/*.py /mnt/nas/projects/<project>/00_pipeline/Commands/
   ```
2. **Instant Sync**:
   ZeroXe checks file timestamps and automatically reloads the NAS module on the fly. Artists do not need to restart the application or download updates.

---

## 5. Testing & Quality Assurance

Run the full automated test suite before committing:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run only versioning and feature tests
pytest test/test_versioning_system.py

# Run path resolution tests
pytest test/test_shot_path.py
```

### Adding a New Unit Test
Add test cases in `test/` following the existing pattern:
```python
# test/test_my_feature.py
def test_my_feature_script_generation(tmp_path):
    blend_file = tmp_path / "shot.blend"
    blend_file.touch()

    res = handle_export_alembic(str(blend_file))
    assert res.success is True
    assert "bpy.ops.wm.alembic_export" in res.script
```

---

## 6. Packaging & AppImage Builds

ZeroXe includes build scripts for distributing standalone executables:

```bash
# 1. Build standalone directory executable with PyInstaller
python scripts/build_executable.py --onedir

# 2. Build local AppImage (for current Linux distribution)
./scripts/build_appimage.sh

# 3. Build 100% portable AppImage (compatible across all Linux distros)
./scripts/build_appimage_docker.sh
```

---

## 7. Troubleshooting & Common Questions

#### Q1: Why is the feature dropdown empty in the UI?
- **Answer**: Features are strictly scoped per project. Ensure that:
  1. A project is selected in the project list.
  2. `zeroxe_map.yaml` has an entry for the project with a valid `pipeline_path`.
  3. The `pipeline.yaml` and `Commands/main.py` files exist at that path.

#### Q2: How do I test pipeline scripts without Blender opening a window?
- **Answer**: ZeroXe runs Blender in headless background mode (`blender -b --python script.py`). Logs from standard output and standard error are automatically captured and displayed if execution fails.

#### Q3: Can I add Maya, Nuke, or Houdini commands?
- **Answer**: Yes. In your `@register_feature` handler, generate the corresponding Python script for Maya (`mayapy`), Nuke, or Houdini, and invoke the appropriate DCC executable.
