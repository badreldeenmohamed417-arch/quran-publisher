"""Download, optional logo overlay, and cleanup helpers."""

import os
import random
import shutil
import subprocess

import requests
import imageio_ffmpeg


class DownloadError(Exception):
    pass


class LogoError(Exception):
    pass


class AudioError(Exception):
    pass


def safe_filename(base_id: int, suffix: str = ".mp4") -> str:
    return f"ayah_{base_id}{suffix}"





def download_audio(dest_path: str, ayah_id: int, timeout: int = 30, max_retries: int = 3) -> tuple[str, dict]:
    """Download a specific Quran Ayah audio from alquran.cloud with retries."""
    last_exc = None
    for attempt in range(max_retries):
        api_url = f"https://api.alquran.cloud/v1/ayah/{ayah_id}/ar.alafasy"
        
        try:
            resp = requests.get(api_url, timeout=timeout)
            if resp.status_code != 200:
                raise AudioError(f"HTTP {resp.status_code} while fetching audio API")
            
            data = resp.json()
            ayah_data = data.get("data", {})
            audio_url = ayah_data.get("audio")
            if not audio_url:
                raise AudioError("No audio URL found in the API response")

            with requests.get(audio_url, stream=True, timeout=timeout) as audio_resp:
                if audio_resp.status_code != 200:
                    raise AudioError(f"HTTP {audio_resp.status_code} while downloading audio")
                
                with open(dest_path, "wb") as f:
                    for chunk in audio_resp.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
            
            # Success
            return dest_path, ayah_data

        except Exception as exc:
            _remove(dest_path)
            last_exc = exc
            
    raise AudioError(f"Audio download failed after {max_retries} retries. Last error: {last_exc}")


def download_surah_audio(dest_path: str, surah_id: int, timeout: int = 60, max_retries: int = 3) -> tuple[str, dict]:
    """Download a full Surah audio from mp3quran and metadata from alquran.cloud."""
    last_exc = None
    for attempt in range(max_retries):
        meta_url = f"https://api.alquran.cloud/v1/surah/{surah_id}"
        audio_url = f"https://server8.mp3quran.net/afs/{surah_id:03d}.mp3"
        
        try:
            resp = requests.get(meta_url, timeout=timeout)
            if resp.status_code != 200:
                raise AudioError(f"HTTP {resp.status_code} while fetching surah metadata")
            
            data = resp.json()
            surah_data = data.get("data", {})
            if not surah_data:
                raise AudioError("No surah data found in the API response")

            with requests.get(audio_url, stream=True, timeout=timeout) as audio_resp:
                if audio_resp.status_code != 200:
                    raise AudioError(f"HTTP {audio_resp.status_code} while downloading surah audio")
                
                with open(dest_path, "wb") as f:
                    for chunk in audio_resp.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            f.write(chunk)
            
            return dest_path, surah_data

        except Exception as exc:
            _remove(dest_path)
            last_exc = exc
            
    raise AudioError(f"Surah audio download failed after {max_retries} retries. Last error: {last_exc}")


def create_black_video(audio_path: str, output_path: str) -> str:
    """Generate a black screen video matching the exact duration of the audio."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise AudioError("ffmpeg was not found on PATH or via imageio_ffmpeg.")
        
    cmd = [
        ffmpeg_exe, "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=1920x1080",
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioError(f"ffmpeg video generation failed: {result.stderr[-500:]}")
        
    return output_path


def create_image_video(audio_path: str, image_path: str, output_path: str) -> str:
    """Generate a video with a static image matching the exact duration of the audio."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise AudioError("ffmpeg was not found on PATH or via imageio_ffmpeg.")
        
    cmd = [
        ffmpeg_exe, "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioError(f"ffmpeg image video generation failed: {result.stderr[-500:]}")
        
    return output_path


def cleanup(*paths: str) -> None:
    for path in paths:
        _remove(path)


def _remove(path: str) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
