from datetime import datetime
from pathlib import Path


def get_output_dir(video_folder_name: str, base_dir: str = "outputs") -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    root = Path(base_dir) / date_str
    root.mkdir(parents=True, exist_ok=True)

    folder = root / video_folder_name
    suffix = 2
    while folder.exists():
        folder = root / f"{video_folder_name}_{suffix}"
        suffix += 1
    folder.mkdir(parents=True, exist_ok=True)
    return folder
