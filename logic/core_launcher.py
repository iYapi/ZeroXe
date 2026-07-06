import subprocess
import json
import sys
from pathlib import Path
from textwrap import dedent
from string import Template


class PathBuilder:
    @staticmethod
    def build_shot_name(
        project_code: str,
        episode_name: str,
        sequence_name: str,
        shot_name: str,
        department_code: str | None = None,
    ):
        if department_code:
            return f"{project_code}_{episode_name}_{sequence_name}_{shot_name}_{department_code}"
        return f"{project_code}_{episode_name}_{sequence_name}_{shot_name}"
        pass

    @staticmethod
    def build_shot_path(episode_name: str, sequence_name: str, shot_name: str):
        shot_path = Path(
            f"{episode_name}/{episode_name}_{sequence_name}/{episode_name}_{sequence_name}_{shot_name}"
        )
        return shot_path


class CoreLauncher:
    def __init__(
        self,
        department_data: dict,
        shot_data: dict,
        output_file: str,
        version_output_file: str,
    ):
        self.data = department_data
        self.shot_data = shot_data
        self.output_file = output_file
        p = Path(version_output_file)
        prefix, ver_str = p.stem.rsplit('_v', 1)
        new_stem = f"{prefix}_v{int(ver_str) + 1:03d}"
        new_path = p.with_name(new_stem + p.suffix)
        self.version_output_file = new_path

    # def __init__(self):
    # region Example Data
    # self.data = {
    #     "departments": {
    #         "Animation": {
    #             "code": "anm",
    #             "based": "shot",
    #             "base_path": "/mnt/M/02_production/04_animation/",
    #             "source": "blk",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/02_blocking_animation_builder.py"
    #                 },
    #                 "playblast": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_playblast.py"
    #                 },
    #                 "bake_animation": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_bake_animation.py"
    #                 },
    #             },
    #         },
    #         "Asset": {
    #             "code": "",
    #             "based": "asset",
    #             "asset_type": {
    #                 "CHAR": {
    #                     "code": "CHR",
    #                     "prefix": "c-",
    #                     "suffix": "",
    #                     "base_path": "/mnt/M/02_production/01_asset/01_char/",
    #                 },
    #                 "PROPS": {
    #                     "code": "PRP",
    #                     "prefix": "p-",
    #                     "suffix": "",
    #                     "base_path": "/mnt/M/02_production/01_asset/02_prop/",
    #                 },
    #                 "SET": {
    #                     "code": "SET",
    #                     "prefix": "s-",
    #                     "suffix": "",
    #                     "base_path": "/mnt/M/02_production/01_asset/03_set/",
    #                 },
    #                 "VEHICLE": {
    #                     "code": "VHC",
    #                     "prefix": "v-",
    #                     "suffix": "",
    #                     "base_path": "/mnt/M/02_production/01_asset/04_vehicle/",
    #                 },
    #             },
    #         },
    #         "Blocking": {
    #             "code": "blk",
    #             "based": "shot",
    #             "base_path": "/mnt/M/02_production/03_blocking/",
    #             "source": "lay",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/02_blocking_animation_builder.py"
    #                 },
    #                 "playblast": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_playblast.py"
    #                 },
    #             },
    #         },
    #         "Compositing": {
    #             "code": "comp",
    #             "based": "shot",
    #             "base_path": "/mnt/M/03_post_production/02_compositing/",
    #             "source": "lgt",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/05_compositing_builder.py"
    #                 },
    #                 "preset": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_comp.py"
    #                 },
    #             },
    #         },
    #         "FX": {
    #             "code": "vfx",
    #             "based": "shot",
    #             "base_path": "/mnt/M/03_post_production/03_vfx/",
    #             "source": "anm",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/04_vfx_builder.py"
    #                 }
    #             },
    #         },
    #         "IT": {
    #             "code": "",
    #             "based": "shot",
    #             "base_path": "",
    #             "source": "",
    #             "presets": {},
    #         },
    #         "Layout": {
    #             "code": "lay",
    #             "based": "shot",
    #             "base_path": "/mnt/M/02_production/02_layout/",
    #             "source": "init",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/01_layout_builder.py"
    #                 },
    #                 "playblast": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_playblast.py"
    #                 },
    #             },
    #         },
    #         "Lighting": {
    #             "code": "lgt",
    #             "based": "shot",
    #             "base_path": "/mnt/M/03_post_production/01_lighting/",
    #             "source": "",
    #             "presets": {
    #                 "builder": {
    #                     "path": "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/app/dynamic/builder/03_lighting_builder.py"
    #                 },
    #                 "preset": {
    #                     "path": "/mnt/M/00_tools/01_preset_script/mdt_preset_lgt.py"
    #                 },
    #             },
    #         },
    #         "LookDev": {
    #             "code": "",
    #             "based": "shot",
    #             "base_path": "",
    #             "source": "",
    #             "presets": {},
    #         },
    #         "Reference": {
    #             "code": "",
    #             "based": "shot",
    #             "base_path": "",
    #             "source": "",
    #             "presets": {},
    #         },
    #     },
    #     "addon_preset": {
    #         "ExLauncher": {
    #             "ops_blp": {
    #                 "base_path": "/mnt/M/03_post_production/01_lighting/00_preset_lighting/JSON/"
    #             }
    #         }
    #     },
    #     "mastershots": {
    #         "mastershot_compositing": {
    #             "code": "ms-comp",
    #             "base_path": "/mnt/M/03_post_production/02_compositing/00_preset_comp/",
    #         },
    #         "mastershot_lit": {
    #             "code": "ms-lit",
    #             "base_path": "/mnt/M/03_post_production/01_lighting/00_preset_lighting/",
    #         },
    #     },
    # }
    # self.shot_data = {
    #     "id": "9745ed0d-8b43-4b61-88df-8e1171cdd1a3",
    #     "name": "sh0010",
    #     "code": None,
    #     "description": None,
    #     "shotgun_id": None,
    #     "canceled": False,
    #     "nb_frames": 84,
    #     "nb_entities_out": 0,
    #     "is_casting_standby": False,
    #     "is_shared": False,
    #     "status": "running",
    #     "project_id": "0f029a6d-603e-4d6d-8217-902e2e32f274",
    #     "entity_type_id": "1c2d916d-5e51-4cdb-83fc-147ec263c359",
    #     "parent_id": "a53271a6-3d0c-491e-8aed-a9d2e150046b",
    #     "source_id": None,
    #     "preview_file_id": "865ce228-567e-4c03-ad48-34eb1ccfa019",
    #     "data": {
    #         "fps": 24,
    #         "set": "s-sekolah",
    #         "char": "c-baha",
    #         "code": "",
    #         "prop": "p-dagangan,p-leupeut_single",
    #         "ms_lit": "LIT_s-ext_sekolah_PAGI",
    #         "ms_comp": "COMP_s-ext_sekolah_PAGI",
    #         "frame_in": 101,
    #         "frame_out": 184,
    #         "resolution": "2560x1080",
    #         "max_retakes": None,
    #     },
    #     "ready_for": None,
    #     "created_by": "03f81449-39fc-4b58-b0e6-d034f741bb1f",
    #     "created_at": "2026-02-24T04:14:42",
    #     "updated_at": "2026-04-15T09:10:49",
    #     "type": "Shot",
    # }
    # self.output_file = "/mnt/M/02_production/04_animation/ep000/ep000_sself.q01/ep000_sq01_sh9999/mdt_ep000_sq01_sh9999_comp.blend"
    # self.version_output_file = "/mnt/M/02_production/04_animation/ep000/ep000_sq01/ep000_sq01_sh9999/progress/mdt_ep000_sq01_sh9999_comp_v000.blend"
    # endregion

    # This is the start point and core of the system
    def create_file(self):
        # Entry data

        # Extract data
        path_obj = Path(self.output_file)
        file_parts = path_obj.stem.split("_")
        if len(file_parts) >= 5:
            project_name = file_parts[0]  # mdt
            episode = file_parts[1]  # ep000
            sequence = file_parts[2]  # sq01
            shot = file_parts[3]  # sh9999
            dept_code = file_parts[4]  # anm
        current_department = self.get_dept_name_by_code(self.data, dept_code)

        # Get source path
        source_department_name = (
            self.data["departments"].get(current_department, {}).get("source")
        )

        source_path, source_file = self.shot_path(
            department=source_department_name,
            project=project_name,
            episode=episode,
            sequence=sequence,
            shot=shot,
        )

        # TODO: Create script to generate
        create_script = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath='{self.output_file}'); bpy.ops.wm.save_as_mainfile(filepath='{self.version_output_file}')"
        builder_script_path = (
            self.data.get("departments", {})
            .get(current_department, {})
            .get("presets", {})
            .get("builder", {})
            .get("path")
        )

        if builder_script_path:
            # Construct args
            asset_dept = {"Asset": self.data.get("departments", {}).get("Asset", {})}
            current_dept = {
                current_department: self.data.get("departments", {}).get(
                    current_department, {}
                )
            }
            shot_data = self.shot_data
            mastershot_data = {"mastershots": self.data.get("mastershots", {})}
            addon_data = {"addons": self.data.get("addons", {})}
            filepath = {
                "final": str(self.output_file),
                "version": str(self.version_output_file),
                "source": str(source_file),
            }
            args = [
                "python",
                "/home/ptp-yp/Documents/project/Jetbrain/PyCharm/work/ZeroXe/logic/builder/02_blocking_animation_builder_option_B_from_previous_shot.py",
                json.dumps(shot_data),
                json.dumps(current_dept),
                json.dumps(asset_dept),
                json.dumps(mastershot_data),
                json.dumps(addon_data),
                json.dumps(filepath),
            ]
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = process.communicate()
            generated_script = None
            if process.returncode == 0:
                generated_script = stdout
                # print("Successfully generated script!")
            else:
                print(f"Failed: {stderr}")

            create_script = generated_script

        return create_script

    # Build final shot
    def shot_path(self, department, project, episode, sequence, shot):
        base_path = self.data["departments"][department]["base_path"]
        department_code = self.data["departments"][department]["code"]

        master_path = Path(base_path)
        file_path = master_path / PathBuilder.build_shot_path(
            episode_name=episode, sequence_name=sequence, shot_name=shot
        )
        file_name = PathBuilder.build_shot_name(
            project_code=project,
            episode_name=episode,
            sequence_name=sequence,
            shot_name=shot,
            department_code=department_code,
        )
        return str(file_path), str(file_path / f"{file_name}.blend")

    # helper
    def get_dept_name_by_code(self, data, search_code):
        for dept_name, info in data["departments"].items():
            if info.get("code") == search_code:
                return dept_name
        return None


if __name__ == "__main__":
    # 1. Capture arguments from subprocess
    # We expect JSON strings for the dictionaries
    try:
        if len(sys.argv) < 5:
            print(
                f"Core Error: Expected 4 arguments, got {len(sys.argv) - 1}",
                file=sys.stderr,
            )
            print(
                "Usage: python script.py <department_json> <shot_json> <final_path> <version_path>",
                file=sys.stderr,
            )
            sys.exit(1)
        department_data = json.loads(sys.argv[1])
        shot_data = json.loads(sys.argv[2])
        final_file_path = sys.argv[-2]
        version_file_path = sys.argv[-1]

        # 2. Run the logic
        builder = CoreLauncher(
            department_data=department_data,
            shot_data=shot_data,
            output_file=final_file_path,
            version_output_file=version_file_path,
        )
        result = builder.create_file()

        # 3. Print the result so the subprocess can "catch" it
        print(result)

    except json.JSONDecodeError as e:
        print(f"Core Error: Invalid JSON - {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Core Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
