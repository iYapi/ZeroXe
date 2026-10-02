"""Path generation and pattern resolution modules."""

try:
    from .shot_path_generator import ShotPathGenerator, ShotPathResult
except ImportError:
    try:
        from shot_path_generator import ShotPathGenerator, ShotPathResult
    except ImportError:
        from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator, ShotPathResult

__all__ = ["ShotPathGenerator", "ShotPathResult"]

