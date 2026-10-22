"""Converter Service for ZeroXe.

Handles dynamic discovery, reloading, and execution of pipeline converter presets
without requiring the application to be recompiled.
"""

import asyncio
import datetime
import importlib.util
import inspect
import logging
import os
import re
import shutil
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx', '.ppm')
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.m2ts')


@dataclass
class ConverterPreset:
    """Represents a dynamically loaded converter preset from the pipeline."""

    id: str
    name: str
    description: str = ""
    input_type: str = "any"  # "folder" | "video" | "sequence" | "any"
    default_framerate: int = 24
    default_quality: int = 15
    output_extension: str = ".mp4"
    file_path: Path | None = None
    mtime: float | None = None
    handler: Callable | None = None


class ConverterService:
    """Service for discovering and executing external pipeline converter presets."""

    _cached_presets: ClassVar[dict[str, ConverterPreset]] = {}
    _cached_mtimes: ClassVar[dict[str, float]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all in-memory preset caches to force fresh reload."""
        cls._cached_presets.clear()
        cls._cached_mtimes.clear()

    @classmethod
    def get_ffmpeg_executable(cls) -> str:
        """Find the path to the ffmpeg executable across multiple environments.

        Order of resolution:
        1. SettingsService.get_ffmpeg_path() if configured and valid
        2. Environment variables FFMPEG_BINARY or FFMPEG_PATH
        3. shutil.which("ffmpeg")
        4. Standard system binary locations:
           - Linux/Unix: /usr/bin/ffmpeg, /usr/sbin/ffmpeg, /usr/local/bin/ffmpeg, /usr/local/sbin/ffmpeg, /bin/ffmpeg
           - macOS: /opt/homebrew/bin/ffmpeg, /opt/local/bin/ffmpeg
           - Windows: C:\\ffmpeg\\bin\\ffmpeg.exe, C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe
        5. Fallback to "ffmpeg"

        Also prepends the executable's directory to os.environ["PATH"] if missing.
        """
        def _try_candidate(candidate_path: str | Path | None) -> str | None:
            if not candidate_path:
                return None
            p = Path(candidate_path)
            try:
                if p.is_file() and os.access(p, os.X_OK):
                    cls._ensure_path_env(p.parent)
                    return str(p.resolve())
            except OSError:
                pass
            return None

        # 1. Configured path in Settings
        try:
            configured = SettingsService.get_ffmpeg_path()
            cand = _try_candidate(configured)
            if cand:
                return cand
        except Exception:
            pass

        # 2. Environment variables
        for var in ("FFMPEG_BINARY", "FFMPEG_PATH"):
            cand = _try_candidate(os.environ.get(var, "").strip())
            if cand:
                return cand

        # 3. PATH search via shutil.which
        which_path = shutil.which("ffmpeg")
        if which_path:
            cand = _try_candidate(which_path)
            if cand:
                return cand

        # 4. Standard candidate locations
        system_candidates = [
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
        for item in system_candidates:
            cand = _try_candidate(item)
            if cand:
                return cand

        return "ffmpeg"

    @classmethod
    def _ensure_path_env(cls, bin_dir: Path) -> None:
        """Ensure the directory containing ffmpeg binary is present in os.environ['PATH']."""
        try:
            dir_str = str(bin_dir.resolve())
            curr_path = os.environ.get("PATH", "")
            parts = curr_path.split(os.pathsep) if curr_path else []
            if dir_str not in parts:
                os.environ["PATH"] = f"{dir_str}{os.pathsep}{curr_path}" if curr_path else dir_str
        except Exception:
            pass

    @classmethod
    def get_preset_directories(cls, project_name: str | None = None) -> list[Path]:
        """Collect all search directories for converter presets."""
        dirs: list[Path] = []

        # 1. Active pipeline presets directory on NAS or configured path
        active_dir = PipelineService.get_converter_presets_dir(project_name=project_name)
        if active_dir and active_dir.is_dir() and active_dir not in dirs:
            dirs.append(active_dir)

        # 2. Local workspace repository fallback
        try:
            local_dir = Path(__file__).resolve().parents[3] / "pipeline" / "Presets" / "Converter"
            if local_dir.is_dir() and local_dir not in dirs:
                dirs.append(local_dir)
        except Exception:
            pass

        return dirs

    @classmethod
    def list_presets(cls, force_reload: bool = False, project_name: str | None = None) -> list[ConverterPreset]:
        """Discover and load all converter presets dynamically from pipeline.

        Automatically detects added or modified preset files on disk/NAS
        without restarting or recompiling the client app.
        """
        search_dirs = cls.get_preset_directories(project_name=project_name)

        if force_reload:
            cls.clear_cache()

        discovered: dict[str, ConverterPreset] = {}

        # Scan each directory for .py preset scripts
        for pdir in search_dirs:
            if not pdir.is_dir():
                continue

            for py_file in sorted(pdir.glob("*.py")):
                if py_file.name.startswith(("_", ".")):
                    continue

                preset_id = py_file.stem
                # Check if file has changed since last cached load
                try:
                    current_mtime = py_file.stat().st_mtime
                except OSError:
                    continue

                cached_preset = cls._cached_presets.get(preset_id)
                if (
                    not force_reload
                    and cached_preset
                    and cls._cached_mtimes.get(preset_id) == current_mtime
                ):
                    discovered[preset_id] = cached_preset
                    continue

                # Load or reload module dynamically via importlib
                loaded = cls._load_preset_from_file(py_file, current_mtime)
                if loaded:
                    cls._cached_presets[preset_id] = loaded
                    cls._cached_mtimes[preset_id] = current_mtime
                    discovered[preset_id] = loaded

        # Fallback to built-in presets if no external preset could be loaded
        if not discovered:
            builtins = cls._get_builtin_fallback_presets()
            for b in builtins:
                discovered[b.id] = b

        return list(discovered.values())

    @classmethod
    def get_preset(cls, preset_id: str, project_name: str | None = None) -> ConverterPreset | None:
        """Get a specific preset by its unique ID."""
        presets = cls.list_presets(project_name=project_name)
        for p in presets:
            if p.id == preset_id or p.name == preset_id:
                return p
        return None

    @classmethod
    def _load_preset_from_file(cls, file_path: Path, mtime: float) -> ConverterPreset | None:
        """Dynamically load preset metadata and execute callable from a Python script."""
        try:
            module_name = f"zeroxe_converter_preset_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if not spec or not spec.loader:
                logger.warning(f"Could not create importlib spec for preset: {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Extract metadata
            preset_name = getattr(
                module,
                "PRESET_NAME",
                file_path.stem.replace("_", " ").title(),
            )
            input_type = getattr(module, "INPUT_TYPE", "any").lower().strip()
            framerate = int(getattr(module, "DEFAULT_FRAMERATE", 24))
            quality = int(getattr(module, "DEFAULT_QUALITY", 15))
            output_ext = getattr(module, "OUTPUT_EXTENSION", ".mp4")
            description = getattr(module, "DESCRIPTION", (module.__doc__ or "").strip())

            # Find callable handler
            handler = getattr(module, "execute", None)
            if not handler:
                handler = getattr(module, "convert", None)
            if not handler:
                handler = getattr(module, "folder_to_mp4", None)
            if not handler:
                handler = getattr(module, "video_to_mp4", None)

            # If inside a class (e.g. FFMPEGManager)
            if not handler and hasattr(module, "FFMPEGManager"):
                mgr = module.FFMPEGManager
                if "folder" in file_path.stem.lower() and hasattr(mgr, "folder_to_mp4"):
                    handler = mgr.folder_to_mp4
                elif "video" in file_path.stem.lower() and hasattr(mgr, "video_to_mp4"):
                    handler = mgr.video_to_mp4
                elif hasattr(mgr, "execute"):
                    handler = mgr.execute

            if not callable(handler):
                logger.warning(f"Preset script '{file_path}' does not define a callable execute/convert handler.")
                return None

            return ConverterPreset(
                id=file_path.stem,
                name=preset_name,
                description=description,
                input_type=input_type,
                default_framerate=framerate,
                default_quality=quality,
                output_extension=output_ext,
                file_path=file_path,
                mtime=mtime,
                handler=handler,
            )

        except Exception as e:
            logger.error(f"Error dynamically loading preset from '{file_path}': {e}\n{traceback.format_exc()}")
            return None

    @classmethod
    def _get_builtin_fallback_presets(cls) -> list[ConverterPreset]:
        """Built-in fallback presets using python-ffmpeg in case external files are unreachable."""
        async def fallback_folder_to_mp4(input_path: str, output_file: str, framerate: int = 24, quality: int = 15, **kwargs) -> bool:
            from ffmpeg.asyncio import FFmpeg
            folder = Path(input_path)
            image_files = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS])
            if not image_files:
                return False
            concat_file = folder / "ffmpeg_files.txt"
            ffmpeg_bin = cls.get_ffmpeg_executable()
            try:
                with open(concat_file, 'w', encoding='utf-8') as f:
                    f.writelines(f"file '{img.name}'\n" for img in image_files)
                ffmpeg = (
                    FFmpeg(executable=ffmpeg_bin)
                    .option("y")
                    .option("f", "concat")
                    .option("safe", "0")
                    .option("r", str(framerate))
                    .input(str(concat_file))
                    .output(
                        output_file,
                        **{"vcodec": "mpeg4", "qscale:v": str(quality), "acodec": "aac", "b:a": "192k", "pix_fmt": "yuv420p", "vsync": "vfr"}
                    )
                )
                import os
                curr = os.getcwd()
                os.chdir(folder)
                try:
                    await ffmpeg.execute()
                finally:
                    os.chdir(curr)
                return True
            finally:
                if concat_file.exists():
                    concat_file.unlink()

        async def fallback_video_to_mp4(input_path: str, output_file: str, framerate: int = 24, quality: int = 15, **kwargs) -> bool:
            from ffmpeg.asyncio import FFmpeg
            ffmpeg_bin = cls.get_ffmpeg_executable()
            ffmpeg = (
                FFmpeg(executable=ffmpeg_bin)
                .option("y")
                .input(input_path)
                .output(
                    output_file,
                    **{"vcodec": "mpeg4", "qscale:v": str(quality), "acodec": "aac", "b:a": "192k", "pix_fmt": "yuv420p", "vsync": "vfr"}
                )
            )
            await ffmpeg.execute()
            return True

        return [
            ConverterPreset(
                id="folder_to_mp4",
                name="Folder (Image Sequence) to MP4",
                description="Convert all images in a folder to MP4 using concat demuxer",
                input_type="folder",
                default_framerate=24,
                default_quality=15,
                output_extension=".mp4",
                handler=fallback_folder_to_mp4,
            ),
            ConverterPreset(
                id="video_to_mp4",
                name="Video to MP4",
                description="Convert any video format to MP4 with MPEG4/H.264 video and AAC audio",
                input_type="video",
                default_framerate=24,
                default_quality=15,
                output_extension=".mp4",
                handler=fallback_video_to_mp4,
            ),
        ]

    @classmethod
    def execute_preset(
        cls,
        preset: str | ConverterPreset,
        input_path: str,
        output_file: str,
        framerate: int = 24,
        quality: int = 15,
        progress_callback: Callable | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """Execute a converter preset either synchronously or asynchronously.

        Returns:
            Tuple of (success: bool, status_message: str)
        """
        if isinstance(preset, str):
            p_obj = cls.get_preset(preset)
            if not p_obj:
                return False, f"Preset '{preset}' not found in pipeline."
        else:
            p_obj = preset

        if not p_obj or not callable(p_obj.handler):
            return False, f"Preset '{getattr(p_obj, 'name', 'Unknown')}' does not have a valid handler."

        start_time = datetime.datetime.now()
        success = False
        msg = ""
        error_trace = ""

        try:
            # Ensure output directory exists
            out_p = Path(output_file)
            out_p.parent.mkdir(parents=True, exist_ok=True)

            # Auto-resolve ffmpeg executable for all handlers if not explicitly specified
            if "ffmpeg_executable" not in kwargs:
                kwargs["ffmpeg_executable"] = cls.get_ffmpeg_executable()

            handler = p_obj.handler

            # Check if handler is an async coroutine function
            if inspect.iscoroutinefunction(handler):
                try:
                    # Run within asyncio event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    coro = handler(
                        input_path=str(input_path),
                        output_file=str(output_file),
                        framerate=framerate,
                        quality=quality,
                        progress_callback=progress_callback,
                        **kwargs,
                    )
                    success = loop.run_until_complete(coro)
                    loop.close()
                except Exception as ex:
                    logger.error(f"Async execution of preset failed: {ex}")
                    success = False
                    msg = f"Conversion failed: {ex}"
                    error_trace = traceback.format_exc()
            else:
                success = handler(
                    input_path=str(input_path),
                    output_file=str(output_file),
                    framerate=framerate,
                    quality=quality,
                    progress_callback=progress_callback,
                    **kwargs,
                )

            if success is False and not msg:
                msg = "Conversion returned failure status from FFmpeg."
            elif success is not False:
                if not Path(output_file).is_file():
                    success = False
                    msg = f"Process finished but output file was not created:\n{output_file}"
                else:
                    success = True
                    msg = f"Successfully converted to {output_file}"

        except Exception as e:
            success = False
            error_trace = traceback.format_exc()
            msg = f"Error during conversion: {e}"
            logger.error(f"{msg}\n{error_trace}")

        # Write to ZeroXe logs system
        if kwargs.get("write_log", True):
            try:
                from zeroxe.utils.log_util import write_process_log
                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                p_id = p_obj.id if p_obj else "unknown"
                p_name = p_obj.name if p_obj else "Unknown Preset"
                status_str = "SUCCESS" if success else "FAILED"
                content_lines = [
                    f"Converter Operation : {p_name}",
                    f"Preset ID           : {p_id}",
                    f"Input Path          : {input_path}",
                    f"Output File         : {output_file}",
                    f"Framerate           : {framerate} fps",
                    f"Quality             : {quality} (qscale)",
                    f"Duration            : {elapsed:.2f} seconds",
                    f"Status              : {status_str}",
                    f"Message             : {msg}",
                ]
                if not success and error_trace:
                    content_lines.extend(["", "Error Details:", error_trace])

                write_process_log(
                    category="converter",
                    process_name=f"converter_{p_id}",
                    content="\n".join(content_lines),
                    extra_meta={
                        "Preset": p_name,
                        "Status": status_str,
                        "Input": Path(input_path).name,
                        "Output": Path(output_file).name,
                        "Duration": f"{elapsed:.2f}s",
                    },
                )
            except Exception as log_err:
                logger.warning(f"Could not write process log for converter: {log_err}")

        return success, msg

    @classmethod
    def inspect_input_path(cls, path_str: str) -> dict[str, Any]:
        """Inspect a file or folder path and return item metadata.

        Returns dict with:
            - is_valid: bool
            - type: "folder" | "video" | "unknown"
            - name: str
            - count_display: str
            - preview_image: Optional[str]
            - suggested_output_name: str
        """
        p = Path(path_str)
        if not p.exists():
            return {"is_valid": False, "type": "unknown", "name": p.name, "version": "_v001", "count_display": "Not found", "preview_image": None}

        def _split_name_and_version(stem: str, is_sequence: bool = False) -> tuple[str, str]:
            if is_sequence:
                # Strip trailing frame digits (e.g. _0101, .0001, -0101) for image sequences
                clean = re.sub(r"([._-])\d+$", "", stem)
                base = clean if clean else stem
            else:
                base = stem
            version = "_v001"
            v_match = re.search(r"([._-]v\d+)$", base, re.IGNORECASE)
            if v_match:
                version = v_match.group(1)
                base = base[:v_match.start()]
            return (base if base else stem), version

        if p.is_dir():
            image_files = sorted([
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            ])
            first_img = str(image_files[0]) if image_files else None
            first_img_name = image_files[0].name if image_files else ""
            if image_files:
                base_name, version = _split_name_and_version(image_files[0].stem, is_sequence=True)
            else:
                base_name, version = p.name, "_v001"

            return {
                "is_valid": len(image_files) > 0,
                "type": "folder",
                "name": base_name,
                "version": version,
                "first_image_name": first_img_name,
                "count_display": f"{len(image_files)} images" if image_files else "No images found",
                "preview_image": first_img,
                "suggested_output_name": f"{base_name}{version}",
                "file_count": len(image_files),
            }

        elif p.is_file():
            ext = p.suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                base_name, version = _split_name_and_version(p.stem, is_sequence=False)
                return {
                    "is_valid": True,
                    "type": "video",
                    "name": base_name,
                    "version": version,
                    "first_image_name": p.name,
                    "count_display": f"1 video ({ext[1:].upper()})",
                    "preview_image": None,
                    "suggested_output_name": f"{base_name}{version}",
                    "file_count": 1,
                }
            elif ext in IMAGE_EXTENSIONS:
                # Single image or image sequence member: detect siblings in same folder
                parent = p.parent
                image_files = sorted([
                    f for f in parent.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                ])
                first_img = str(image_files[0]) if image_files else str(p)
                first_img_name = image_files[0].name if image_files else p.name
                base_name, version = _split_name_and_version(Path(first_img).stem, is_sequence=True)
                return {
                    "is_valid": True,
                    "type": "folder",
                    "name": base_name,
                    "version": version,
                    "first_image_name": first_img_name,
                    "count_display": f"{len(image_files)} images",
                    "preview_image": first_img,
                    "suggested_output_name": f"{base_name}{version}",
                    "file_count": len(image_files),
                    "override_path": str(parent),
                }

        return {"is_valid": False, "type": "unknown", "name": p.name, "count_display": "Unsupported format", "preview_image": None}
