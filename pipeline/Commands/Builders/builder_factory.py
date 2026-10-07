"""Builder Factory for ZeroXe Pipeline Shot and File Generation.

Dynamically discovers and executes division/department builders from project tools
and builder search paths without hardcoding department names.
"""

from dataclasses import dataclass
import importlib.util
import inspect
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

from .animatic_builder import AnimaticBuilder
from .animation_builder import AnimationBuilder, BlockingAnimationBuilder
from .layout_builder import LayoutBuilder

logger = logging.getLogger(__name__)


@dataclass
class BuilderResult:
    """Result of builder file generation."""

    success: bool
    message: str
    script: str = ""
    target_version_path: str = ""
    target_final_path: str = ""
    source_path: str = ""


class SafeAssetDepartment(dict):
    """Dictionary supporting nested {"Asset": {"asset_type": ...}}, "asset_type", and flat keys safely."""

    def __init__(
        self,
        asset_types: Dict[str, Any],
        raw_asset_dept: Optional[Dict[str, Any]] = None,
        project_path: Optional[str] = None,
    ):
        raw = dict(raw_asset_dept or {})
        proj_root = (project_path or "").rstrip("/\\")

        # Normalize each asset_type entry to have both 'id' and 'kitsu_id', and resolve @project_path@
        resolved_types: Dict[str, Dict[str, Any]] = {}
        for k, v in asset_types.items():
            if isinstance(v, dict):
                v_copy = dict(v)
                k_id = v_copy.get("kitsu_id") or v_copy.get("id") or ""
                v_copy["id"] = k_id
                v_copy["kitsu_id"] = k_id
                if "base_path" in v_copy and isinstance(v_copy["base_path"], str):
                    v_copy["base_path"] = v_copy["base_path"].replace("@project_path@", proj_root)
                resolved_types[k] = v_copy
            else:
                resolved_types[k] = v

        asset_section = {
            "based": "asset",
            "asset_type": resolved_types,
            **raw,
        }
        super().__init__({
            "Asset": asset_section,
            "asset": asset_section,
            "asset_type": resolved_types,
            "asset_types": resolved_types,
            **resolved_types,
        })
        self._asset_types = resolved_types
        self._asset_section = asset_section

    def __getitem__(self, key: Any) -> Any:
        if key in self:
            return super().__getitem__(key)
        key_str = str(key)
        if key_str.lower() in ("asset", "assets"):
            return self._asset_section
        if key_str.lower() in ("asset_type", "asset_types"):
            return self._asset_types
        if key_str.upper() in self._asset_types:
            return self._asset_types[key_str.upper()]
        return {}

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            return super().get(key, default)
        key_str = str(key)
        if key_str.lower() in ("asset", "assets"):
            return self._asset_section
        if key_str.lower() in ("asset_type", "asset_types"):
            return self._asset_types
        if key_str.upper() in self._asset_types:
            return self._asset_types[key_str.upper()]
        return default if default is not None else {}


class BuilderFactory:
    """Factory and dynamic dispatcher for pipeline division builders."""

    _cached_builder_classes: Dict[str, Any] = {}

    @classmethod
    def _resolve_search_paths(
        cls,
        project_path: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        global_cfg: Optional[Dict[str, Any]] = None,
        dept_cfg: Optional[Dict[str, Any]] = None,
    ) -> List[Path]:
        """Collect potential search directories for division builder scripts."""
        search_paths: List[Path] = []
        proj_root = (project_path or "").rstrip("/\\")

        # 1. Department-specific builder path in pipeline.yaml
        if dept_cfg:
            b_path = dept_cfg.get("builder") or (dept_cfg.get("scripts") or {}).get("builder")
            if b_path and isinstance(b_path, str):
                resolved_b = b_path.replace("@project_path@", proj_root) if proj_root else b_path
                p = Path(resolved_b)
                if p.is_dir():
                    search_paths.append(p)
                elif p.is_file():
                    search_paths.append(p.parent)

        # 2. Global builder path in pipeline.yaml
        if global_cfg:
            g_builder = global_cfg.get("builder_path") or (global_cfg.get("tools") or {}).get("builder")
            if g_builder and isinstance(g_builder, str):
                resolved_g = g_builder.replace("@project_path@", proj_root) if proj_root else g_builder
                p = Path(resolved_g)
                if p.is_dir():
                    search_paths.append(p)

        # 3. Pipeline repository directories (Modular pipeline builders)
        if config_path:
            cfg_dir = Path(config_path).parent
            pipe_candidates = [
                cfg_dir / "Commands" / "Builders",
                cfg_dir / "Builders",
            ]
            for pc in pipe_candidates:
                if pc.is_dir() and pc not in search_paths:
                    search_paths.append(pc)

        # 4. Standard NAS tool preset builder paths (Legacy fallback)
        if proj_root:
            p_root = Path(proj_root)
            candidates = [
                p_root / "00_tools" / "01_preset_script" / "zeroxe-conf" / "builder",
                p_root / "00_tools" / "01_preset_script" / "builder",
                p_root / "00_tools" / "builder",
                p_root / "zeroxe-conf" / "builder",
            ]
            for c in candidates:
                if c.is_dir() and c not in search_paths:
                    search_paths.append(c)

        return search_paths

    @classmethod
    def _find_builder_file(
        cls,
        department: str,
        dept_cfg: Optional[Dict[str, Any]] = None,
        search_paths: Optional[List[Path]] = None,
        project_path: Optional[str] = None,
    ) -> Optional[Path]:
        """Scan candidate search paths for a matching division builder python file."""
        if not search_paths:
            return None

        cfg = dept_cfg or {}
        code = str(cfg.get("code", "")).strip().lower()
        dept_clean = department.strip().lower().replace(" ", "_")
        source = str(cfg.get("source", "")).strip().lower()

        # Direct department builder configuration
        custom_builder = cfg.get("builder") or (cfg.get("scripts") or {}).get("builder")
        if custom_builder and isinstance(custom_builder, str):
            proj_root = (project_path or "").rstrip("/\\")
            resolved = custom_builder.replace("@project_path@", proj_root) if proj_root else custom_builder
            p = Path(resolved)
            if p.is_file():
                return p

        # Candidate filenames based on department naming
        candidate_names = [
            f"{dept_clean}_builder.py",
            f"{code}_builder.py" if code else None,
            f"builder_{dept_clean}.py",
            f"builder_{code}.py" if code else None,
            f"{dept_clean}.py",
            f"{code}.py" if code else None,
        ]

        # Structural candidate filenames based on pipeline division role
        if source == "init":
            candidate_names.extend(["layout_builder.py", "init_builder.py"])
        elif source and source not in ("", "none", "null"):
            candidate_names.extend(["blocking_animation_builder.py", "animation_builder.py", "shot_sync_builder.py"])
        else:
            candidate_names.extend(["animatic_builder.py", "2d_builder.py", "empty_builder.py"])

        candidate_names = [c for c in candidate_names if c]

        for s_dir in search_paths:
            if not s_dir.is_dir():
                continue

            # 1. Exact candidate matches
            for fname in candidate_names:
                target_file = s_dir / fname
                if target_file.is_file():
                    return target_file

            # 2. Number-prefixed / glob matches in s_dir (e.g. 00_animatic_builder.py, 01_layout_builder.py, 03_lighting_builder.py, 04_vfx_builder.py, 05_compositing_builder.py, 06_editing_builder.py)
            try:
                dir_files = [f for f in s_dir.iterdir() if f.is_file() and f.suffix.lower() == ".py"]
            except Exception:
                continue

            # Search keywords based on department name and code
            patterns: List[str] = [dept_clean]
            if code and len(code) >= 2:
                patterns.append(code)

            if "animat" in dept_clean or "2d" in dept_clean or code == "anc":
                patterns.extend(["animatic", "2d", "anc"])
            if "layout" in dept_clean or code == "lay":
                patterns.extend(["layout", "lay"])
            if "anim" in dept_clean or "block" in dept_clean or code in ("anm", "blk"):
                patterns.extend(["blocking", "animation", "anm", "blk"])
            if "light" in dept_clean or code == "lgt":
                patterns.extend(["lighting", "light", "lgt"])
            if "vfx" in dept_clean or "fx" in dept_clean or code == "fx":
                patterns.extend(["vfx", "fx"])
            if "comp" in dept_clean or code == "comp":
                patterns.extend(["compositing", "comp"])
            if "edit" in dept_clean or code == "edit":
                patterns.extend(["editing", "edit"])

            # Find matching file in directory
            for f in sorted(dir_files, key=lambda x: x.name):
                f_lower = f.stem.lower()
                for pat in patterns:
                    if pat and pat in f_lower and "builder" in f_lower:
                        return f

            # Fallback matching based on division source role
            for f in sorted(dir_files, key=lambda x: x.name):
                f_lower = f.stem.lower()
                if source == "init" and ("layout" in f_lower or "init" in f_lower):
                    return f
                elif source and source not in ("", "none", "null") and ("blocking" in f_lower or "animation" in f_lower):
                    return f
                elif not source and ("animatic" in f_lower or "2d" in f_lower):
                    return f

        return None

    @classmethod
    def _load_builder_from_file(cls, file_path: Path) -> Any:
        """Dynamically load and instantiate builder class from a Python file."""
        key = str(file_path.resolve())
        if key in cls._cached_builder_classes:
            return cls._cached_builder_classes[key]()

        module_name = f"zeroxe_builder_{file_path.stem}_{abs(hash(key))}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if not (spec and spec.loader):
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Inspect classes in module
        target_cls = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if inspect.isclass(attr) and attr.__module__ == module_name:
                if hasattr(attr, "extract_data") or attr_name.endswith("Builder"):
                    target_cls = attr
                    break

        if target_cls:
            cls._cached_builder_classes[key] = target_cls
            return target_cls()

        # If no class, return the module itself if it has extract_data
        if hasattr(module, "extract_data"):
            cls._cached_builder_classes[key] = lambda: module
            return module

        return None

    @classmethod
    def get_builder(
        cls,
        department: str,
        department_config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Union[str, Path]] = None,
        project_path: Optional[str] = None,
        global_config: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Select appropriate division builder instance dynamically from path or pipeline schema.

        Does not hardcode department names; dynamically inspects builder paths and schema roles.
        """
        dept_cfg = department_config or {}

        # 1. Search for builder script file in configured builder search paths (e.g. 00_tools/01_preset_script/zeroxe-conf/builder)
        search_paths = cls._resolve_search_paths(
            project_path=project_path,
            config_path=config_path,
            global_cfg=global_config,
            dept_cfg=dept_cfg,
        )

        builder_file = cls._find_builder_file(
            department=department,
            dept_cfg=dept_cfg,
            search_paths=search_paths,
            project_path=project_path,
        )

        if builder_file:
            try:
                loaded = cls._load_builder_from_file(builder_file)
                if loaded:
                    return loaded
            except Exception as e:
                logger.warning(f"Could not load builder from {builder_file}: {e}")

        # 2. Built-in Fallback by division role and type
        return cls._get_builtin_builder(department=department, dept_cfg=dept_cfg)

    @classmethod
    def _get_builtin_builder(cls, department: str, dept_cfg: Optional[Dict[str, Any]] = None) -> Any:
        """Instantiate standard built-in division builder."""
        from .lighting_builder import LightingBuilder
        from .vfx_builder import VFXBuilder
        from .compositing_builder import CompositingBuilder
        from .editing_builder import EditingBuilder

        cfg = dept_cfg or {}
        dept_clean = department.strip().lower()
        code = str(cfg.get("code", "")).strip().lower()
        source = str(cfg.get("source", "")).strip().lower()
        builder_role = str(cfg.get("builder", "")).strip().lower()

        if "light" in dept_clean or code == "lgt":
            return LightingBuilder()
        if "vfx" in dept_clean or "fx" in dept_clean or code == "fx":
            return VFXBuilder()
        if "comp" in dept_clean or code == "comp":
            return CompositingBuilder()
        if "edit" in dept_clean or code == "edit":
            return EditingBuilder()
        if builder_role == "init" or source == "init" or "layout" in dept_clean or code == "lay":
            return LayoutBuilder()
        if not source or source in ("", "none", "null") or "animat" in dept_clean or "2d" in dept_clean or code == "anc":
            return AnimaticBuilder()

        # Department has a source division
        return BlockingAnimationBuilder()

    @classmethod
    def invoke_builder_extract_data(
        cls,
        builder: Any,
        asset_department: Dict[str, Any],
        current_department: Dict[str, Any],
        shot_data: Dict[str, Any],
        filepath: Dict[str, str],
        builder_mode: str = "previous",
        project_path: Optional[str] = None,
        setting_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Intelligently invoke extract_data on any builder instance matching its parameter signature."""
        extract_fn = getattr(builder, "extract_data", None)
        if not callable(extract_fn):
            raise AttributeError(f"Builder {builder} does not implement extract_data()")

        sig = inspect.signature(extract_fn)
        param_names = list(sig.parameters.keys())

        # Map of all available contextual arguments
        context_args: Dict[str, Any] = {
            "asset_department": asset_department,
            "asset_types": asset_department,
            "current_department": current_department,
            "dept_info": current_department,
            "shot_data": shot_data,
            "shot_info": shot_data,
            "filepath": filepath,
            "file_paths": filepath,
            "builder_type": builder_mode,
            "builder_mode": builder_mode,
            "project_path": project_path,
            "setting_data": setting_data,
        }
        context_args.update(kwargs)

        # Check if function accepts **kwargs
        accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

        if accepts_var_kw:
            call_kwargs = {}
            for k, v in context_args.items():
                call_kwargs[k] = v
            return extract_fn(**call_kwargs)

        # Filter kwargs to only what extract_fn explicitly accepts
        matched_kwargs = {}
        for p_name in param_names:
            if p_name in context_args:
                matched_kwargs[p_name] = context_args[p_name]

        # If keyword arguments matched, invoke with them
        if matched_kwargs:
            return extract_fn(**matched_kwargs)

        # Positional fallback based on common signature permutations
        if len(param_names) == 1:
            return extract_fn(filepath)
        elif len(param_names) == 2:
            return extract_fn(current_department, filepath)
        elif len(param_names) == 3:
            return extract_fn(shot_data, current_department, filepath)
        elif len(param_names) == 4:
            return extract_fn(asset_department, current_department, shot_data, filepath)
        elif len(param_names) >= 5:
            return extract_fn(asset_department, shot_data, current_department, filepath, builder_mode)

        return extract_fn(filepath)

    @classmethod
    def generate_shot_script(
        cls,
        filepath: Union[str, Path],
        department: str,
        shot_data: Optional[Dict[str, Any]] = None,
        config_path: Optional[Union[str, Path]] = None,
        project_path: Optional[str] = None,
        setting_data: Optional[Dict[str, Any]] = None,
        builder_mode: str = "previous",
        **kwargs: Any,
    ) -> BuilderResult:
        """Generate Blender setup script and resolve paths for a division shot file."""
        # 1. Load pipeline.yaml configuration
        cfg_dict: Dict[str, Any] = {}
        if config_path and Path(config_path).is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg_dict = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not load config from {config_path}: {e}")

        # 2. Resolve project mount root path
        if not project_path:
            mounts = cfg_dict.get("global", {}).get("mounts", {})
            if sys.platform.startswith("linux"):
                project_path = mounts.get("linux", "")
            elif sys.platform.startswith("win32"):
                project_path = mounts.get("windows", "")
            elif sys.platform.startswith("darwin"):
                project_path = mounts.get("darwin", "")
            else:
                project_path = mounts.get("linux", "")

        # 3. Resolve department info
        departments = cfg_dict.get("departments", {})
        dept_info: Dict[str, Any] = {}
        if department in departments:
            dept_info = departments[department]
        else:
            dept_clean = department.lower().strip()
            for k, v in departments.items():
                if isinstance(v, dict):
                    if k.lower() == dept_clean or str(v.get("code", "")).lower() == dept_clean:
                        dept_info = v
                        break

        # 4. Resolve target version path and final/master path
        try:
            from versioning import VersioningSystem
        except ImportError:
            try:
                from Commands.versioning import VersioningSystem
            except ImportError:
                try:
                    from pipeline.Commands.versioning import VersioningSystem
                except ImportError:
                    from ..versioning import VersioningSystem

        final_path = VersioningSystem.get_master_path(filepath)
        version_path = VersioningSystem.get_version_path(filepath, version=1)

        # 5. Resolve source department file path if configured
        source_dept = dept_info.get("source", "")
        source_path = ""
        if source_dept and source_dept != "init":
            src_info = departments.get(source_dept, {})
            if not src_info:
                for k, v in departments.items():
                    if k.lower() == source_dept.lower() or str(v.get("code", "")).lower() == source_dept.lower():
                        src_info = v
                        break

            if src_info:
                src_code = src_info.get("code", "")
                dept_code = dept_info.get("code", "")
                if dept_code and src_code and f"_{dept_code}" in Path(final_path).name:
                    source_final = Path(final_path).name.replace(f"_{dept_code}", f"_{src_code}")
                    dept_base = dept_info.get("base_path", "").replace("@project_path@", (project_path or "").rstrip("/\\"))
                    src_base = src_info.get("base_path", "").replace("@project_path@", (project_path or "").rstrip("/\\"))
                    if dept_base and src_base and dept_base in str(Path(final_path).parent):
                        source_dir_str = str(Path(final_path).parent).replace(dept_base, src_base)
                        source_path = str(Path(source_dir_str) / source_final)
                    else:
                        source_path = str(Path(final_path).parent / source_final)

        filepath_dict = {
            "final": final_path,
            "version": version_path,
            "source": source_path,
        }

        # 6. Retrieve division builder instance dynamically
        asset_types = cfg_dict.get("asset_type", {})
        raw_asset_dept = departments.get("Asset", {}) if isinstance(departments.get("Asset"), dict) else {}
        asset_dept_payload = SafeAssetDepartment(
            asset_types=asset_types,
            raw_asset_dept=raw_asset_dept,
            project_path=project_path,
        )

        global_cfg = cfg_dict.get("global", {})
        raw_ms = cfg_dict.get("master_shot", {}) or cfg_dict.get("mastershots", {})
        resolved_ms = {}
        for mk, mv in raw_ms.items():
            if isinstance(mv, dict):
                resolved_ms[mk] = {
                    **mv,
                    "base_path": mv.get("base_path", "").replace("@project_path@", (project_path or "").rstrip("/\\")),
                }
        mastershots_data = {
            "mastershots": resolved_ms,
            **resolved_ms,
        }

        raw_addons = cfg_dict.get("addons", {})
        resolved_addons = {}
        for ak, av in raw_addons.items():
            if isinstance(av, dict):
                resolved_addons[ak] = {
                    **av,
                    "base_path": av.get("base_path", "").replace("@project_path@", (project_path or "").rstrip("/\\")),
                }
        addons_data = resolved_addons

        builder = cls.get_builder(
            department=department,
            department_config=dept_info,
            config_path=config_path,
            project_path=project_path,
            global_config=global_cfg,
        )

        # Resolve scripts and presets in dept_info
        resolved_dept_info = dict(dept_info or {})
        scripts = {}
        for sk, sv in (resolved_dept_info.get("scripts") or {}).items():
            scripts[sk] = sv.replace("@project_path@", (project_path or "").rstrip("/\\")) if isinstance(sv, str) else sv
        presets = {}
        for pk, pv in (resolved_dept_info.get("presets") or {}).items():
            if isinstance(pv, dict):
                presets[pk] = {**pv, "path": pv.get("path", "").replace("@project_path@", (project_path or "").rstrip("/\\"))}
            elif isinstance(pv, str):
                presets[pk] = {"path": pv.replace("@project_path@", (project_path or "").rstrip("/\\"))}
        if "playblast" in scripts and "playblast" not in presets:
            presets["playblast"] = {"path": scripts["playblast"]}
        if "preset" in scripts and "preset" not in presets:
            presets["preset"] = {"path": scripts["preset"]}
        resolved_dept_info["scripts"] = scripts
        resolved_dept_info["presets"] = presets

        # Normalize current_department payload so that both dept_info.values() and dept_info.get("code") work
        current_dept_payload = {
            department: resolved_dept_info,
            **resolved_dept_info,
        }

        # Normalize shot_data
        normalized_shot_data = dict(shot_data or {})
        raw_data = normalized_shot_data.get("data")
        if not isinstance(raw_data, dict):
            raw_data = {}

        def _safe_val(v, default):
            return default if v is None or str(v).strip() == "" else v

        normalized_shot_data["data"] = {
            "frame_in": _safe_val(raw_data.get("frame_in") or normalized_shot_data.get("frame_in"), 1),
            "frame_out": _safe_val(raw_data.get("frame_out") or normalized_shot_data.get("frame_out"), 100),
            "fps": _safe_val(raw_data.get("fps") or normalized_shot_data.get("fps"), 24),
            "resolution": _safe_val(raw_data.get("resolution") or normalized_shot_data.get("resolution"), "1920x1080"),
        }
        if "assets" not in normalized_shot_data:
            normalized_shot_data["assets"] = []

        try:
            script = cls.invoke_builder_extract_data(
                builder=builder,
                asset_department=asset_dept_payload,
                current_department=current_dept_payload,
                shot_data=normalized_shot_data,
                mastershots_data=mastershots_data,
                addons_data=addons_data,
                filepath=filepath_dict,
                builder_mode=builder_mode,
                project_path=project_path,
                setting_data=setting_data,
                **kwargs,
            )

            return BuilderResult(
                success=True,
                message=f"Successfully generated builder script for {department} shot:\n{version_path}",
                script=script,
                target_version_path=version_path,
                target_final_path=final_path,
                source_path=source_path,
            )
        except Exception as e:
            builtin_builder = cls._get_builtin_builder(department, dept_info)
            if builtin_builder and type(builtin_builder) is not type(builder):
                logger.info(f"Custom builder failed ({e}), falling back to built-in {builtin_builder.__class__.__name__}")
                try:
                    script = cls.invoke_builder_extract_data(
                        builder=builtin_builder,
                        asset_department=asset_dept_payload,
                        current_department=current_dept_payload,
                        shot_data=normalized_shot_data,
                        mastershots_data=mastershots_data,
                        addons_data=addons_data,
                        filepath=filepath_dict,
                        builder_mode=builder_mode,
                        project_path=project_path,
                        setting_data=setting_data,
                        **kwargs,
                    )
                    return BuilderResult(
                        success=True,
                        message=f"Successfully generated builder script for {department} shot using built-in builder:\n{version_path}",
                        script=script,
                        target_version_path=version_path,
                        target_final_path=final_path,
                        source_path=source_path,
                    )
                except Exception as ex:
                    logger.error(f"Built-in builder generation also failed: {ex}")

            logger.error(f"Builder script generation failed: {e}")
            return BuilderResult(
                success=False,
                message=f"Builder generation failed: {e}",
                target_version_path=version_path,
                target_final_path=final_path,
            )
