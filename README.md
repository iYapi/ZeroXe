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

## 🛠️ Pipeline CLI & Path Generation

The `pipeline/` folder in this repository acts as a local example and reference implementation. In production, ZeroXe resolves the live `pipeline.yaml` dynamically from the NAS via `zeroxe_map.yaml`.

The pipeline core can be imported in Python or used as a standalone CLI tool:

```bash
# Resolve shot master and version paths
python -m pipeline.Commands.main shot-path --dept Layout --ep ep998 --sq sq01 --sh sh0020 --json
```

**Example Output**:
- **Master Path**: `/mnt/I/.../02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/mdt_ep998_sq01_sh0020_lay.blend`
- **Version Path**: `/mnt/I/.../02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/progress/mdt_ep998_sq01_sh0020_lay_v001.blend`

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
