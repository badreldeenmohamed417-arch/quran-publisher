"""FastAPI entrypoint for FastAPI Cloud."""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException

import main

app = FastAPI(title="Quran Publisher")


def scheduled_ayah_id() -> int:
    now = datetime.now(timezone.utc)
    slot = now.hour // 6
    return ((now.toordinal() * 4 + slot) % 6236) + 1


def scheduled_surah_id() -> int:
    now = datetime.now(timezone.utc)
    return (now.toordinal() % 114) + 1


@app.get("/")
def health():
    return {"status": "ok", "service": "quran-publisher"}


@app.get("/api/cron")
def run_cron(type: str = "short", authorization: str | None = Header(default=None)):
    secret = os.getenv("CRON_SECRET", "")
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="unauthorized")

    cfg = main.load_config()

    try:
        if type == "short":
            result = main.cmd_run(cfg, scheduled_ayah_id())
        elif type == "long":
            result = main.cmd_run_surah(cfg, scheduled_surah_id())
        else:
            raise HTTPException(status_code=400, detail="invalid_type")
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Cron job crashed: {exc}")
        raise HTTPException(status_code=500, detail="failed") from exc

    if result != 0:
        raise HTTPException(status_code=500, detail="failed")

    return {"status": "success", "type": type}
