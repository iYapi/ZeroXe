"""Pipeline Preset: Image Sequence Pattern to MP4.

Converts an image sequence pattern (e.g., render_%04d.exr) to MP4.
Editable dynamically in the pipeline without recompiling ZeroXe application.
"""

import logging
import traceback
from collections.abc import Callable
from pathlib import Path

from ffmpeg.asyncio import FFmpeg

logger = logging.getLogger(__name__)

PRESET_NAME = "Image Sequence (Pattern) to MP4"
INPUT_TYPE = "sequence"
DEFAULT_FRAMERATE = 24
DEFAULT_QUALITY = 15
OUTPUT_EXTENSION = ".mp4"
DESCRIPTION = "Convert an image sequence pattern (e.g. shot_%04d.png) to MP4"


async def execute(
    input_path: str,
    output_file: str,
    framerate: int = DEFAULT_FRAMERATE,
    quality: int = DEFAULT_QUALITY,
    start_frame: int = 101,
    progress_callback: Callable | None = None,
    **kwargs,
) -> bool:
    """Convert an image sequence pattern to MP4.

    Args:
        input_path: Sequence pattern string (e.g. /path/to/img_%04d.png)
        output_file: Output MP4 path
        framerate: Output framerate (default 24)
        quality: Quality level 1-31 (default 15)
        start_frame: Start frame number (default 101)
        progress_callback: Optional callback for progress

    Returns:
        True if successful, False otherwise
    """
    try:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Executing FFmpeg to convert {input_path} to {output_file}...")

        ffmpeg = (
            FFmpeg()
            .option("y")  # overwrite output
            .input(
                str(input_path),
                framerate=str(framerate), start_number=str(start_frame),
            )
            .output(
                str(out_path.resolve()),
                **{"vcodec": "mpeg4", "qscale:v": str(quality), "pix_fmt": "yuv420p"},
            )
        )

        if progress_callback:
            @ffmpeg.on("progress")
            def on_progress(p):
                try:
                    progress_callback(p)
                except Exception:
                    pass

        await ffmpeg.execute()
        return True

    except Exception as e:
        logger.error(f"An error occurred while executing FFmpeg: {e}")
        logger.error(traceback.format_exc())
        return False
