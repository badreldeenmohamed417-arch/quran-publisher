"""Quran -> YouTube publisher.

Vercel scheduling is handled by api/cron.py. There is deliberately no
background scheduler here because serverless instances are ephemeral.
"""

import argparse
import os
import random
import sys

from dotenv import load_dotenv

import database
import processor
import youtube


def load_config() -> dict:
    load_dotenv()
    runtime_dir = os.getenv("RUNTIME_DIR", "/tmp/quran-publisher")
    return {
        "youtube_client_secrets_file": os.getenv(
            "YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json"
        ),
        "youtube_token_file": os.getenv(
            "YOUTUBE_TOKEN_FILE", os.path.join(runtime_dir, "youtube_token.json")
        ),
        "youtube_privacy_status": os.getenv("YOUTUBE_PRIVACY_STATUS", "public"),
        "youtube_category_id": os.getenv("YOUTUBE_CATEGORY_ID", "22"),
        "download_dir": os.getenv(
            "DOWNLOAD_DIR", os.path.join(runtime_dir, "downloads")
        ),
        "database_path": os.getenv(
            "DATABASE_PATH", os.path.join(runtime_dir, "publisher.db")
        ),
        "background_image_path": os.getenv(
            "BACKGROUND_IMAGE_PATH", "assets/background.jpg"
        ),
        "api_key": os.getenv("API_KEY", ""),
    }


def build_ayah_metadata(ayah_data: dict) -> dict:
    surah = ayah_data.get("surah", {})
    surah_name = surah.get("englishName", "Quran")
    surah_arabic = surah.get("name", "قرآن")
    ayah_num = ayah_data.get("numberInSurah", 1)
    title = f"Surah {surah_name} - Ayah {ayah_num} #shorts"
    description = (
        f"Surah {surah_name} ({surah_arabic}) - Ayah {ayah_num}\n\n"
        f"{ayah_data.get('text', '')}\n\n"
        "Reciter: Mishary Alafasy\n\n"
        "Quran recitation. #quran #islam #shorts"
    )
    tags = [
        "quran", "islam", "recitation", "muslim", "allah",
        surah_name.lower(), "shorts",
    ]
    return {"title": title[:100], "description": description[:5000], "tags": tags[:15]}


def build_surah_metadata(surah_data: dict) -> dict:
    surah_name = surah_data.get("englishName", "Quran")
    surah_arabic = surah_data.get("name", "قرآن")
    title = f"Surah {surah_name} Full | Quran Recitation"
    description = (
        f"Full recitation of Surah {surah_name} ({surah_arabic})\n\n"
        "Reciter: Mishary Alafasy\n\n"
        "Beautiful full Quran recitation."
    )
    tags = [
        "quran", "islam", "recitation", "muslim", "allah",
        surah_name.lower(), "full surah",
    ]
    return {"title": title[:100], "description": description[:5000], "tags": tags[:15]}


def _db(cfg: dict) -> database.Database:
    os.makedirs(cfg["download_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["database_path"]) or ".", exist_ok=True)
    return database.Database(cfg["database_path"])


def _select_new_id(db: database.Database, low: int, high: int) -> int | None:
    for _ in range(100):
        candidate = random.randint(low, high)
        if not db.exists(candidate):
            return candidate
    return None


def cmd_run(cfg: dict, ayah_id: int | None = None) -> int:
    db = _db(cfg)
    ayah_id = ayah_id or _select_new_id(db, 1, 6236)
    if not ayah_id:
        return 1

    audio_path = os.path.join(
        cfg["download_dir"], processor.safe_filename(ayah_id, "_audio.mp3")
    )
    video_path = os.path.join(
        cfg["download_dir"], processor.safe_filename(ayah_id, "_short.mp4")
    )

    try:
        _, ayah_data = processor.download_audio(audio_path, ayah_id)
        meta = build_ayah_metadata(ayah_data)
        surah_num = ayah_data.get("surah", {}).get("number", 1)
        ayah_num = ayah_data.get("numberInSurah", 1)
        db.mark_pending(
            ayah_id, f"https://quran.com/{surah_num}/{ayah_num}", meta["title"]
        )
        processor.create_short_video(audio_path, video_path)
        return _upload(cfg, db, ayah_id, video_path, audio_path, meta)
    except (processor.AudioError, youtube.YouTubeAuthError, youtube.YouTubeUploadError) as exc:
        print(f"Short failed: {exc}")
        db.remove_pending(ayah_id)
        processor.cleanup(audio_path, video_path)
        return 1


def cmd_run_surah(cfg: dict, surah_id: int | None = None) -> int:
    db = _db(cfg)
    surah_id = surah_id or _select_new_id(db, 1, 114)
    if not surah_id:
        return 1

    db_id = 10000 + surah_id
    audio_path = os.path.join(
        cfg["download_dir"], processor.safe_filename(db_id, "_audio.mp3")
    )
    video_path = os.path.join(
        cfg["download_dir"], processor.safe_filename(db_id, "_long.mp4")
    )

    try:
        _, surah_data = processor.download_surah_audio(audio_path, surah_id)
        meta = build_surah_metadata(surah_data)
        db.mark_pending(db_id, f"https://quran.com/{surah_id}", meta["title"])

        image_path = cfg["background_image_path"]
        if os.path.exists(image_path):
            processor.create_long_video(audio_path, image_path, video_path)
        else:
            processor.create_long_video(audio_path, None, video_path)

        return _upload(cfg, db, db_id, video_path, audio_path, meta)
    except (processor.AudioError, youtube.YouTubeAuthError, youtube.YouTubeUploadError) as exc:
        print(f"Long failed: {exc}")
        db.remove_pending(db_id)
        processor.cleanup(audio_path, video_path)
        return 1


def _upload(cfg, db, item_id, video_path, audio_path, meta) -> int:
    try:
        service = youtube.get_authenticated_service(cfg["youtube_token_file"])
        youtube_id = youtube.upload_video(
            service,
            file_path=video_path,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            category_id=cfg["youtube_category_id"],
            privacy_status=cfg["youtube_privacy_status"],
        )
    except (youtube.YouTubeAuthError, youtube.YouTubeUploadError) as exc:
        print(f"Upload failed: {exc}")
        db.remove_pending(item_id)
        processor.cleanup(audio_path, video_path)
        return 1

    db.mark_uploaded(item_id, youtube_id)
    processor.cleanup(audio_path, video_path)
    print(f"SUCCESS: https://youtu.be/{youtube_id}")
    return 0


def cmd_auth(cfg: dict) -> int:
    try:
        youtube.run_oauth_flow(
            cfg["youtube_client_secrets_file"], cfg["youtube_token_file"]
        )
        return 0
    except youtube.YouTubeAuthError as exc:
        print(f"ERROR: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Quran -> YouTube publisher")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--auth", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--run-surah", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    if args.auth:
        return cmd_auth(cfg)
    if args.run_surah:
        return cmd_run_surah(cfg)
    return cmd_run(cfg)


if __name__ == "__main__":
    sys.exit(main())
