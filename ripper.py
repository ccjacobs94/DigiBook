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

def rip_disk(output_dir, disk_num):
    """
    Attempts to rip a CD disk using cdparanoia. If no drive is found,
    it falls back to a simulated rip (useful for development/testing).
    """
    cd_drive = get_cd_drive_path()
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

def merge_disks(temp_dir, output_file_path):
    """
    Merges all MP3 files in a directory into a single MP3 file.
    """
    # Verify pydub has its requirements
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except FileNotFoundError:
        raise Exception("ffmpeg not found. Please install ffmpeg to enable MP3 merging.")
    audio_files = []
    # Collect all mp3 files, assuming they are named predictably like disk_1.mp3
    for f in os.listdir(temp_dir):
        if f.endswith(".mp3"):
            audio_files.append(f)

    # Sort files to ensure order (e.g., disk_1, disk_2, etc.)
    # We sort based on the number part of 'disk_N.mp3'
    audio_files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

    if not audio_files:
        print("No files to merge.")
        return

    # Use ffmpeg concat demuxer for memory efficient merging
    concat_file_path = os.path.join(temp_dir, "files.txt")
    with open(concat_file_path, 'w') as f:
        for audio_file in audio_files:
            f.write(f"file '{audio_file}'\n")

    try:
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file_path, '-c', 'copy', output_file_path], check=True)
        print(f"Merged {len(audio_files)} disks into {output_file_path}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to merge files: {e}")
