import os
import time
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image, ImageOps
from io import BytesIO

MIN_WIDTH = 1080
MIN_HEIGHT = 1920
TARGET_W = 1080
TARGET_H = 1920
SERPER_IMAGE_SIZE_FILTER = "isz:l"
SERPER_NUM_RESULTS = 5


def load_config(config_file: str = "my_config.json") -> Dict:
    try:
        with open(config_file) as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file {config_file} not found")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in {config_file}")


def search_serper_images(query: str, api_key: str, num: int = 3, tbs: Optional[str] = None) -> List[str]:
    url = "https://google.serper.dev/images"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {"q": query, "num": num}
    if tbs:
        payload["tbs"] = tbs

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        error_msg = f"Serper API error: status {response.status_code}"
        try:
            error_detail = response.json()
            error_msg += f" - {error_detail}"
        except Exception:
            error_msg += f" - {response.text[:200]}"
        raise Exception(error_msg)

    data = response.json()
    images = data.get("images", [])
    if not images:
        raise Exception(f"No image results found for query: {query[:80]}")

    urls = []
    for img in images:
        url_str = img.get("imageUrl")
        if url_str:
            urls.append(url_str)
    return urls


def download_image(url: str, output_path: Path, timeout: int = 30) -> bool:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=95)
        return True
    except Exception as e:
        print(f"  Download error: {type(e).__name__}: {e}")
        return False


def _is_resolution_sufficient(img, min_width: int = MIN_WIDTH, min_height: int = MIN_HEIGHT) -> bool:
    w, h = img.size
    return (w >= min_width and h >= min_height) or (w >= min_height and h >= min_width)


def _crop_to_9_16(img: Image.Image) -> Image.Image:
    target_ratio = TARGET_W / TARGET_H
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        crop_width = int(img.height * target_ratio)
        left = (img.width - crop_width) // 2
        img = img.crop((left, 0, left + crop_width, img.height))
    else:
        crop_height = int(img.width / target_ratio)
        top = (img.height - crop_height) // 2
        img = img.crop((0, top, img.width, top + crop_height))

    return img


def _resize_to_vertical(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img = _crop_to_9_16(img)
    return img.resize((TARGET_W, TARGET_H), Image.LANCZOS)


def _build_search_query(prompt_obj: Dict) -> str:
    parts = []
    subject = prompt_obj.get("subject", "")
    if subject:
        parts.append(subject)

    photo_style = prompt_obj.get("photography_style", [])
    if photo_style and isinstance(photo_style, list) and photo_style[0]:
        parts.append(photo_style[0])

    device = prompt_obj.get("device", [])
    if device and isinstance(device, list) and device[0]:
        parts.append(device[0])

    scene_details = prompt_obj.get("scene_details", {})
    if isinstance(scene_details, dict):
        place = scene_details.get("place", [])
        if place and isinstance(place, list) and place[0]:
            parts.append(place[0])

    return ", ".join(p for p in parts if p).strip()


def prompt_to_search_query(prompt_obj: Dict) -> str:
    return _build_search_query(prompt_obj)


def fetch_images(
    image_prompts_path: str,
    output_dir: str,
    prompts: Optional[List[Dict]] = None,
) -> None:
    image_prompts_path = Path(image_prompts_path)
    output_dir = Path(output_dir)

    config = load_config()
    api_key = config.get("serper_api_key")
    if not api_key:
        raise ValueError(
            "serper_api_key not found in my_config.json. "
            "Silakan isi API key Serper.dev Anda."
        )

    image_cfg = config.get("image_fetch", {})
    tbs_value = image_cfg.get("serper_image_size_filter", SERPER_IMAGE_SIZE_FILTER)
    num_requested = image_cfg.get("serper_num_results", SERPER_NUM_RESULTS)
    min_width = image_cfg.get("min_width", MIN_WIDTH)
    min_height = image_cfg.get("min_height", MIN_HEIGHT)

    if prompts is None:
        if not image_prompts_path.exists():
            raise FileNotFoundError(f"Prompt file {image_prompts_path} not found")
        with open(image_prompts_path, "r") as f:
            prompts_data = json.load(f)
        if "prompts" not in prompts_data or not isinstance(prompts_data["prompts"], list):
            raise ValueError("Invalid prompts format - expected {'prompts': [...]}")
        prompts = prompts_data["prompts"]
    else:
        if not isinstance(prompts, list):
            raise ValueError("Invalid prompts format - expected a list")

    output_dir.mkdir(parents=True, exist_ok=True)

    num_images = len(prompts)
    print(f"\n🔍 Fetching {num_images} images via Serper.dev Google Images...")

    for i, prompt_obj in enumerate(prompts):
        query = _build_search_query(prompt_obj)
        print(f"\n  [{i+1}/{num_images}] Searching: {query[:120]}{'...' if len(query) > 120 else ''}")

        try:
            image_urls = search_serper_images(query, api_key, num=num_requested, tbs=tbs_value)
            print(f"  Got {len(image_urls)} result(s), filtering for HD...")

            downloaded = False
            best_img = None
            best_area = 0

            for idx, url in enumerate(image_urls):
                temp_path = output_dir / f".temp_{i+1}_{idx}.jpeg"
                if not download_image(url, temp_path):
                    continue

                try:
                    with open(temp_path, "rb") as f:
                        img_data = f.read()
                    img = Image.open(BytesIO(img_data))
                    img = ImageOps.exif_transpose(img)
                    img = img.convert("RGB")
                    w, h = img.size

                    if _is_resolution_sufficient(img, min_width, min_height):
                        work_img = _crop_to_9_16(img)
                        work_path = output_dir / f"{i+1}_work.jpeg"
                        work_img.save(work_path, "JPEG", quality=95)

                        final_img = _resize_to_vertical(img.copy())
                        output_path = output_dir / f"{i+1}.jpeg"
                        final_img.save(output_path, "JPEG", quality=95)

                        print(f"  ✅ Saved: {output_path} ({final_img.size[0]}x{final_img.size[1]}), "
                              f"work: {work_img.size[0]}x{work_img.size[1]}")
                        downloaded = True
                        temp_path.unlink(missing_ok=True)
                        break
                    else:
                        print(f"  [Image Fetcher] Skip gambar — resolusi {w}x{h} di bawah "
                              f"ambang minimum ({min_width}x{min_height})")
                        area = w * h
                        if area > best_area:
                            best_img = img.copy()
                            best_area = area
                finally:
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)

            if not downloaded:
                if best_img is not None:
                    print(f"  ⚠️ [Image Fetcher] Semua kandidat gagal validasi resolusi, "
                          f"fallback ke gambar terbaik ({best_img.size[0]}x{best_img.size[1]})")
                    work_img = _crop_to_9_16(best_img)
                    work_path = output_dir / f"{i+1}_work.jpeg"
                    work_img.save(work_path, "JPEG", quality=95)
                    final_img = _resize_to_vertical(best_img)
                    output_path = output_dir / f"{i+1}.jpeg"
                    final_img.save(output_path, "JPEG", quality=95)
                    downloaded = True
                else:
                    print(f"  ❌ Failed to download any image for prompt {i+1}, skipping")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
            print(f"  Skipping image {i+1}")

        if i < num_images - 1:
            time.sleep(0.5)

    saved = len(sorted(output_dir.glob("[0-9]*.jpeg")))
    print(f"\nDone: {saved}/{num_images} images saved to {output_dir}")


if __name__ == "__main__":
    print("Testing Serper image fetch...")
    test_prompts = [
        {"subject": "anak sekolah berjalan kaki di pagi hari pedesaan"}
    ]
    fetch_images(
        image_prompts_path="dummy.json",
        output_dir="test_output_serper",
        prompts=test_prompts,
    )
