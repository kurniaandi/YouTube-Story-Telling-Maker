import os
import re
import glob
import sys
from pathlib import Path

# Pastikan stdout bisa mencetak emoji di Windows (cp1252 default), termasuk saat di-pipe
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Workaround: moviepy 1.0.3 masih pakai Image.ANTIALIAS yang sudah dihapus
# di Pillow 10+. Shim ini membuat ANTIALIAS tersedia lagi sebelum moviepy
# diimpor di manapun. Idealnya moviepy di-upgrade ke versi kompatibel Pillow 10+.
from PIL import Image
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.config import change_settings

# Path ImageMagick terkonfirmasi ada di:
# C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe
confirmed_path = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

imagemagick_path = None
if os.path.exists(confirmed_path):
    imagemagick_path = confirmed_path
else:
    # Fallback: cari otomatis via glob kalau versi berbeda di komputer lain
    candidates = glob.glob(r"C:\Program Files\ImageMagick-*\magick.exe")
    if candidates:
        imagemagick_path = candidates[0]

if imagemagick_path:
    change_settings({"IMAGEMAGICK_BINARY": imagemagick_path})
    print(f"✅ ImageMagick path diset ke: {imagemagick_path}")
else:
    print("⚠️ ImageMagick tidak ditemukan, caption mungkin gagal ditambahkan ke video")

import json
from utils.groq_key_rotator import MultiProviderKeyRotator
from utils.script_generator import generate_script, save_script
from utils.image_prompt_generator import main as generate_image_prompts
from utils.image_fetcher import fetch_images
from utils.audio_generator import main as generate_audio
from utils.video_composer import main as create_video
from utils.caption_generator import main as generate_captions
from utils.caption_overlay import main as add_captions_to_video
from utils.youtube_metadata_generator import generate_youtube_metadata
from utils.youtube_uploader import upload_video
from utils.output_path_helper import get_output_dir

router_client = MultiProviderKeyRotator()
MOTIVATIONAL_TOPICS_PATH = "config/motivational_topics.json"


def _load_youtube_upload_config() -> dict | None:
    """
    Baca konfigurasi opsional untuk auto-upload YouTube dari my_config.json:

    {
      "youtube_upload": {
        "enabled": true,
        "privacy_status": "public",
        "category_id": "22",
        "publish_at": null,
        "rotation": { ... },
        "projects": [ ... ]
      }
    }

    Return None kalau tidak ada / enabled=false, supaya pipeline tetap
    jalan normal tanpa upload (mis. saat masih testing/belum setup token.json).
    """
    cfg_path = Path("my_config.json")
    if not cfg_path.exists():
        return None
    try:
        with open(cfg_path, "r") as f:
            cfg = json.load(f).get("youtube_upload")
    except (json.JSONDecodeError, OSError):
        return None
    if not cfg or not cfg.get("enabled"):
        return None
    return cfg

# 3 gaya penceritaan berbeda untuk tiap premis cerita (batch mode)
ANGLE_PRESETS = [
    {
        "name": "kisah_perjuangan",
        "video_style": "kisah_perjuangan",
        "angle_hint": (
            "Ceritakan dari sudut pandang PERJUANGAN: tunjukkan betapa beratnya "
            "situasi yang dihadapi tokoh, keraguan dan ketakutannya, sebelum "
            "akhirnya ia menemukan kekuatan untuk terus melangkah. Gaya bahasa "
            "personal dan jujur, seperti curhat pengalaman pribadi."
        ),
        "voice": "id-ID-ArdiNeural",
        "crossfade_duration": 0.4,
        "ken_burns_seed_offset": 0,
    },
    {
        "name": "hikmah_reflektif",
        "video_style": "reflektif",
        "angle_hint": (
            "Ceritakan dengan nada TENANG dan REFLEKTIF, fokus pada perenungan "
            "batin tokoh dan pelajaran hidup yang ia petik. Gaya bahasa lebih "
            "puitis dan menyentuh, mengajak penonton merenung tentang hidupnya "
            "sendiri, bukan sekadar menceritakan kejadian."
        ),
        "voice": "id-ID-GadisNeural",
        "crossfade_duration": 0.5,
        "ken_burns_seed_offset": 1,
    },
    {
        "name": "membangkitkan_semangat",
        "video_style": "membangkitkan_semangat",
        "angle_hint": (
            "Ceritakan dengan nada MEMBANGKITKAN SEMANGAT dan penuh energi "
            "positif, terutama pada bagian titik balik dan resolusi. Buat "
            "penonton merasa termotivasi dan ingin langsung bertindak setelah "
            "menonton, tanpa terkesan menggurui."
        ),
        "voice": "id-ID-ArdiNeural",
        "crossfade_duration": 0.35,
        "ken_burns_seed_offset": 2,
    },
]


def _load_ai_client():
    """Load an AI client using the existing groq_api_key in config (DEPRECATED - kept for backward compatibility)."""
    for cfg in ("my_config.json", "config.json"):
        cfg_path = Path(cfg)
        if cfg_path.exists():
            try:
                with open(cfg_path, "r") as f:
                    api_key = json.load(f).get("groq_api_key", "")
                if api_key:
                    return Groq(api_key=api_key)
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _auto_fill_from_ai(story_title: str, story_theme: str, premise: str, curated_moral: str = "", angle_hint: str = "") -> dict:
    """
    Minta AI (via 9Router) meng-generate video_topic, video_style,
    target_audience, dan cta (pesan/hikmah) berdasarkan premis cerita terpilih.
    angle_hint: instruksi gaya penceritaan (kisah_perjuangan, hikmah_reflektif,
    membangkitkan_semangat) supaya hasil mencerminkan angle yang diminta.
    Return dict hasil, atau None kalau gagal (caller fallback ke manual).
    """
    if curated_moral:
        moral_instruction = f'''
    Referensi pesan/hikmah (sudah dikurasi, sesuaikan gaya bahasanya saja
    supaya konsisten dengan video_topic dan video_style yang kamu buat, jangan
    ubah makna/pesan intinya): {curated_moral}
'''
    else:
        moral_instruction = ""

    prompt_auto_fill = f'''
    Kamu adalah asisten kreatif untuk membuat video STORYTELLING MOTIVASI
    berbahasa Indonesia yang menyentuh dan menginspirasi, untuk YouTube Shorts.
    Berdasarkan premis cerita ini:

    Judul cerita: {story_title}
    Tema: {story_theme}
    Premis: {premise}
{moral_instruction}
    GAYA PENCERITAAN YANG DIMINTA: {angle_hint}

    Buatkan HANYA dalam format JSON (tanpa teks lain, tanpa markdown code
    block) dengan struktur persis berikut:

    {{
      "video_topic": "deskripsi topik cerita yang matang dan detail, mencakup situasi awal, konflik, dan arah resolusi, gaya bahasa Indonesia yang mengalir",
      "video_style": "salah satu dari: kisah_perjuangan, reflektif, membangkitkan_semangat",
      "target_audience": "deskripsi target penonton yang relevan dengan tema cerita ini, usia dan situasi hidup spesifik",
      "cta": "pesan/hikmah penutup final berdasarkan referensi di atas, disesuaikan gaya bahasanya dengan video_topic dan video_style yang kamu buat"
    }}
    '''

    def _call(client, model_name):
        return client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that outputs ONLY valid JSON. No markdown, no explanation, no code fences."
                },
                {
                    "role": "user",
                    "content": prompt_auto_fill
                }
            ],
            temperature=0.7,
            max_tokens=1024,
        )

    try:
        completion = router_client.call_with_rotation(_call)
        raw = completion.choices[0].message.content
        
        # Extract JSON from response (handles BOM, markdown, preamble text, etc.)
        cleaned_text = raw.strip()
        cleaned_text = cleaned_text.lstrip('\ufeff\u200b\u200c\u200d\ufffe\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f')
        
        # Hapus markdown code block
        if cleaned_text.startswith("```"):
            match = re.search(r'```(?:json)?\s*\n(.*?)\n```', cleaned_text, re.DOTALL)
            if match:
                cleaned_text = match.group(1).strip()
        
        # Find first { and do balanced-brace extraction (outermost only)
        start = cleaned_text.find('{')
        if start == -1:
            return None
        
        depth = 0
        in_string = False
        escape_next = False
        
        for i in range(start, len(cleaned_text)):
            c = cleaned_text[i]
            if escape_next:
                escape_next = False
                continue
            if c == '\\' and in_string:
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned_text[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        
        return None
    except Exception as e:
        import traceback
        print(f"⚠️ Auto-fill AI gagal untuk {story_title}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


MAX_IMAGES = 15


def limit_prompts_evenly(prompts: list, max_count: int = MAX_IMAGES) -> list:
    """Batasi jumlah prompt secara merata (downsampling) supaya alur
    cerita dari awal sampai akhir tetap terwakili, tanpa asal potong
    dari belakang."""
    if len(prompts) <= max_count:
        return prompts
    indices = [round(i * (len(prompts) - 1) / (max_count - 1)) for i in range(max_count)]
    indices = sorted(set(indices))
    selected = [prompts[i] for i in indices]
    return selected[:max_count]


def run_pipeline(
    folder_name: str,
    video_topic: str,
    video_style: str,
    target_audience: str,
    cta: str,
    max_images_limit: int | None = None,
    voice_override: str | None = None,
    crossfade_duration: float = 0.4,
    ken_burns_seed_offset: int = 0,
    story_title: str = "",
) -> None:
    """
    Jalankan pipeline lengkap untuk 1 cerita motivasi:
    generate script -> image prompts -> images -> audio -> video.
    """
    project_path = get_output_dir(folder_name)
    (project_path / "images").mkdir(exist_ok=True)
    (project_path / "audio").mkdir(exist_ok=True)
    print(f"✅ Created project folder at: {project_path}")

    script_path = project_path / "script.json"
    image_prompts_path = project_path / "image_prompts.json"
    images_dir = project_path / "images"
    audio_dir = project_path / "audio"
    video_path = project_path / "final_video.mp4"
    captioned_video_path = project_path / "final_video_captioned.mp4"

    print("\n🚀 Generating storytelling script with Llama3...")
    script_data = generate_script(video_topic, video_style, target_audience, cta)
    save_script(script_data, script_path)

    print("\n🎨 Generating image prompts...")
    generate_image_prompts(script_path, image_prompts_path)

    # Batasi jumlah gambar: default maksimal MAX_IMAGES (15), kecuali user
    # set max_images_limit yang lebih kecil. Downsampling merata supaya
    # alur cerita tetap terwakili.
    with open(image_prompts_path, "r") as f:
        _prompts_data = json.load(f)
    all_prompts = _prompts_data.get("prompts", [])

    effective_limit = max_images_limit if max_images_limit is not None else MAX_IMAGES
    prompts_list = limit_prompts_evenly(all_prompts, effective_limit)
    print(f"🖼️  Jumlah gambar dibatasi ke {len(prompts_list)} (dari {len(all_prompts)} prompt)")

    print("\n🌄 Fetching images from Google Images via Serper...")
    fetch_images(
        image_prompts_path,
        images_dir,
        prompts=prompts_list,
    )

    print("\n🔊 Generating audio...")
    audio_path = audio_dir / "voiceover.mp3"
    try:
        generate_audio(script_path, audio_dir, voice_override=voice_override, enable_background_music=True)
    except Exception as e:
        # Bersihkan file audio partial jika ada
        if audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Audio generation failed: {e}")

    print("\n🎥 Composing video...")
    create_video(
        images_dir,
        audio_dir / "voiceover.mp3",
        video_path,
        crossfade_duration=crossfade_duration,
        ken_burns_seed_offset=ken_burns_seed_offset,
    )

    generated_count = len(prompts_list)
    print(f"\n📝 Total duration: {script_data['total_duration']}s")
    print(f"🎬 Number of scenes: {len(script_data['scenes'])}")
    print(f"🖼️  Generated images: {generated_count}/{generated_count}")
    print(f"🔊 Audio generated: {os.path.exists(audio_dir / 'voiceover.mp3')}")
    print(f"🎥 Video generated: {os.path.exists(video_path)}")

    # --- Step 7: Generate karaoke captions & overlay ke video ---
    print("\n🎤 Generating karaoke captions with Whisper...")
    generate_captions(audio_dir / "voiceover.mp3", audio_dir)

    print("\n📝 Adding karaoke-style captions to video...")
    add_captions_to_video(
        video_path,
        audio_dir / "captions.json",
        captioned_video_path,
        karaoke_style=True,
    )
    print(f"🎬 Captioned video: {os.path.exists(captioned_video_path)}")

    # --- Step 8: Auto-upload ke YouTube (opsional, tergantung config) ---
    upload_cfg = _load_youtube_upload_config()
    final_video = captioned_video_path if os.path.exists(captioned_video_path) else video_path
    if upload_cfg and os.path.exists(final_video):
        try:
            print("\n📤 Generating YouTube metadata...")
            metadata = generate_youtube_metadata(script_data, story_title=story_title, moral=cta)

            upload_video(
                video_path=final_video,
                title=metadata["title"],
                description=metadata["description"],
                tags=metadata["tags"],
                category_id=upload_cfg.get("category_id", "22"),
                privacy_status=upload_cfg.get("privacy_status", "public"),
                publish_at=upload_cfg.get("publish_at"),
                config=upload_cfg,
            )
        except Exception as e:
            print(f"⚠️ Auto-upload YouTube gagal (video tetap tersimpan lokal): {e}")
    elif not upload_cfg:
        print("\nℹ️ Auto-upload YouTube tidak aktif (set youtube_upload.enabled=true di my_config.json untuk mengaktifkan)")


def main():
    try:
        print("""
██╗   ██╗ ██████╗ ██╗   ██╗████████╗██╗   ██╗██████╗ ███████╗
╚██╗ ██╔╝██╔═══██╗██║   ██║╚══██╔══╝╚██╗ ██╔╝██╔══██╗██╔════╝
 ╚████╔╝ ██║   ██║██║   ██║   ██║    ╚████╔╝ ██████╔╝█████╗
  ╚██╔╝  ██║   ██║██║   ██║   ██║     ╚██╔╝  ██╔══██╗██╔══╝
   ██║   ╚██████╔╝╚██████╔╝   ██║      ██║   ██████╔╝███████╗
   ╚═╝    ╚═════╝  ╚═════╝    ╚═╝      ╚═╝   ╚═════╝ ╚══════╝

███████╗████████╗ ██████╗ ██████╗ ██╗   ██╗████████╗███████╗██╗     ██╗     ██╗███╗   ██╗ ██████╗
██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗╚██╗ ██╔╝╚══██╔══╝██╔════╝██║     ██║     ██║████╗  ██║██╔════╝
███████╗   ██║   ██║   ██║██████╔╝ ╚████╔╝    ██║   █████╗  ██║     ██║     ██║██╔██╗ ██║██║  ███╗
╚════██║   ██║   ██║   ██║██╔══██╗  ╚██╔╝     ██║   ██╔══╝  ██║     ██║     ██║██║╚██╗██║██║   ██║
███████║   ██║   ╚██████╔╝██║  ██║   ██║      ██║   ███████╗███████╗███████╗██║██║ ╚████║╚██████╔╝
╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝

            YouTube Story Telling Maker - Generate & Upload Story Videos
""")

        print("\n🎬 Pilih mode:")
        print("1. Batch otomatis - generate video untuk SEMUA cerita di motivational_topics.json")
        print("2. Manual - pilih 1 premis cerita / input custom seperti biasa")
        mode = input("Pilih mode (1/2): ").strip()

        if mode == "1":
            try:
                with open(MOTIVATIONAL_TOPICS_PATH, "r") as f:
                    stories = json.load(f).get("stories", [])
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                stories = []

            if not stories:
                print("❌ Tidak ada cerita di motivational_topics.json, fallback ke mode manual.")
                mode = "2"
            else:
                for idx, story in enumerate(stories, 1):
                    print(f"\n{'='*60}")
                    print(f"🚀 Memproses cerita {idx}/{len(stories)}: {story['title']}")
                    print(f"{'='*60}")

                    for angle in ANGLE_PRESETS:
                        print(f"\n  🎯 Gaya: {angle['name']}")

                        base_folder = re.sub(r'[^a-z0-9]+', '_', story['title'].lower()).strip('_')
                        folder_name = f"{base_folder[:40]}_{angle['name']}"

                        auto = _auto_fill_from_ai(
                            story['title'],
                            story.get('theme', ''),
                            story.get('premise', ''),
                            curated_moral=story.get('moral', ''),
                            angle_hint=angle['angle_hint'],
                        )
                        if not auto or not all(k in auto for k in ("video_topic", "video_style", "target_audience", "cta")):
                            print(f"  ⚠️ Auto-fill AI gagal untuk {story['title']} ({angle['name']}), lanjut ke gaya berikutnya.")
                            continue

                        try:
                            run_pipeline(
                                folder_name=folder_name,
                                video_topic=auto['video_topic'],
                                video_style=angle['video_style'],
                                target_audience=auto['target_audience'],
                                cta=auto['cta'],
                                max_images_limit=None,
                                voice_override=angle['voice'],
                                crossfade_duration=angle['crossfade_duration'],
                                ken_burns_seed_offset=angle['ken_burns_seed_offset'],
                                story_title=story['title'],
                            )
                            print(f"  ✅ Selesai: {story['title']} ({angle['name']})")
                        except Exception as e:
                            print(f"  ❌ Gagal memproses {story['title']} ({angle['name']}): {e}")
                            print("  ⏭️  Lanjut ke gaya/cerita berikutnya...")
                            continue

                print(f"\n🎉 Batch selesai! Total {len(stories)} cerita x 3 gaya = {len(stories) * 3} video diproses.")
                return

        if mode == "2":
            folder_name = input("Enter the name of the folder to save the project: ").strip()

            # --- Alur manual: pilih premis cerita dari curated list lalu auto-fill via AI (9Router) ---
            story_title = ""
            story_theme = ""
            premise = ""
            curated_moral = ""
            try:
                with open(MOTIVATIONAL_TOPICS_PATH, "r") as f:
                    stories = json.load(f).get("stories", [])
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                stories = []

            if stories:
                print("\n📖 Daftar premis cerita motivasi (curated):")
                for idx, s in enumerate(stories, 1):
                    print(f"{idx}. {s['title']} ({s['theme']}) - {s['premise']}")
                print(f"{len(stories) + 1}. Input premis cerita custom (bukan dari daftar)")

                choice = input("\nPilih nomor premis cerita (atau nomor custom): ").strip()
                if choice.isdigit():
                    choice_idx = int(choice)
                    if 1 <= choice_idx <= len(stories):
                        chosen = stories[choice_idx - 1]
                        story_title = chosen["title"]
                        story_theme = chosen.get("theme", "")
                        premise = chosen.get("premise", "")
                        curated_moral = chosen.get("moral", "")
                    elif choice_idx == len(stories) + 1:
                        story_title = input("Masukkan judul cerita custom: ").strip()
                        story_theme = input("Masukkan tema singkat: ").strip()
                        premise = input("Masukkan premis singkat cerita: ").strip()
                        curated_moral = ""
                    else:
                        story_title = input("Masukkan judul cerita custom: ").strip()
                        story_theme = input("Masukkan tema singkat: ").strip()
                        premise = input("Masukkan premis singkat cerita: ").strip()
                        curated_moral = ""
                else:
                    story_title = input("Masukkan judul cerita custom: ").strip()
                    story_theme = input("Masukkan tema singkat: ").strip()
                    premise = input("Masukkan premis singkat cerita: ").strip()
                    curated_moral = ""

                # Auto-fill via AI (9Router)
                if story_title:
                    print("\n🤖 Meminta AI meng-generate topic/style/audience/hikmah...")
                    auto = _auto_fill_from_ai(story_title, story_theme, premise, curated_moral=curated_moral)
                    if auto and all(k in auto for k in ("video_topic", "video_style", "target_audience", "cta")):
                        print(f"\n✨ Hasil auto-generate dari AI:")
                        print(f"Topic: {auto['video_topic']}")
                        print(f"Style: {auto['video_style']}")
                        print(f"Target Audience: {auto['target_audience']}")
                        print(f"Hikmah/CTA: {auto['cta']}")
                        confirm = input("\nGunakan hasil ini? (y = lanjut, n = edit manual): ").strip().lower()
                        if confirm == "y":
                            video_topic = auto["video_topic"]
                            video_style = auto["video_style"]
                            target_audience = auto["target_audience"]
                            cta = auto["cta"]
                        else:
                            video_topic = input("Masukkan topik cerita: ")
                            video_style = input("Masukkan gaya penceritaan (kisah_perjuangan/reflektif/membangkitkan_semangat): ")
                            target_audience = input("Masukkan target penonton: ")
                            cta = input("Masukkan pesan/hikmah penutup: ")
                    else:
                        print("⚠️ Auto-fill AI gagal, lanjut ke input manual.")
                        video_topic = input("Masukkan topik cerita: ")
                        video_style = input("Masukkan gaya penceritaan (kisah_perjuangan/reflektif/membangkitkan_semangat): ")
                        target_audience = input("Masukkan target penonton: ")
                        cta = input("Masukkan pesan/hikmah penutup: ")
                else:
                    video_topic = input("Masukkan topik cerita: ")
                    video_style = input("Masukkan gaya penceritaan (kisah_perjuangan/reflektif/membangkitkan_semangat): ")
                    target_audience = input("Masukkan target penonton: ")
                    cta = input("Masukkan pesan/hikmah penutup: ")
            else:
                video_topic = input("Masukkan topik cerita: ")
                video_style = input("Masukkan gaya penceritaan (kisah_perjuangan/reflektif/membangkitkan_semangat): ")
                target_audience = input("Masukkan target penonton: ")
                cta = input("Masukkan pesan/hikmah penutup: ")

            test_mode_input = input("Enter max number of images for testing (press Enter for no limit): ")
            max_images_limit = int(test_mode_input) if test_mode_input.strip().isdigit() else None

            run_pipeline(
                folder_name=folder_name,
                video_topic=video_topic,
                video_style=video_style,
                target_audience=target_audience,
                cta=cta,
                max_images_limit=max_images_limit,
                story_title=story_title,
            )
        else:
            print("❌ Pilihan mode tidak valid.")

    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    main()