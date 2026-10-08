"""Non-blocking animated Loading Dialog and Background Worker Runner.

Provides smooth, non-freezing UI loading popups with animated GIF support
(assets/animations/loading.gif) and dynamic progress bars (indeterminate or determinate).
"""

import inspect
import logging
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Callable, Dict, Optional, Tuple, Union

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QMovie, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zeroxe import config
from zeroxe.utils.icon_util import get_app_icon

logger = logging.getLogger(__name__)


def get_loading_gif_path() -> Optional[Path]:
    """Resolve the location of the loading.gif asset across dev and packaged bundles."""
    candidates = [
        config.ASSETS_DIR / "animations" / "loading.gif",
        config.ASSETS_DIR / "loading.gif",
        config.BASE_DIR / "assets" / "animations" / "loading.gif",
        config.BASE_DIR / "assets" / "loading.gif",
    ]

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "_internal" / "assets" / "animations" / "loading.gif",
            exe_dir / "assets" / "animations" / "loading.gif",
        ])

    appdir = os.environ.get("APPDIR")
    if appdir:
        candidates.append(Path(appdir) / "usr" / "share" / "zeroxe" / "loading.gif")

    # Project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.append(project_root / "assets" / "animations" / "loading.gif")

    for p in candidates:
        if p.is_file():
            return p
    return None


class AsyncWorker(QThread):
    """Background worker thread executing tasks without blocking the Qt main event loop."""

    progress_updated = Signal(int, int, str)  # current, total, message
    status_updated = Signal(str)
    task_finished = Signal(object)
    task_failed = Signal(Exception, str)

    def __init__(
        self,
        task_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def cancel(self) -> None:
        """Signal the worker to request early termination."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._is_cancelled

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Thread-safe progress callback for long-running batch operations."""
        self.progress_updated.emit(current, total, message)

    def report_status(self, message: str) -> None:
        """Thread-safe status message callback."""
        self.status_updated.emit(message)

    def run(self) -> None:
        """Execute task_func on background thread."""
        try:
            # Check if task_func accepts progress_callback or is_cancelled_callback
            sig = inspect.signature(self.task_func)
            params = sig.parameters
            call_kwargs = dict(self.kwargs)

            if "progress_callback" in params and "progress_callback" not in call_kwargs:
                call_kwargs["progress_callback"] = self.report_progress
            if "is_cancelled" in params and "is_cancelled" not in call_kwargs:
                call_kwargs["is_cancelled"] = self.is_cancelled

            result = self.task_func(*self.args, **call_kwargs)
            self.task_finished.emit(result)
        except Exception as e:
            tb = traceback.format_exc()
            logger.debug(f"AsyncWorker encountered error: {e}")
            self.task_failed.emit(e, tb)


class LoadingDialog(QDialog):
    """Loading popup with animated GIF and dynamic progress bar using native Qt styling."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Loading...",
        message: str = "Please wait while the operation completes...",
        total_steps: Optional[int] = None,
        can_cancel: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        flags = (
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        flags &= ~Qt.WindowType.WindowCloseButtonHint
        flags &= ~Qt.WindowType.WindowMinimizeButtonHint
        flags &= ~Qt.WindowType.WindowMaximizeButtonHint
        flags &= ~Qt.WindowType.WindowContextHelpButtonHint
        flags &= ~Qt.WindowType.WindowFullscreenButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(False)

        h = 165 if can_cancel else 130
        self.setFixedSize(380, h)
        self.setMinimumSize(380, h)
        self.setMaximumSize(380, h)

        self.worker: Optional[AsyncWorker] = None
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.traceback_str: str = ""
        self._is_finished: bool = False

        self._setup_ui(title, message, total_steps, can_cancel)

    def changeEvent(self, event: QEvent) -> None:
        """Prevent maximizing or fullscreening the loading dialog across all window managers."""
        if event.type() == QEvent.Type.WindowStateChange:
            if (
                self.isMaximized()
                or self.isFullScreen()
                or bool(self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
            ):
                self.setWindowState(Qt.WindowState.WindowNoState)
                self.showNormal()
        super().changeEvent(event)

    def showMaximized(self) -> None:
        """Enforce normal unmaximized window state."""
        self.showNormal()

    def showFullScreen(self) -> None:
        """Enforce normal unmaximized window state."""
        self.showNormal()

    def keyPressEvent(self, event) -> None:
        """Prevent closing popup with Escape or Close keys while busy."""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Close):
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Prevent closing window while background worker is actively running."""
        if not self._is_finished and self.worker and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        """Prevent closing dialog via Esc or standard reject when worker is active."""
        if not self._is_finished and self.worker and self.worker.isRunning():
            return
        super().reject()

    def _setup_ui(
        self,
        title: str,
        message: str,
        total_steps: Optional[int],
        can_cancel: bool,
    ) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Row: Animated GIF + Title & Message
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        self.gif_label = QLabel(self)
        self.gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gif_path = get_loading_gif_path()
        if gif_path:
            self.movie = QMovie(str(gif_path))
            reader = QImageReader(str(gif_path))
            orig_size = reader.size()
            if orig_size.isValid() and orig_size.height() > 0:
                target_height = 48
                aspect = orig_size.width() / orig_size.height()
                target_width = max(32, min(120, int(target_height * aspect)))
                self.gif_label.setFixedSize(target_width, target_height)
                self.movie.setScaledSize(QSize(target_width, target_height))
            else:
                self.gif_label.setFixedSize(72, 48)
                self.movie.setScaledSize(QSize(72, 48))

            self.gif_label.setMovie(self.movie)
            self.movie.start()
        else:
            self.gif_label.setFixedSize(48, 48)
            app_icon = get_app_icon()
            if not app_icon.isNull():
                self.gif_label.setPixmap(app_icon.pixmap(44, 44))
            else:
                self.gif_label.setText("⏳")

        header_layout.addWidget(self.gif_label)

        # Title and message column
        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        self.title_label = QLabel(title, self)
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        text_col.addWidget(self.title_label)

        self.message_label = QLabel(message, self)
        self.message_label.setWordWrap(True)
        text_col.addWidget(self.message_label)

        header_layout.addLayout(text_col, 1)
        main_layout.addLayout(header_layout)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        if total_steps is not None and total_steps > 0:
            self.progress_bar.setRange(0, total_steps)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p% (%v/%m)")
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Optional Cancel Action
        if can_cancel:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            self.cancel_button = QPushButton("Cancel", self)
            self.cancel_button.clicked.connect(self._on_cancel_clicked)
            btn_layout.addWidget(self.cancel_button)
            main_layout.addLayout(btn_layout)

    def set_progress(self, current: int, total: int, message: Optional[str] = None) -> None:
        """Update progress bar values and message text dynamically."""
        if total > 0:
            if self.progress_bar.maximum() != total:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setTextVisible(True)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{int(current/total*100)}% ({current}/{total})")

        if message:
            self.message_label.setText(message)

    def set_status_message(self, message: str) -> None:
        """Update the descriptive status message."""
        self.message_label.setText(message)

    def _on_cancel_clicked(self) -> None:
        """Handle user clicking cancel button."""
        if self.worker:
            self.worker.cancel()
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelling...")
        self.message_label.setText("Cancelling operation...")

    def on_worker_finished(self, result: Any) -> None:
        """Handle worker successful completion."""
        self._is_finished = True
        self.result = result
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        self.accept()

    def on_worker_failed(self, error: Exception, tb: str) -> None:
        """Handle worker failure."""
        self._is_finished = True
        self.error = error
        self.traceback_str = tb
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        self.reject()


def run_async_task(
    parent: Optional[QWidget],
    title: str,
    message: str,
    task_func: Callable[..., Any],
    *args: Any,
    total_steps: Optional[int] = None,
    can_cancel: bool = False,
    **kwargs: Any,
) -> Any:
    """Execute task_func on a background thread while displaying an animated modal loading popup.

    Keeps the main Qt GUI completely responsive and avoids any window freezes.
    Returns the return value of task_func, or raises any captured Exception.
    """
    top_parent = parent.window() if (parent and hasattr(parent, "window")) else parent

    dialog = LoadingDialog(
        parent=top_parent,
        title=title,
        message=message,
        total_steps=total_steps,
        can_cancel=can_cancel,
    )

    worker = AsyncWorker(task_func, *args, **kwargs)
    worker.setParent(dialog)
    dialog.worker = worker

    # Connect signals using QueuedConnection for thread safety
    worker.progress_updated.connect(dialog.set_progress, Qt.ConnectionType.QueuedConnection)
    worker.status_updated.connect(dialog.set_status_message, Qt.ConnectionType.QueuedConnection)
    worker.task_finished.connect(dialog.on_worker_finished, Qt.ConnectionType.QueuedConnection)
    worker.task_failed.connect(dialog.on_worker_failed, Qt.ConnectionType.QueuedConnection)

    # Start worker and open modal event loop
    worker.start()
    dialog.exec()

    # Ensure worker has finished execution before continuing
    if worker.isRunning():
        worker.wait(5000)

    if dialog.error is not None:
        raise dialog.error

    return dialog.result
