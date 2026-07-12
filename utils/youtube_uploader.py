import time
import random
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from utils.youtube_project_manager import YouTubeProjectManager

DEFAULT_TOKEN_FILE = "token.json"
DEFAULT_CLIENT_SECRET = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 5


def _get_authenticated_service(project: Optional[dict] = None):
    if project:
        token_file = project.get("token_file", DEFAULT_TOKEN_FILE)
        client_secret = project.get("client_secret_file", DEFAULT_CLIENT_SECRET)
    else:
        token_file = DEFAULT_TOKEN_FILE
        client_secret = DEFAULT_CLIENT_SECRET

    token_path = Path(token_file)
    if not token_path.exists():
        raise RuntimeError(
            f"'{token_file}' tidak ditemukan. Jalankan "
            "utils/youtube_auth_setup.py --project <nama_project> "
            "terlebih dahulu untuk mengotorisasi akun YouTube."
        )

    credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        with open(token_path, "w") as f:
            f.write(credentials.to_json())

    return build("youtube", "v3", credentials=credentials)


def _do_upload(
    youtube,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    privacy_status: str,
    publish_at: Optional[str],
    made_for_kids: bool,
) -> str:
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private" if publish_at else privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry_count = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   ⏳ Progress upload: {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES and retry_count < MAX_RETRIES:
                retry_count += 1
                sleep_time = (2 ** retry_count) + random.random()
                print(f"   ⚠️ Error sementara ({e.resp.status}), retry ke-{retry_count} dalam {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                raise

    return response["id"]


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "22",
    privacy_status: str = "public",
    publish_at: Optional[str] = None,
    made_for_kids: bool = False,
    config: Optional[dict] = None,
) -> Optional[str]:
    rotation_cfg = (config or {}).get("rotation", {})
    projects = (config or {}).get("projects", [])
    rotation_enabled = rotation_cfg.get("enabled", False) and len(projects) > 0

    if not rotation_enabled:
        print("📤 Mengunggah ke YouTube (proyek tunggal)...")
        youtube = _get_authenticated_service()
        try:
            video_id = _do_upload(
                youtube, video_path, title, description, tags,
                category_id, privacy_status, publish_at, made_for_kids,
            )
            print(f"✅ Video berhasil diunggah: https://youtube.com/shorts/{video_id}")
            return video_id
        except HttpError as e:
            # Raise non-quota errors; caller handles the exception
            raise RuntimeError(f"Upload gagal: {e}")

    manager = YouTubeProjectManager(config)
    tried_projects: list[str] = []

    while True:
        project = manager.get_available_project(exclude=tried_projects)
        if project is None:
            print(
                "❌ [YouTube Upload] Semua project kehabisan kuota harian. "
                "Video tetap tersimpan di lokal."
            )
            return None

        project_name = project["name"]
        print(f"📤 Mengunggah '{title}' ke YouTube menggunakan project: {project_name}...")

        try:
            youtube = _get_authenticated_service(project)
            video_id = _do_upload(
                youtube, video_path, title, description, tags,
                category_id, privacy_status, publish_at, made_for_kids,
            )
            manager.record_usage(project_name)
            print(f"✅ Video berhasil diunggah: https://youtube.com/shorts/{video_id}")
            return video_id
        except HttpError as e:
            if e.resp.status == 403:
                error_body = str(e).lower()
                if "quotaExceeded" in error_body or "dailyLimitExceeded" in error_body:
                    print(f"   ⚠️ [YouTube Upload] Kuota {project_name} habis/gagal karena limit, mencoba project berikutnya...")
                    manager.mark_exhausted(project_name)
                    tried_projects.append(project_name)
                    continue
            raise RuntimeError(f"Upload gagal: {e}")
