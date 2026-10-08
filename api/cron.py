"""Vercel Cron endpoint.

One invocation = one upload. There is no infinite background scheduler.
"""

import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import main


def scheduled_ayah_id() -> int:
    now = datetime.now(timezone.utc)
    slot = now.hour // 6
    return ((now.toordinal() * 4 + slot) % 6236) + 1


def scheduled_surah_id() -> int:
    now = datetime.now(timezone.utc)
    return (now.toordinal() % 114) + 1


class handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        secret = os.getenv("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if not secret or auth != f"Bearer {secret}":
            self._json(401, '{"status":"unauthorized"}')
            return

        query = parse_qs(urlparse(self.path).query)
        job_type = query.get("type", ["short"])[0]
        cfg = main.load_config()

        try:
            if job_type == "long":
                result = main.cmd_run_surah(cfg, scheduled_surah_id())
            elif job_type == "short":
                result = main.cmd_run(cfg, scheduled_ayah_id())
            else:
                self._json(400, '{"status":"invalid_type"}')
                return
        except Exception as exc:
            print(f"Cron job crashed: {exc}")
            self._json(500, '{"status":"failed"}')
            return

        self._json(200 if result == 0 else 500,
                   '{"status":"success"}' if result == 0 else '{"status":"failed"}')
