"""Minimal YouTube Data API v3 wrapper: one-time OAuth + resumable upload."""

import http.client
import os
import random
import time

import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Errors worth retrying a resumable upload chunk on.
RETRIABLE_STATUS_CODES = (500, 502, 503, 504)
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    http.client.NotConnected,
    http.client.IncompleteRead,
    http.client.ImproperConnectionState,
    http.client.CannotSendRequest,
    http.client.CannotSendHeader,
    http.client.ResponseNotReady,
    http.client.BadStatusLine,
)


class YouTubeAuthError(Exception):
    pass


class YouTubeUploadError(Exception):
    pass


def run_oauth_flow(client_secrets_file: str, token_file: str) -> None:
    """One-time interactive authorization. Opens a browser."""
    if not os.path.exists(client_secrets_file):
        raise YouTubeAuthError(
            f"OAuth client secrets file not found: {client_secrets_file}. "
            "Download it from Google Cloud Console (OAuth client, Desktop app "
            "type) and place it at this path."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    creds = flow.run_local_server(port=0)

    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
    with open(token_file, "w") as f:
        f.write(creds.to_json())

    print(f"Authorization complete. Token saved to {token_file}")


def get_authenticated_service(token_file: str):
    """Headless load of a previously saved token, refreshing if needed."""
    if not os.path.exists(token_file):
        raise YouTubeAuthError(
            f"No saved YouTube token at {token_file}. "
            "Run: python main.py --auth"
        )

    creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            raise YouTubeAuthError(
                "Saved YouTube token is invalid and cannot be refreshed. "
                "Run: python main.py --auth"
            )

    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


def upload_video(service, file_path: str, title: str, description: str,
                  tags: list[str], category_id: str = "22",
                  privacy_status: str = "public",
                  max_retries: int = 5) -> str:
    """Resumable upload. Returns the new YouTube video ID."""
    if not os.path.exists(file_path):
        raise YouTubeUploadError(f"File not found: {file_path}")

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = service.videos().insert(
        part=",".join(body.keys()), body=body, media_body=media
    )

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES and retries < max_retries:
                retries += 1
                time.sleep(min(2 ** retries + random.random(), 30))
                continue
            raise YouTubeUploadError(f"YouTube upload failed: {exc}") from exc
        except RETRIABLE_EXCEPTIONS as exc:
            if retries < max_retries:
                retries += 1
                time.sleep(min(2 ** retries + random.random(), 30))
                continue
            raise YouTubeUploadError(f"YouTube upload failed: {exc}") from exc

    if not response or "id" not in response:
        raise YouTubeUploadError(f"Upload finished without a video ID: {response}")

    return response["id"]
