import sys
import json
from pathlib import Path
from textwrap import dedent
from string import Template

class BlockingAnimationBuilder:
    def extract_data(self, current_department, filepath):
        # Create parent folder
        Path(filepath['version']).parent.mkdir(parents=True, exist_ok=True)
        
        # Copy from source
        start_script = f"import bpy; import os; bpy.ops.wm.open_mainfile(filepath='{filepath['source']}'); bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}');"
        end_script = f"bpy.ops.wm.save_as_mainfile(filepath='{filepath['final']}'); bpy.ops.wm.save_as_mainfile(filepath='{filepath['version']}')"
        
        # Apply preset
        dept_data = next(iter(current_department.values()))
        preset_name = "playblast"
        preset_path = dept_data.get("presets", {}).get(preset_name, {}).get("path")
        if preset_path and Path(preset_path).is_file():
            with open(preset_path, "r") as f:
                preset_code = f.read()
                create_script = start_script + "\n\n" + preset_code + "\n\n" + end_script
        else:
            create_script = start_script + "\n\n" + end_script
        
        return create_script


AnimationBuilder = BlockingAnimationBuilder


if __name__ == "__main__":
    # 1. Capture arguments from subprocess
    # We expect JSON strings for the dictionaries
    try:
        shot_info = json.loads(sys.argv[1])
        current_dept = json.loads(sys.argv[2])
        # asset_dept = json.loads(sys.argv[3])
        # mastershot_dept = json.loads(sys.argv[4])
        file_paths = json.loads(sys.argv[-1])

        # 2. Run the logic
        builder = BlockingAnimationBuilder()
        result = builder.extract_data(current_dept, file_paths)

        # 3. Print the result so the subprocess can "catch" it
        print(result)
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
