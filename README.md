# Pixabay Publisher (MVP)

A small script that finds Islamic/religious stock footage on Pixabay,
filters it with a keyword-scoring classifier, and uploads one accepted
video to YouTube per run. No frontend, no database server, no
scheduler — just SQLite and plain functions.

## How it works

```
Search Pixabay (several queries)
  -> score & classify each candidate
  -> keep only ISLAMIC candidates above MIN_RELIGIOUS_SCORE
  -> skip anything already uploaded (SQLite)
  -> download the best-scoring new candidate
  -> optionally overlay a logo (ffmpeg)
  -> upload to YouTube (resumable upload)
  -> record the Pixabay ID + YouTube ID
  -> delete local temp files
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install ffmpeg (only needed if `ADD_LOGO=true`):

```bash
sudo apt install ffmpeg
```

## Configuration

```bash
cp .env .env
```

Edit `.env` and set:

```env
PIXABAY_API_KEY=your_key_here
```

Get a free Pixabay API key at https://pixabay.com/api/docs/ (create a
Pixabay account, then your key is shown on that docs page once logged
in).

Other settings in `.env`:

| Variable | Purpose |
|---|---|
| `SEARCH_QUERY` | Space-separated list of search terms, each run as its own Pixabay query |
| `PER_PAGE` | Results requested per query (kept small on purpose) |
| `MIN_RELIGIOUS_SCORE` | Minimum score (0–1) to accept a candidate as `ISLAMIC` |
| `ADD_LOGO` / `LOGO_PATH` | Optional ffmpeg logo overlay (top-right) |
| `YOUTUBE_PRIVACY_STATUS` | `public`, `unlisted`, or `private` |
| `YOUTUBE_CATEGORY_ID` | YouTube category ID for uploads (default `22`, People & Blogs) |

## YouTube setup

1. In Google Cloud Console, create a project and enable the **YouTube
   Data API v3**.
2. Create an **OAuth client ID** of type **Desktop app**.
3. Download the JSON and save it as `client_secret.json` in this
   project's root (or point `YOUTUBE_CLIENT_SECRETS_FILE` at it).
4. Run the one-time authorization (opens a browser):

   ```bash
   python main.py --auth
   ```

   This saves a reusable token to `data/youtube_token.json`. Every
   run after this is headless.

## Run

```bash
python main.py --run
```

Publishes exactly one video, or exits with a non-zero status and a
clear error if nothing suitable was found or a step failed. Nothing
is marked as uploaded unless the YouTube upload actually succeeded,
so a retry after a failure will never double-upload the same video.

## Licensing note

This tool only uses Pixabay content via the official API and expects
usage to follow the current [Pixabay Content
License](https://pixabay.com/service/license/). The video description
generated for YouTube explicitly credits Pixabay and links back to the
original page — it does not claim the footage was originally filmed
by your channel. Re-check Pixabay's current license terms before
publishing at scale; if your use case requires further transformation
of the footage (beyond an optional logo overlay) to comply, add that
step before uploading.

## Notes on the filter

The Pixabay Video API does not return a title or description field —
only `tags`, `category`, and IDs/URLs. The scoring in `filter.py`
works off tags plus the search query that surfaced each candidate,
using weighted English + Arabic Islamic keywords against a set of
negative keywords for other religions/irrelevant content. It's a
heuristic, not a certainty — tune `MIN_RELIGIOUS_SCORE` and the
keyword lists in `filter.py` as you observe real results.

## What's intentionally not here

No scheduling, no multiple videos per run, no web dashboard, no AI
classifier API. `--run` publishes one video. Scheduling (e.g. 4–5
videos/day via cron or a simple loop) is meant to be a second
iteration once this MVP is proven reliable.
