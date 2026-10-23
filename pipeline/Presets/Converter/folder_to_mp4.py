"""Pipeline Preset: Folder (Image Sequence) to MP4.

Converts all images in a folder to MP4 using the FFmpeg concat demuxer.
Editable dynamically in the pipeline without recompiling ZeroXe application.
"""

import logging
import os
import traceback
from collections.abc import Callable
from pathlib import Path

from ffmpeg.asyncio import FFmpeg

logger = logging.getLogger(__name__)

PRESET_NAME = "Folder (Image Sequence) to MP4"
INPUT_TYPE = "folder"  # Accepts folders containing image sequences
DEFAULT_FRAMERATE = 24
DEFAULT_QUALITY = 15
OUTPUT_EXTENSION = ".mp4"
DESCRIPTION = "Convert all images in a folder (jpg, png, exr, tif, dpx, bmp) to MP4 via concat demuxer"


def _ensure_in_path(bin_dir: Path) -> None:
    """Ensure directory containing ffmpeg binary is present in os.environ['PATH']."""
    try:
        dir_str = str(bin_dir.resolve())
        curr_path = os.environ.get("PATH", "")
        parts = curr_path.split(os.pathsep) if curr_path else []
        if dir_str not in parts:
            os.environ["PATH"] = f"{dir_str}{os.pathsep}{curr_path}" if curr_path else dir_str
    except Exception:
        pass


def _resolve_ffmpeg_executable(custom_path: str | None = None) -> str:
    """Resolve FFmpeg executable robustly across environments, prioritizing pipeline and bundled builds."""
    def _is_executable(p_str: str | Path | None) -> str | None:
        if not p_str:
            return None
        p = Path(p_str)
        try:
            if p.is_file() and os.access(p, os.X_OK):
                _ensure_in_path(p.parent)
                return str(p.resolve())
        except OSError:
            pass
        return None

    # 1. Explicitly provided path
    res = _is_executable(custom_path)
    if res:
        return res

    # 2. Try ConverterService centralized resolver if accessible
    try:
        from zeroxe.services.converter_service import ConverterService
        res = _is_executable(ConverterService.get_ffmpeg_executable())
        if res:
            return res
    except Exception:
        pass

    # Determine platform subfolder and binary name
    import sys
    if sys.platform.startswith("linux"):
        platform_dir = "linux"
        exe_name = "ffmpeg"
    elif sys.platform == "win32":
        platform_dir = "windows"
        exe_name = "ffmpeg.exe"
    elif sys.platform == "darwin":
        platform_dir = "darwin"
        exe_name = "ffmpeg"
    else:
        platform_dir = "other"
        exe_name = "ffmpeg"

    # 3. Try SettingsService if available
    try:
        from zeroxe.services.settings_service import SettingsService
        res = _is_executable(SettingsService.get_ffmpeg_path())
        if res:
            return res
    except Exception:
        pass

    # 4. Environment variables
    for var in ("FFMPEG_BINARY", "FFMPEG_PATH"):
        res = _is_executable(os.environ.get(var, "").strip())
        if res:
            return res

    # 5. Pipeline distribution bundled binary (local or NAS)
    try:
        from zeroxe.services.pipeline_service import PipelineService
        active_dir = PipelineService.get_active_pipeline_dir()
        if active_dir and active_dir.is_dir():
            for p_cand in (
                active_dir / "bin" / platform_dir / exe_name,
                active_dir / "bin" / exe_name,
                active_dir / "Presets" / "Converter" / "bin" / platform_dir / exe_name,
            ):
                res = _is_executable(p_cand)
                if res:
                    return res
    except Exception:
        pass

    # Local repository pipeline/bin
    try:
        repo_pipe_dir = Path(__file__).resolve().parents[2] / "bin"
        for p_cand in (
            repo_pipe_dir / platform_dir / exe_name,
            repo_pipe_dir / exe_name,
        ):
            res = _is_executable(p_cand)
            if res:
                return res
    except Exception:
        pass

    # 6. Application bundled assets (assets/bin)
    try:
        from zeroxe import config
        for a_cand in (
            config.ASSETS_DIR / "bin" / platform_dir / exe_name,
            config.ASSETS_DIR / "bin" / exe_name,
            config.BASE_DIR / "bin" / exe_name,
        ):
            res = _is_executable(a_cand)
            if res:
                return res
    except Exception:
        pass

    # 7. PATH search via shutil.which
    import shutil
    res = _is_executable(shutil.which("ffmpeg"))
    if res:
        return res

    # 8. Standard candidate locations
    candidates = [
        "/usr/bin/ffmpeg",
        "/usr/sbin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/local/sbin/ffmpeg",
        "/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/opt/local/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
    ]
    for c in candidates:
        res = _is_executable(c)
        if res:
            return res

    return "ffmpeg"


async def execute(
    input_path: str,
    output_file: str,
    framerate: int = DEFAULT_FRAMERATE,
    quality: int = DEFAULT_QUALITY,
    progress_callback: Callable | None = None,
    ffmpeg_executable: str | None = None,
    **kwargs,
) -> tuple[bool, str]:
    """Convert all images in a folder to MP4 using concat demuxer.

    Args:
        input_path: Path to folder containing images
        output_file: Output MP4 file path
        framerate: Frame rate for output video (default: 24)
        quality: Quality level 1-31, where 1 is best (default: 15)
        progress_callback: Optional callable for progress updates
        ffmpeg_executable: Optional explicit path to ffmpeg binary

    Returns:
        Tuple of (success: bool, status_message: str)
    """
    concat_file: Path | None = None
    try:
        folder = Path(input_path)
        if not folder.is_dir():
            msg = f"Input path is not a directory: {input_path}"
            logger.error(msg)
            return False, msg

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Get all image files sorted by name
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx', '.ppm')
        image_files = sorted([
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ])

        if not image_files:
            msg = f"No supported image files found in {input_path}"
            logger.error(msg)
            return False, msg

        ffmpeg_bin = _resolve_ffmpeg_executable(ffmpeg_executable or kwargs.get("ffmpeg_executable"))

        logger.info(
            f"Executing FFmpeg ({ffmpeg_bin}) to convert {len(image_files)} images from {input_path} to {output_file}...\n"
            f"  First image: {image_files[0].name}\n"
            f"  Last image: {image_files[-1].name}\n"
            f"  Framerate: {framerate} fps\n"
            f"  Quality: {quality}"
        )

        # Create safe temporary concat file in system temp (avoids read-only network shares)
        import tempfile
        concat_fd, concat_str = tempfile.mkstemp(prefix="zeroxe_concat_", suffix=".txt")
        concat_file = Path(concat_str)

        with os.fdopen(concat_fd, 'w', encoding='utf-8') as f:
            for img_file in image_files:
                # Escape single quotes and write absolute POSIX paths
                escaped_path = img_file.resolve().as_posix().replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        logger.info(f"Created temp concat file with {len(image_files)} entries at {concat_file}")

        # Build FFmpeg command using concat demuxer with absolute paths
        ffmpeg = (
            FFmpeg(executable=ffmpeg_bin)
            .option("y")  # overwrite output
            .option("f", "concat")
            .option("safe", "0")
            .option("r", str(framerate))  # input framerate
            .input(str(concat_file.resolve()))
            .output(
                str(out_path.resolve()),
                **{
                    "vcodec": "mpeg4",
                    "qscale:v": str(quality),
                    "pix_fmt": "yuv420p",
                }
            )
        )

        if progress_callback:
            @ffmpeg.on("progress")
            def on_progress(p):
                try:
                    progress_callback(p)
                except Exception:
                    pass

        logger.info("Starting FFmpeg conversion...")
        await ffmpeg.execute()
        logger.info("✓ Conversion complete!")
        return True, f"Successfully converted to {out_path.name}"

    except Exception as e:
        err_msg = f"FFmpeg execution failed ({ffmpeg_bin if 'ffmpeg_bin' in locals() else 'ffmpeg'}): {e}"
        logger.error(err_msg)
        logger.error(traceback.format_exc())
        return False, err_msg

    finally:
        # Clean up temporary concat file
        if concat_file and concat_file.exists():
            try:
                concat_file.unlink()
                logger.info(f"Cleaned up temporary concat file: {concat_file}")
            except Exception as ex:
                logger.warning(f"Could not remove temporary concat file: {ex}")
