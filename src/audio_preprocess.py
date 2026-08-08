#audio_preprocess.py
import os
import subprocess


def convert_to_wav(input_path, output_path):
    """
    Convert any audio/video file to 16kHz mono WAV using ffmpeg
    """

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    command = [
        "ffmpeg",
        "-y",  # overwrite if exists
        "-i", input_path,
        "-ac", "1",        # mono
        "-ar", "16000",    # 16kHz
        output_path
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print(f"✅ Converted: {output_path}")
    except subprocess.CalledProcessError as e:
        print("❌ FFmpeg conversion failed")
        raise e