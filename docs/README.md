# ZeroXe Documentation

Welcome to the **ZeroXe** project documentation.

## Guides & References

1. **[Architecture Guide](ARCHITECTURE_GUIDE.md)**
   - Decoupled Layered MVC (Model - View - Controller - Service)
   - Directory structure & layer responsibilities
   - Model, Service, Controller, and View patterns
   - Local credential security & encryption (`src/zeroxe/utils/security.py`)
   - Concurrency & asynchronous `QThread` patterns

2. **[CLI Architecture & Command Manual](CLI_USAGE_AND_MANUAL.md)**
   - Hybrid GUI/CLI invocation (`zeroxe`, `python -m zeroxe`, standalone binary)
   - Headless execution mode without active display servers
   - Full subcommand reference (`shot-path`, `asset-path`, `generate`, `up-version`, `up-master`, `convert`, `lock`, `config`, `kitsu`, `info`)
   - Standardized exit codes and JSON output schemas for automation & CI/CD pipelines

3. **[Development Workflow & Cookbook](DEVELOPMENT_WORKFLOW.md)**
   - 6-step guide for creating new screens/tabs
   - Qt Designer & `compile_ui.py` workflow
   - Qt Model/View & Search Proxy best practices
   - Useful CLI and build commands

4. **[File Locking & Version History System](LOCK_AND_VERSION_SYSTEM.md)**
   - Cooperative application-level locks in `00_pipeline/locks/`
   - Chronological audit logs in `00_pipeline/history/`
   - Kitsu ID & artist identity tracking
   - Process monitoring & auto-unlock on DCC exit
   - Force unlock mechanism & CLI reference

5. **[Pipeline Features & Batch Execution Guide](PIPELINE_FEATURES_AND_BATCH_EXECUTION.md)**
   - Dynamic `@register_feature` pipeline discovery
   - Incremental versioning (`Up Version`) and publish (`Up Master`)
   - Strict per-project feature scoping via `zeroxe_map.yaml`
   - Multi-select batch execution workflow
   - NAS deployment and CLI commands

6. **[Complete Developer & Pipeline Manual](FULL_DEVELOPER_GUIDE.md)**
   - End-to-end guide for modifying desktop codebase (`src/zeroxe/`) and pipeline (`pipeline/`)
   - Creating UI components, views, controllers, and services
   - Step-by-step adding custom features with `@register_feature`
   - Cooperative locks, path resolvers, presets, and NAS deployment

7. **[Lighting Builder & FG Asset Batch Generation Guide](LIGHTING_BUILDER_AND_FG_BATCH_GUIDE.md)**
   - Lighting scene generation architecture & view layer presets
   - Foreground (`fg`) and Background (`bg`) collection hierarchy
   - Single shot interactive modal (`LightingAssetDialog`)
   - Batch generation using YAML mapping files (Per-Shot, Global, Per-Sequence, Wildcards)
   - Auto-discovery mechanism & CLI usage

8. **[Compositing Builder & Mastershot Guide](COMPOSITING_BUILDER_AND_MASTERSHOT_GUIDE.md)**
   - Node graph setup, mastershot template inheritance, and sibling shot matching
   - Custom template file selection and batch execution workflow

9. **[Notification & Kitsu Real-Time Event System Guide](NOTIFICATION_SYSTEM_GUIDE.md)**
   - Native OS desktop notifications via `QSystemTrayIcon`
   - Dedicated background Socket.IO worker (`KitsuNotificationWorker`)
   - Intelligent user filtering (ignores self-actions, targets assigned tasks)
   - Real-time data hydration & project code formatting
   - Centralized notification history & detail inspection modal
