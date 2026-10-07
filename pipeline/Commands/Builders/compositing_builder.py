import sys
import json
from pathlib import Path
from textwrap import dedent
from string import Template


class CompositingBuilder:
    def extract_data(
        self,
        shot_data,
        current_department,
        asset_department,
        mastershots_data,
        addons_data,
        filepath,
    ):
        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)
        
        # Get mastershot base path
        mastershot_name = "mastershot_compositing"
        current_mastershot = mastershots_data.get("mastershots", {}).get(
            mastershot_name, {}
        )

        asset_types = asset_department.get("Asset", {}).get("asset_type", {})
        shot_assets_content = shot_data.get("assets", [])
        asset_type_map = {config["id"]: (category_key, config) for category_key, config in asset_types.items()}
        
        comp_mastershot_name = ""
        comp_mastershot_base_path = ""

        for asset in shot_assets_content:
            asset_type_id = asset.get("entity_type_id")
            if asset_type_id in asset_type_map:
                category_key, config = asset_type_map[asset_type_id]
                if category_key.lower().startswith("ms_"):
                    if category_key.lower() == "ms_comp":
                        comp_mastershot_name = asset.get("name", "")
                        comp_mastershot_base_path = config.get("base_path", "")
                    if category_key in asset_types:
                        del asset_types[category_key]

        comp_mastershot_file = (
            Path(comp_mastershot_base_path)
            / comp_mastershot_name
            / f"{comp_mastershot_name}.blend"
        )
        # Get preset
        dept_data = next(iter(current_department.values()))
        preset_name = "preset"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")

        # Construct shot metadata
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

        comp_script = self.script_builder(
            filepath=filepath["final"],
            version_path=filepath["version"],
            master_file=str(comp_mastershot_file),
            setting_data=setting_data,
        )
        
        return comp_script

    def script_builder(
        self, filepath: str, version_path: str, master_file: str, setting_data: dict
    ):
        tpl = Template(
            dedent(
                """
import bpy
from pathlib import Path

bpy.ops.wm.open_mainfile(filepath="$FILEPATH")

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
        end_script = end_script.substitute(
            OUTPUT_PATH=filepath, OUTPUT_PATH_PROGRESS=version_path
        )

        script_path = setting_data.get("script_path")
        if script_path and Path(script_path).is_file():
            with open(script_path, "r") as f:
                preset_code = f.read()
                script = (
                    script
                    + "\n\n"
                    + preset_code.replace("$SETTINGS", json.dumps(setting_data))
                    + "\n\n"
                )
        script = script + end_script
        return script


CompBuilder = CompositingBuilder


if __name__ == "__main__":
    # 1. Capture arguments from subprocess
    # We expect JSON strings for the dictionaries
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        asset_dept = json.loads(sys.argv[3])
        mastershot_data = json.loads(sys.argv[4])
        addon_data = json.loads(sys.argv[5])
        file_paths = json.loads(sys.argv[-1])

        # 2. Run the logic
        builder = CompositingBuilder()
        result = builder.extract_data(
            shot_data=shot_info,
            current_department=current_dept,
            asset_department=asset_dept,
            mastershots_data=mastershot_data,
            addons_data=addon_data,
            filepath=file_paths,
        )

        # 3. Print the result so the subprocess can "catch" it
        print(result)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
