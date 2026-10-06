"""Dynamic Pipeline Feature Registry and Dispatcher.

Enables modular registration and discovery of pipeline actions and DCC tools
without modifying or recompiling the client application.
"""

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from string import Template
import sys
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import yaml

# Relative / local import of versioning system
try:
    from versioning import VersioningSystem
except ImportError:
    try:
        from Commands.versioning import VersioningSystem
    except ImportError:
        try:
            from pipeline.Commands.versioning import VersioningSystem
        except ImportError:
            from .versioning import VersioningSystem

logger = logging.getLogger(__name__)


@dataclass
class PipelineFeatureResult:
    """Encapsulates the result of a pipeline feature execution."""

    success: bool
    message: str = ""
    target_path: Optional[str] = None
    script: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


# In-memory registry of pipeline features
_FEATURE_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_feature(
    name: str,
    description: str = "",
    departments: Optional[List[str]] = None,
    order: int = 100,
) -> Callable:
    """Decorator to register a pipeline feature dynamically.

    Args:
        name: Human-readable feature name displayed in UI combobox (e.g. 'Up Version', 'Playblast')
        description: Short description of the feature
        departments: List of allowed departments, or None for all departments
        order: Sort priority (lower numbers appear first)
    """

    def decorator(fn: Callable) -> Callable:
        _FEATURE_REGISTRY[name] = {
            "name": name,
            "description": description,
            "handler": fn,
            "departments": [d.lower() for d in departments] if departments else None,
            "order": order,
        }
        return fn

    return decorator


# ==============================================================================
# Built-in Core Pipeline Features
# ==============================================================================
@register_feature(name="Up Version", description="Incrementally save next version file", order=10)
def handle_up_version(filepath: str, **kwargs: Any) -> PipelineFeatureResult:
    """Handler for Up Version action."""
    if not filepath:
        return PipelineFeatureResult(success=False, message="No working file path provided.")

    try:
        script, version_path = VersioningSystem.up_version(filepath)
        return PipelineFeatureResult(
            success=True,
            message=f"Successfully generated Up Version script for:\n{version_path}",
            target_path=version_path,
            script=script,
            data={"action": "up_version", "version_path": version_path},
        )
    except Exception as e:
        return PipelineFeatureResult(success=False, message=f"Failed to generate Up Version: {e}")


@register_feature(
    name="Up Master",
    description="Publish working version to Master file with optional department preset",
    order=20,
)
def handle_up_master(
    filepath: str,
    setting_data: Optional[Dict[str, Any]] = None,
    department: Optional[str] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    **kwargs: Any,
) -> PipelineFeatureResult:
    """Handler for Up Master action."""
    if not filepath:
        return PipelineFeatureResult(success=False, message="No working file path provided.")

    try:
        # If preset not explicitly in setting_data, check pipeline.yaml for department preset
        if (not setting_data or not setting_data.get("script")) and config_path:
            cfg_p = Path(config_path)
            if cfg_p.is_file():
                try:
                    with open(cfg_p, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}

                    departments = cfg.get("departments", {})
                    if department and department in departments:
                        dept_info = departments[department]
                    else:
                        # Normalize match
                        target_d = (department or "").lower()
                        dept_info = next(
                            (v for k, v in departments.items() if k.lower() == target_d or str(v.get("code", "")).lower() == target_d),
                            {},
                        )

                    scripts_cfg = dept_info.get("scripts", {}) if isinstance(dept_info, dict) else {}
                    raw_preset = scripts_cfg.get("up_master")
                    if raw_preset:
                        # Resolve project mount
                        if not project_path:
                            mounts = cfg.get("global", {}).get("mounts", {})
                            if sys.platform.startswith("linux"):
                                project_path = mounts.get("linux", "")
                            elif sys.platform.startswith("win32"):
                                project_path = mounts.get("windows", "")
                            elif sys.platform.startswith("darwin"):
                                project_path = mounts.get("darwin", "")

                        resolved_preset = raw_preset.replace("@project_path@", (project_path or "").rstrip("/\\"))
                        if Path(resolved_preset).is_file():
                            setting_data = {"script": resolved_preset}
                except Exception as ex:
                    logger.warning(f"Could not load preset from config: {ex}")

        script, master_path = VersioningSystem.up_master(filepath, setting_data=setting_data)
        applied_preset = setting_data.get("script") if setting_data else None

        return PipelineFeatureResult(
            success=True,
            message=f"Successfully generated Up Master script for:\n{master_path}",
            target_path=master_path,
            script=script,
            data={"action": "up_master", "master_path": master_path, "preset": applied_preset},
        )
    except Exception as e:
        return PipelineFeatureResult(success=False, message=f"Failed to generate Up Master: {e}")


# ==============================================================================
# Discovery and Execution APIs
# ==============================================================================
def list_available_features(
    department: Optional[str] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
) -> List[str]:
    """Dynamically discover and list all registered pipeline features.

    Returns a sorted list of human-readable feature names (e.g. ['Up Version', 'Up Master']).
    """
    feature_names: List[Tuple[int, str]] = []
    dept_lower = (department or "").lower()

    # Collect registered features matching department (or available for all)
    for name, info in _FEATURE_REGISTRY.items():
        allowed_depts = info.get("departments")
        if allowed_depts is None or not dept_lower or dept_lower in allowed_depts:
            feature_names.append((info.get("order", 100), name))

    # Sort by order priority, then by name
    feature_names.sort(key=lambda x: (x[0], x[1]))
    return [name for _, name in feature_names]


def execute_feature(
    feature_name: str,
    filepath: str,
    department: Optional[str] = None,
    config_path: Optional[Union[str, Path]] = None,
    project_path: Optional[str] = None,
    setting_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> PipelineFeatureResult:
    """Execute a pipeline feature dynamically by name."""
    # 1. Exact or normalized registry match
    target_clean = feature_name.strip().lower().replace("_", " ")
    handler_info = None

    for name, info in _FEATURE_REGISTRY.items():
        if name.lower().replace("_", " ") == target_clean:
            handler_info = info
            break

    if handler_info:
        handler = handler_info["handler"]
        return handler(
            filepath=filepath,
            department=department,
            config_path=config_path,
            project_path=project_path,
            setting_data=setting_data,
            **kwargs,
        )

    # 2. Check if it corresponds to a custom department script in pipeline.yaml
    if config_path:
        cfg_p = Path(config_path)
        if cfg_p.is_file():
            try:
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}

                dept_lower = (department or "").lower()
                departments = cfg.get("departments", {})
                dept_info = {}
                if department and department in departments:
                    dept_info = departments[department]
                else:
                    dept_info = next(
                        (v for k, v in departments.items() if k.lower() == dept_lower or str(v.get("code", "")).lower() == dept_lower),
                        {},
                    )

                scripts = dept_info.get("scripts", {}) if isinstance(dept_info, dict) else {}
                script_key = feature_name.strip().lower().replace(" ", "_")
                raw_script_path = scripts.get(script_key)

                if raw_script_path:
                    if not project_path:
                        mounts = cfg.get("global", {}).get("mounts", {})
                        if sys.platform.startswith("linux"):
                            project_path = mounts.get("linux", "")
                        elif sys.platform.startswith("win32"):
                            project_path = mounts.get("windows", "")
                        elif sys.platform.startswith("darwin"):
                            project_path = mounts.get("darwin", "")

                    resolved_path = raw_script_path.replace("@project_path@", (project_path or "").rstrip("/\\"))
                    if Path(resolved_path).is_file():
                        with open(resolved_path, "r", encoding="utf-8") as sf:
                            custom_code = sf.read()

                        tpl = Template(dedent("""
                            import bpy

                            bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

                            $CUSTOM_CODE
                        """).strip())

                        script = tpl.substitute(FILEPATH=filepath, CUSTOM_CODE=custom_code)
                        return PipelineFeatureResult(
                            success=True,
                            message=f"Custom pipeline script '{feature_name}' generated from {resolved_path}",
                            script=script,
                            target_path=filepath,
                            data={"feature": feature_name, "script_path": resolved_path},
                        )
            except Exception as e:
                return PipelineFeatureResult(success=False, message=f"Failed to execute custom feature '{feature_name}': {e}")

    return PipelineFeatureResult(
        success=False,
        message=f"Feature '{feature_name}' is not registered in the pipeline.",
    )
