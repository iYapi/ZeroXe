#!/usr/bin/env python3
"""Setup script for bundled FFmpeg binaries in pipeline and application distribution.

Manages static standalone FFmpeg binaries for Linux and Windows so ZeroXe can run
completely standalone across studio workstations without requiring machine-level
FFmpeg installation.

Usage:
    python scripts/setup_bundled_ffmpeg.py --status
    python scripts/setup_bundled_ffmpeg.py --install-linux
    python scripts/setup_bundled_ffmpeg.py --install-all
"""

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_BIN = PROJECT_ROOT / "pipeline" / "bin"
ASSETS_BIN = PROJECT_ROOT / "assets" / "bin"

LINUX_STATIC_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
WINDOWS_STATIC_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def get_binary_version(bin_path: Path) -> str | None:
    """Run binary with -version and return first line."""
    if not bin_path.is_file() or not os.access(bin_path, os.X_OK):
        return None
    try:
        res = subprocess.run([str(bin_path), "-version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout:
            return res.stdout.splitlines()[0]
    except Exception:
        pass
    return None


def show_status() -> None:
    """Report status of bundled binaries across pipeline and assets."""
    print("=" * 65)
    print("ZeroXe Bundled FFmpeg Distribution Status")
    print("=" * 65)

    targets = [
        ("Pipeline Linux", PIPELINE_BIN / "linux" / "ffmpeg"),
        ("Pipeline Windows", PIPELINE_BIN / "windows" / "ffmpeg.exe"),
        ("Assets Linux", ASSETS_BIN / "linux" / "ffmpeg"),
        ("Assets Windows", ASSETS_BIN / "windows" / "ffmpeg.exe"),
    ]

    for label, target in targets:
        if target.is_file():
            size_mb = target.stat().st_size / (1024 * 1024)
            ver = get_binary_version(target)
            ver_str = f"({ver})" if ver else "[Exists, not executable on host]"
            print(f"  [✓] {label:<18}: {target.relative_to(PROJECT_ROOT)} [{size_mb:.1f} MB] {ver_str}")
        else:
            print(f"  [✗] {label:<18}: Not found ({target.relative_to(PROJECT_ROOT)})")

    # Check host system ffmpeg
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        print(f"\n  Host System FFmpeg : {system_ffmpeg}")
    else:
        print("\n  Host System FFmpeg : [Not installed on host]")
    print("=" * 65)


def install_linux_static() -> bool:
    """Download and install static Linux FFmpeg binary."""
    print("==> Fetching static Linux FFmpeg (x86_64)...")
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="zeroxe_ff_linux_"))
    tar_path = tmp_dir / "ffmpeg.tar.xz"

    try:
        print(f"    Downloading from: {LINUX_STATIC_URL}")
        urllib.request.urlretrieve(LINUX_STATIC_URL, tar_path)

        print("    Extracting archive...")
        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path, "r:xz") as tar:
            tar.extractall(extract_dir)

        # Find ffmpeg binary
        ff_candidates = list(extract_dir.glob("**/ffmpeg"))
        valid_binary = None
        for cand in ff_candidates:
            if cand.is_file() and not cand.is_symlink():
                valid_binary = cand
                break

        if not valid_binary:
            print("[Error] Could not find 'ffmpeg' binary inside downloaded archive.")
            return False

        # Copy to pipeline/bin/linux and assets/bin/linux
        for dest_dir in (PIPELINE_BIN / "linux", ASSETS_BIN / "linux"):
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / "ffmpeg"
            shutil.copy2(valid_binary, dest_file)
            dest_file.chmod(0o755)
            print(f"    ✓ Installed: {dest_file.relative_to(PROJECT_ROOT)}")

        return True

    except Exception as e:
        print(f"[Error] Failed to install Linux static FFmpeg: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def install_windows_static() -> bool:
    """Download and install static Windows FFmpeg binary."""
    print("==> Fetching static Windows FFmpeg (x86_64 essentials)...")
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="zeroxe_ff_win_"))
    zip_path = tmp_dir / "ffmpeg.zip"

    try:
        print(f"    Downloading from: {WINDOWS_STATIC_URL}")
        urllib.request.urlretrieve(WINDOWS_STATIC_URL, zip_path)

        print("    Extracting archive...")
        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # Find ffmpeg.exe
        ff_candidates = list(extract_dir.glob("**/ffmpeg.exe"))
        valid_binary = None
        for cand in ff_candidates:
            if cand.is_file():
                valid_binary = cand
                break

        if not valid_binary:
            print("[Error] Could not find 'ffmpeg.exe' binary inside downloaded archive.")
            return False

        # Copy to pipeline/bin/windows and assets/bin/windows
        for dest_dir in (PIPELINE_BIN / "windows", ASSETS_BIN / "windows"):
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / "ffmpeg.exe"
            shutil.copy2(valid_binary, dest_file)
            print(f"    ✓ Installed: {dest_file.relative_to(PROJECT_ROOT)}")

        return True

    except Exception as e:
        print(f"[Error] Failed to install Windows static FFmpeg: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Manage bundled FFmpeg binaries for ZeroXe pipeline distribution.")
    parser.add_argument("--status", action="store_true", help="Report status of bundled binaries.")
    parser.add_argument("--install-linux", action="store_true", help="Download static Linux x86_64 FFmpeg.")
    parser.add_argument("--install-windows", action="store_true", help="Download static Windows x86_64 FFmpeg.")
    parser.add_argument("--install-all", action="store_true", help="Download static builds for all supported platforms.")

    args = parser.parse_args()

    if args.install_linux or args.install_all:
        install_linux_static()

    if args.install_windows or args.install_all:
        install_windows_static()

    show_status()


if __name__ == "__main__":
    main()
