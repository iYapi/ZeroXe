"""Additional Feature Factory and Entrypoint for ZeroXe Pipeline.

Analogous to BuilderFactory for Builders, AdditionalFactory serves as the
unified entry point and dispatcher for Additional pipeline tools, utilities,
and dialogs (e.g. Playblast Collect, review aggregators, review collectors).
"""

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .playblast_collector import (
    CollectPlayblastResult,
    CopiedFileInfo,
    PlayblastCollector,
    collect_playblasts,
    get_render_path,
    scan_playblasts,
)
from .playblast_dialog import (
    PlayblastCollectDialog,
    PlayblastResultDialog,
)

logger = logging.getLogger(__name__)


@dataclass
class AdditionalFeatureResult:
    """Standardized result of an additional feature execution."""

    success: bool
    message: str = ""
    target_path: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


class AdditionalFactory:
    """Unified factory and entry point for Additional pipeline tools and dialogs."""

    _handlers: Dict[str, Callable] = {}
    _batch_prompters: Dict[str, Callable] = {}

    @classmethod
    def register_tool(
        cls,
        name: str,
        handler: Optional[Callable] = None,
        batch_prompter: Optional[Callable] = None,
        aliases: Optional[List[str]] = None,
    ) -> None:
        """Register an additional feature handler and optional batch prompter."""
        norm_name = name.lower().strip().replace("_", " ")
        names = [norm_name] + [a.lower().strip().replace("_", " ") for a in (aliases or [])]
        for n in names:
            if handler:
                cls._handlers[n] = handler
            if batch_prompter:
                cls._batch_prompters[n] = batch_prompter

    @classmethod
    def can_handle(cls, action: str) -> bool:
        """Check if an action is handled by AdditionalFactory."""
        clean = (action or "").lower().strip().replace("_", " ")
        if clean in cls._handlers or clean in cls._batch_prompters:
            return True
        if clean in ("playblast", "playblast collect", "collect playblast", "collect playblasts"):
            return True
        return False

    @classmethod
    def prompt_batch_parameters(
        cls,
        action: str,
        selected_items: List[Any],
        department: Optional[str] = None,
        parent: Optional[Any] = None,
        config_path: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Prompt for tool-specific batch parameters or interactive dialog."""
        action_clean = (action or "").lower().strip().replace("_", " ")

        # 1. Custom registered prompter
        if action_clean in cls._batch_prompters:
            return cls._batch_prompters[action_clean](
                selected_items=selected_items,
                department=department,
                parent=parent,
                config_path=config_path,
                **kwargs,
            )

        # 2. Built-in Playblast Collect batch dialog
        if action_clean in ("playblast", "playblast collect", "collect playblast", "collect playblasts"):
            return cls.prompt_playblast_collect_dialog(
                selected_items=selected_items,
                department=department,
                config_path=config_path,
                parent=parent,
                **kwargs,
            )

        return {}

    @classmethod
    def prompt_playblast_collect_dialog(
        cls,
        selected_items: List[Any],
        department: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        parent: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Launch PlayblastCollectDialog to collect parameters interactively."""
        try:
            from PySide6.QtWidgets import QApplication, QDialog

            if QApplication.instance() is not None and PlayblastCollectDialog is not None:
                dlg = PlayblastCollectDialog(
                    selected_items=selected_items,
                    department=department or "Layout",
                    config_path=config_path,
                    parent=parent,
                    **kwargs,
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    return dlg.get_parameters()
                return None  # Cancelled by user
        except Exception as e:
            logger.warning(f"Error opening PlayblastCollectDialog: {e}")
        return {}

    @classmethod
    def show_playblast_result_dialog(
        cls,
        result: CollectPlayblastResult,
        total_shots: int,
        parent: Optional[Any] = None,
    ) -> None:
        """Launch PlayblastResultDialog to display results interactively."""
        try:
            from PySide6.QtWidgets import QApplication

            if QApplication.instance() is not None and parent is not None and PlayblastResultDialog is not None:
                dlg = PlayblastResultDialog(
                    result=result,
                    total_shots=total_shots,
                    parent=parent,
                )
                dlg.exec()
        except Exception as e:
            logger.debug(f"Could not open PlayblastResultDialog: {e}")

    @classmethod
    def execute(
        cls,
        action: str,
        shots: Optional[List[Any]] = None,
        department: Optional[str] = None,
        destination_dir: Optional[Union[str, Path]] = None,
        render_path: Optional[Union[str, Path]] = None,
        file_format: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
        show_ui: bool = True,
        parent: Optional[Any] = None,
        **kwargs: Any,
    ) -> AdditionalFeatureResult:
        """Unified entry point to execute an Additional tool."""
        action_clean = (action or "").lower().strip().replace("_", " ")

        # Custom handler
        if action_clean in cls._handlers:
            res = cls._handlers[action_clean](
                shots=shots,
                department=department,
                destination_dir=destination_dir,
                render_path=render_path,
                file_format=file_format,
                config_path=config_path,
                episode=episode,
                sequence=sequence,
                show_ui=show_ui,
                parent=parent,
                **kwargs,
            )
            if isinstance(res, AdditionalFeatureResult):
                return res
            return AdditionalFeatureResult(success=bool(res), message=str(res))

        # Playblast Collect
        if action_clean in ("playblast", "playblast collect", "collect playblast", "collect playblasts"):
            return cls.collect_playblasts(
                shots=shots,
                department=department,
                destination_dir=destination_dir,
                render_path=render_path,
                file_format=file_format,
                config_path=config_path,
                episode=episode,
                sequence=sequence,
                show_ui=show_ui,
                parent=parent,
                **kwargs,
            )

        return AdditionalFeatureResult(
            success=False,
            message=f"Additional feature '{action}' is not registered.",
        )

    @classmethod
    def collect_playblasts(
        cls,
        shots: Optional[List[Any]] = None,
        department: Optional[str] = None,
        destination_dir: Optional[Union[str, Path]] = None,
        render_path: Optional[Union[str, Path]] = None,
        file_format: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
        show_ui: bool = True,
        parent: Optional[Any] = None,
        **kwargs: Any,
    ) -> AdditionalFeatureResult:
        """Execute Playblast Collect workflow (interactive dialog + collector + results dialog)."""
        shot_list = shots or []
        if not shot_list:
            return AdditionalFeatureResult(success=False, message="No shots specified for playblast collection.")

        r_path = render_path or get_render_path(config_path=config_path)
        fmt = file_format or ".mov"
        dest = destination_dir

        # Auto-infer common episode / sequence across shots
        if not episode and shot_list:
            ep_set = {
                getattr(s, "episode", None) or (s.get("episode") if isinstance(s, dict) else None)
                for s in shot_list
            }
            ep_set.discard(None)
            ep_set.discard("")
            if len(ep_set) == 1:
                episode = next(iter(ep_set))

        if not sequence and shot_list:
            sq_set = {
                getattr(s, "sequence", None) or (s.get("sequence") if isinstance(s, dict) else None)
                for s in shot_list
            }
            sq_set.discard(None)
            sq_set.discard("")
            if len(sq_set) == 1:
                sequence = next(iter(sq_set))

        # If interactive and destination not provided, show dialog
        if not dest and show_ui and PlayblastCollectDialog is not None:
            batch_params = cls.prompt_playblast_collect_dialog(
                selected_items=shot_list,
                department=department,
                config_path=config_path,
                render_path=r_path,
                episode=episode,
                sequence=sequence,
                parent=parent,
            )
            if batch_params is None:
                return AdditionalFeatureResult(success=False, message="Playblast Collect cancelled by user.")
            dest = batch_params.get("destination_dir")
            fmt = batch_params.get("file_format", fmt)
            if batch_params.get("render_path"):
                r_path = batch_params.get("render_path")

        if not r_path:
            return AdditionalFeatureResult(
                success=False,
                message="Could not resolve render path from pipeline configuration (renders in pipeline.yaml).",
            )
        if not dest:
            return AdditionalFeatureResult(
                success=False,
                message="No destination directory provided to copy playblasts.",
            )

        res = collect_playblasts(
            render_path=r_path,
            destination_dir=dest,
            shots=shot_list,
            department=department or "Layout",
            file_format=fmt,
            config_path=config_path,
            episode=episode,
            sequence=sequence,
        )

        if show_ui and parent is not None:
            cls.show_playblast_result_dialog(result=res, total_shots=len(shot_list), parent=parent)

        return AdditionalFeatureResult(
            success=res.success,
            message=res.message,
            target_path=str(res.destination_dir),
            data={
                "action": "playblast_collect",
                "copied_count": len(res.copied_files),
                "missing_count": len(res.missing_shots),
                "destination_dir": str(res.destination_dir),
                "copied_files": [
                    {
                        "shot": c.shot,
                        "source": str(c.source),
                        "destination": str(c.destination),
                        "size_bytes": c.size_bytes,
                        "version": c.version_number,
                    }
                    for c in res.copied_files
                ],
                "missing_shots": res.missing_shots,
            },
        )
