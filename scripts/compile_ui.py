#!/usr/bin/env python3
"""Script to automatically compile Qt Designer (.ui) files to PySide6 Python view modules.

Usage:
    python scripts/compile_ui.py              # Compile all .ui files
    python scripts/compile_ui.py --watch      # Watch for changes and recompile automatically
    python scripts/compile_ui.py --clean      # Clean all generated UI files
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

# Base Project Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT_ROOT / "ui"
VIEWS_DIR = PROJECT_ROOT / "src" / "zeroxe" / "ui"


def find_tool(tool_name: str) -> Path:
    """Locate PySide6 binary (e.g., pyside6-uic or pyside6-rcc)."""
    # 1. Check in active/current Python venv bin/Scripts
    venv_dir = Path(sys.executable).parent
    ext = ".exe" if sys.platform == "win32" else ""
    candidate = venv_dir / f"{tool_name}{ext}"
    if candidate.is_file():
        return candidate

    # 2. Check system PATH
    which_path = shutil.which(tool_name)
    if which_path:
        return Path(which_path)

    # 3. Check inside PySide6 package Qt libexec directory
    try:
        import PySide6

        pyside_dir = Path(PySide6.__file__).parent
        base_name = tool_name.replace("pyside6-", "")
        libexec_candidate = pyside_dir / "Qt" / "libexec" / f"{base_name}{ext}"
        if libexec_candidate.is_file():
            return libexec_candidate
    except ImportError:
        pass

    raise FileNotFoundError(
        f"Could not find '{tool_name}'. Ensure PySide6 is installed in your environment."
    )


def compile_single_ui(uic_path: Path, ui_file: Path, output_dir: Path, prefix: str = "ui_") -> Optional[Path]:
    """Compile a single .ui file to a python file."""
    output_file = output_dir / f"{prefix}{ui_file.stem}.py"

    cmd = [
        str(uic_path),
        str(ui_file),
        "-o",
        str(output_file),
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        rel_src = ui_file.relative_to(PROJECT_ROOT)
        rel_out = output_file.relative_to(PROJECT_ROOT)
        print(f"  ✓ Compiled: {rel_src} -> {rel_out}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error compiling {ui_file.name}: {e.stderr.strip() or e.stdout.strip()}")
        return None


def compile_single_qrc(rcc_path: Path, qrc_file: Path, output_dir: Path, prefix: str = "rc_") -> Optional[Path]:
    """Compile a single .qrc resource file to a python file."""
    output_file = output_dir / f"{prefix}{qrc_file.stem}.py"

    cmd = [
        str(rcc_path),
        str(qrc_file),
        "-o",
        str(output_file),
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        rel_src = qrc_file.relative_to(PROJECT_ROOT)
        rel_out = output_file.relative_to(PROJECT_ROOT)
        print(f"  ✓ Compiled Resource: {rel_src} -> {rel_out}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error compiling resource {qrc_file.name}: {e.stderr.strip() or e.stdout.strip()}")
        return None


def compile_all(
    ui_dir: Path = UI_DIR,
    output_dir: Path = VIEWS_DIR,
    prefix: str = "ui_",
    compile_resources: bool = True,
) -> int:
    """Compile all .ui files in ui_dir to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure __init__.py exists in output views package
    init_file = output_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("# Views package\n", encoding="utf-8")

    try:
        uic_path = find_tool("pyside6-uic")
    except FileNotFoundError as err:
        print(f"[Error] {err}")
        return 1

    ui_files: List[Path] = sorted(list(ui_dir.rglob("*.ui")))

    if not ui_files:
        print(f"No .ui files found in '{ui_dir.relative_to(PROJECT_ROOT)}'.")
        return 0

    print(f"==> Compiling {len(ui_files)} UI file(s) from '{ui_dir.relative_to(PROJECT_ROOT)}' to '{output_dir.relative_to(PROJECT_ROOT)}'...")

    success_count = 0
    for ui_file in ui_files:
        if compile_single_ui(uic_path, ui_file, output_dir, prefix=prefix):
            success_count += 1

    if compile_resources:
        qrc_files = sorted(list(ui_dir.rglob("*.qrc")) + list((PROJECT_ROOT / "assets").rglob("*.qrc")))
        if qrc_files:
            try:
                rcc_path = find_tool("pyside6-rcc")
                print(f"==> Compiling {len(qrc_files)} resource file(s)...")
                for qrc_file in qrc_files:
                    if compile_single_qrc(rcc_path, qrc_file, output_dir):
                        success_count += 1
            except FileNotFoundError:
                print("  [Warning] pyside6-rcc not found, skipping resource files.")

    print(f"==> Done! Successfully compiled {success_count} file(s).\n")
    return 0 if success_count == len(ui_files) else 1


def clean_generated(output_dir: Path = VIEWS_DIR, prefix: str = "ui_") -> None:
    """Remove generated UI and RC python files."""
    count = 0
    for file in output_dir.glob(f"{prefix}*.py"):
        file.unlink()
        print(f"  Removed: {file.relative_to(PROJECT_ROOT)}")
        count += 1
    for file in output_dir.glob("rc_*.py"):
        file.unlink()
        print(f"  Removed: {file.relative_to(PROJECT_ROOT)}")
        count += 1
    print(f"==> Cleaned {count} generated file(s).")


def watch_directory(ui_dir: Path = UI_DIR, output_dir: Path = VIEWS_DIR, prefix: str = "ui_") -> None:
    """Watch ui_dir for modifications and recompile on change."""
    print(f"==> Watching '{ui_dir.relative_to(PROJECT_ROOT)}' for changes... (Press Ctrl+C to stop)")
    compile_all(ui_dir=ui_dir, output_dir=output_dir, prefix=prefix)

    mtimes = {}
    try:
        while True:
            changed = False
            for ui_file in ui_dir.rglob("*.ui"):
                current_mtime = ui_file.stat().st_mtime
                if ui_file not in mtimes:
                    mtimes[ui_file] = current_mtime
                elif current_mtime > mtimes[ui_file]:
                    mtimes[ui_file] = current_mtime
                    changed = True
                    print(f"\n[Change detected] {ui_file.name}")
                    uic_path = find_tool("pyside6-uic")
                    compile_single_ui(uic_path, ui_file, output_dir, prefix=prefix)

            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n==> Stopped watcher.")


def main():
    parser = argparse.ArgumentParser(description="Compile Qt .ui files to PySide6 view modules.")
    parser.add_argument(
        "--ui-dir",
        type=Path,
        default=UI_DIR,
        help=f"Directory containing .ui files (default: {UI_DIR.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=VIEWS_DIR,
        help=f"Output directory for generated python views (default: {VIEWS_DIR.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="ui_",
        help="Prefix for generated python files (default: 'ui_')",
    )
    parser.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Watch UI directory for changes and compile automatically.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean all compiled UI files.",
    )

    args = parser.parse_args()

    if args.clean:
        clean_generated(output_dir=args.output_dir, prefix=args.prefix)
        return

    if args.watch:
        watch_directory(ui_dir=args.ui_dir, output_dir=args.output_dir, prefix=args.prefix)
        return

    sys.exit(compile_all(ui_dir=args.ui_dir, output_dir=args.output_dir, prefix=args.prefix))


if __name__ == "__main__":
    main()
