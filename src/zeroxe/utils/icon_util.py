"""Application icon resolution utility."""

import os
from pathlib import Path
import sys
from PySide6.QtGui import QIcon
from zeroxe import config


def get_app_icon() -> QIcon:
    """Resolve the main application icon from the assets directory or system theme."""
    candidates = []

    # 1. Config paths (dev and standard bundle)
    candidates.extend([
        config.ASSETS_DIR / "icons" / "icon.png",
        config.ASSETS_DIR / "icons" / "zeroxe.png",
        config.ASSETS_DIR / "icon.png",
        config.ASSETS_DIR / "zeroxe.png",
        config.BASE_DIR / "assets" / "icons" / "icon.png",
        config.BASE_DIR / "assets" / "icons" / "zeroxe.png",
        config.BASE_DIR / "assets" / "icon.png",
    ])

    # 2. Executable parent and PyInstaller _internal directories
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "_internal" / "assets" / "icons" / "icon.png",
            exe_dir / "_internal" / "assets" / "icons" / "zeroxe.png",
            exe_dir / "assets" / "icons" / "icon.png",
            exe_dir / "assets" / "icons" / "zeroxe.png",
            exe_dir.parent / "share" / "icons" / "hicolor" / "512x512" / "apps" / "zeroxe.png",
            exe_dir.parent / "share" / "icons" / "hicolor" / "256x256" / "apps" / "zeroxe.png",
            exe_dir.parent / "share" / "pixmaps" / "zeroxe.png",
        ])

    # 3. AppImage APPDIR environment variable
    appdir = os.environ.get("APPDIR")
    if appdir:
        appdir_path = Path(appdir)
        candidates.extend([
            appdir_path / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "zeroxe.png",
            appdir_path / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "zeroxe.png",
            appdir_path / "usr" / "share" / "pixmaps" / "zeroxe.png",
            appdir_path / "zeroxe.png",
            appdir_path / ".DirIcon",
        ])

    # 4. Project root (source tree)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.extend([
        project_root / "assets" / "icons" / "icon.png",
        project_root / "assets" / "icons" / "zeroxe.png",
        project_root / "assets" / "icon.png",
    ])

    for p in candidates:
        if p.is_file():
            icon = QIcon(str(p))
            if not icon.isNull():
                return icon

    # 5. Try resolving from desktop icon theme
    theme_icon = QIcon.fromTheme("zeroxe")
    if not theme_icon.isNull():
        return theme_icon

    # Fallback: stylized icon from NotificationService
    try:
        from zeroxe.services.notification_service import NotificationService
        return NotificationService._create_default_icon()
    except Exception:
        return QIcon()

