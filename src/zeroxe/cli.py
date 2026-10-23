"""Command Line Interface (CLI) Entrypoint for ZerØXe.

Provides unified terminal command handling for launching the desktop GUI,
querying environment info, resolving shot & asset paths, generating DCC scene files,
executing pipeline features, transcoding media, managing file locks, and configuring settings.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _get_app_info() -> dict[str, Any]:
    """Gather diagnostic application and environment details safely and quickly."""
    import shutil

    from zeroxe import config
    from zeroxe.api.gazu_client import is_kitsu_configured, is_kitsu_connected
    from zeroxe.services.settings_service import SettingsService

    ffmpeg_bin = SettingsService.get_ffmpeg_path()
    if not ffmpeg_bin:
        bundled_candidate = config.BASE_DIR / "pipeline" / "bin" / ("windows" if sys.platform == "win32" else "linux") / "ffmpeg"
        if bundled_candidate.is_file():
            ffmpeg_bin = str(bundled_candidate)
        else:
            ffmpeg_bin = shutil.which("ffmpeg") or ""

    return {
        "app_name": config.APP_NAME,
        "version": config.APP_VERSION,
        "organization": config.ORGANIZATION_NAME,
        "maintainer": config.MAINTAINER,
        "website": config.MAINTAINER_WEB,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": sys.platform,
        "base_dir": str(config.BASE_DIR),
        "user_data_dir": str(config.USER_DATA_DIR),
        "scripts_dir": str(config.SCRIPTS_DIR),
        "assets_dir": str(config.ASSETS_DIR),
        "zeroxe_map_path": SettingsService.get_zeroxe_map_path(),
        "active_blender": SettingsService.get_active_blender(),
        "pureref_path": SettingsService.get_pureref_path(),
        "ffmpeg_executable": ffmpeg_bin,
        "kitsu_url": SettingsService.get_kitsu_url(),
        "kitsu_configured": is_kitsu_configured(),
        "kitsu_connected": is_kitsu_connected(),
    }



def _run_gui(project: str | None = None) -> int:
    """Launch the PySide6 Qt desktop GUI application."""
    from zeroxe.main import run
    run()
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Build and return the comprehensive Zeroxe argument parser."""
    from zeroxe import config

    parser = argparse.ArgumentParser(
        prog="zeroxe",
        description=f"{config.APP_NAME} v{config.APP_VERSION} - Modular Animation & VFX Production Pipeline Launcher & CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  zeroxe                                            # Launch desktop GUI
  zeroxe gui                                        # Explicitly launch desktop GUI
  zeroxe info                                       # Show application and environment info
  zeroxe shot-path -d Layout -e ep998 -s sq01 --sh sh0020
  zeroxe asset-path -t CHAR -n Hero_Char -d Model
  zeroxe generate -f /path/to/shot.blend -d Layout
  zeroxe up-version -f /path/to/shot_v001.blend
  zeroxe up-master -f /path/to/progress/shot_v002.blend
  zeroxe convert -i /path/to/frames_folder/ -p folder_to_mp4
  zeroxe lock -k ep998_sq01_sh0020_lay --check
  zeroxe config --list
""",
    )

    parser.add_argument(
        "-v",
        "-V",
        "--version",
        action="version",
        version=f"{config.APP_NAME} {config.APP_VERSION}",
        help="Show program's version number and exit.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. gui command
    gui_parser = subparsers.add_parser("gui", help="Launch the Zeroxe PySide6 desktop GUI application")
    gui_parser.add_argument("--project", "-p", default=None, help="Preload a specific project by name on startup")

    # 2. info command
    info_parser = subparsers.add_parser("info", help="Display application environment, runtime paths, and configuration")
    info_parser.add_argument("--json", action="store_true", help="Output information in JSON format")

    # 3. shot-path command
    shot_parser = subparsers.add_parser("shot-path", help="Resolve master and version paths for a shot")
    shot_parser.add_argument("--dept", "-d", required=True, help="Department name or code (e.g. Layout, lay, Animation, anm)")
    shot_parser.add_argument("--ep", "-e", required=True, help="Episode code (e.g. ep998)")
    shot_parser.add_argument("--sq", "-s", required=True, help="Sequence code (e.g. sq01)")
    shot_parser.add_argument("--sh", required=True, help="Shot code (e.g. sh0020)")
    shot_parser.add_argument("--ver", "-v", type=int, default=1, help="Version number (default: 1)")
    shot_parser.add_argument("--ver-folder", default="progress", help="Version folder name (default: progress)")
    shot_parser.add_argument("--mount", help="Override project mount root path")
    shot_parser.add_argument("--config", "-c", type=Path, default=None, help="Path to custom pipeline.yaml")
    shot_parser.add_argument("--project", "-p", default=None, help="Project name (from zeroxe_map.yaml)")
    shot_parser.add_argument("--list-versions", action="store_true", help="List all existing version files on disk")
    shot_parser.add_argument("--next-version", action="store_true", help="Calculate next incremental version path")
    shot_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 4. asset-path command
    asset_parser = subparsers.add_parser("asset-path", help="Resolve master and version paths for an asset")
    asset_parser.add_argument("--type", "-t", required=True, help="Asset type (e.g. CHAR, PROPS, SET, VEHICLE)")
    asset_parser.add_argument("--name", "-n", required=True, help="Asset name (e.g. Hero_Char, c-hero)")
    asset_parser.add_argument("--dept", "-d", default="", help="Department/task name (e.g. Model, Texture)")
    asset_parser.add_argument("--ver", "-v", type=int, default=1, help="Version number (default: 1)")
    asset_parser.add_argument("--ver-folder", default="progress", help="Version folder name (default: progress)")
    asset_parser.add_argument("--mount", help="Override project mount root path")
    asset_parser.add_argument("--config", "-c", type=Path, default=None, help="Path to custom pipeline.yaml")
    asset_parser.add_argument("--project", "-p", default=None, help="Project name (from zeroxe_map.yaml)")
    asset_parser.add_argument("--list-versions", action="store_true", help="List all existing asset version files on disk")
    asset_parser.add_argument("--next-version", action="store_true", help="Calculate next incremental version path")
    asset_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 5. generate command
    gen_parser = subparsers.add_parser("generate", help="Generate initial DCC scene file using pipeline builder")
    gen_parser.add_argument("--file", "-f", required=True, help="Input DCC file path or target shot file path")
    gen_parser.add_argument("--dept", "-d", default="Layout", help="Department name (e.g. Layout, Animation, Lighting)")
    gen_parser.add_argument("--mode", "-m", default="previous", help="Builder resolution mode (e.g. previous, scan)")
    gen_parser.add_argument("--shot-data", default="{}", help="JSON string of shot data / metadata (frame_in, frame_out, etc.)")
    gen_parser.add_argument("--fg-yaml", default="", help="Path to YAML file defining FG assets for Lighting")
    gen_parser.add_argument("--master-shot", default="", help="Sibling shot name for Mastershot template (Compositing)")
    gen_parser.add_argument("--master-file", default="", help="Custom .blend file for Mastershot template (Compositing)")
    gen_parser.add_argument("--run", "--execute", action="store_true", dest="run_blender", help="Execute generated script in Blender immediately")
    gen_parser.add_argument("--blender", default="", help="Path to Blender executable (defaults to configured active blender)")
    gen_parser.add_argument("--config", "-c", type=Path, default=None, help="Path to custom pipeline.yaml")
    gen_parser.add_argument("--project", "-p", default=None, help="Project name")
    gen_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 6. up-version command
    up_ver_parser = subparsers.add_parser("up-version", help="Generate or execute Up Version script for a DCC file")
    up_ver_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    up_ver_parser.add_argument("--run", "--execute", action="store_true", dest="run_blender", help="Execute Up Version script in Blender immediately")
    up_ver_parser.add_argument("--blender", default="", help="Path to Blender executable")
    up_ver_parser.add_argument("--project", "-p", default=None, help="Project name")
    up_ver_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 7. up-master command
    up_mst_parser = subparsers.add_parser("up-master", help="Generate or execute Up Master script to publish to master")
    up_mst_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    up_mst_parser.add_argument("--preset", default="", help="Path to preset python script to embed (e.g. bake animation)")
    up_mst_parser.add_argument("--run", "--execute", action="store_true", dest="run_blender", help="Execute Up Master script in Blender immediately")
    up_mst_parser.add_argument("--blender", default="", help="Path to Blender executable")
    up_mst_parser.add_argument("--project", "-p", default=None, help="Project name")
    up_mst_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 8. list-features command
    list_feat_parser = subparsers.add_parser("list-features", help="List all available registered pipeline features")
    list_feat_parser.add_argument("--dept", "-d", default="", help="Filter by department (e.g. Animation, Layout)")
    list_feat_parser.add_argument("--project", "-p", default=None, help="Project name")
    list_feat_parser.add_argument("--config", "-c", type=Path, default=None, help="Path to pipeline.yaml")
    list_feat_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 9. execute-feature command
    exec_feat_parser = subparsers.add_parser("execute-feature", help="Execute a pipeline feature dynamically")
    exec_feat_parser.add_argument("--name", "-n", required=True, help="Feature name (e.g. 'Up Version', 'Up Master')")
    exec_feat_parser.add_argument("--file", "-f", required=True, help="Input DCC file path")
    exec_feat_parser.add_argument("--dept", "-d", default="", help="Department name")
    exec_feat_parser.add_argument("--preset", default="", help="Path to preset python script")
    exec_feat_parser.add_argument("--fg-yaml", default="", help="Path to FG assets YAML for Lighting")
    exec_feat_parser.add_argument("--master-shot", default="", help="Sibling shot name for Mastershot template")
    exec_feat_parser.add_argument("--master-file", default="", help="Custom .blend file for Mastershot template")
    exec_feat_parser.add_argument("--run", "--execute", action="store_true", dest="run_blender", help="Execute script in Blender if feature requires DCC")
    exec_feat_parser.add_argument("--blender", default="", help="Path to Blender executable")
    exec_feat_parser.add_argument("--project", "-p", default=None, help="Project name")
    exec_feat_parser.add_argument("--config", "-c", type=Path, default=None, help="Path to custom pipeline.yaml")
    exec_feat_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 10. lock command
    lock_parser = subparsers.add_parser("lock", help="Check, acquire, or release cooperative entity file locks")
    lock_parser.add_argument("--key", "-k", required=True, help="Entity key (e.g. ep998_sq01_sh0010_anm)")
    lock_parser.add_argument("--check", action="store_true", help="Check current lock status (default)")
    lock_parser.add_argument("--acquire", action="store_true", help="Acquire lock on entity")
    lock_parser.add_argument("--release", action="store_true", help="Release lock on entity")
    lock_parser.add_argument("--force", action="store_true", help="Force break lock (unlock or steal)")
    lock_parser.add_argument("--history", action="store_true", help="Retrieve version audit history for entity")
    lock_parser.add_argument("--user", "-u", default="", help="User name (defaults to current user)")
    lock_parser.add_argument("--kitsu-id", default="", help="Kitsu user ID")
    lock_parser.add_argument("--project", "-p", default=None, help="Project name")
    lock_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 11. convert command
    conv_parser = subparsers.add_parser("convert", help="Transcode image sequence folders or video files using presets")
    conv_parser.add_argument("--input", "-i", required=True, help="Path to input sequence folder or video file")
    conv_parser.add_argument("--preset", default="", help="Preset ID (e.g. 'folder_to_mp4', 'video_to_mp4', auto-detected if empty)")
    conv_parser.add_argument("--output", "-o", default="", help="Destination output file path (auto-generated if empty)")
    conv_parser.add_argument("--framerate", "-r", type=int, default=24, help="Target framerate (default: 24)")
    conv_parser.add_argument("--quality", "-q", type=int, default=15, help="Quality / CRF factor (default: 15)")
    conv_parser.add_argument("--project", "-p", default=None, help="Project name")
    conv_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 12. list-presets command
    list_pre_parser = subparsers.add_parser("list-presets", help="List available converter / transcoder presets")
    list_pre_parser.add_argument("--project", "-p", default=None, help="Project name")
    list_pre_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 13. inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect an image sequence folder or media file")
    inspect_parser.add_argument("--input", "-i", required=True, help="Path to media file or folder")
    inspect_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 14. config / settings command
    cfg_parser = subparsers.add_parser("config", aliases=["settings"], help="Read or update Zeroxe application settings")
    cfg_parser.add_argument("--list", action="store_true", help="List all application configuration settings")
    cfg_parser.add_argument("--get", metavar="KEY", default="", help="Get value for a configuration key (e.g. software/active_blender)")
    cfg_parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set value for a configuration key")
    cfg_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # 15. kitsu command
    kitsu_parser = subparsers.add_parser("kitsu", help="Check Kitsu authentication status and inspect projects")
    kitsu_parser.add_argument("--status", action="store_true", help="Check Kitsu connection & credential status (default)")
    kitsu_parser.add_argument("--login", action="store_true", help="Attempt authentication with configured credentials")
    kitsu_parser.add_argument("--projects", action="store_true", help="List projects available on Kitsu")
    kitsu_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    return parser


def handle_info(args: argparse.Namespace) -> int:
    """Handle `zeroxe info` subcommand."""
    info = _get_app_info()
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print("=" * 60)
    print(f"  {info['app_name']} System & Runtime Information")
    print("=" * 60)
    print(f"Version:            {info['version']}")
    print(f"Platform:           {info['platform']}")
    print(f"Python:             {info['python_version']} ({info['python_executable']})")
    print(f"Base Directory:     {info['base_dir']}")
    print(f"User Data Dir:      {info['user_data_dir']}")
    print(f"Scripts Dir:        {info['scripts_dir']}")
    print("-" * 60)
    print(f"Active Blender:     {info['active_blender'] or '(Not configured)'}")
    print(f"PureRef:            {info['pureref_path'] or '(Not configured)'}")
    print(f"FFmpeg Binary:      {info['ffmpeg_executable'] or '(Not found)'}")
    if info.get('active_pipeline_dir'):
        print(f"Pipeline Dir:       {info['active_pipeline_dir']}")
    if info.get('active_pipeline_yaml'):
        print(f"Pipeline YAML:      {info['active_pipeline_yaml']}")
    print("-" * 60)
    print(f"Kitsu Host:         {info['kitsu_url'] or '(Not configured)'}")
    print(f"Kitsu Configured:   {'Yes' if info['kitsu_configured'] else 'No'}")
    print(f"Kitsu Connected:    {'Yes' if info['kitsu_connected'] else 'No'}")
    print("=" * 60)
    return 0


def handle_shot_path(args: argparse.Namespace) -> int:
    """Handle `zeroxe shot-path` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService
    from zeroxe.services.settings_service import SettingsService

    res = None
    try:
        from pipeline.Commands.main import resolve_shot_paths
        config_path = args.config or PipelineService.get_active_pipeline_yaml_path(args.project)
        ver_folder = args.ver_folder or SettingsService.get_version_folder() or "progress"

        res = resolve_shot_paths(
            department=args.dept,
            episode=args.ep,
            sequence=args.sq,
            shot=args.sh,
            version_number=args.ver,
            version_folder=ver_folder,
            config_path=config_path,
            project_path=args.mount,
        )
    except Exception:
        try:
            res = PipelineService.resolve_shot(
                department=args.dept,
                episode=args.ep,
                sequence=args.sq,
                shot=args.sh,
                version_number=args.ver,
                project_name=args.project,
                project_path=args.mount,
            )
        except Exception:
            res = None

    if not res:
        err = f"Failed to resolve shot path for {args.ep}_{args.sq}_{args.sh} in department '{args.dept}'."
        if args.json:
            print(json.dumps({"success": False, "error": err}, indent=2))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    existing_versions: list[str] = []
    if args.list_versions:
        try:
            from pipeline.Commands.main import list_shot_versions
            existing_tuples = list_shot_versions(
                department=args.dept,
                episode=args.ep,
                sequence=args.sq,
                shot=args.sh,
                version_folder=args.ver_folder,
                config_path=args.config or PipelineService.get_active_pipeline_yaml_path(args.project),
                project_path=args.mount,
            )
            existing_versions = [str(p[1]) for p in existing_tuples]
        except Exception:
            existing_versions = [
                str(p) for p in PipelineService.list_versions(res.master_path, version_folder=args.ver_folder, project_name=args.project)
            ]

    next_version_str = ""
    if args.next_version:
        try:
            from pipeline.Commands.main import get_next_shot_version_path
            next_version_str = str(get_next_shot_version_path(
                department=args.dept,
                episode=args.ep,
                sequence=args.sq,
                shot=args.sh,
                version_folder=args.ver_folder,
                config_path=args.config or PipelineService.get_active_pipeline_yaml_path(args.project),
                project_path=args.mount,
            ))
        except Exception:
            next_version_str = str(PipelineService.get_next_version(res.master_path, version_folder=args.ver_folder, project_name=args.project))

    data: dict[str, Any] = {
        "success": True,
        "master_path": str(res.master_path),
        "version_path": str(res.version_path),
        "shot_dir": str(res.shot_dir),
        "version_dir": str(res.version_dir),
        "file_name": res.file_name,
        "version_file_name": res.version_file_name,
        "version_number": res.version_number,
    }
    if args.list_versions:
        data["existing_versions"] = existing_versions
    if args.next_version:
        data["next_version_path"] = next_version_str

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Master Path:  {res.master_path}")
        print(f"Version Path: {res.version_path}")
        print(f"Shot Dir:     {res.shot_dir}")
        print(f"Version Dir:  {res.version_dir}")
        if args.next_version:
            print(f"Next Version: {next_version_str}")
        if args.list_versions:
            print(f"Existing Versions ({len(existing_versions)}):")
            for v in existing_versions:
                print(f"  - {v}")
    return 0


def handle_asset_path(args: argparse.Namespace) -> int:
    """Handle `zeroxe asset-path` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService
    from zeroxe.services.settings_service import SettingsService

    res = None
    try:
        from pipeline.Commands.main import resolve_asset_paths
        config_path = args.config or PipelineService.get_active_pipeline_yaml_path(args.project)
        ver_folder = args.ver_folder or SettingsService.get_version_folder() or "progress"

        res = resolve_asset_paths(
            asset_type=args.type,
            asset_name=args.name,
            department=args.dept,
            version_number=args.ver,
            version_folder=ver_folder,
            config_path=config_path,
            project_path=args.mount,
        )
    except Exception:
        try:
            res = PipelineService.resolve_asset(
                asset_type=args.type,
                asset_name=args.name,
                department=args.dept,
                version_number=args.ver,
                project_name=args.project,
                project_path=args.mount,
            )
        except Exception:
            res = None

    if not res:
        err = f"Failed to resolve asset path for {args.type}/{args.name}."
        if args.json:
            print(json.dumps({"success": False, "error": err}, indent=2))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    existing_versions: list[str] = []
    if args.list_versions:
        try:
            from pipeline.Commands.main import list_asset_versions
            existing_tuples = list_asset_versions(
                asset_type=args.type,
                asset_name=args.name,
                department=args.dept,
                version_folder=args.ver_folder,
                config_path=args.config or PipelineService.get_active_pipeline_yaml_path(args.project),
                project_path=args.mount,
            )
            existing_versions = [str(p[1]) for p in existing_tuples]
        except Exception:
            existing_versions = [
                str(p) for p in PipelineService.list_asset_versions(res.master_path, version_folder=args.ver_folder, project_name=args.project)
            ]

    next_version_str = ""
    if args.next_version:
        try:
            from pipeline.Commands.main import get_next_asset_version_path
            next_version_str = str(get_next_asset_version_path(
                asset_type=args.type,
                asset_name=args.name,
                department=args.dept,
                version_folder=args.ver_folder,
                config_path=args.config or PipelineService.get_active_pipeline_yaml_path(args.project),
                project_path=args.mount,
            ))
        except Exception:
            next_version_str = str(PipelineService.get_next_asset_version(res.master_path, version_folder=args.ver_folder, project_name=args.project))

    data: dict[str, Any] = {
        "success": True,
        "master_path": str(res.master_path),
        "version_path": str(res.version_path),
        "asset_dir": str(res.asset_dir),
        "version_dir": str(res.version_dir),
        "file_name": res.file_name,
        "version_file_name": res.version_file_name,
        "version_number": res.version_number,
    }
    if args.list_versions:
        data["existing_versions"] = existing_versions
    if args.next_version:
        data["next_version_path"] = next_version_str

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Master Path:  {res.master_path}")
        print(f"Version Path: {res.version_path}")
        print(f"Asset Dir:    {res.asset_dir}")
        print(f"Version Dir:  {res.version_dir}")
        if args.next_version:
            print(f"Next Version: {next_version_str}")
        if args.list_versions:
            print(f"Existing Versions ({len(existing_versions)}):")
            for v in existing_versions:
                print(f"  - {v}")
    return 0


def handle_generate(args: argparse.Namespace) -> int:
    """Handle `zeroxe generate` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService

    shot_data = {}
    if args.shot_data:
        try:
            shot_data = json.loads(args.shot_data)
        except Exception as e:
            if not args.json:
                print(f"Warning: Could not parse --shot-data JSON: {e}", file=sys.stderr)

    success, msg, target_path = PipelineService.execute_feature(
        feature_name="Generate",
        filepath=args.file,
        department=args.dept,
        project_name=args.project,
        config_path=args.config,
        shot_data=shot_data,
        builder_mode=args.mode,
        fg_yaml=args.fg_yaml or None,
        master_shot=args.master_shot or None,
        master_file=args.master_file or None,
    )

    blender_executed = False
    blender_output = ""
    blender_success = False

    if success and getattr(args, "run_blender", False):
        # We need the generated script to execute it in Blender
        # PipelineService execute_feature generated the target file and script
        module = PipelineService.load_pipeline_module(args.project)
        gen_script = ""
        if module and hasattr(module, "generate_builder_script"):
            gen_script, _ = module.generate_builder_script(
                filepath=args.file,
                department=args.dept,
                shot_data=shot_data,
                config_path=args.config,
                builder_mode=args.mode,
                fg_yaml=args.fg_yaml or None,
                master_shot=args.master_shot or None,
                master_file=args.master_file or None,
            )
        if gen_script:
            blender_success, blender_output = PipelineService.execute_blender_script(
                script=gen_script,
                blender_path=args.blender or None,
            )
            blender_executed = True

    data = {
        "success": success and (not blender_executed or blender_success),
        "message": msg,
        "target_path": target_path,
        "blender_executed": blender_executed,
        "blender_success": blender_success,
        "blender_output": blender_output,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if success:
            print("Generated Scene Setup successfully.")
            print(f"Target Path: {target_path}")
            if blender_executed:
                status_str = "SUCCESS" if blender_success else "FAILED"
                print(f"Blender Headless Execution: {status_str}")
                if blender_output:
                    print(f"Output:\n{blender_output}")
        else:
            print(f"Error: {msg}", file=sys.stderr)
    return 0 if (success and (not blender_executed or blender_success)) else 1


def handle_up_version(args: argparse.Namespace) -> int:
    """Handle `zeroxe up-version` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService

    success, msg, target_path = PipelineService.execute_feature(
        feature_name="Up Version",
        filepath=args.file,
        project_name=args.project,
    )

    blender_executed = False
    blender_output = ""
    blender_success = False

    if success and getattr(args, "run_blender", False):
        module = PipelineService.load_pipeline_module(args.project)
        if module and hasattr(module, "generate_up_version_script"):
            script, _ = module.generate_up_version_script(args.file)
            blender_success, blender_output = PipelineService.execute_blender_script(
                script=script,
                blender_path=args.blender or None,
            )
            blender_executed = True

    data = {
        "success": success and (not blender_executed or blender_success),
        "message": msg,
        "target_path": target_path,
        "blender_executed": blender_executed,
        "blender_success": blender_success,
        "blender_output": blender_output,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if success:
            print(f"Up Version successful: {target_path}")
            if blender_executed:
                print(f"Blender Execution: {'SUCCESS' if blender_success else 'FAILED'}")
        else:
            print(f"Error: {msg}", file=sys.stderr)
    return 0 if (success and (not blender_executed or blender_success)) else 1


def handle_up_master(args: argparse.Namespace) -> int:
    """Handle `zeroxe up-master` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService

    setting_data = {"script": args.preset} if args.preset else None
    success, msg, target_path = PipelineService.execute_feature(
        feature_name="Up Master",
        filepath=args.file,
        setting_data=setting_data,
        project_name=args.project,
    )

    blender_executed = False
    blender_output = ""
    blender_success = False

    if success and getattr(args, "run_blender", False):
        module = PipelineService.load_pipeline_module(args.project)
        if module and hasattr(module, "generate_up_master_script"):
            script, _ = module.generate_up_master_script(args.file, setting_data=setting_data)
            blender_success, blender_output = PipelineService.execute_blender_script(
                script=script,
                blender_path=args.blender or None,
            )
            blender_executed = True

    data = {
        "success": success and (not blender_executed or blender_success),
        "message": msg,
        "target_path": target_path,
        "blender_executed": blender_executed,
        "blender_success": blender_success,
        "blender_output": blender_output,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if success:
            print(f"Up Master successful: {target_path}")
            if blender_executed:
                print(f"Blender Execution: {'SUCCESS' if blender_success else 'FAILED'}")
        else:
            print(f"Error: {msg}", file=sys.stderr)
    return 0 if (success and (not blender_executed or blender_success)) else 1


def handle_list_features(args: argparse.Namespace) -> int:
    """Handle `zeroxe list-features` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService

    features = []
    try:
        from pipeline.Commands.main import list_features
        features = list_features(
            department=args.dept,
            config_path=args.config or PipelineService.get_active_pipeline_yaml_path(args.project),
        )
    except Exception:
        features = PipelineService.list_features(
            department=args.dept,
            project_name=args.project,
        )

    if args.json:
        print(json.dumps({"features": features}, indent=2))
    else:
        print("Available Pipeline Features:")
        for f in features:
            print(f"  - {f}")
    return 0


def handle_execute_feature(args: argparse.Namespace) -> int:
    """Handle `zeroxe execute-feature` subcommand."""
    from zeroxe.services.pipeline_service import PipelineService

    setting_data = {"script": args.preset} if args.preset else None
    success = False
    msg = ""
    target_path = None

    if args.config:
        try:
            from pipeline.Commands.main import run_pipeline_feature
            res = run_pipeline_feature(
                feature_name=args.name,
                filepath=args.file,
                department=args.dept,
                config_path=args.config,
                setting_data=setting_data,
                fg_yaml=args.fg_yaml or None,
                master_shot=args.master_shot or None,
                master_file=args.master_file or None,
            )
            if hasattr(res, "success"):
                success = res.success
                msg = res.message
                target_path = res.target_path
            elif isinstance(res, dict):
                success = res.get("success", True)
                msg = res.get("message", "")
                target_path = res.get("target_path") or res.get("version_path")
            else:
                success = True
                msg = str(res)
        except Exception as e:
            msg = str(e)
            success = False

    if not success and not args.config:
        success, msg, target_path = PipelineService.execute_feature(
            feature_name=args.name,
            filepath=args.file,
            department=args.dept,
            project_name=args.project,
            setting_data=setting_data,
            fg_yaml=args.fg_yaml or None,
            master_shot=args.master_shot or None,
            master_file=args.master_file or None,
        )

    data = {
        "success": success,
        "message": msg,
        "target_path": target_path,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if success:
            print(f"Feature '{args.name}' executed successfully.")
            if target_path:
                print(f"Target Path: {target_path}")
        else:
            print(f"Error executing feature '{args.name}': {msg}", file=sys.stderr)
    return 0 if success else 1


def handle_lock(args: argparse.Namespace) -> int:
    """Handle `zeroxe lock` subcommand."""
    from zeroxe.services.lock_service import LockService

    if args.history:
        history = LockService.get_history(args.key, project_name=args.project)
        if args.json:
            print(json.dumps({"key": args.key, "history": history}, indent=2))
        else:
            print(f"Version History for '{args.key}':")
            versions = history.get("versions", [])
            if not versions:
                print("  No recorded history.")
            for v in versions:
                print(f"  - Version: {v.get('version')}, User: {v.get('user')}, Date: {v.get('timestamp')}, File: {v.get('file_path')}")
        return 0

    if args.release:
        success, msg = LockService.release_lock(args.key, project_name=args.project)
        if args.json:
            print(json.dumps({"success": success, "message": msg}, indent=2))
        else:
            print(f"Lock Release: {'Success' if success else 'Failed'} - {msg}")
        return 0 if success else 1

    if args.force:
        success, msg = LockService.force_unlock(args.key, project_name=args.project)
        if args.json:
            print(json.dumps({"success": success, "message": msg}, indent=2))
        else:
            print(f"Force Unlock: {'Success' if success else 'Failed'} - {msg}")
        return 0 if success else 1

    if args.acquire:
        success, msg, lock_info = LockService.acquire_lock(args.key, force=args.force, project_name=args.project)
        if args.json:
            print(json.dumps({"success": success, "message": msg, "lock_info": lock_info}, indent=2))
        else:
            print(f"Acquire Lock: {'Success' if success else 'Failed'} - {msg}")
        return 0 if success else 1

    # Default to check lock
    is_locked, lock_info = LockService.check_lock(args.key, project_name=args.project)
    user = LockService.get_current_user()
    current_kitsu_id = user.kitsu_id
    current_name = user.name

    locked_by = ""
    locked_by_id = ""
    timestamp = ""
    is_locked_by_me = False
    if is_locked and lock_info:
        locked_by = lock_info.get("name", "")
        locked_by_id = lock_info.get("kitsu_id", "")
        timestamp = lock_info.get("timestamp", "")
        if current_kitsu_id and locked_by_id:
            is_locked_by_me = (str(current_kitsu_id) == str(locked_by_id))
        elif current_name and locked_by:
            is_locked_by_me = (current_name.strip().lower() == locked_by.strip().lower())

    data = {
        "key": args.key,
        "is_locked": is_locked,
        "is_locked_by_me": is_locked_by_me,
        "locked_by": locked_by,
        "locked_by_id": locked_by_id,
        "timestamp": timestamp,
        "lock_info": lock_info,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if is_locked:
            by_str = f"Locked by: {locked_by or 'Unknown user'}"
            if is_locked_by_me:
                by_str += " (You)"
            if timestamp:
                by_str += f" since {timestamp}"
            print(f"Status: LOCKED\n{by_str}")
        else:
            print("Status: UNLOCKED (Available)")
    return 0


def handle_convert(args: argparse.Namespace) -> int:
    """Handle `zeroxe convert` subcommand."""
    from zeroxe.services.converter_service import ConverterService

    input_path = args.input
    preset = args.preset
    output_file = args.output

    # Auto-inspect if preset or output is missing
    inspect_data = ConverterService.inspect_input_path(input_path)
    if not inspect_data.get("is_valid"):
        err = f"Input path '{input_path}' is invalid or contains no readable media."
        if args.json:
            print(json.dumps({"success": False, "error": err}, indent=2))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    if not preset:
        preset = "folder_to_mp4" if inspect_data.get("type") == "folder" else "video_to_mp4"

    if not output_file:
        suggested = inspect_data.get("suggested_output_name") or "output"
        out_ext = ".mp4"
        p_obj = ConverterService.get_preset(preset, project_name=args.project)
        if p_obj and p_obj.output_extension:
            out_ext = p_obj.output_extension
        output_file = str(Path(input_path).resolve().parent / f"{suggested}{out_ext}")

    success, msg = ConverterService.execute_preset(
        preset=preset,
        input_path=input_path,
        output_file=output_file,
        framerate=args.framerate,
        quality=args.quality,
        project_name=args.project,
    )

    data = {
        "success": success,
        "message": msg,
        "input": input_path,
        "preset": preset,
        "output": output_file,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if success:
            print("Conversion Succeeded!")
            print(f"Output File: {output_file}")
        else:
            print(f"Conversion Failed: {msg}", file=sys.stderr)
    return 0 if success else 1


def handle_list_presets(args: argparse.Namespace) -> int:
    """Handle `zeroxe list-presets` subcommand."""
    from zeroxe.services.converter_service import ConverterService

    presets = ConverterService.list_presets(project_name=args.project)
    p_list = [
        {
            "id": p.id,
            "name": p.name,
            "input_type": p.input_type,
            "default_framerate": p.default_framerate,
            "default_quality": p.default_quality,
            "output_extension": p.output_extension,
        }
        for p in presets
    ]

    if args.json:
        print(json.dumps({"presets": p_list}, indent=2))
    else:
        print(f"Available Converter Presets ({len(p_list)}):")
        for p in p_list:
            print(f"  - [{p['id']}] {p['name']} (Input: {p['input_type']}, Ext: {p['output_extension']}, FPS: {p['default_framerate']})")
    return 0


def handle_inspect(args: argparse.Namespace) -> int:
    """Handle `zeroxe inspect` subcommand."""
    from zeroxe.services.converter_service import ConverterService

    res = ConverterService.inspect_input_path(args.input)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if not res.get("is_valid"):
            print(f"Path '{args.input}' is invalid or media was not detected.")
            return 1
        print(f"Media Inspection: {args.input}")
        print(f"  Type:                  {res.get('type')}")
        print(f"  Detected Name:         {res.get('name')}")
        print(f"  Detected Version:      {res.get('version')}")
        print(f"  File Count:            {res.get('file_count')}")
        print(f"  Suggested Output:      {res.get('suggested_output_name')}")
    return 0


def handle_config(args: argparse.Namespace) -> int:
    """Handle `zeroxe config` subcommand."""
    from zeroxe.services.settings_service import SettingsService
    from zeroxe.utils.security import encrypt_string

    settings = SettingsService._settings()

    if args.set:
        key, val = args.set
        # Encrypt password keys automatically
        if "password" in key.lower():
            enc_key = key if key.endswith("_enc") else f"{key}_enc"
            settings.setValue(enc_key, encrypt_string(val))
        else:
            settings.setValue(key, val)
        settings.sync()
        if args.json:
            print(json.dumps({"success": True, "key": key, "value": val}, indent=2))
        else:
            print(f"Updated setting '{key}' = '{val}'")
        return 0

    if args.get:
        val = settings.value(args.get, "")
        if "password" in args.get.lower():
            val = SettingsService.get_kitsu_password()
        if args.json:
            print(json.dumps({"key": args.get, "value": val}, indent=2))
        else:
            print(f"{args.get}: {val}")
        return 0

    # Default to listing all keys
    all_keys = sorted(settings.allKeys())
    data: dict[str, Any] = {}
    for k in all_keys:
        if "password" in k.lower():
            data[k] = "******"
        else:
            data[k] = settings.value(k)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("Zeroxe Configuration Settings:")
        if not data:
            print("  (No settings found or defaults in use)")
        for k, v in data.items():
            print(f"  {k} = {v}")
    return 0


def handle_kitsu(args: argparse.Namespace) -> int:
    """Handle `zeroxe kitsu` subcommand."""
    from zeroxe.api.gazu_client import (
        init_kitsu,
        is_kitsu_configured,
        is_kitsu_connected,
    )
    from zeroxe.services.settings_service import SettingsService

    if args.login or args.projects:
        success, msg = init_kitsu()
    else:
        success = is_kitsu_connected()
        msg = "Connected" if success else ("Configured" if is_kitsu_configured() else "Not configured")

    projects = []
    if args.projects and is_kitsu_connected():
        from zeroxe.services.project_service import ProjectService
        projs = ProjectService.get_all_projects()
        projects = [{"id": p.id, "name": p.name, "code": p.code} for p in projs]

    data = {
        "configured": is_kitsu_configured(),
        "connected": is_kitsu_connected(),
        "url": SettingsService.get_kitsu_url(),
        "email": SettingsService.get_kitsu_email(),
        "message": msg,
    }
    if args.projects:
        data["projects"] = projects

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Kitsu Host:       {data['url'] or '(Not set)'}")
        print(f"Kitsu User:       {data['email'] or '(Not set)'}")
        print(f"Status:           {msg}")
        if args.projects:
            print(f"\nProjects ({len(projects)}):")
            for p in projects:
                print(f"  - [{p['code']}] {p['name']} (ID: {p['id']})")
    return 0 if (not args.login or success) else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Zeroxe unified CLI and GUI entrypoint.

    - When executed without CLI arguments, launches the desktop Qt GUI.
    - When executed with subcommands/flags, runs headless terminal workflows.
    """
    if argv is None:
        argv = sys.argv[1:]

    # 1. If no arguments are passed, launch the PySide6 GUI
    if not argv:
        return _run_gui()

    # 2. Check for explicit GUI flag
    if argv == ["--gui"]:
        return _run_gui()

    # 3. Create parser and parse arguments
    parser = create_parser()
    args = parser.parse_args(argv)

    # 4. Dispatch based on subcommand
    if not args.command or args.command == "gui":
        return _run_gui(getattr(args, "project", None))

    dispatch_map = {
        "info": handle_info,
        "shot-path": handle_shot_path,
        "asset-path": handle_asset_path,
        "generate": handle_generate,
        "up-version": handle_up_version,
        "up-master": handle_up_master,
        "list-features": handle_list_features,
        "execute-feature": handle_execute_feature,
        "lock": handle_lock,
        "convert": handle_convert,
        "list-presets": handle_list_presets,
        "inspect": handle_inspect,
        "config": handle_config,
        "settings": handle_config,
        "kitsu": handle_kitsu,
    }

    handler = dispatch_map.get(args.command)
    if handler:
        try:
            return handler(args)
        except Exception as e:
            if getattr(args, "json", False):
                print(json.dumps({"success": False, "error": str(e)}, indent=2))
            else:
                print(f"Error: {e}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
