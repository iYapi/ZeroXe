# ZerØXe

**Desktop application** berbasis PyQt6 sebagai Blender Asset/Shot Launcher dan Version Manager terintegrasi dengan **Kitsu** project management.

- **Versi:** v0.0.18
- **Python:** 3.10+
- **Author:** MrYapikZ

---

## Fitur

### Authentication
| Fitur | Deskripsi |
|---|---|
| [Login & Authentication](docs/features/login-authentication.md) | Login ke Kitsu dengan email/password, session terenkripsi, dan auto-login |

### Blender Launcher
| Fitur | Deskripsi |
|---|---|
| [Blender Launcher](docs/features/blender-launcher.md) | Buka file Blender langsung dari launcher dengan navigasi project, asset, dan shot |
| [Version Management](docs/features/version-management.md) | Buat versi baru, upload ke master file, dan kelola riwayat versi Blender |

### Asset & Shot Management
| Fitur | Deskripsi |
|---|---|
| [Asset & Shot Management](docs/features/asset-shot-management.md) | Browse asset dan shot dari Kitsu berdasarkan department, project, episode, dan tipe |

---

## Instalasi

1. Clone repository ini
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Salin `.env.example` menjadi `.env` dan isi konfigurasi (untuk saat ini `FERNET_KEY` hardcoded di config.py)
4. Jalankan aplikasi:
   ```
   python app/main.py
   ```

### Build Executable

```
pyinstaller --clean --noconsole --onefile -n ZeroXe -p . --collect-submodules app --add-data ".env:." app/main.py
```

---

## Struktur Project

```
ZeroXe/
├── app/
│   ├── main.py                    # Entry point aplikasi
│   ├── config.py                  # Konfigurasi & settings
│   ├── core/
│   │   ├── app_states.py         # Singleton state manager
│   │   ├── gazu_client.py        # Kitsu API client
│   │   └── logger.py             # Rotating file logger
│   ├── modules/
│   │   ├── startup/
│   │   │   └── handle_login.py   # Handler login dialog
│   │   └── blender/
│   │       └── b_launcher/
│   │           └── handle_b_launcher.py  # Handler Blender launcher
│   ├── ui/
│   │   ├── main/                 # UI main window
│   │   ├── startup/              # UI login dialog
│   │   └── modules/blender/      # UI BLauncher
│   └── utils/
│       ├── auth.py               # Autentikasi
│       ├── blender_functions.py  # Generator script Blender
│       ├── versioning.py         # Sistem version control
│       ├── path_builder.py       # Pembangun path
│       ├── file_manager.py       # Operasi file
│       ├── json_manager.py       # Utilitas JSON
│       ├── subprocess.py         # Eksekusi subprocess
│       └── api/gazu/             # Wrapper Kitsu API
├── run.py                         # Script runner
├── requirements.txt               # Dependencies
├── .env.example                   # Template konfigurasi
└── docs/                          # Dokumentasi
    ├── features/                  # Dokumentasi per fitur
    └── images/                    # Screenshot panduan
```

---

## Dokumentasi

Dokumentasi lengkap tersedia di folder [`docs/`](docs/SUMMARY.md).
