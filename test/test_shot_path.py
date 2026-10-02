"""Test to Verify Dynamic Pipeline Loading and Path Generation without Hardcoded Paths.

Run with:
    python test/test_shot_path.py
or:
    pytest test/test_shot_path.py
"""

import shutil
import tempfile
from pathlib import Path
import sys
import yaml
import pytest

# Ensure src/ is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from zeroxe.services.settings_service import SettingsService
from zeroxe.services.pipeline_service import PipelineService, ShotPathResult


def create_dynamic_test_environment(base_dir: Path) -> Path:
    """Create dynamic external pipeline and zeroxe_map.yaml in a given directory."""
    ext_pipeline_dir = base_dir / "external_pipeline"
    ext_commands = ext_pipeline_dir / "Commands"
    ext_paths = ext_commands / "Paths"
    ext_paths.mkdir(parents=True, exist_ok=True)

    # Copy pipeline scripts to external directory to simulate external NAS/drive
    repo_pipeline = REPO_ROOT / "pipeline"
    if (repo_pipeline / "Commands" / "main.py").is_file():
        shutil.copy2(repo_pipeline / "Commands" / "main.py", ext_commands / "main.py")
        shutil.copy2(repo_pipeline / "Commands" / "Paths" / "shot_path_generator.py", ext_paths / "shot_path_generator.py")
        shutil.copy2(repo_pipeline / "Commands" / "Paths" / "__init__.py", ext_paths / "__init__.py")

    # Create dynamic pipeline.yaml
    pipeline_yaml_path = ext_pipeline_dir / "pipeline.yaml"
    mount_root = str(base_dir / "projects_root")
    pipeline_config = {
        "global": {
            "code": "mdt",
            "name": "Test Project",
            "mounts": {
                "linux": mount_root,
                "windows": mount_root,
                "darwin": mount_root,
            },
        },
        "departments": {
            "Layout": {
                "code": "lay",
                "base_path": "@project_path@/02_production/02_layout",
            }
        },
    }
    with open(pipeline_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(pipeline_config, f)

    # Create dynamic zeroxe_map.yaml
    map_yaml_path = base_dir / "zeroxe_map.yaml"
    zeroxe_map_config = {
        "project": {
            "Test Project": {
                "code": "mdt",
                "name": "Test Project",
                "pipeline_path": str(pipeline_yaml_path),
            }
        }
    }
    with open(map_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(zeroxe_map_config, f)

    return map_yaml_path


@pytest.fixture(autouse=True)
def setup_test_pipeline(tmp_path):
    """Set up dynamic test pipeline and zeroxe_map before running tests."""
    map_path = create_dynamic_test_environment(tmp_path)
    SettingsService.set_zeroxe_map_path(str(map_path))
    SettingsService.set_version_folder("progress")
    PipelineService.clear_cache()
    yield
    PipelineService.clear_cache()


def test_shot_path_generation(tmp_path):
    """Test generating master and version shot paths matching pipeline rules without hardcoded paths."""
    department = "Layout"
    episode = "ep998"
    sequence = "sq01"
    shot = "sh0020"
    version_num = 1

    result = PipelineService.resolve_shot(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_number=version_num,
    )

    mount_root = tmp_path / "projects_root"
    expected_master = (
        mount_root
        / "02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020"
        / "mdt_ep998_sq01_sh0020_lay.blend"
    )
    expected_version = (
        mount_root
        / "02_production/02_layout/ep998/ep998_sq01/ep998_sq01_sh0020/progress"
        / "mdt_ep998_sq01_sh0020_lay_v001.blend"
    )

    print("=" * 70)
    print("DYNAMIC SHOT PATH GENERATOR TEST RESULT")
    print("=" * 70)
    print(f"Master Path   : {result.master_path}")
    print(f"Version Path  : {result.version_path}")
    print(f"Shot Directory: {result.shot_dir}")
    print(f"Version Dir   : {result.version_dir}")
    print(f"File Name     : {result.file_name}")
    print(f"Version File  : {result.version_file_name}")
    print("=" * 70)

    assert result.master_path == expected_master
    assert result.version_path == expected_version
    assert result.file_name == "mdt_ep998_sq01_sh0020_lay.blend"
    assert result.version_file_name == "mdt_ep998_sq01_sh0020_lay_v001.blend"
    print("✓ Dynamic shot path assertions passed successfully!")


def test_token_normalization():
    """Test normalization when sequence or shot already include prefixes."""
    res_a = PipelineService.resolve_shot("Layout", "ep998", "ep998_sq01", "sh0020")
    assert res_a.file_name == "mdt_ep998_sq01_sh0020_lay.blend"

    res_b = PipelineService.resolve_shot("Layout", "ep998", "sq01", "ep998_sq01_sh0020")
    assert res_b.file_name == "mdt_ep998_sq01_sh0020_lay.blend"

    print("✓ Token normalization test passed!")


def test_loading_speed_and_caching():
    """Test performance and speed of repeated path generation with caching."""
    import time

    # Warm up / first load via dynamic importlib
    t0 = time.perf_counter()
    PipelineService.resolve_shot("Layout", "ep998", "sq01", "sh0020")
    t_first = time.perf_counter() - t0

    # Execute 1,000 path generations to measure cached throughput
    iterations = 1000
    t0 = time.perf_counter()
    for i in range(iterations):
        PipelineService.resolve_shot("Layout", "ep998", "sq01", f"sh{i:04d}", version_number=i % 10 + 1)
    total_time = time.perf_counter() - t0
    avg_us = (total_time / iterations) * 1_000_000

    print("=" * 70)
    print("SPEED & OPTIMIZATION BENCHMARK")
    print("=" * 70)
    print(f"First Load (dynamic importlib) : {t_first * 1000:.3f} ms")
    print(f"1,000 Iterations Total Time   : {total_time * 1000:.3f} ms")
    print(f"Average Time per Resolution   : {avg_us:.2f} µs ({iterations / total_time:.0f} ops/sec)")
    print("=" * 70)
    assert avg_us < 200, f"Expected average resolution time under 200 µs, got {avg_us:.2f} µs"
    print("✓ Speed benchmark passed successfully!")


def test_missing_pipeline_error(tmp_path):
    """Test that PipelineService raises clear FileNotFoundError when pipeline cannot be found."""
    # 1. Test when zeroxe_map is not configured
    SettingsService.set_zeroxe_map_path("")
    PipelineService.clear_cache()

    with pytest.raises(FileNotFoundError) as exc_info:
        PipelineService.resolve_shot("Layout", "ep998", "sq01", "sh0020")
    assert "zeroxe_map.yaml path is not configured" in str(exc_info.value)

    # 2. Test when zeroxe_map points to non-existent file
    fake_map = tmp_path / "non_existent_map.yaml"
    SettingsService.set_zeroxe_map_path(str(fake_map))
    PipelineService.clear_cache()

    with pytest.raises(FileNotFoundError) as exc_info:
        PipelineService.resolve_shot("Layout", "ep998", "sq01", "sh0020")
    assert "zeroxe_map.yaml file not found" in str(exc_info.value)

def test_live_settings_apply_hot_swap(tmp_path):
    """Test that applying new zeroxe_map dynamically takes effect immediately without restart."""
    # 1. Start with no map -> should raise FileNotFoundError
    SettingsService.set_zeroxe_map_path("")
    with pytest.raises(FileNotFoundError):
        PipelineService.resolve_shot("Layout", "ep998", "sq01", "sh0020")

    # 2. Dynamically set map path (simulating user clicking Apply in Settings)
    map_p = create_dynamic_test_environment(tmp_path)
    SettingsService.set_zeroxe_map_path(str(map_p))

    # 3. Next call must immediately succeed without app restart
    res = PipelineService.resolve_shot("Layout", "ep998", "sq01", "sh0020")
    assert res.file_name == "mdt_ep998_sq01_sh0020_lay.blend"
    print("✓ Live settings apply hot-swap test passed successfully!")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        map_p = create_dynamic_test_environment(tmp_p)
        SettingsService.set_zeroxe_map_path(str(map_p))
        SettingsService.set_version_folder("progress")
        PipelineService.clear_cache()

        test_shot_path_generation(tmp_p)
        test_token_normalization()
        test_loading_speed_and_caching()
        test_missing_pipeline_error(tmp_p)
        test_live_settings_apply_hot_swap(tmp_p)


