#!/usr/bin/env python3
"""Build script to bundle Zeroxe into a standalone executable using PyInstaller.

Usage:
    uv run python scripts/build_executable.py [--onedir | --onefile]
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
ASSETS_DIR = PROJECT_ROOT / "assets"
TEMPLATES_DIR = PROJECT_ROOT / "user_scripts" / "templates"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
ENTRY_POINT = SRC_DIR / "zeroxe" / "main.py"


def build_binary(onefile: bool = True, clean: bool = True) -> None:
    """Run PyInstaller for manual-code PySide6 architecture."""
    if clean:
        print("==> Cleaning previous build artifacts...")
        shutil.rmtree(DIST_DIR, ignore_errors=True)
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    print("==> Bundling with PyInstaller...")

    # Separator differs by OS (: on Linux/macOS, ; on Windows)
    sep = ";" if platform.system() == "Windows" else ":"

    # Generate build_info.json stamping the compile date (YY.MM.DD)
    import datetime
    import json

    now = datetime.datetime.now()
    compile_version = now.strftime("%y.%m.%d")
    build_info = {
        "version": compile_version,
        "compiled_at": now.isoformat(),
        "build_type": "onefile" if onefile else "onedir",
    }
    build_info_file = PROJECT_ROOT / "build_info.json"
    build_info_file.write_text(json.dumps(build_info, indent=2), encoding="utf-8")
    print(f"==> Stamped compile version: {compile_version} into build_info.json")

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=zeroxe",
        "--onefile" if onefile else "--onedir",
        "--clean",
        "--noconfirm",
        # Keep console attached so CLI/headless flags work (-b, -P, etc.)
        "--console",
        # Ensure root of src is resolvable for 'zeroxe.*' imports
        f"--paths={SRC_DIR}",
    ]

    # Embed build_info.json
    if build_info_file.exists():
        pyinstaller_cmd.append(f"--add-data={build_info_file}{sep}.")

    # Add icon to PyInstaller binary if found
    for icon_cand in (
        ASSETS_DIR / "icons" / "icon.png",
        ASSETS_DIR / "icons" / "zeroxe.png",
        ASSETS_DIR / "icons" / "icon.ico",
        ASSETS_DIR / "icon.png",
    ):
        if icon_cand.exists():
            pyinstaller_cmd.append(f"--icon={icon_cand}")
            print(f"==> Embedding icon: {icon_cand}")
            break

    # Bundle assets (icons, styles) if directory exists
    if ASSETS_DIR.exists() and any(ASSETS_DIR.iterdir()):
        pyinstaller_cmd.append(f"--add-data={ASSETS_DIR}{sep}assets")

    # Bundle starter script templates if directory exists
    if TEMPLATES_DIR.exists() and any(TEMPLATES_DIR.iterdir()):
        pyinstaller_cmd.append(f"--add-data={TEMPLATES_DIR}{sep}user_scripts/templates")

    # Explicit hidden imports to prevent runtime missing module errors
    hidden_imports = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "zeroxe.api",
        "zeroxe.controllers",
        "zeroxe.models",
        "zeroxe.services",
        "zeroxe.ui",
        "zeroxe.utils",
        "zeroxe.views",
        "packaging",
        "packaging.version",
        "requests",
    ]
    for imp in hidden_imports:
        pyinstaller_cmd.extend(["--hidden-import", imp])

    # Application entry point
    pyinstaller_cmd.append(str(ENTRY_POINT))

    print(f"    Running command: {' '.join(pyinstaller_cmd)}")
    result = subprocess.run(pyinstaller_cmd)

    if result.returncode != 0:
        print("\n[Build Failed] PyInstaller exited with an error.")
        sys.exit(result.returncode)

    executable_name = "zeroxe.exe" if platform.system() == "Windows" else "zeroxe"
    output_target = (
        DIST_DIR / executable_name if onefile else DIST_DIR / "zeroxe" / executable_name
    )

    print("\n" + "=" * 50)
    print("Build succeeded! Binary created at:")
    print(f"  -> {output_target}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Build standalone Zeroxe executable.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--onefile",
        action="store_true",
        default=True,
        help="Package executable into a single binary file (default).",
    )
    group.add_argument(
        "--onedir",
        action="store_true",
        help="Package into a directory containing dependencies (faster startup).",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not wipe dist/ and build/ directories before compiling.",
    )

    args = parser.parse_args()
    onefile_mode = not args.onedir

    build_binary(onefile=onefile_mode, clean=not args.no_clean)


if __name__ == "__main__":
    main()