"""Lock and Version History Module."""

try:
    from .lock_manager import LockManager
except ImportError:
    try:
        from lock_manager import LockManager
    except ImportError:
        from pipeline.Commands.Locks.lock_manager import LockManager

__all__ = ["LockManager"]
