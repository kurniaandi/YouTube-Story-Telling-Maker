import os
import random

from PIL import Image
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

IMAGEMAGICK_BINARY_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_BINARY_PATH

from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY_PATH})

from pathlib import Path
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout

CROSSFADE_DURATION = 0.4

KEN_BURNS_PRESETS = [
    {"name": "zoom_in_center", "zoom_start": 1.0, "zoom_end": 1.15, "pan": "center"},
    {"name": "zoom_out_center", "zoom_start": 1.15, "zoom_end": 1.0, "pan": "center"},
    {"name": "zoom_in_pan_left_to_right", "zoom_start": 1.1, "zoom_end": 1.2, "pan": "left_to_right"},
    {"name": "zoom_in_pan_top_to_bottom", "zoom_start": 1.1, "zoom_end": 1.2, "pan": "top_to_bottom"},
    {"name": "zoom_out_pan_right_to_left", "zoom_start": 1.2, "zoom_end": 1.1, "pan": "right_to_left"},
]

OUTPUT_W = 1080
OUTPUT_H = 1920


def pick_ken_burns_preset(previous_preset_name=None):
    available = [p for p in KEN_BURNS_PRESETS if p["name"] != previous_preset_name]
    return random.choice(available)


def resize_and_crop_to_9_16(clip, target_w: int = 1080, target_h: int = 1920):
    target_ratio = target_w / target_h
    clip_ratio = clip.w / clip.h

    if abs(clip_ratio - target_ratio) < 0.001:
        return clip.resize((target_w, target_h))

    if clip_ratio > target_ratio:
        resized = clip.resize(height=target_h)
        excess_width = resized.w - target_w
        resized = resized.crop(x1=excess_width / 2, x2=resized.w - excess_width / 2)
    else:
        resized = clip.resize(width=target_w)
        excess_height = resized.h - target_h
        resized = resized.crop(y1=excess_height / 2, y2=resized.h - excess_height / 2)

    return resized.resize((target_w, target_h))


def calculate_image_duration(audio_path: Path, num_images: int) -> float:
    try:
        audio = AudioFileClip(str(audio_path))
        audio_duration = audio.duration
        return audio_duration / num_images
    except Exception as e:
        raise RuntimeError(f"Failed to calculate image duration: {str(e)}")


def apply_ken_burns(clip, duration: float, preset: dict) -> CompositeVideoClip:
    w, h = clip.size
    zoom_start = preset["zoom_start"]
    zoom_end = preset["zoom_end"]
    pan = preset["pan"]

    def zoom_func(t):
        progress = t / duration if duration > 0 else 0
        return zoom_start + (zoom_end - zoom_start) * progress

    def pos_func(t):
        progress = t / duration if duration > 0 else 0
        z = zoom_start + (zoom_end - zoom_start) * progress
        if pan == "center":
            return ("center", "center")
        elif pan == "left_to_right":
            x = -(w * z - w) * progress
            return (x, "center")
        elif pan == "right_to_left":
            x = -(w * z - w) * (1 - progress)
            return (x, "center")
        elif pan == "top_to_bottom":
            y = -(h * z - h) * progress
            return ("center", y)
        elif pan == "bottom_to_top":
            y = -(h * z - h) * (1 - progress)
            return ("center", y)
        else:
            return ("center", "center")

    zoomed = clip.resize(zoom_func)
    zoomed = zoomed.set_position(pos_func)
    return CompositeVideoClip([zoomed], size=(w, h)).set_duration(duration)


def create_video_clip(image_folder: Path, audio_path: Path, output_path: Path,
                      crossfade_duration: float = 0.4, ken_burns_seed_offset: int = 0) -> None:
    try:
        all_work = sorted(image_folder.glob("*_work.jpeg"))
        all_normal = sorted(f for f in image_folder.glob("*.jpeg") if "_work" not in f.name)

        if all_work and len(all_work) == len(all_normal):
            image_files = all_work
            use_work_images = True
            print(f"🖼️  Menggunakan gambar kerja resolusi tinggi untuk Ken Burns headroom ({len(all_work)} gambar)")
        else:
            image_files = all_normal
            use_work_images = False

        if not image_files:
            raise ValueError("No images found in the specified folder")

        num_images = len(image_files)
        image_duration = calculate_image_duration(audio_path, num_images)
        compensated_duration = image_duration + crossfade_duration
        print(f"⏱️  Each image will be displayed for {image_duration:.2f} seconds "
              f"(+{crossfade_duration}s crossfade compensation)")

        rng = random.Random(ken_burns_seed_offset)

        clips = []
        previous_preset_name = None
        for i, image_file in enumerate(image_files):
            clip = ImageSequenceClip([str(image_file)], durations=[compensated_duration])

            if use_work_images:
                clip = resize_and_crop_to_9_16(clip, target_w=clip.w, target_h=clip.h)
            else:
                clip = resize_and_crop_to_9_16(clip)

            available = [p for p in KEN_BURNS_PRESETS if p["name"] != previous_preset_name]
            preset = rng.choice(available)
            previous_preset_name = preset["name"]
            clip = apply_ken_burns(clip, duration=compensated_duration, preset=preset)
            print(f"🎬 Menerapkan Ken Burns '{preset['name']}' ke gambar {i+1}/{num_images}...")

            if i > 0:
                clip = clip.crossfadein(crossfade_duration)

            clips.append(clip)

        video = concatenate_videoclips(
            clips,
            method="compose",
            padding=-crossfade_duration,
        )

        audio = AudioFileClip(str(audio_path))
        video = video.set_audio(audio)

        if use_work_images:
            print(f"📐 Menurunkan resolusi video dari gambar kerja ke {OUTPUT_W}x{OUTPUT_H}...")
            video = video.resize((OUTPUT_W, OUTPUT_H))

        video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            audio_fps=44100,
            bitrate="8000k",
            preset="medium",
            threads=4,
            ffmpeg_params=["-crf", "19"],
        )

        with VideoFileClip(str(output_path)) as check_clip:
            print(f"✅ Video final: {check_clip.w}x{check_clip.h} @ {check_clip.fps}fps, "
                  f"durasi {check_clip.duration:.1f}s")

        print(f"✅ Video saved to: {output_path}")

    except Exception as e:
        raise RuntimeError(f"Failed to create video: {str(e)}")


def main(image_folder: Path, audio_path: Path, output_path: Path,
         crossfade_duration: float = 0.4, ken_burns_seed_offset: int = 0) -> None:
    try:
        create_video_clip(
            image_folder,
            audio_path,
            output_path,
            crossfade_duration=crossfade_duration,
            ken_burns_seed_offset=ken_burns_seed_offset,
        )
    except Exception as e:
        print(f"❌ Error: {str(e)}")
