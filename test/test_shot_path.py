"""Simple Test to Verify Shot Path Generator.

Run with:
    python test/test_shot_path.py
or:
    pytest test/test_shot_path.py
"""

from pathlib import Path
import sys

# Ensure repository root and src/ are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from pipeline.Commands.main import resolve_shot_paths
from pipeline.Commands.Paths.shot_path_generator import ShotPathGenerator


def test_shot_path_generation():
    """Test generating master and version shot paths matching pipeline rules."""

    # 1. Inputs
    department = "Layout"
    episode = "ep998"
    sequence = "sq01"
    shot = "sh0020"
    version_num = 1
    version_folder = "progress"

    # 2. Resolve paths using the replicated pipeline.yaml
    pipeline_yaml = REPO_ROOT / "pipeline" / "pipeline.yaml"
    result = resolve_shot_paths(
        department=department,
        episode=episode,
        sequence=sequence,
        shot=shot,
        version_number=version_num,
        version_folder=version_folder,
        config_path=pipeline_yaml,
    )

    # 3. Expected paths
    expected_master = (
        "/mnt/I/20260222_melangkah_dari_timur/02_production/02_layout"
        "/ep998/ep998_sq01/ep998_sq01_sh0020"
        "/mdt_ep998_sq01_sh0020_lay.blend"
    )
    expected_version = (
        "/mnt/I/20260222_melangkah_dari_timur/02_production/02_layout"
        "/ep998/ep998_sq01/ep998_sq01_sh0020/progress"
        "/mdt_ep998_sq01_sh0020_lay_v001.blend"
    )

    print("=" * 70)
    print("SHOT PATH GENERATOR TEST RESULT")
    print("=" * 70)
    print(f"Master Path   : {result.master_path}")
    print(f"Version Path  : {result.version_path}")
    print(f"Shot Directory: {result.shot_dir}")
    print(f"Version Dir   : {result.version_dir}")
    print("=" * 70)

    # 4. Assertions
    assert str(result.master_path) == expected_master, (
        f"Master path mismatch!\nGot     : {result.master_path}\nExpected: {expected_master}"
    )
    assert str(result.version_path) == expected_version, (
        f"Version path mismatch!\nGot     : {result.version_path}\nExpected: {expected_version}"
    )
    print("✓ All assertions passed successfully!")


def test_token_normalization():
    """Test normalization when sequence or shot already include prefixes."""
    generator = ShotPathGenerator(config=REPO_ROOT / "pipeline" / "pipeline.yaml")

    # Case A: Sequence already has episode prefix 'ep998_sq01', shot is 'sh0020'
    res_a = generator.generate_shot_paths("Layout", "ep998", "ep998_sq01", "sh0020")
    assert res_a.file_name == "mdt_ep998_sq01_sh0020_lay.blend"

    # Case B: Shot already has full prefix 'ep998_sq01_sh0020'
    res_b = generator.generate_shot_paths("Layout", "ep998", "sq01", "ep998_sq01_sh0020")
    assert res_b.file_name == "mdt_ep998_sq01_sh0020_lay.blend"

    print("✓ Token normalization test passed!")


if __name__ == "__main__":
    test_shot_path_generation()
    test_token_normalization()
