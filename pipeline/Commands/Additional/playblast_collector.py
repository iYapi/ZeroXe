"""Playblast Collector for ZeroXe Pipeline.

Recursively scans the render path (defined in pipeline.yaml under global.renders)
to find and collect playblasts matching configured file formats and department codes.
For each selected shot, automatically identifies and copies the latest version or number.
"""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import yaml

logger = logging.getLogger(__name__)


@dataclass
class CopiedFileInfo:
    """Information about a successfully copied playblast file."""

    shot: str
    source: Path
    destination: Path
    size_bytes: int
    version_number: int


@dataclass
class CollectPlayblastResult:
    """Encapsulates the result of a playblast collection operation."""

    success: bool
    message: str
    destination_dir: Path
    copied_files: List[CopiedFileInfo] = field(default_factory=list)
    missing_shots: List[str] = field(default_factory=list)
    found_files: Dict[str, Path] = field(default_factory=dict)


class PlayblastCollector:
    """Core engine for scanning render paths and collecting the latest playblast versions."""

    @staticmethod
    def get_render_path(
        config_path: Optional[Union[str, Path]] = None,
        platform_name: Optional[str] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """Resolve render root directory for the specified or current platform from pipeline.yaml."""
        cfg = config_dict
        if cfg is None and config_path:
            p = Path(config_path)
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                except Exception as e:
                    logger.warning(f"Failed to read config from {p}: {e}")
                    cfg = {}
        if cfg is None:
            cfg = {}

        renders = (
            cfg.get("global", {}).get("renders", {})
            or cfg.get("renders", {})
            or cfg.get("project", {}).get("renders", {})
        )
        if not renders:
            module_dir = Path(__file__).resolve().parent
            for fb_path in [
                Path("pipeline/pipeline.yaml"),
                module_dir.parent.parent / "pipeline.yaml",
                module_dir.parent / "pipeline.yaml",
            ]:
                if fb_path.is_file():
                    try:
                        with open(fb_path, "r", encoding="utf-8") as fb:
                            fb_cfg = yaml.safe_load(fb) or {}
                            renders = (
                                fb_cfg.get("global", {}).get("renders", {})
                                or fb_cfg.get("renders", {})
                            )
                            if renders:
                                break
                    except Exception:
                        pass

        if not renders or not isinstance(renders, dict):
            return None

        plat = platform_name
        if not plat:
            if sys.platform.startswith("linux"):
                plat = "linux"
            elif sys.platform.startswith("win32") or sys.platform.startswith("win"):
                plat = "windows"
            elif sys.platform.startswith("darwin"):
                plat = "darwin"
            else:
                plat = "linux"

        render_str = renders.get(plat) or renders.get("linux") or next(iter(renders.values()), None)
        if render_str:
            return Path(str(render_str).strip())
        return None

    @staticmethod
    def get_department_code(
        department_name_or_code: str,
        config_path: Optional[Union[str, Path]] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Resolve department short code (e.g. 'Animation' -> 'anm', 'Layout' -> 'lay')."""
        target = (department_name_or_code or "").strip().lower()
        if not target:
            return ""

        cfg = config_dict
        if cfg is None and config_path:
            p = Path(config_path)
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                except Exception:
                    cfg = {}
        if cfg is None:
            cfg = {}

        departments = cfg.get("departments", {})
        if isinstance(departments, dict):
            # 1. Exact match by key
            for d_name, d_info in departments.items():
                if d_name.lower() == target:
                    code = str(d_info.get("code", "")).strip().lower() if isinstance(d_info, dict) else ""
                    return code or target

            # 2. Match by configured code
            for d_name, d_info in departments.items():
                if isinstance(d_info, dict):
                    code = str(d_info.get("code", "")).strip().lower()
                    if code == target:
                        return code

            # 3. Substring match
            for d_name, d_info in departments.items():
                d_lower = d_name.lower()
                if (d_lower in target or target in d_lower) and isinstance(d_info, dict):
                    code = str(d_info.get("code", "")).strip().lower()
                    if code:
                        return code

        # Known standard pipeline fallbacks
        fallbacks = {
            "animation": "anm",
            "layout": "lay",
            "blocking": "blk",
            "compositing": "comp",
            "lighting": "lgt",
            "fx": "fx",
            "2d": "anc",
            "animatic": "anc",
            "edit": "edit",
            "editing": "edit",
        }
        return fallbacks.get(target, target)

    @staticmethod
    def extract_version_or_number(filename: str, dept_code: Optional[str] = None) -> int:
        """Extract the version number or numeric identifier from a filename.

        Handles patterns like:
            - 'mdt_ep998_sq01_sh0010_lay_v001.mov' -> 1
            - 'mdt_ep998_sq01_sh0010_lay_v002.mov' -> 2
            - 'sh0010_anm_1.mov'                   -> 1
            - 'sh0010_anm_2.mov'                   -> 2
            - 'ep998_sq01_sh0010_anm_001.mov'      -> 1
            - 'sh0010_lay_v02_preview.mov'         -> 2
            - 'sh0010_lay.mov'                     -> 0
        """
        stem = Path(filename).stem

        # 1. Look for explicit version tag like v001, v1, ver01, version02
        # Preceded by delimiter or start of string, followed by delimiter, non-digit, or end of string
        m = re.search(r"(?:^|[_\-.])v(?:er(?:sion)?)?(\d+)(?=[_\-.]|$)", stem, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        # 2. Look for number directly following the department code (e.g. ..._lay_002 or ..._anm_1)
        if dept_code:
            clean_code = re.escape(dept_code.strip().lower())
            m = re.search(rf"(?:^|[_\-.])(?:{clean_code})[_\-.]+(\d+)(?=[_\-.]|$)", stem, flags=re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass

        # 3. Look for a trailing number at the end of the stem (e.g. ..._01, ..._2)
        m = re.search(r"[_\-.](\d+)$", stem)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        return 0

    @classmethod
    def get_shot_tokens(cls, shot_identifier: str) -> Set[str]:
        """Extract possible token variations that identify a shot in file paths and filenames.

        Guarantees that sequence tags (e.g. 'sq01') and episode tags (e.g. 'ep998')
        are NOT returned as shot tokens to prevent cross-shot false matching.
        """
        raw = str(shot_identifier or "").strip().lower()
        if not raw:
            return set()

        tokens: Set[str] = set()

        # If raw is a composite identifier like 'sq01_sh0010' or 'ep998_sq01_sh0010'
        shot_candidate = raw
        if "_" in raw:
            parts = [p.strip() for p in raw.split("_") if p.strip()]
            # Filter out episode (ep\d+) and sequence (sq\d+, seq\d+) parts
            non_seq_ep = [
                p for p in parts
                if not re.match(r"^ep\d+$", p) and not re.match(r"^(sq|seq)\d+$", p)
            ]
            if non_seq_ep:
                shot_candidate = non_seq_ep[-1]
                tokens.add(shot_candidate)
                # If sequence is present in composite, keep composite sequence+shot token (e.g. 'sq01_sh0010')
                seq_parts = [p for p in parts if re.match(r"^(sq|seq)\d+$", p)]
                if seq_parts:
                    tokens.add(f"{seq_parts[0]}_{shot_candidate}")
            else:
                tokens.add(raw)
        else:
            tokens.add(raw)

        # Generate shot token variations from shot_candidate
        # Examples: 'sh0010', 'shot0010', 'sh_0010', 'shot_0010', '0010', '10'
        m = re.search(r"(?:sh(?:ot)?_?)?(\d+)", shot_candidate)
        if m:
            digits = m.group(1)
            tokens.add(digits)
            tokens.add(f"sh{digits}")
            tokens.add(f"sh_{digits}")
            tokens.add(f"shot{digits}")
            tokens.add(f"shot_{digits}")
            try:
                num_int = int(digits)
                padded_4 = f"{num_int:04d}"
                tokens.add(padded_4)
                tokens.add(f"sh{padded_4}")
                tokens.add(f"sh_{padded_4}")
                tokens.add(f"shot{padded_4}")
                tokens.add(f"shot_{padded_4}")
            except ValueError:
                pass

        # Final safety cleanup: remove empty, single-character, or pure sequence/episode tokens
        cleaned: Set[str] = set()
        for t in tokens:
            t_clean = t.strip()
            if not t_clean or re.match(r"^ep\d+$", t_clean) or re.match(r"^(sq|seq)\d+$", t_clean):
                continue
            cleaned.add(t_clean)

        return cleaned

    @classmethod
    def matches_shot(
        cls,
        file_path: Union[str, Path],
        shot_identifier: str,
        dept_code: Optional[str] = None,
        file_format: Optional[str] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
    ) -> bool:
        """Check whether a playblast file matches a shot, department code, and format."""
        p = Path(file_path)

        # 1. Check file format / extension
        if file_format and file_format != "*":
            norm_fmt = ("." + file_format.lstrip(".")).lower()
            if p.suffix.lower() != norm_fmt:
                return False

        stem = p.stem.lower()
        full_str = str(p).lower().replace("\\", "/")

        # 2. Check department code in filename (e.g. '..._anm_...', '..._lay_...')
        if dept_code:
            code = dept_code.strip().lower()
            dept_pattern = rf"(?:^|[_\-.])({re.escape(code)})(?:[_\-.]|$)"
            if not re.search(dept_pattern, stem, flags=re.IGNORECASE):
                return False

        # Infer sequence / episode from composite shot_identifier if not provided
        shot_str = str(shot_identifier or "").strip().lower()
        if not sequence and "_" in shot_str:
            m_sq = re.search(r"(?:^|[_\-.])(sq\d+)(?:[_\-.]|$)", shot_str)
            if m_sq:
                sequence = m_sq.group(1)

        if not episode and "_" in shot_str:
            m_ep = re.search(r"(?:^|[_\-.])(ep\d+)(?:[_\-.]|$)", shot_str)
            if m_ep:
                episode = m_ep.group(1)

        # 3. Check episode match if provided
        if episode:
            ep_clean = episode.strip().lower()
            if ep_clean:
                ep_pattern = rf"(?:^|[_\-.])({re.escape(ep_clean)})(?:[_\-.]|$)"
                # If path contains a conflicting episode tag (e.g. ep02 when ep01 was requested)
                all_ep_in_path = re.findall(r"(?:^|[_\-.])(ep\d+)(?:[_\-.]|$)", full_str)
                if all_ep_in_path and ep_clean not in all_ep_in_path:
                    return False
                has_requested_ep = bool(re.search(ep_pattern, stem) or ep_clean in full_str)
                if not has_requested_ep:
                    return False

        # 4. Check sequence match if provided
        if sequence:
            sq_clean = sequence.strip().lower()
            if sq_clean:
                sq_pattern = rf"(?:^|[_\-.])({re.escape(sq_clean)})(?:[_\-.]|$)"
                # If path contains a different sequence (e.g. sq02 when sq01 requested)
                all_sq_in_path = re.findall(r"(?:^|[_\-.])(sq\d+)(?:[_\-.]|$)", full_str)
                if all_sq_in_path and sq_clean not in all_sq_in_path:
                    return False

        # 5. Check shot identifier match
        shot_tokens = cls.get_shot_tokens(shot_identifier)
        matched_shot = False
        for tok in shot_tokens:
            if not tok:
                continue
            # Match token as word/delimited token in stem or in parent directory name
            tok_pattern = rf"(?:^|[_\-.])({re.escape(tok)})(?:[_\-.]|$)"
            if re.search(tok_pattern, stem) or re.search(tok_pattern, p.parent.name.lower()):
                matched_shot = True
                break

        return matched_shot

    @classmethod
    def scan_playblasts(
        cls,
        render_path: Union[str, Path],
        shots: List[Any],
        dept_code: str,
        file_format: str,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
    ) -> Dict[str, Optional[Path]]:
        """Recursively scan render_path for matching playblasts and pick the latest version per shot.

        Returns a dictionary mapping shot_name -> Path of latest playblast (or None if not found).
        """
        render_root = Path(render_path)
        if not render_root.is_dir():
            logger.warning(f"Render path directory does not exist: {render_root}")
            return {cls._shot_to_name(s): None for s in shots}

        # Normalize file format
        norm_fmt = ("." + (file_format or "mov").lstrip(".")).lower()
        clean_dept = (dept_code or "").strip().lower()

        # Decide starting search directory: if all shots share a single episode, start at render_root / episode
        episodes_in_shots: Set[str] = set()
        if episode:
            episodes_in_shots.add(episode.strip().lower())
        for s in shots:
            s_ep = getattr(s, "episode", None) or (s.get("episode") if isinstance(s, dict) else None)
            if s_ep:
                episodes_in_shots.add(str(s_ep).strip().lower())

        search_dir = render_root
        if len(episodes_in_shots) == 1:
            single_ep = next(iter(episodes_in_shots))
            for cand in [render_root / single_ep, render_root / single_ep.upper()]:
                if cand.is_dir():
                    search_dir = cand
                    break

        # Build shot lookup list preserving each shot's specific sequence and episode
        shot_info_list: List[Tuple[str, str, Optional[str], Optional[str]]] = []
        shot_candidates: Dict[str, List[Path]] = {}
        seen_keys: Set[str] = set()

        for idx, s in enumerate(shots):
            s_name = cls._shot_to_name(s)
            s_seq = getattr(s, "sequence", sequence) if hasattr(s, "sequence") else (s.get("sequence") if isinstance(s, dict) else sequence)
            s_ep = getattr(s, "episode", episode) if hasattr(s, "episode") else (s.get("episode") if isinstance(s, dict) else episode)

            key = s_name
            if key in seen_keys:
                key = f"{s_name}_{idx}"
            seen_keys.add(key)

            shot_candidates[key] = []
            shot_info_list.append((key, s_name, s_seq, s_ep))

        # Recursive scan via os.walk
        for root, _, files in os.walk(search_dir):
            root_p = Path(root)
            for f_name in files:
                if not f_name.lower().endswith(norm_fmt):
                    continue

                f_path = root_p / f_name

                # Filter each shot
                for key, s_name, s_seq, s_ep in shot_info_list:
                    if cls.matches_shot(
                        file_path=f_path,
                        shot_identifier=s_name,
                        dept_code=clean_dept,
                        file_format=norm_fmt,
                        episode=s_ep,
                        sequence=s_seq,
                    ):
                        shot_candidates[key].append(f_path)

        # For each shot, select the candidate with highest version / number (tiebreak with mtime)
        result: Dict[str, Optional[Path]] = {}
        for s_name, candidates in shot_candidates.items():
            if not candidates:
                result[s_name] = None
                continue

            # Sort by (version_number, st_mtime)
            def _sort_key(p: Path) -> Tuple[int, float]:
                ver = cls.extract_version_or_number(p.name, clean_dept)
                try:
                    mtime = p.stat().st_mtime
                except Exception:
                    mtime = 0.0
                return (ver, mtime)

            candidates.sort(key=_sort_key)
            result[s_name] = candidates[-1]

        return result

    @classmethod
    def collect(
        cls,
        render_path: Union[str, Path],
        destination_dir: Union[str, Path],
        shots: List[Any],
        department: str,
        file_format: str = ".mov",
        config_path: Optional[Union[str, Path]] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
    ) -> CollectPlayblastResult:
        """Scan render path and copy the latest playblast for each shot into destination_dir."""
        dest_p = Path(destination_dir)
        dest_p.mkdir(parents=True, exist_ok=True)

        dept_code = cls.get_department_code(department, config_path=config_path)
        found_map = cls.scan_playblasts(
            render_path=render_path,
            shots=shots,
            dept_code=dept_code,
            file_format=file_format,
            episode=episode,
            sequence=sequence,
        )

        copied: List[CopiedFileInfo] = []
        missing: List[str] = []

        for s_name, src_file in found_map.items():
            if not src_file or not src_file.is_file():
                missing.append(s_name)
                continue

            target_dst = dest_p / src_file.name
            if target_dst.exists() and any(c.destination == target_dst for c in copied):
                # Avoid destination file collision if multiple shots produce same filename
                target_dst = dest_p / f"{s_name}_{src_file.name}"

            try:
                shutil.copy2(src_file, target_dst)
                size_b = target_dst.stat().st_size if target_dst.is_file() else 0
                ver = cls.extract_version_or_number(src_file.name, dept_code)
                copied.append(
                    CopiedFileInfo(
                        shot=s_name,
                        source=src_file,
                        destination=target_dst,
                        size_bytes=size_b,
                        version_number=ver,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to copy playblast {src_file} -> {target_dst}: {e}")
                missing.append(s_name)

        success = len(copied) > 0
        total = len(shots)

        if success and not missing:
            msg = f"Successfully collected {len(copied)}/{total} playblast(s) into:\n{dest_p}"
        elif success and missing:
            missing_str = ", ".join(missing[:5])
            if len(missing) > 5:
                missing_str += f", ... (+{len(missing) - 5} more)"
            msg = (
                f"Collected {len(copied)}/{total} playblast(s) into:\n{dest_p}\n\n"
                f"Playblasts not found for {len(missing)} shot(s): {missing_str}"
            )
        else:
            msg = (
                f"No matching playblast files found for {len(shots)} shot(s) in render path:\n{render_path}\n"
                f"(Filtering: format='{file_format}', department code='{dept_code}')"
            )

        return CollectPlayblastResult(
            success=success,
            message=msg,
            destination_dir=dest_p,
            copied_files=copied,
            missing_shots=missing,
            found_files={k: v for k, v in found_map.items() if v is not None},
        )

    @staticmethod
    def _shot_to_name(shot_item: Any) -> str:
        """Helper to extract shot name string from Shot object, dict, or str."""
        if hasattr(shot_item, "name"):
            name = str(shot_item.name)
            seq = getattr(shot_item, "sequence", "") or ""
            ep = getattr(shot_item, "episode", "") or ""
            res = name
            if seq and not res.startswith(f"{seq}_"):
                res = f"{seq}_{res}"
            if ep and not res.startswith(f"{ep}_"):
                res = f"{ep}_{res}"
            return res
        if isinstance(shot_item, dict):
            name = str(shot_item.get("name") or shot_item.get("id") or "")
            seq = str(shot_item.get("sequence") or "")
            ep = str(shot_item.get("episode") or "")
            res = name
            if seq and not res.startswith(f"{seq}_"):
                res = f"{seq}_{res}"
            if ep and not res.startswith(f"{ep}_"):
                res = f"{ep}_{res}"
            return res
        return str(shot_item)


# Standalone functional entrypoints
def scan_playblasts(
    render_path: Union[str, Path],
    shots: List[Any],
    dept_code: str,
    file_format: str,
    episode: Optional[str] = None,
    sequence: Optional[str] = None,
) -> Dict[str, Optional[Path]]:
    """Scan render path and return map of shot_name -> latest playblast Path."""
    return PlayblastCollector.scan_playblasts(
        render_path=render_path,
        shots=shots,
        dept_code=dept_code,
        file_format=file_format,
        episode=episode,
        sequence=sequence,
    )


def collect_playblasts(
    render_path: Union[str, Path],
    destination_dir: Union[str, Path],
    shots: List[Any],
    department: str,
    file_format: str = ".mov",
    config_path: Optional[Union[str, Path]] = None,
    episode: Optional[str] = None,
    sequence: Optional[str] = None,
) -> CollectPlayblastResult:
    """Collect latest playblasts for given shots from render_path into destination_dir."""
    return PlayblastCollector.collect(
        render_path=render_path,
        destination_dir=destination_dir,
        shots=shots,
        department=department,
        file_format=file_format,
        config_path=config_path,
        episode=episode,
        sequence=sequence,
    )


def get_render_path(
    config_path: Optional[Union[str, Path]] = None,
    platform_name: Optional[str] = None,
) -> Optional[Path]:
    """Resolve render path from pipeline.yaml configuration."""
    return PlayblastCollector.get_render_path(config_path=config_path, platform_name=platform_name)
