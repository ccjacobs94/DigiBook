import os
import time
import subprocess
from pydub import AudioSegment

def get_cd_drive_path():
    # Attempt to find the CD drive, typically /dev/cdrom on Linux
    if os.path.exists('/dev/cdrom'):
        return '/dev/cdrom'
    elif os.path.exists('/dev/sr0'):
        return '/dev/sr0'
    else:
        return None

def eject_drive(cd_drive=None):
    """
    Ejects the CD drive using OS-level commands.
    """
    cd_drive = cd_drive or get_cd_drive_path()
    try:
        # Currently defaults to eject on Linux.
        # Fallback to no-op for mock environments if eject command doesn't exist
        if cd_drive:
            subprocess.run(['eject', cd_drive], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Ejected drive {cd_drive}")
        else:
            print("No CD drive specified to eject.")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Could not eject drive: {e}")

def check_drive_ready(cd_drive=None):
    """
    Checks if the CD drive is ready and contains a medium.
    TODO: Replace with real OS-level check (like 'cdparanoia -Q') for physical hardware support.
    Since this is mostly simulated, we'll return True to allow ripping to proceed.
    """
    return True

def rip_disk(output_dir, disk_num, cd_drive=None):
    """
    Attempts to rip a CD disk using cdparanoia. If no drive is found,
    it falls back to a simulated rip (useful for development/testing).
    """
    cd_drive = cd_drive or get_cd_drive_path()
    file_path = os.path.join(output_dir, f"disk_{disk_num}.mp3")

    if cd_drive:
        print(f"Ripping disk {disk_num} from {cd_drive}...")
        # Rip to a temporary wav file first
        temp_wav = os.path.join(output_dir, f"disk_{disk_num}.wav")
        try:
            # -B creates batch files which is wrong for single file output. Remove it.
            subprocess.run(['cdparanoia', '-d', cd_drive, '1-', temp_wav], check=True)
            # Convert to mp3
            audio = AudioSegment.from_wav(temp_wav)
            audio.export(file_path, format="mp3")
            # Clean up wav
            os.remove(temp_wav)
            print(f"Successfully ripped and converted disk {disk_num} to {file_path}")
        except FileNotFoundError:
            raise Exception("cdparanoia not found. Please install it to enable real CD ripping.")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error ripping CD: {e}")
    else:
        print(f"No CD drive found. Simulating rip for disk {disk_num}...")
        time.sleep(2) # Simulate processing time
        # Generate 5 seconds of silence
        silent_audio = AudioSegment.silent(duration=5000)
        silent_audio.export(file_path, format="mp3")
        print(f"Mock ripped disk {disk_num} to {file_path}")

def merge_disks(temp_dir, output_file_path, output_format='.mp3'):
    """
    Merges all MP3 files in a directory into a single MP3 or M4B file with chapter markers.
    """
    # Verify pydub has its requirements
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except FileNotFoundError:
        raise Exception("ffmpeg not found. Please install ffmpeg to enable MP3 merging.")
    # Collect all mp3 files, assuming they are named predictably like disk_1.mp3
    audio_files = [f for f in os.listdir(temp_dir) if f.endswith(".mp3")]

    # Sort files to ensure order (e.g., disk_1, disk_2, etc.)
    # We sort based on the number part of 'disk_N.mp3'
    audio_files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

    if not audio_files:
        print("No files to merge.")
        return

    # Generate metadata with chapters
    metadata_file_path = os.path.join(temp_dir, "metadata.txt")
    with open(metadata_file_path, 'w') as f:
        f.write(";FFMETADATA1\n")

        current_start_ms = 0
        for audio_file in audio_files:
            full_path = os.path.join(temp_dir, audio_file)

            # Use ffprobe to get exact duration in seconds
            duration_res = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', full_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            duration_sec = float(duration_res.stdout.strip())
            duration_ms = int(duration_sec * 1000)

            title = audio_file.replace('.mp3', '').replace('_', ' ').title()

            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={current_start_ms}\n")
            f.write(f"END={current_start_ms + duration_ms}\n")
            f.write(f"title={title}\n")

            current_start_ms += duration_ms

    # Use ffmpeg concat demuxer for memory efficient merging
    concat_file_path = os.path.join(temp_dir, "files.txt")
    with open(concat_file_path, 'w') as f:
        for audio_file in audio_files:
            f.write(f"file '{audio_file}'\n")

    temp_merged_path = os.path.join(temp_dir, "temp_merged.mp3")
    try:
        # First pass: merge files into a temporary file with chapter metadata
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file_path, '-i', metadata_file_path, '-map_metadata', '1', '-map', '0:a', '-c:a', 'copy', temp_merged_path], check=True)

        # Second pass depends on output format
        if output_format == '.m4b':
            # Re-encode to AAC for m4b support
            subprocess.run(['ffmpeg', '-y', '-i', temp_merged_path, '-c:a', 'aac', output_file_path], check=True)
        else:
            # Re-mux the temporary file to generate an accurate Xing/Info VBR header
            subprocess.run(['ffmpeg', '-y', '-i', temp_merged_path, '-write_xing', '1', '-c', 'copy', output_file_path], check=True)

        print(f"Merged and corrected for {len(audio_files)} disks into {output_file_path}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to merge files: {e}")
    finally:
        # Clean up temporary files
        if os.path.exists(temp_merged_path):
            os.remove(temp_merged_path)
