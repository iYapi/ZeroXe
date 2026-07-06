import sys
import json
from pathlib import Path
from textwrap import dedent
from string import Template


class AnimaticBuilder:
    def extract_data(self, filepath):
        Path(filepath["version"]).parent.mkdir(parents=True, exist_ok=True)
        return "import bpy"


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
        builder = AnimaticBuilder()
        result = builder.extract_data(filepath=file_paths)

        # 3. Print the result so the subprocess can "catch" it
        print(result)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
