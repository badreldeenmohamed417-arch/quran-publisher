"""Download Quran audio and create Shorts/long-form videos with FFmpeg."""

import os
import shutil
import subprocess

import imageio_ffmpeg
import requests


class DownloadError(Exception):
    pass


class LogoError(Exception):
    pass


class AudioError(Exception):
    pass


def safe_filename(base_id: int, suffix: str = ".mp4") -> str:
    return f"ayah_{base_id}{suffix}"


def download_audio(dest_path: str, ayah_id: int, timeout: int = 30, max_retries: int = 3):
    last_exc = None
    for _ in range(max_retries):
        try:
            resp = requests.get(
                f"https://api.alquran.cloud/v1/ayah/{ayah_id}/ar.alafasy",
                timeout=timeout,
            )
            resp.raise_for_status()
            ayah_data = resp.json().get("data", {})
            audio_url = ayah_data.get("audio")
            if not audio_url:
                raise AudioError("No audio URL found")

            with requests.get(audio_url, stream=True, timeout=timeout) as audio_resp:
                audio_resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in audio_resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
            return dest_path, ayah_data
        except Exception as exc:
            _remove(dest_path)
            last_exc = exc
    raise AudioError(f"Audio download failed: {last_exc}")


def download_surah_audio(dest_path: str, surah_id: int, timeout: int = 60, max_retries: int = 3):
    last_exc = None
    for _ in range(max_retries):
        try:
            meta = requests.get(
                f"https://api.alquran.cloud/v1/surah/{surah_id}", timeout=timeout
            )
            meta.raise_for_status()
            surah_data = meta.json().get("data", {})
            if not surah_data:
                raise AudioError("No Surah metadata found")

            with requests.get(
                f"https://server8.mp3quran.net/afs/{surah_id:03d}.mp3",
                stream=True,
                timeout=timeout,
            ) as audio_resp:
                audio_resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in audio_resp.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            f.write(chunk)
            return dest_path, surah_data
        except Exception as exc:
            _remove(dest_path)
            last_exc = exc
    raise AudioError(f"Surah audio download failed: {last_exc}")


def _ffmpeg() -> str:
    exe = imageio_ffmpeg.get_ffmpeg_exe() or shutil.which("ffmpeg")
    if not exe:
        raise AudioError("ffmpeg was not found")
    return exe


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise AudioError(f"ffmpeg failed: {result.stderr[-1000:]}")


def create_short_video(audio_path: str, output_path: str) -> str:
    """1080x1920, 30fps, vertical video suitable for YouTube Shorts."""
    _run([
        _ffmpeg(), "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30",
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", output_path,
    ])
    return output_path


def create_long_video(audio_path: str, image_path: str | None, output_path: str) -> str:
    """1920x1080, 16:9, with a fitted image or a generated black background."""
    ffmpeg = _ffmpeg()
    if image_path:
        inputs = ["-loop", "1", "-i", image_path]
        vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    else:
        inputs = ["-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30"]
        vf = "null"

    _run([
        ffmpeg, "-y", *inputs, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", output_path,
    ])
    return output_path


create_black_video = create_short_video
create_image_video = create_long_video


def cleanup(*paths: str) -> None:
    for path in paths:
        _remove(path)


def _remove(path: str) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
