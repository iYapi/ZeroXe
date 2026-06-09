from ffmpeg.asyncio import FFmpeg
from pathlib import Path
from typing import List


class FFMPEGManager:
    @staticmethod
    async def img_to_mp4(input_sequence: str, output_file: str, start_frame: int = 101, framerate: int = 24,
                         quality: int = 15) -> bool:
        try:
            print(f"Executing FFmpeg to convert {input_sequence} to {output_file}...")

            ffmpeg = (
                FFmpeg()
                .option("y")  # overwrite output
                .input(
                    input_sequence,
                    **{"framerate": str(framerate), "start_number": str(start_frame)}
                )
                .output(
                    output_file,
                    **{"vcodec": "mpeg4", "qscale:v": str(quality), "pix_fmt": "yuv420p"}
                )
            )

            await ffmpeg.execute()
            return True

        except Exception as e:
            print(f"An error occurred while executing FFmpeg: {e}")
            return False

    @staticmethod
    async def folder_to_mp4(folder_path: str, output_file: str, framerate: int = 24, quality: int = 15) -> bool:
        """
        Convert all images in a folder to MP4 using concat demuxer.
        This method processes ALL images in the folder, regardless of naming pattern or gaps.
        
        Args:
            folder_path: Path to folder containing images
            output_file: Output MP4 file path
            framerate: Frame rate for output video (default: 24)
            quality: Quality level 1-31, where 1 is best (default: 15)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            folder = Path(folder_path)
            
            # Get all image files sorted by name
            image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.exr', '.dpx')
            image_files = sorted([f for f in folder.iterdir() 
                                 if f.is_file() and f.suffix.lower() in image_extensions])
            
            if not image_files:
                print(f"No image files found in {folder_path}")
                return False
            
            print(f"\nExecuting FFmpeg to convert {len(image_files)} images from {folder_path} to {output_file}...")
            print(f"  First image: {image_files[0].name}")
            print(f"  Last image: {image_files[-1].name}")
            print(f"  Framerate: {framerate} fps")
            print(f"  Quality: {quality}")
            
            # Create concat file listing all images
            concat_file = folder / "ffmpeg_files.txt"
            
            try:
                with open(concat_file, 'w') as f:
                    for img_file in image_files:
                        # Use relative path
                        f.write(f"file '{img_file.name}'\n")
                
                print(f"  Created concat file with {len(image_files)} entries")
                
                # Build FFmpeg command using concat demuxer
                # -f concat: use concat demuxer
                # -safe 0: allow any file paths
                # -r {framerate}: input framerate (fps for each image)
                ffmpeg = (
                    FFmpeg()
                    .option("y")  # overwrite output
                    .option("f", "concat")
                    .option("safe", "0")
                    .option("r", str(framerate))  # input framerate
                    .input(str(concat_file))
                    .output(
                        output_file,
                        **{
                            "vcodec": "mpeg4",
                            "qscale:v": str(quality),
                            "acodec": "aac",
                            "b:a": "192k",
                            "pix_fmt": "yuv420p",
                            "vsync": "vfr"
                        }
                    )
                )
                
                # Change to folder directory for relative paths
                import os
                original_dir = os.getcwd()
                os.chdir(folder)
                
                try:
                    print(f"  Starting FFmpeg conversion...")
                    await ffmpeg.execute()
                    print(f"  ✓ Conversion complete!")
                finally:
                    os.chdir(original_dir)
                
                return True
                
            finally:
                # Clean up concat file
                if concat_file.exists():
                    concat_file.unlink()
                    print(f"  Cleaned up temporary concat file")

        except Exception as e:
            print(f"An error occurred while executing FFmpeg: {e}")
            import traceback
            print(traceback.format_exc())
            return False
        
    @staticmethod
    async def video_to_mp4(
        input_file: str,
        output_file: str,
        quality: int = 15
    ) -> bool:
        """
        Convert any video format to MP4 with:
        - H.264 video
        - AAC audio
        """

        try:
            print(f"\nConverting video:")
            print(f"  Input : {input_file}")
            print(f"  Output: {output_file}")

            ffmpeg = (
                FFmpeg()
                .option("y")
                .input(input_file)
                .output(
                    output_file,
                        **{
                            "vcodec": "mpeg4",
                            "qscale:v": str(quality),
                            "acodec": "aac",
                            "b:a": "192k",
                            "pix_fmt": "yuv420p",
                            "vsync": "vfr"
                        }
                )
            )

            await ffmpeg.execute()

            print("  ✓ Video conversion complete")
            return True

        except Exception as e:
            print(f"FFmpeg error: {e}")
            import traceback
            print(traceback.format_exc())
            return False