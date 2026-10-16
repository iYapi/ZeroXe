import sys
from pathlib import Path
import pytest
import yaml

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

commands_dir = repo_root / "pipeline" / "Commands"
if str(commands_dir) not in sys.path:
    sys.path.insert(0, str(commands_dir))

from pipeline.Commands.Additional.playblast_collector import (
    PlayblastCollector,
    collect_playblasts,
    scan_playblasts,
    get_render_path,
)
from pipeline.Commands.Additional.playblast_dialog import (
    PlayblastCollectDialog,
    PlayblastResultDialog,
)


def test_version_extraction_standard():
    assert PlayblastCollector.extract_version_or_number("mdt_ep998_sq01_sh0010_lay_v001.mov") == 1
    assert PlayblastCollector.extract_version_or_number("mdt_ep998_sq01_sh0010_lay_v002.mov") == 2
    assert PlayblastCollector.extract_version_or_number("mdt_ep998_sq01_sh0010_lay_v010.mov") == 10
    assert PlayblastCollector.extract_version_or_number("mdt_ep998_sq01_sh0010_anm_v3.mov") == 3


def test_version_extraction_varying_patterns():
    # Number following department code
    assert PlayblastCollector.extract_version_or_number("sh0010_anm_1.mov", dept_code="anm") == 1
    assert PlayblastCollector.extract_version_or_number("sh0010_anm_2.mov", dept_code="anm") == 2
    assert PlayblastCollector.extract_version_or_number("ep998_sq01_sh0010_anm_005.mov", dept_code="anm") == 5

    # Trailing number at end of stem
    assert PlayblastCollector.extract_version_or_number("sh0010_lay_review_03.mov") == 3

    # Pattern with preview suffix
    assert PlayblastCollector.extract_version_or_number("sh0010_lay_v02_preview.mov") == 2

    # No version
    assert PlayblastCollector.extract_version_or_number("sh0010_lay.mov") == 0


def test_get_department_code():
    cfg = {
        "departments": {
            "Animation": {"code": "anm"},
            "Layout": {"code": "lay"},
            "Blocking": {"code": "blk"},
        }
    }
    assert PlayblastCollector.get_department_code("Animation", config_dict=cfg) == "anm"
    assert PlayblastCollector.get_department_code("Layout", config_dict=cfg) == "lay"
    assert PlayblastCollector.get_department_code("lay", config_dict=cfg) == "lay"
    assert PlayblastCollector.get_department_code("Blocking", config_dict=cfg) == "blk"
    assert PlayblastCollector.get_department_code("Unknown", config_dict=cfg) == "unknown"


def test_get_render_path():
    cfg = {
        "global": {
            "renders": {
                "linux": "/mnt/K/20260222_melangkah_dari_timur/",
                "windows": "K:/20260222_melangkah_dari_timur/",
                "darwin": "/Volumes/K/20260222_melangkah_dari_timur/",
            }
        }
    }
    p_linux = PlayblastCollector.get_render_path(platform_name="linux", config_dict=cfg)
    assert p_linux == Path("/mnt/K/20260222_melangkah_dari_timur/")

    p_win = PlayblastCollector.get_render_path(platform_name="windows", config_dict=cfg)
    assert p_win == Path("K:/20260222_melangkah_dari_timur/")


def test_matches_shot():
    file_path = "/renders/ep998/ep998_sq01/ep998_sq01_sh0010/playblast/lay/mdt_ep998_sq01_sh0010_lay_v001.mov"

    # Exact match
    assert PlayblastCollector.matches_shot(
        file_path=file_path,
        shot_identifier="sh0010",
        dept_code="lay",
        file_format=".mov",
        episode="ep998",
        sequence="sq01",
    )

    # Number-only shot identifier
    assert PlayblastCollector.matches_shot(
        file_path=file_path,
        shot_identifier="0010",
        dept_code="lay",
        file_format=".mov",
        episode="ep998",
    )

    # Wrong department code
    assert not PlayblastCollector.matches_shot(
        file_path=file_path,
        shot_identifier="sh0010",
        dept_code="anm",
        file_format=".mov",
    )

    # Wrong format
    assert not PlayblastCollector.matches_shot(
        file_path=file_path,
        shot_identifier="sh0010",
        dept_code="lay",
        file_format=".mp4",
    )

    # Wrong shot
    assert not PlayblastCollector.matches_shot(
        file_path=file_path,
        shot_identifier="sh0020",
        dept_code="lay",
        file_format=".mov",
    )


def test_scan_and_collect_latest_version(tmp_path):
    # Setup simulated render directory tree
    render_root = tmp_path / "renders"
    ep_dir = render_root / "ep998" / "ep998_sq01"
    sh10_dir = ep_dir / "ep998_sq01_sh0010" / "playblast" / "lay"
    sh20_dir = ep_dir / "ep998_sq01_sh0020" / "playblast" / "lay"
    sh10_dir.mkdir(parents=True, exist_ok=True)
    sh20_dir.mkdir(parents=True, exist_ok=True)

    # Shot 10 has v001, v002, and an mp4
    f_sh10_v1 = sh10_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov"
    f_sh10_v2 = sh10_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov"
    f_sh10_mp4 = sh10_dir / "mdt_ep998_sq01_sh0010_lay_v003.mp4"
    f_sh10_v1.write_text("v1 content")
    f_sh10_v2.write_text("v2 content (latest)")
    f_sh10_mp4.write_text("mp4 content")

    # Shot 20 has v001
    f_sh20_v1 = sh20_dir / "mdt_ep998_sq01_sh0020_lay_v001.mov"
    f_sh20_v1.write_text("sh20 v1 content")

    # Destination directory
    dest_dir = tmp_path / "collected"

    result = collect_playblasts(
        render_path=render_root,
        destination_dir=dest_dir,
        shots=["sh0010", "sh0020", "sh0030"],
        department="Layout",
        file_format=".mov",
        episode="ep998",
    )

    assert result.success is True
    assert len(result.copied_files) == 2
    assert "sh0030" in result.missing_shots

    # Check that latest version (v002) of sh0010 was copied
    dest_sh10 = dest_dir / "mdt_ep998_sq01_sh0010_lay_v002.mov"
    assert dest_sh10.is_file()
    assert dest_sh10.read_text() == "v2 content (latest)"

    # Check sh0020
    dest_sh20 = dest_dir / "mdt_ep998_sq01_sh0020_lay_v001.mov"
    assert dest_sh20.is_file()
    assert dest_sh20.read_text() == "sh20 v1 content"


def test_playblast_dialogs_instantiation(qtbot, tmp_path):
    """Verify PlayblastCollectDialog and PlayblastResultDialog initialize and set parameters correctly."""
    dest = tmp_path / "playblast_dest"
    dest.mkdir(parents=True, exist_ok=True)

    dlg = PlayblastCollectDialog(
        selected_items=["sh0010", "sh0020"],
        department="Animation",
        project_name="Melangkah Dari Timur",
        episode="ep998",
        render_path=tmp_path / "renders",
    )
    qtbot.addWidget(dlg)

    # Check initial values
    dlg.edit_destination.setText(str(dest))
    dlg.combo_format.setCurrentText(".mov")

    params = dlg.get_parameters()
    assert params["destination_dir"] == str(dest)
    assert params["file_format"] == ".mov"
    assert params["department"] == "Animation"
    assert len(params["shots"]) == 2

    # Test result dialog
    from pipeline.Commands.Additional.playblast_collector import CollectPlayblastResult, CopiedFileInfo

    mock_res = CollectPlayblastResult(
        success=True,
        message="Done",
        destination_dir=dest,
        copied_files=[
            CopiedFileInfo(
                shot="sh0010",
                source=dest / "sh0010.mov",
                destination=dest / "sh0010.mov",
                size_bytes=1024 * 1024,
                version_number=1,
            )
        ],
        missing_shots=["sh0020"],
    )
    res_dlg = PlayblastResultDialog(result=mock_res, total_shots=2)
    qtbot.addWidget(res_dlg)
    assert res_dlg.windowTitle() == "Playblast Collect Results"


def test_get_shot_tokens_no_seq_or_ep_pollution():
    """Verify that get_shot_tokens never includes sequence or episode tokens."""
    tokens_composite = PlayblastCollector.get_shot_tokens("sq01_sh0010")
    assert "sq01" not in tokens_composite
    assert "sq01_sh0010" in tokens_composite or "sh0010" in tokens_composite
    assert "0010" in tokens_composite

    tokens_full = PlayblastCollector.get_shot_tokens("ep998_sq01_sh0010")
    assert "ep998" not in tokens_full
    assert "sq01" not in tokens_full
    assert "sh0010" in tokens_full


def test_multiple_shot_collect_no_cross_matching(tmp_path):
    """Verify collecting multiple shots in the same sequence never cross-matches files."""
    render_root = tmp_path / "renders"
    seq_dir = render_root / "ep998" / "ep998_sq01"
    sh10_dir = seq_dir / "ep998_sq01_sh0010" / "playblast" / "lay"
    sh20_dir = seq_dir / "ep998_sq01_sh0020" / "playblast" / "lay"
    sh10_dir.mkdir(parents=True, exist_ok=True)
    sh20_dir.mkdir(parents=True, exist_ok=True)

    # Shot 10 has version 1
    f10 = sh10_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov"
    f10.write_text("sh10 content v1")

    # Shot 20 has version 2 (higher version number than shot 10)
    f20 = sh20_dir / "mdt_ep998_sq01_sh0020_lay_v002.mov"
    f20.write_text("sh20 content v2")

    dest_dir = tmp_path / "collected"

    res = collect_playblasts(
        render_path=render_root,
        destination_dir=dest_dir,
        shots=["sq01_sh0010", "sq01_sh0020"],
        department="Layout",
        file_format=".mov",
        episode="ep998",
        sequence="sq01",
    )

    assert res.success is True
    assert len(res.copied_files) == 2
    assert len(res.missing_shots) == 0

    # Ensure shot 10 copied f10, NOT f20
    out10 = dest_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov"
    out20 = dest_dir / "mdt_ep998_sq01_sh0020_lay_v002.mov"
    assert out10.is_file()
    assert out10.read_text() == "sh10 content v1"
    assert out20.is_file()
    assert out20.read_text() == "sh20 content v2"


def test_multiple_shot_collect_across_sequences_and_episodes(tmp_path):
    """Verify collecting shots across sequences and episodes scans and collects without collision."""
    render_root = tmp_path / "renders"

    p1 = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0010" / "playblast" / "lay"
    p2 = render_root / "ep998" / "ep998_sq02" / "ep998_sq02_sh0010" / "playblast" / "lay"
    p3 = render_root / "ep999" / "ep999_sq01" / "ep999_sq01_sh0010" / "playblast" / "lay"
    for p in [p1, p2, p3]:
        p.mkdir(parents=True, exist_ok=True)

    (p1 / "mdt_ep998_sq01_sh0010_lay_v001.mov").write_text("ep998 sq01 sh0010")
    (p2 / "mdt_ep998_sq02_sh0010_lay_v001.mov").write_text("ep998 sq02 sh0010")
    (p3 / "mdt_ep999_sq01_sh0010_lay_v001.mov").write_text("ep999 sq01 sh0010")

    dest_dir = tmp_path / "collected"

    shots = [
        {"name": "sh0010", "sequence": "sq01", "episode": "ep998"},
        {"name": "sh0010", "sequence": "sq02", "episode": "ep998"},
        {"name": "sh0010", "sequence": "sq01", "episode": "ep999"},
    ]

    res = collect_playblasts(
        render_path=render_root,
        destination_dir=dest_dir,
        shots=shots,
        department="Layout",
        file_format=".mov",
    )

    assert res.success is True
    assert len(res.copied_files) == 3
    assert len(res.missing_shots) == 0


def test_additional_factory_entrypoint(tmp_path):
    """Verify AdditionalFactory serves as modular entrypoint for Additional features."""
    from pipeline.Commands.Additional import AdditionalFactory, AdditionalFeatureResult

    # Check can_handle
    assert AdditionalFactory.can_handle("Playblast Collect") is True
    assert AdditionalFactory.can_handle("playblast") is True
    assert AdditionalFactory.can_handle("collect_playblasts") is True
    assert AdditionalFactory.can_handle("Generate") is False
    assert AdditionalFactory.can_handle("Up Version") is False

    # Check custom tool registration
    AdditionalFactory.register_tool(
        name="Custom Review Tool",
        handler=lambda **kw: AdditionalFeatureResult(success=True, message="Custom executed"),
        aliases=["review_tool"],
    )
    assert AdditionalFactory.can_handle("Custom Review Tool") is True
    assert AdditionalFactory.can_handle("review_tool") is True

    custom_res = AdditionalFactory.execute("review_tool")
    assert custom_res.success is True
    assert custom_res.message == "Custom executed"

    # Check collect_playblasts via AdditionalFactory
    render_root = tmp_path / "renders"
    dest_dir = tmp_path / "collected"
    p = render_root / "ep998" / "ep998_sq01" / "ep998_sq01_sh0010" / "playblast" / "lay"
    p.mkdir(parents=True, exist_ok=True)
    (p / "mdt_ep998_sq01_sh0010_lay_v001.mov").write_text("lay v1")

    res = AdditionalFactory.execute(
        action="Playblast Collect",
        shots=["sh0010"],
        department="Layout",
        destination_dir=dest_dir,
        render_path=render_root,
        file_format=".mov",
        episode="ep998",
        show_ui=False,
    )
    assert res.success is True
    assert res.data.get("copied_count") == 1
    assert (dest_dir / "mdt_ep998_sq01_sh0010_lay_v001.mov").is_file()



