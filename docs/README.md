# ZeroXe Technical Documentation

Welcome to the **ZeroXe** technical documentation portal. This documentation provides in-depth guides covering the application architecture, command-line interface, pipeline builders, DCC automation, and collaborative production services.

---

## Documentation Directory

The documentation is organized into four core functional domains:

```
docs/
├── README.md                  # Documentation Hub & Central Index
│
├── [ Core Architecture & Development ]
│   ├── ARCHITECTURE.md            # System Architecture, Layered MVC & Security Model
│   ├── DEVELOPMENT_WORKFLOW.md    # UI Design, Qt Designer Workflow & Build Recipes
│   └── DEVELOPER_MANUAL.md        # Comprehensive Engineering Guide & NAS Deployment
│
├── [ Interfaces & Automation ]
│   └── CLI_REFERENCE.md           # Command Line Reference, Headless Modes & CI/CD Recipes
│
├── [ Pipeline Builders & DCC Integration ]
│   ├── PIPELINE_FEATURES.md       # Dynamic Feature Registry (@register_feature) & Batch Execution
│   ├── LIGHTING_BUILDER.md        # Lighting Scene Generation & FG/BG Collection Schemas
│   └── COMPOSITING_BUILDER.md     # Node Graph Generation & Mastershot Template System
│
└── [ Collaboration & Production Services ]
    ├── FILE_LOCKING.md            # Cooperative Application Locks & Version Audit Trail
    └── NOTIFICATION_SYSTEM.md     # Real-Time Kitsu Event Stream & OS Desktop Alerts
```

---

## 1. Core Architecture & Development

Guides for software engineers and contributors working on the desktop application codebase (`src/zeroxe/`).

| Document | Primary Topics | Target Audience |
| :--- | :--- | :--- |
| **[Architecture Guide](ARCHITECTURE.md)** | Decoupled Layered MVC, Service layer design, machine-bound symmetric encryption, asynchronous `QThread` patterns. | Core Developers, Architects |
| **[Development Workflow](DEVELOPMENT_WORKFLOW.md)** | 6-step UI creation guide, Qt Designer `.ui` workflow, UI compilation via `compile_ui.py`, PySide6 model/view best practices. | UI Engineers, Contributors |
| **[Developer Manual](DEVELOPER_MANUAL.md)** | End-to-end instructions for modifying views/controllers, implementing custom DCC plugins, and deploying to studio NAS mounts. | Senior Engineers, Technical Directors |

---

## 2. Interfaces & Automation

Documentation for running ZeroXe in production environments, terminal workflows, and automated pipeline scripts.

| Document | Primary Topics | Target Audience |
| :--- | :--- | :--- |
| **[CLI Reference Manual](CLI_REFERENCE.md)** | Unified CLI entrypoint (`zeroxe`), headless execution, JSON output schemas, subcommands (`shot-path`, `convert`, `generate`, `lock`, `config`), and automation recipes. | Pipeline TDs, DevOps, Automation Engineers |

---

## 3. Pipeline Builders & DCC Integration

Detailed specifications for scene builders, DCC execution (Blender), and version publishing workflows.

| Document | Primary Topics | Target Audience |
| :--- | :--- | :--- |
| **[Pipeline Features & Batch Execution](PIPELINE_FEATURES.md)** | Dynamic `@register_feature` discovery, incremental versioning (`Up Version`), master publish (`Up Master`), and multi-select batch execution. | Pipeline Technical Directors |
| **[Lighting Builder & FG Assets](LIGHTING_BUILDER.md)** | Scene generation architecture, view layer presets, Foreground (`fg`) / Background (`bg`) collection hierarchies, and YAML batch mapping schemas. | Lighting Leads, Pipeline TDs |
| **[Compositing Builder & Mastershots](COMPOSITING_BUILDER.md)** | Node graph initialization, mastershot template inheritance, sibling shot matching, and custom blend template overrides. | Compositing Leads, TDs |

---

## 4. Collaboration & Production Services

Systems that synchronize local workstations with shared production storage and tracking platforms.

| Document | Primary Topics | Target Audience |
| :--- | :--- | :--- |
| **[File Locking & Version History](FILE_LOCKING.md)** | Cooperative file locking (`00_pipeline/locks/`), user identity resolution via Kitsu, process monitoring, auto-unlock on DCC termination, and version audit logs. | Pipeline TDs, System Administrators |
| **[Notification System](NOTIFICATION_SYSTEM.md)** | Real-time Kitsu WebSocket/Socket.IO worker (`KitsuNotificationWorker`), smart event filtering, native desktop notifications, and detail inspection modals. | Production Coordinators, Developers |

---

## Recommended Reading Paths

- **New Desktop App Developers**: Start with [Architecture](ARCHITECTURE.md) $\rightarrow$ [Development Workflow](DEVELOPMENT_WORKFLOW.md) $\rightarrow$ [Developer Manual](DEVELOPER_MANUAL.md).
- **Pipeline Technical Directors**: Start with [CLI Reference](CLI_REFERENCE.md) $\rightarrow$ [Pipeline Features](PIPELINE_FEATURES.md) $\rightarrow$ [Lighting Builder](LIGHTING_BUILDER.md) $\rightarrow$ [Compositing Builder](COMPOSITING_BUILDER.md).
- **Production & Systems TDs**: Start with [File Locking](FILE_LOCKING.md) $\rightarrow$ [Notification System](NOTIFICATION_SYSTEM.md) $\rightarrow$ [CLI Reference](CLI_REFERENCE.md).
