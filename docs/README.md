# ZeroXe Documentation

Welcome to the **ZeroXe** project documentation.

## Guides & References

1. **[Architecture Guide](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/docs/ARCHITECTURE_GUIDE.md)**
   - Decoupled Layered MVC (Model - View - Controller - Service)
   - Directory structure & layer responsibilities
   - Model, Service, Controller, and View patterns
   - Local credential security & encryption (`src/zeroxe/utils/security.py`)
   - Concurrency & asynchronous `QThread` patterns

2. **[Development Workflow & Cookbook](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/docs/DEVELOPMENT_WORKFLOW.md)**
   - 6-step guide for creating new screens/tabs
   - Qt Designer & `compile_ui.py` workflow
   - Qt Model/View & Search Proxy best practices
   - Useful CLI and build commands

3. **[File Locking & Version History System](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/docs/LOCK_AND_VERSION_SYSTEM.md)**
   - Cooperative application-level locks in `00_pipeline/locks/`
   - Chronological audit logs in `00_pipeline/history/`
   - Kitsu ID & artist identity tracking
   - Process monitoring & auto-unlock on DCC exit
   - Force unlock mechanism & CLI reference

4. **[Pipeline Features & Batch Execution Guide](file:///home/iyapi/Documents/Project/2026/remake/ZeroXe/docs/PIPELINE_FEATURES_AND_BATCH_EXECUTION.md)**
   - Dynamic `@register_feature` pipeline discovery
   - Incremental versioning (`Up Version`) and publish (`Up Master`)
   - Strict per-project feature scoping via `zeroxe_map.yaml`
   - Multi-select batch execution workflow
   - NAS deployment and CLI commands

