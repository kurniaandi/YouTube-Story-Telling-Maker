import os

# Workaround: moviepy 1.0.3 masih pakai Image.ANTIALIAS yang sudah dihapus
# di Pillow 10+. Shim ini membuat ANTIALIAS tersedia lagi sebelum moviepy
# diimpor di manapun. Idealnya moviepy di-upgrade ke versi kompatibel Pillow 10+.
from PIL import Image
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

IMAGEMAGICK_BINARY_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_BINARY_PATH

from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY_PATH})

from pathlib import Path
from typing import List, Dict
import json
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

def load_captions(captions_path: Path) -> List[Dict]:
    """Load captions from a JSON file."""
    try:
        with open(captions_path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load captions: {str(e)}")

def group_words_into_captions(captions: List[Dict], max_words_per_caption: int = 4) -> List[Dict]:
    """
    Group words into captions with a maximum number of words per caption.
    Split captions at punctuation marks to maintain natural pauses.
    """
    grouped_captions = []
    current_group = []
    current_start = None
    current_end = None

    for caption in captions:
        text = caption["text"]
        start = caption["start"]
        end = caption["end"]

        ends_with_punctuation = any(text.endswith(p) for p in [".", ",", "!", "?", ";", ":"])

        current_group.append(text)
        if current_start is None:
            current_start = start
        current_end = end

        if ends_with_punctuation or len(current_group) >= max_words_per_caption:
            grouped_captions.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_group)
            })
            current_group = []
            current_start = None
            current_end = None

    if current_group:
        grouped_captions.append({
            "start": current_start,
            "end": current_end,
            "text": " ".join(current_group)
        })

    return grouped_captions

def add_captions_to_video(video_path: Path, captions_path: Path, output_path: Path, karaoke_style: bool = True) -> None:
    """
    Add captions to the video at the specified timestamps.
    YouTube Shorts safe zone compliant: avoids bottom 450px UI overlay.
    
    Args:
        video_path: Path to video file
        captions_path: Path to captions JSON (word-level timestamps)
        output_path: Path to save output video
        karaoke_style: If True, show words one-by-one (karaoke). If False, show 4 words at a time.
    """
    try:
        video = VideoFileClip(str(video_path))

        captions = load_captions(captions_path)

        # YouTube Shorts safe zone positioning:
        # Frame height: 1920px
        # Bottom UI: ~450px from bottom (1920-450=1470px)
        # Caption position: 1300px from top (safely above bottom UI)
        # Width: 75% (810px) for safe margins from right UI buttons
        caption_y_position = 1300  # Pixels from top
        caption_width_ratio = 0.75  # 75% of frame width (810px on 1080px width)
        
        text_clips = []
        
        if karaoke_style:
            # KARAOKE MODE: Satu kata per satu (word-by-word)
            print("🎤 Rendering captions dalam karaoke-style (kata per kata)...")
            
            for i, caption in enumerate(captions):
                text_clip = TextClip(
                    caption["text"],
                    fontsize=90,  
                    color="yellow",
                    font="EastMan", 
                    stroke_color="black",  
                    stroke_width=2,
                    size=(video.size[0] * caption_width_ratio, None),  
                    method="caption"  
                ).set_position(("center", caption_y_position)) \
                 .set_start(caption["start"]) \
                 .set_duration(caption["end"] - caption["start"])
                
                text_clips.append(text_clip)
                
                # Progress indicator setiap 10 kata
                if (i + 1) % 10 == 0:
                    print(f"   Processed {i + 1}/{len(captions)} words...")
            
            print(f"✅ Total {len(captions)} kata dirender sebagai caption individual")
        
        else:
            # GROUPED MODE: 4 kata sekaligus (mode lama)
            print("📝 Rendering captions dalam grouped mode (4 kata per caption)...")
            grouped_captions = group_words_into_captions(captions, max_words_per_caption=4)
            
            for caption in grouped_captions:
                text_clip = TextClip(
                    caption["text"],
                    fontsize=90,  
                    color="yellow",
                    font="EastMan", 
                    stroke_color="black",  
                    stroke_width=2,
                    size=(video.size[0] * caption_width_ratio, None),  
                    method="caption"  
                ).set_position(("center", caption_y_position)) \
                 .set_start(caption["start"]) \
                 .set_end(caption["end"])
                text_clips.append(text_clip)

        final_video = CompositeVideoClip([video] + text_clips)

        final_video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",  # Increased to 192kbps for better audio quality
            threads=4,
            ffmpeg_params=["-crf", "19"],  # CRF 19 for quality control
        )

        print(f"✅ Video with captions saved to: {output_path}")

    except Exception as e:
        raise RuntimeError(f"Failed to add captions to video: {str(e)}")

def main(video_path: Path, captions_path: Path, output_path: Path, karaoke_style: bool = True) -> None:
    """
    Add captions to the video and save the final output.
    
    Args:
        video_path: Path to input video
        captions_path: Path to captions JSON
        output_path: Path to output video
        karaoke_style: Enable karaoke-style captions (default: True)
    """
    try:
        if not video_path.exists():
            raise FileNotFoundError(f"Video file {video_path} not found")
        if not captions_path.exists():
            raise FileNotFoundError(f"Captions file {captions_path} not found")

        print("\n📝 Adding captions to video...")
        add_captions_to_video(video_path, captions_path, output_path, karaoke_style=karaoke_style)

    except Exception as e:
        print(f"❌ Error: {str(e)}")