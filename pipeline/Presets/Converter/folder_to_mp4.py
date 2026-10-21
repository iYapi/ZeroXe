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


async def execute(
    input_path: str,
    output_file: str,
    framerate: int = DEFAULT_FRAMERATE,
    quality: int = DEFAULT_QUALITY,
    progress_callback: Callable | None = None,
    **kwargs,
) -> bool:
    """Convert all images in a folder to MP4 using concat demuxer.

    Args:
        input_path: Path to folder containing images
        output_file: Output MP4 file path
        framerate: Frame rate for output video (default: 24)
        quality: Quality level 1-31, where 1 is best (default: 15)
        progress_callback: Optional callable for progress updates

    Returns:
        True if successful, False otherwise
    """
    try:
        folder = Path(input_path)
        if not folder.is_dir():
            logger.error(f"Input path is not a directory: {input_path}")
            return False

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Get all image files sorted by name
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx', '.ppm')
        image_files = sorted([
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ])

        if not image_files:
            logger.error(f"No image files found in {input_path}")
            return False

        logger.info(
            f"Executing FFmpeg to convert {len(image_files)} images from {input_path} to {output_file}...\n"
            f"  First image: {image_files[0].name}\n"
            f"  Last image: {image_files[-1].name}\n"
            f"  Framerate: {framerate} fps\n"
            f"  Quality: {quality}"
        )

        # Create concat file listing all images
        concat_file = folder / "ffmpeg_files.txt"

        try:
            with open(concat_file, 'w', encoding='utf-8') as f:
                for img_file in image_files:
                    # Write relative path for safe concat demuxing
                    f.write(f"file '{img_file.name}'\n")

            logger.info(f"Created concat file with {len(image_files)} entries")

            # Build FFmpeg command using concat demuxer
            ffmpeg = (
                FFmpeg()
                .option("y")  # overwrite output
                .option("f", "concat")
                .option("safe", "0")
                .option("r", str(framerate))  # input framerate
                .input(str(concat_file))
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

            # Change to folder directory for relative paths
            original_dir = os.getcwd()
            os.chdir(folder)

            try:
                logger.info("Starting FFmpeg conversion...")
                await ffmpeg.execute()
                logger.info("✓ Conversion complete!")
            finally:
                os.chdir(original_dir)

            return True

        finally:
            # Clean up concat file
            if concat_file.exists():
                try:
                    concat_file.unlink()
                    logger.info("Cleaned up temporary concat file")
                except Exception as ex:
                    logger.warning(f"Could not remove temporary concat file: {ex}")

    except Exception as e:
        logger.error(f"An error occurred while executing FFmpeg: {e}")
        logger.error(traceback.format_exc())
        return False
