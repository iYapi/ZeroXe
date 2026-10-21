"""Converter Presets Package for ZeroXe Pipeline.

Provides FFMPEGManager and dynamically discoverable converter presets.
"""

from pathlib import Path
from typing import List

from .folder_to_mp4 import execute as _folder_to_mp4
from .img_to_mp4 import execute as _img_to_mp4
from .video_to_mp4 import execute as _video_to_mp4


class FFMPEGManager:
    """Unified FFmpeg manager matching pipeline conversion script."""

    folder_to_mp4 = staticmethod(_folder_to_mp4)
    video_to_mp4 = staticmethod(_video_to_mp4)
    img_to_mp4 = staticmethod(_img_to_mp4)


__all__ = ["FFMPEGManager", "folder_to_mp4", "img_to_mp4", "video_to_mp4"]
