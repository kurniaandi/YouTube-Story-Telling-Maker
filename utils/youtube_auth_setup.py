"""
Jalankan file ini SATU KALI SAJA per project Google Cloud (manual, dari
komputer/server yang punya akses browser) untuk mengotorisasi akun YouTube
dan menyimpan token yang akan dipakai otomatis selamanya oleh pipeline
(auto-refresh, tidak perlu login ulang selama refresh_token belum dicabut).

Cara pakai (single project, backward compatible):
    python utils/youtube_auth_setup.py

Cara pakai (multi project / rotation):
    python utils/youtube_auth_setup.py --project project_a

Tanpa argumen, akan otomatis mendeteksi project dari my_config.json.
Kalau ada lebih dari 1 project, akan menampilkan daftar untuk dipilih.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_CLIENT_SECRET = "client_secret.json"
DEFAULT_TOKEN_FILE = "token.json"
CONFIG_PATH = "my_config.json"


def _load_config() -> dict:
    if Path(CONFIG_PATH).exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            return cfg.get("youtube_upload", {})
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _run_auth_flow(client_secret_file: str, token_file: str):
    if not Path(client_secret_file).exists():
        print(f"❌ File '{client_secret_file}' tidak ditemukan.")
        print("   Download dari Google Cloud Console -> Credentials -> OAuth Client ID (Desktop app).")
        return False

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    print("🔐 Membuka browser untuk login & otorisasi akun YouTube...")
    credentials = flow.run_local_server(port=0)

    Path(token_file).parent.mkdir(parents=True, exist_ok=True)
    with open(token_file, "w") as f:
        f.write(credentials.to_json())

    print(f"✅ Otorisasi berhasil! Token disimpan di: {token_file}")
    return True


def main():
    # Parse --project arg manually (avoid dependency on argparse for simplicity)
    project_name = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--project" and i + 1 < len(args):
            project_name = args[i + 1]
            break

    config = _load_config()
    projects = config.get("projects", [])

    if project_name:
        match = [p for p in projects if p["name"] == project_name]
        if not match:
            available = [p["name"] for p in projects]
            print(f"❌ Project '{project_name}' tidak ditemukan di config.")
            print(f"   Project tersedia: {available}")
            return
        project = match[0]
        client_secret = project.get("client_secret_file", DEFAULT_CLIENT_SECRET)
        token_file = project.get("token_file", DEFAULT_TOKEN_FILE)
        _run_auth_flow(client_secret, token_file)
        return

    # No --project arg: backward-compatible mode or interactive selection
    if not projects:
        _run_auth_flow(DEFAULT_CLIENT_SECRET, DEFAULT_TOKEN_FILE)
        return

    if len(projects) == 1:
        p = projects[0]
        _run_auth_flow(p.get("client_secret_file"), p.get("token_file"))
        return

    print("📋 Pilih project Google Cloud yang akan diotorisasi:")
    for idx, p in enumerate(projects, 1):
        print(f"   {idx}. {p['name']}")
    print(f"   {len(projects) + 1}. Keluar")

    choice = input("\nPilih nomor: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(projects):
            p = projects[idx]
            _run_auth_flow(p.get("client_secret_file"), p.get("token_file"))
        else:
            print("Dibatalkan.")
    else:
        print("Dibatalkan.")


if __name__ == "__main__":
    main()
