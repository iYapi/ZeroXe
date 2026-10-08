"""Compositing Scene Builder.

Builds Compositing department scene files by opening a mastershot template .blend file
(either from Kitsu MS_COMP casting, another shot in the sequence, or a custom file),
configuring frame ranges, resolution, and compositing preset node trees.
"""

import json
import logging
import os
import sys
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def _get_compositing_dialog_classes():
    """Dynamically resolve and import CompositingDialog and CompositingBatchDialog."""
    if "pipeline.Commands.Builders.compositing_dialog" in sys.modules:
        mod = sys.modules["pipeline.Commands.Builders.compositing_dialog"]
        return getattr(mod, "CompositingDialog", None), getattr(mod, "CompositingBatchDialog", None)

    try:
        from .compositing_dialog import CompositingBatchDialog, CompositingDialog
        return CompositingDialog, CompositingBatchDialog
    except Exception:
        pass

    for mod_name in [
        "pipeline.Commands.Builders.compositing_dialog",
        "Commands.Builders.compositing_dialog",
        "Builders.compositing_dialog",
        "compositing_dialog",
    ]:
        try:
            mod = __import__(mod_name, fromlist=["CompositingDialog", "CompositingBatchDialog"])
            if hasattr(mod, "CompositingDialog"):
                return getattr(mod, "CompositingDialog"), getattr(mod, "CompositingBatchDialog", None)
        except Exception:
            pass

    try:
        dialog_file = Path(__file__).parent / "compositing_dialog.py"
        if dialog_file.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("zeroxe_comp_dialog", str(dialog_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "CompositingDialog", None), getattr(mod, "CompositingBatchDialog", None)
    except Exception:
        pass

    return None, None


class CompositingBuilder:
    """Builder for Compositing department scene generation with multi-source mastershot support."""

    @classmethod
    def resolve_kitsu_ms_comp(
        cls,
        shot_data: Dict[str, Any],
        asset_department: Optional[Dict[str, Any]] = None,
        mastershots_data: Optional[Dict[str, Any]] = None,
        project_path: Optional[str] = None,
    ) -> Tuple[Optional[Path], str]:
        """Discover the Kitsu MS_COMP asset cast in this shot.

        Returns:
            Tuple[Optional[Path], str]: (resolved_file_path, ms_comp_asset_name)
        """
        asset_dept = asset_department or {}
        asset_types = asset_dept.get("Asset", {}).get("asset_type", {})
        if not asset_types and "asset_type" in asset_dept:
            asset_types = asset_dept.get("asset_type", {})

        shot_assets_content = shot_data.get("assets", []) or []
        if not shot_assets_content and shot_data.get("id"):
            try:
                import gazu
                shot_assets_content = gazu.asset.all_assets_for_shot(shot_data["id"]) or []
            except Exception:
                try:
                    from zeroxe.services.shot_service import ShotService
                    shot_assets_content = ShotService.get_assets_for_shot(shot_data["id"]) or []
                except Exception:
                    pass

        asset_type_map = {
            config["id"] if isinstance(config, dict) and "id" in config else config.get("kitsu_id", category_key): (category_key, config)
            for category_key, config in asset_types.items()
            if isinstance(config, dict)
        }

        comp_mastershot_name = ""
        comp_mastershot_base_path = ""

        # 1. Search in shot assets casting
        for asset in shot_assets_content:
            if not isinstance(asset, dict):
                continue
            asset_type_id = asset.get("entity_type_id")
            asset_name = asset.get("name", "")

            if asset_type_id in asset_type_map:
                category_key, config = asset_type_map[asset_type_id]
                cat_lower = str(category_key).lower()
                if cat_lower.startswith("ms_") or asset_name.startswith("COMP_") or asset_name.startswith("ms_comp"):
                    if cat_lower in ("ms_comp", "ms_compositing") or asset_name.startswith("COMP_") or "comp" in cat_lower:
                        comp_mastershot_name = asset_name
                        comp_mastershot_base_path = config.get("base_path", "")
                        break
            elif asset_name.startswith("COMP_") or asset_name.startswith("ms_comp"):
                comp_mastershot_name = asset_name
                break

        # 2. Fallback to mastershots_data configuration
        if not comp_mastershot_base_path and mastershots_data:
            ms_cfg = (
                mastershots_data.get("mastershots", {}).get("mastershot_compositing")
                or mastershots_data.get("master_shot", {}).get("master_shot_compositing")
                or mastershots_data.get("MS_COMP")
                or {}
            )
            if isinstance(ms_cfg, dict):
                comp_mastershot_base_path = ms_cfg.get("base_path", "")

        # 3. Resolve mount variables
        if comp_mastershot_base_path and project_path:
            comp_mastershot_base_path = comp_mastershot_base_path.replace("@project_path@", project_path.rstrip("/\\"))

        if comp_mastershot_base_path and comp_mastershot_name:
            cand = Path(comp_mastershot_base_path) / comp_mastershot_name / f"{comp_mastershot_name}.blend"
            return cand, comp_mastershot_name
        elif comp_mastershot_name:
            return Path(f"{comp_mastershot_name}.blend"), comp_mastershot_name

        return None, ""

    @classmethod
    def resolve_sibling_shot_comp(
        cls,
        sibling_shot_name: str,
        shot_data: Dict[str, Any],
        current_department: Optional[Dict[str, Any]] = None,
        project_path: Optional[str] = None,
    ) -> Optional[Path]:
        """Resolve the compositing .blend file for another shot in the sequence."""
        if not sibling_shot_name or not str(sibling_shot_name).strip():
            return None

        _, batch_dialog_cls = _get_compositing_dialog_classes()
        try:
            from .compositing_dialog import _resolve_sibling_shot_comp_path
            return _resolve_sibling_shot_comp_path(
                sibling_shot_name=sibling_shot_name,
                shot_data=shot_data,
                current_department=current_department,
                project_path=project_path,
            )
        except Exception:
            pass

        ep = shot_data.get("episode") or ""
        sq = shot_data.get("sequence") or ""
        proj = shot_data.get("project_name") or shot_data.get("project") or ""
        if isinstance(proj, dict):
            proj = proj.get("name", "")

        raw = str(sibling_shot_name).strip()
        parts = [p.strip() for p in raw.split("_") if p.strip()]
        if len(parts) >= 3 and (parts[0].lower().startswith("ep") or parts[0].lower().startswith("e")):
            target_ep, target_sq, target_sh = parts[0], parts[1], "_".join(parts[2:])
        elif len(parts) == 2:
            target_ep, target_sq, target_sh = ep, parts[0], parts[1]
        elif len(parts) == 1:
            target_ep, target_sq, target_sh = ep, sq, parts[0]
        else:
            target_ep, target_sq, target_sh = ep, parts[0], "_".join(parts[1:])

        clean_sh = target_sh
        if target_sq and clean_sh.startswith(f"{target_sq}_"):
            clean_sh = clean_sh[len(target_sq) + 1:]

        try:
            from zeroxe.services.pipeline_service import PipelineService
            shot_res = PipelineService.resolve_shot(
                department="Compositing",
                episode=ep,
                sequence=sq,
                shot=clean_sh,
                project_name=proj if isinstance(proj, str) else None,
                project_path=project_path,
            )
            if shot_res and shot_res.master_path:
                m_path = Path(shot_res.master_path)
                if m_path.is_file():
                    return m_path

                # Check progress versions
                versions = PipelineService.list_versions(
                    department="Compositing",
                    episode=ep,
                    sequence=sq,
                    shot=clean_sh,
                    project_name=proj if isinstance(proj, str) else None,
                )
                if versions:
                    return Path(versions[-1][1])
                return m_path
        except Exception:
            pass

        # Filesystem fallback
        base_comp_dir = None
        if current_department:
            dept_cfg = current_department.get("Compositing") or next(iter(current_department.values()), {})
            if isinstance(dept_cfg, dict) and dept_cfg.get("base_path"):
                b_path = dept_cfg["base_path"]
                if project_path:
                    b_path = b_path.replace("@project_path@", project_path.rstrip("/\\"))
                base_comp_dir = Path(b_path)

        if base_comp_dir and base_comp_dir.exists():
            for s_dir in [
                base_comp_dir / ep / f"{ep}_{sq}" / f"{ep}_{sq}_{clean_sh}",
                base_comp_dir / sq / f"{sq}_{clean_sh}",
                base_comp_dir / clean_sh,
            ]:
                if s_dir.is_dir():
                    blend_files = list(s_dir.glob("*.blend"))
                    if blend_files:
                        return blend_files[0]

        return None

    @classmethod
    def prompt_batch_dialog(
        cls,
        selected_items: List[Any],
        parent: Optional[Any] = None,
        available_shots: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Open batch dialog allowing artists to configure mastershot strategy for multiple shots."""
        try:
            from PySide6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return {}

            _, batch_dialog_cls = _get_compositing_dialog_classes()
            if batch_dialog_cls is not None:
                from PySide6.QtWidgets import QDialog
                dlg = batch_dialog_cls(selected_items=selected_items, available_shots=available_shots, parent=parent)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    return dlg.get_result()
                return None  # User clicked Cancel
        except Exception as e:
            logger.warning(f"Could not open CompositingBatchDialog: {e}")
        return {}

    def extract_data(
        self,
        shot_data: Dict[str, Any],
        current_department: Dict[str, Any],
        asset_department: Optional[Dict[str, Any]] = None,
        mastershots_data: Optional[Dict[str, Any]] = None,
        addons_data: Optional[Dict[str, Any]] = None,
        filepath: Optional[Dict[str, str]] = None,
        master_file: Optional[Union[str, Path]] = None,
        master_shot: Optional[str] = None,
        master_mode: Optional[str] = None,
        show_ui: bool = True,
        project_path: Optional[str] = None,
        available_shots: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Extract data and generate the Compositing Blender script."""
        file_paths = filepath or {}
        version_file = file_paths.get("version", "")
        final_file = file_paths.get("final", "")

        # Create parent directory for target version file
        if version_file:
            Path(version_file).parent.mkdir(parents=True, exist_ok=True)
        if final_file:
            Path(final_file).parent.mkdir(parents=True, exist_ok=True)

        # 1. Resolve Kitsu MS_COMP asset details
        kitsu_ms_file, kitsu_ms_name = self.resolve_kitsu_ms_comp(
            shot_data=shot_data,
            asset_department=asset_department,
            mastershots_data=mastershots_data,
            project_path=project_path,
        )

        # 2. Mastershot Resolution
        chosen_master_file: Optional[Union[str, Path]] = master_file

        # A. Explicit master_shot provided (e.g. from Batch or CLI)
        if not chosen_master_file and master_shot:
            resolved_sh_file = self.resolve_sibling_shot_comp(
                sibling_shot_name=master_shot,
                shot_data=shot_data,
                current_department=current_department,
                project_path=project_path,
            )
            if resolved_sh_file:
                chosen_master_file = resolved_sh_file

        # B. Interactive Dialog UI (Single Shot)
        if not chosen_master_file and show_ui and not os.environ.get("PYTEST_CURRENT_TEST"):
            dialog_cls, _ = _get_compositing_dialog_classes()
            if dialog_cls is not None:
                try:
                    from PySide6.QtWidgets import QApplication, QDialog
                    if QApplication.instance() is not None:
                        dlg = dialog_cls(
                            shot_data=shot_data,
                            kitsu_ms_comp_file=kitsu_ms_file,
                            kitsu_ms_comp_name=kitsu_ms_name,
                            current_department=current_department,
                            available_shots=available_shots,
                            project_path=project_path,
                        )
                        if dlg.exec() == QDialog.DialogCode.Accepted:
                            res = dlg.get_result()
                            chosen_master_file = res.get("master_file")
                        else:
                            raise RuntimeError("Compositing scene generation cancelled by user.")
                except ImportError:
                    pass
                except RuntimeError:
                    raise
                except Exception as e:
                    logger.warning(f"Could not open CompositingDialog: {e}")

        # C. Default Fallback
        if not chosen_master_file:
            if kitsu_ms_file:
                chosen_master_file = kitsu_ms_file
            else:
                chosen_master_file = ""

        # 3. Resolve Preset script
        dept_data = next(iter(current_department.values())) if current_department else {}
        preset_name = "preset"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path") if isinstance(dept_data, dict) else None

        # 4. Construct shot metadata
        shot_meta = shot_data.get("data") if isinstance(shot_data.get("data"), dict) else {}

        def safe_int(val, default):
            try:
                return int(val) if val is not None and str(val).strip() != "" else default
            except (ValueError, TypeError):
                return default

        frame_in = safe_int(shot_meta.get("frame_in") or shot_data.get("frame_in"), 0)
        frame_out = safe_int(shot_meta.get("frame_out") or shot_data.get("frame_out"), 0)
        fps = safe_int(shot_meta.get("fps") or shot_data.get("fps"), 24)

        raw_res = shot_meta.get("resolution") or shot_data.get("resolution") or "1920x1080"
        if isinstance(raw_res, (list, tuple)) and len(raw_res) >= 2:
            resolution = [safe_int(raw_res[0], 1920), safe_int(raw_res[1], 1080)]
        else:
            res_str = str(raw_res or "1920x1080")
            if "x" in res_str.lower():
                parts = res_str.lower().split("x")
                resolution = [safe_int(parts[0], 1920), safe_int(parts[1], 1080)]
            else:
                resolution = [1920, 1080]

        setting_data = {
            "frame_in": frame_in,
            "frame_out": frame_out,
            "fps": fps,
            "resolution": resolution,
            "script_path": preset_path,
        }

        # 5. Build Blender Script
        comp_script = self.script_builder(
            filepath=final_file,
            version_path=version_file,
            master_file=str(chosen_master_file) if chosen_master_file else "",
            setting_data=setting_data,
        )

        return comp_script

    def script_builder(
        self,
        filepath: str,
        version_path: str,
        master_file: str,
        setting_data: dict,
    ) -> str:
        """Build Python script to execute inside headless Blender."""
        tpl = Template(
            dedent(
                """
import bpy
from pathlib import Path

master_file = "$FILEPATH"
if master_file and Path(master_file).is_file():
    print(f"Opening Compositing Master template: {master_file}")
    bpy.ops.wm.open_mainfile(filepath=master_file)
else:
    print(f"[INFO] Initializing new Compositing scene (no existing template at '{master_file}')")

bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
"""
            )
        )
        end_script = Template(
            dedent(
                """
# Save the modified Blender file
bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH")
bpy.ops.wm.save_as_mainfile(filepath="$OUTPUT_PATH_PROGRESS")
print("File saved as: $OUTPUT_PATH")

# Quit Blender
bpy.ops.wm.quit_blender()
"""
            )
        )
        script = tpl.substitute(
            FILEPATH=master_file,
            OUTPUT_PATH=filepath,
        )
        end_script_str = end_script.substitute(
            OUTPUT_PATH=filepath,
            OUTPUT_PATH_PROGRESS=version_path,
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    preset_code = f.read()
                    script = (
                        script
                        + "\n\n"
                        + preset_code.replace("$SETTINGS", json.dumps(setting_data))
                        + "\n\n"
                    )
            except Exception as e:
                logger.warning(f"Could not read comp preset script {script_path}: {e}")

        script = script + end_script_str
        return script


CompBuilder = CompositingBuilder


if __name__ == "__main__":
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        mastershot_data = json.loads(sys.argv[4])
        addon_data = json.loads(sys.argv[5])
        file_paths = json.loads(sys.argv[-1])

        builder = CompositingBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            mastershots_data=mastershot_data,
            addons_data=addon_data,
            filepath=file_paths,
            show_ui=False,
        )
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
