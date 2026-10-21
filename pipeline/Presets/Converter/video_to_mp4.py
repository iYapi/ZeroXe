"""Pipeline Preset: Video to MP4.

Converts any video format to MP4 with MPEG4/H.264 video and AAC audio.
Editable dynamically in the pipeline without recompiling ZeroXe application.
"""

import logging
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


async def execute(
    input_path: str,
    output_file: str,
    framerate: int = DEFAULT_FRAMERATE,
    quality: int = DEFAULT_QUALITY,
    progress_callback: Callable | None = None,
    **kwargs,
) -> bool:
    """Convert any video format to MP4.

    Args:
        input_path: Path to input video file
        output_file: Output MP4 file path
        framerate: Optional frame rate
        quality: Quality level 1-31, where 1 is best (default: 15)
        progress_callback: Optional callable for progress updates

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

        logger.info(
            f"Converting video:\n"
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
            FFmpeg()
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
