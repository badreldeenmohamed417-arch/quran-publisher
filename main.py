"""CLI and Server entrypoint.

    python main.py --auth       one-time YouTube OAuth authorization
    python main.py --run        run one complete publish operation for a single Ayah (black screen)
    python main.py --run-surah  run one complete publish operation for a full Surah (with background image)
    python main.py --server     run continuously as a local server daemon
"""

import argparse
import os
import sys
import random
import time
import threading
from contextlib import asynccontextmanager

import schedule
from dotenv import load_dotenv
from fastapi import FastAPI

import database
import processor
import youtube


def load_config() -> dict:
    load_dotenv()

    cfg = {
        "youtube_client_secrets_file": os.getenv(
            "YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json"
        ),
        "youtube_token_file": os.getenv(
            "YOUTUBE_TOKEN_FILE", "data/youtube_token.json"
        ),
        "youtube_privacy_status": os.getenv("YOUTUBE_PRIVACY_STATUS", "public"),
        "youtube_category_id": os.getenv("YOUTUBE_CATEGORY_ID", "22"),
        "download_dir": os.getenv("DOWNLOAD_DIR", "downloads"),
        "database_path": os.getenv("DATABASE_PATH", "data/publisher.db"),
        "background_image_path": os.getenv("BACKGROUND_IMAGE_PATH", "assets/background.jpg"),
    }
    return cfg


def cmd_auth(cfg: dict) -> int:
    try:
        youtube.run_oauth_flow(
            cfg["youtube_client_secrets_file"], cfg["youtube_token_file"]
        )
    except youtube.YouTubeAuthError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


def build_ayah_metadata(ayah_data: dict) -> dict:
    surah = ayah_data.get("surah", {})
    surah_name = surah.get("englishName", "Quran")
    surah_arabic = surah.get("name", "قرآن")
    ayah_num = ayah_data.get("numberInSurah", 1)
    
    title = f"Surah {surah_name} - Ayah {ayah_num} | Quran Recitation"
    if len(title) > 100:
        title = title[:97] + "..."
        
    text = ayah_data.get("text", "")
    
    description = (
        f"Surah {surah_name} ({surah_arabic}) - Ayah {ayah_num}\n\n"
        f"{text}\n\n"
        f"Reciter: Mishary Alafasy\n\n"
        "Beautiful short Quran recitation to bring peace to your heart."
    )
    
    tags = ["quran", "islam", "recitation", "muslim", "allah", surah_name.lower()]

    return {"title": title, "description": description, "tags": tags[:15]}


def build_surah_metadata(surah_data: dict) -> dict:
    surah_name = surah_data.get("englishName", "Quran")
    surah_arabic = surah_data.get("name", "قرآن")
    
    title = f"Surah {surah_name} Full | Quran Recitation"
    if len(title) > 100:
        title = title[:97] + "..."
        
    description = (
        f"Full recitation of Surah {surah_name} ({surah_arabic})\n\n"
        f"Reciter: Mishary Alafasy\n\n"
        "Beautiful and soothing full Quran recitation to bring peace to your heart."
    )
    
    tags = ["quran", "islam", "recitation", "muslim", "allah", surah_name.lower(), "full surah"]

    return {"title": title, "description": description, "tags": tags[:15]}


def cmd_run(cfg: dict) -> int:
    os.makedirs(cfg["download_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["database_path"]) or ".", exist_ok=True)
    db = database.Database(cfg["database_path"])

    ayah_id = None
    for _ in range(50):
        candidate_id = random.randint(1, 6236)
        if not db.exists(candidate_id):
            ayah_id = candidate_id
            break
            
    if not ayah_id:
        print("Could not find an un-uploaded Ayah after 50 tries.")
        return 1
        
    print(f"Selected Ayah ID: {ayah_id}")
    audio_path = os.path.join(cfg["download_dir"], processor.safe_filename(ayah_id, "_audio.mp3"))
    video_path = os.path.join(cfg["download_dir"], processor.safe_filename(ayah_id, "_video.mp4"))
    
    try:
        _, ayah_data = processor.download_audio(audio_path, ayah_id)
    except processor.AudioError as exc:
        print(f"Failed to download audio: {exc}")
        return 1

    meta = build_ayah_metadata(ayah_data)
    print(f"Title: {meta['title']}\n")
    
    surah_num = ayah_data.get('surah', {}).get('number', 1)
    ayah_num = ayah_data.get('numberInSurah', 1)
    db.mark_pending(ayah_id, f"https://quran.com/{surah_num}/{ayah_num}", meta["title"])
    
    print("Generating black screen video...")
    try:
        processor.create_black_video(audio_path, video_path)
    except processor.AudioError as exc:
        print(f"Video generation failed: {exc}")
        processor.cleanup(audio_path, video_path)
        db.remove_pending(ayah_id)
        return 1
        
    return _upload(cfg, db, ayah_id, video_path, audio_path, meta)


def cmd_run_surah(cfg: dict) -> int:
    image_path = cfg["background_image_path"]
    if not os.path.exists(image_path):
        print(f"ERROR: Background image not found at {image_path}.")
        print("Please place an image there or update BACKGROUND_IMAGE_PATH in .env.")
        return 1

    os.makedirs(cfg["download_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["database_path"]) or ".", exist_ok=True)
    db = database.Database(cfg["database_path"])

    surah_id = None
    for _ in range(50):
        candidate_id = random.randint(1, 114)
        db_id = 10000 + candidate_id
        if not db.exists(db_id):
            surah_id = candidate_id
            break
            
    if not surah_id:
        print("Could not find an un-uploaded full Surah after 50 tries.")
        return 1
        
    db_id = 10000 + surah_id
    print(f"Selected Surah ID: {surah_id}")
    audio_path = os.path.join(cfg["download_dir"], processor.safe_filename(db_id, "_audio.mp3"))
    video_path = os.path.join(cfg["download_dir"], processor.safe_filename(db_id, "_video.mp4"))
    
    try:
        _, surah_data = processor.download_surah_audio(audio_path, surah_id)
    except processor.AudioError as exc:
        print(f"Failed to download audio: {exc}")
        return 1

    meta = build_surah_metadata(surah_data)
    print(f"Title: {meta['title']}\n")
    
    db.mark_pending(db_id, f"https://quran.com/{surah_id}", meta["title"])
    
    print("Generating image video...")
    try:
        processor.create_image_video(audio_path, image_path, video_path)
    except processor.AudioError as exc:
        print(f"Video generation failed: {exc}")
        processor.cleanup(audio_path, video_path)
        db.remove_pending(db_id)
        return 1
        
    return _upload(cfg, db, db_id, video_path, audio_path, meta)


def _upload(cfg: dict, db: database.Database, item_id: int, video_path: str, audio_path: str, meta: dict) -> int:
    try:
        service = youtube.get_authenticated_service(cfg["youtube_token_file"])
    except youtube.YouTubeAuthError as exc:
        print(f"ERROR: {exc}")
        db.remove_pending(item_id)
        processor.cleanup(audio_path, video_path)
        return 1

    print("Uploading to YouTube...")
    try:
        youtube_id = youtube.upload_video(
            service,
            file_path=video_path,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            category_id=cfg["youtube_category_id"],
            privacy_status=cfg["youtube_privacy_status"],
        )
    except youtube.YouTubeUploadError as exc:
        print(f"  Upload failed: {exc}")
        db.remove_pending(item_id)
        processor.cleanup(audio_path, video_path)
        return 1
        
    print("Upload complete.\n")
    print(f"YouTube ID: {youtube_id}\n")

    db.mark_uploaded(item_id, youtube_id)
    processor.cleanup(audio_path, video_path)
    print("Cleanup complete.\n")
    print("SUCCESS")
    return 0


# =======================================================
# FASTAPI & DAEMON INTEGRATION
# =======================================================

def daemon_loop(cfg: dict):
    print("Starting Quran Publisher Daemon Thread...")
    schedule.every().day.at("08:00").do(cmd_run_surah, cfg)
    schedule.every().day.at("10:00").do(cmd_run, cfg)
    schedule.every().day.at("16:00").do(cmd_run, cfg)
    schedule.every().day.at("22:00").do(cmd_run, cfg)
    schedule.every().day.at("04:00").do(cmd_run, cfg)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as exc:
            print(f"Error in scheduled task: {exc}")
            time.sleep(60)

cfg = load_config()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the daemon loop in a background thread when the app starts
    thread = threading.Thread(target=daemon_loop, args=(cfg,), daemon=True)
    thread.start()
    yield
    # Background thread will be killed automatically because daemon=True

# This object is detected by FastAPI Cloud and Uvicorn
app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "Quran Publisher Server is running. The video daemon is active in the background!"}

@app.get("/trigger/short")
def trigger_short():
    """Manual trigger to generate a short video immediately via API."""
    threading.Thread(target=cmd_run, args=(cfg,), daemon=True).start()
    return {"status": "Short video generation triggered in background."}

@app.get("/trigger/long")
def trigger_long():
    """Manual trigger to generate a long video immediately via API."""
    threading.Thread(target=cmd_run_surah, args=(cfg,), daemon=True).start()
    return {"status": "Long video generation triggered in background."}


def cmd_server(cfg: dict) -> int:
    """Fallback local server command for those running manually without uvicorn."""
    daemon_loop(cfg)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Quran -> YouTube publisher")
    # For CLI, we only parse if args are provided. Otherwise, if it's run via uvicorn/fastapi,
    # sys.argv won't match our argparse. So we only run CLI if run directly as script.
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--auth", action="store_true", help="Run YouTube OAuth flow")
    group.add_argument("--run", action="store_true", help="Publish one Ayah video")
    group.add_argument("--run-surah", action="store_true", help="Publish one full Surah video")
    group.add_argument("--server", action="store_true", help="Run continuously as a local server daemon")
    
    args = parser.parse_args()

    if args.auth:
        return cmd_auth(cfg)
    elif args.run_surah:
        return cmd_run_surah(cfg)
    elif args.server:
        return cmd_server(cfg)
    else:
        return cmd_run(cfg)

if __name__ == "__main__":
    sys.exit(main())
