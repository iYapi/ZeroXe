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
    """Convert any video format to MP4.

    Args:
        input_path: Path to input video file
        output_file: Output MP4 file path
        framerate: Optional frame rate
        quality: Quality level 1-31, where 1 is best (default: 15)
        progress_callback: Optional callable for progress updates
        ffmpeg_executable: Optional explicit path to ffmpeg binary

    Returns:
        Tuple of (success: bool, status_message: str)
    """
    try:
        inp = Path(input_path)
        if not inp.is_file():
            msg = f"Input file not found: {input_path}"
            logger.error(msg)
            return False, msg

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
        return True, f"Successfully converted to {out_path.name}"

    except Exception as e:
        err_msg = f"FFmpeg error ({ffmpeg_bin if 'ffmpeg_bin' in locals() else 'ffmpeg'}): {e}"
        logger.error(err_msg)
        logger.error(traceback.format_exc())
        return False, err_msg
