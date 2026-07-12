"""
Migrasi satu kali: pindahkan folder video yang sudah ada dari root project
ke outputs/YYYY-MM-DD/ berdasarkan timestamp file video di dalamnya.

Cara pakai:
    python scripts/migrate_existing_outputs.py --dry-run    # review dulu
    python scripts/migrate_existing_outputs.py              # migrasi sungguhan
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    ".git", ".github", "__pycache__", "venv", ".venv", "env",
    "utils", "scripts", "secrets", "data", "config", "assets",
    "outputs", "node_modules",
}

EXCLUDE_FILES = {".gitignore", "README.md", "LICENSE", "my_config.json",
                 "client_secret.json", "token.json", "requirements.txt",
                 "main.py", "pyproject.toml", "setup.py", "setup.cfg"}

VIDEO_SIGNATURES = ["final_video.mp4", "final_video_captioned.mp4"]
METADATA_SIGNATURES = ["script.json", "image_prompts.json"]


def is_video_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name in EXCLUDE_DIRS or path.name.startswith("."):
        return False
    has_video = any((path / sig).exists() for sig in VIDEO_SIGNATURES)
    has_metadata = any((path / sig).exists() for sig in METADATA_SIGNATURES)
    return has_video and has_metadata


def get_folder_date(path: Path) -> str:
    for sig in VIDEO_SIGNATURES:
        video_file = path / sig
        if video_file.exists():
            mtime = os.path.getmtime(video_file)
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    for sig in METADATA_SIGNATURES:
        meta_file = path / sig
        if meta_file.exists():
            mtime = os.path.getmtime(meta_file)
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")


def find_video_folders(root: Path) -> list[Path]:
    folders = []
    for entry in sorted(root.iterdir()):
        if is_video_folder(entry):
            folders.append(entry)
    return folders


def migrate_folder(folder: Path, dry_run: bool = False) -> None:
    date_str = get_folder_date(folder)
    target_dir = ROOT / "outputs" / date_str / folder.name

    if target_dir.exists():
        print(f"  ⚠️  KONFLIK: {target_dir} sudah ada. Skip.")
        return

    print(f"  [Migrate] {folder.relative_to(ROOT)} → {target_dir.relative_to(ROOT)} "
          f"(berdasarkan tanggal: {date_str})")

    if not dry_run:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder), str(target_dir))


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=" * 60)
        print("  DRY-RUN MODE — Tidak ada perubahan yang dilakukan")
        print("=" * 60)
    else:
        confirm = input("Jalankan migrasi sungguhan? Semua folder akan DIPINDAHKAN (y/N): ").strip().lower()
        if confirm != "y":
            print("Dibatalkan.")
            return

    folders = find_video_folders(ROOT)
    if not folders:
        print("Tidak ada folder video yang ditemukan di root project.")
        return

    print(f"\nDitemukan {len(folders)} folder video:\n")

    for folder in folders:
        migrate_folder(folder, dry_run=dry_run)

    if dry_run:
        print("\n" + "=" * 60)
        print("  Dry-run selesai. Jalankan tanpa --dry-run untuk migrasi sungguhan.")
        print("=" * 60)
    else:
        print(f"\n✅ Migrasi selesai. {len(folders)} folder dipindahkan ke outputs/.")


if __name__ == "__main__":
    main()
