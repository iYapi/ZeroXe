# ZerØXe

**ZerØXe** is a modern, modular desktop application designed for animation and VFX production pipelines. Built with **PySide6 (Qt 6)** and Python, it seamlessly connects production tracking (Kitsu / Gazu) with local and network storage (NAS) workflows, DCC launcher scripts, and automated shot path resolution.

---

## 🌟 Key Features

- **Production Launcher**: Browse projects, departments, shots, and asset types with instant filtering.
- **Modular Pipeline Core**: Pattern-based shot and asset path resolution supporting master files and version histories.
- **Kitsu / Gazu Integration**: Authenticate with production tracking instances with encrypted local credential storage.
- **Configurable NAS Mappings**: Locate `zeroxe_map.yaml` and dynamic `pipeline.yaml` across Linux, Windows, and macOS mounts.
- **DCC & Tool Launchers**: Directly launch Blender, PureRef, and custom pipeline builder scripts.
- **Decoupled Architecture**: Clean Layered MVC (Model - View - Controller - Service) design for testability and maintainability.

---

## 🚀 Quickstart

### Prerequisites
- Python >= 3.14 (or compatible Python 3.11+)
- [`uv`](https://github.com/astral-sh/uv) (recommended package manager) or `pip`

### 1. Installation

Clone the repository and install dependencies:

```bash
# Using uv (fastest)
uv sync

# Or using pip
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Running the Application

```bash
# Run with uv
uv run zeroxe

# Or run directly with Python
python -m zeroxe.main
```

### 3. Packaging & Building AppImages

```bash
# Build standalone directory executable with PyInstaller
python scripts/build_executable.py --onedir

# Build AppImage inside Docker (Interactive prompt: choose Ubuntu 22 or Fedora 42)
./scripts/build_appimage_docker.sh

# Or select target directly:
./scripts/build_appimage_docker.sh ubuntu22   # Maximum portability (GLIBC 2.35)
./scripts/build_appimage_docker.sh fedora42   # Modern toolchain (GLIBC 2.41+)
```

---

## ⚙️ Configuration

### Local Environment (`.env`)
For running headless tests and local overrides:
```bash
cp .env.example .env
```
Fill in your credentials in `.env` (automatically ignored by Git):
```env
KITSU_HOST=http://localhost:8080/api
KITSU_EVENT_HOST=http://localhost:8080
KITSU_EMAIL=user@example.com
KITSU_PASSWORD=password
```

### In-App Settings (`Edit -> Settings`)
- **Kitsu**: Set URL, email, and password (credentials are encrypted machine-bound).
- **Software**: Set paths for Blender executables and PureRef.
- **NAS**: Set `zeroxe_map.yaml` path and version folder name (default: `progress`).

---

## 🛠️ CLI Interface & Usage

ZerØXe provides a unified CLI entrypoint (`zeroxe`) for launching the desktop GUI, running batch pipeline tasks, resolving paths, and managing media headless:

```bash
# Launch the desktop GUI
zeroxe
# Or explicitly:
zeroxe gui
python -m zeroxe
python -m zeroxe.main

# Show version and info
zeroxe --version
zeroxe info
zeroxe info --json

# Resolve shot and asset paths
zeroxe shot-path -d Layout -e ep998 -s sq01 --sh sh0020 --json
zeroxe asset-path -t CHAR -n Hero_Char -d Model --json

# DCC scene file generation & versioning
zeroxe generate -f /path/to/shot.blend -d Layout
zeroxe up-version -f /path/to/shot_v001.blend
zeroxe up-master -f /path/to/progress/shot_v002.blend

# Transcode media & image sequences
zeroxe convert -i /path/to/frames_folder/ -p folder_to_mp4
zeroxe list-presets --json
zeroxe inspect -i /path/to/media.mov

# Cooperative file locks
zeroxe lock -k ep998_sq01_sh0020_lay --check
zeroxe lock -k ep998_sq01_sh0020_lay --acquire

# Inspect & update application configuration
zeroxe config --list
zeroxe config --get software/active_blender
zeroxe config --set software/dcc_timeout 900
```

---

## 🧪 Testing

Run the automated test suite:

```bash
# Run all tests
pytest

# Run shot path resolution test
python test/test_shot_path.py
```

---

## 📚 Developer Documentation

Detailed architectural and workflow guides are available in the [`docs/`](docs/) directory:

1. **[Architecture Guide](docs/ARCHITECTURE_GUIDE.md)**: Detailed MVC layers, security encryption, and pipeline design.
2. **[Development Workflow & Cookbook](docs/DEVELOPMENT_WORKFLOW.md)**: Step-by-step UI creation guide, compiler usage, and AppImage building.
3. **[File Locking & Version History System](docs/LOCK_AND_VERSION_SYSTEM.md)**: Cooperative application locks, Kitsu identity tracking, and audit trails.
4. **[Pipeline Features & Batch Execution Guide](docs/PIPELINE_FEATURES_AND_BATCH_EXECUTION.md)**: Dynamic pipeline discovery, `@register_feature`, incremental versioning (`Up Version`), master publish (`Up Master`), and multi-select batch processing.
5. **[Complete Developer & Pipeline Manual](docs/FULL_DEVELOPER_GUIDE.md)**: End-to-end instructions for modifying desktop codebase, creating UI screens, adding custom DCC features, and NAS deployment.
6. **[Lighting Builder & FG Asset Batch Generation Guide](docs/LIGHTING_BUILDER_AND_FG_BATCH_GUIDE.md)**: Architecture, collection hierarchy (`fg`/`bg`), interactive checklist, and YAML mapping schemas for batch execution.
7. **[Notification & Kitsu Real-Time Event System Guide](docs/NOTIFICATION_SYSTEM_GUIDE.md)**: System tray notifications, background Socket.IO worker, smart user filtering, data hydration, and project code display.


---

## 📄 License

Maintained by **[iYapi](https://yapi.expiproject.com)**. All rights reserved.
