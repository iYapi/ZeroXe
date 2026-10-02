"""Modular Entrypoint for ZeroXe Pipeline Commands.

Provides unified Python API and CLI interface for Qt app integration,
path generation, and builder dispatching.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult

# Default pipeline configuration location (relative to project)
DEFAULT_PIPELINE_YAML = Path(__file__).resolve().parent.parent / "pipeline.yaml"


def get_generator(config_path: Optional[Union[str, Path]] = None) -> ShotPathGenerator:
    """Create ShotPathGenerator initialized with pipeline.yaml."""
    cfg = Path(config_path) if config_path else DEFAULT_PIPELINE_YAML
    return ShotPathGenerator(config=cfg)


def resolve_shot_paths(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_number: int = 1,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> ShotPathResult:
    """Resolve master path and version path for a given shot.

    Args:
        department: Department name or code (e.g. 'Layout' or 'lay')
        episode: Episode identifier (e.g. 'ep998')
        sequence: Sequence identifier (e.g. 'sq01' or 'ep998_sq01')
        shot: Shot identifier (e.g. 'sh0020' or 'ep998_sq01_sh0020')
        version_number: Integer version number (e.g. 1 -> v001)
        version_folder: Folder name for version files (e.g. 'progress')
        config_path: Path to custom pipeline.yaml (defaults to pipeline/pipeline.yaml)
        project_path: Override mount root path if needed
        extension: File extension (default '.blend')

    Returns:
        ShotPathResult dataclass with master_path, version_path, directories, and filenames.
    """
    generator = get_generator(config_path)
    return generator.generate_shot_paths(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_number=version_number,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def list_shot_versions(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> List[Tuple[int, Path]]:
    """List existing versions for a shot."""
    generator = get_generator(config_path)
    return generator.list_existing_versions(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


def get_next_shot_version(
    department: str,
    episode: str,
    sequence: str,
    shot: str,
    version_folder: str = "progress",
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    extension: str = ".blend",
) -> int:
    """Get the next version number for a shot."""
    generator = get_generator(config_path)
    return generator.get_next_version_number(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_folder=version_folder,
        project_path=project_path,
        extension=extension,
    )


# ==============================================================================
# CLI Interface
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="ZeroXe Pipeline Command Line Tool")
    parser.add_argument("--config", "-c", type=Path, default=None, help="Path to pipeline.yaml")

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # shot-path command
    shot_parser = subparsers.add_parser("shot-path", help="Resolve master and version paths for a shot")
    shot_parser.add_argument("--dept", "-d", required=True, help="Department name or code (e.g. Layout, lay)")
    shot_parser.add_argument("--ep", "-e", required=True, help="Episode (e.g. ep998)")
    shot_parser.add_argument("--sq", "-s", required=True, help="Sequence (e.g. sq01)")
    shot_parser.add_argument("--sh", required=True, help="Shot (e.g. sh0020)")
    shot_parser.add_argument("--ver", "-v", type=int, default=1, help="Version number (default: 1)")
    shot_parser.add_argument("--ver-folder", default="progress", help="Version folder name (default: progress)")
    shot_parser.add_argument("--mount", help="Override project mount root path")
    shot_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.command == "shot-path":
        result = resolve_shot_paths(
            department=args.dept,
            episode=args.ep,
            sequence=args.sq,
            shot=args.sh,
            version_number=args.ver,
            version_folder=args.ver_folder,
            config_path=args.config,
            project_path=args.mount,
        )

        if args.json:
            output = {
                "master_path": str(result.master_path),
                "version_path": str(result.version_path),
                "shot_dir": str(result.shot_dir),
                "version_dir": str(result.version_dir),
                "file_name": result.file_name,
                "version_file_name": result.version_file_name,
                "version_number": result.version_number,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Master Path : {result.master_path}")
            print(f"Version Path: {result.version_path}")
            print(f"Shot Dir    : {result.shot_dir}")
            print(f"Version Dir : {result.version_dir}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
