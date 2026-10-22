"""Pipeline Preset: Video to MP4.

Converts any video format to MP4 with MPEG4/H.264 video and AAC audio.
Editable dynamically in the pipeline without recompiling ZeroXe application.
"""

import logging
import os
import traceback
from collections.abc import Callable
from pathlib import Path

from ffmpeg.asyncio import FFmpeg

logger = logging.getLogger(__name__)

PRESET_NAME = "Video to MP4"
INPUT_TYPE = "video"  # Accepts video files
DEFAULT_FRAMERATE = 24
DEFAULT_QUALITY = 15
OUTPUT_EXTENSION = ".mp4"
DESCRIPTION = "Convert any video format to MP4 with MPEG4/H.264 video and AAC audio"


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
    """Resolve FFmpeg executable robustly across environments."""
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

    # 2. Try SettingsService if available
    try:
        from zeroxe.services.settings_service import SettingsService
        res = _is_executable(SettingsService.get_ffmpeg_path())
        if res:
            return res
    except Exception:
        pass

    # 3. Environment variables
    for var in ("FFMPEG_BINARY", "FFMPEG_PATH"):
        res = _is_executable(os.environ.get(var, "").strip())
        if res:
            return res

    # 4. PATH search via shutil.which
    import shutil
    res = _is_executable(shutil.which("ffmpeg"))
    if res:
        return res

    # 5. Standard candidate locations
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
) -> bool:
    """Convert any video format to MP4.

    Args:
        input_path: Path to input video file
        output_file: Output MP4 file path
        framerate: Optional frame rate
        quality: Quality level 1-31, where 1 is best (default: 15)
        progress_callback: Optional callable for progress updates
        ffmpeg_executable: Optional explicit path to ffmpeg binary

    Returns:
        True if successful, False otherwise
    """
    try:
        inp = Path(input_path)
        if not inp.is_file():
            logger.error(f"Input file not found: {input_path}")
            return False

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg_bin = _resolve_ffmpeg_executable(ffmpeg_executable or kwargs.get("ffmpeg_executable"))

        logger.info(
            f"Converting video via FFmpeg ({ffmpeg_bin}):\n"
            f"  Input : {input_path}\n"
            f"  Output: {output_file}\n"
            f"  Quality: {quality}"
        )

        output_params = {
            "vcodec": "mpeg4",
            "qscale:v": str(quality),
            "acodec": "aac",
            "b:a": "192k",
            "pix_fmt": "yuv420p",
        }
        if framerate and framerate > 0:
            output_params["r"] = str(framerate)

        ffmpeg = (
            FFmpeg(executable=ffmpeg_bin)
            .option("y")  # overwrite output
            .input(str(inp.resolve()))
            .output(str(out_path.resolve()), **output_params)
        )

        if progress_callback:
            @ffmpeg.on("progress")
            def on_progress(p):
                try:
                    progress_callback(p)
                except Exception:
                    pass

        await ffmpeg.execute()

        logger.info("✓ Video conversion complete")
        return True

    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
        logger.error(traceback.format_exc())
        return False
