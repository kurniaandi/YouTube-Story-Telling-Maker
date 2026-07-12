# TikTokAIVideoGenerator — Dokumentasi Lengkap

> **YouTube Story Telling Maker** — Generate + Auto-Upload video storytelling motivasi ke YouTube Shorts secara otomatis.

---

## Daftar Isi

1. [Gambaran Sistem](#1-gambaran-sistem)
2. [Persyaratan Sistem](#2-persyaratan-sistem)
3. [Instalasi](#3-instalasi)
4. [Konfigurasi API Keys](#4-konfigurasi-api-keys)
5. [Konfigurasi LLM Providers (9Router)](#5-konfigurasi-llm-providers-9router)
6. [ImageMagick & FFmpeg](#6-imagemagick--ffmpeg)
7. [Background Music](#7-background-music)
8. [Konfigurasi YouTube Auto-Upload](#8-konfigurasi-youtube-auto-upload)
9. [Menjalankan Pipeline](#9-menjalankan-pipeline)
10. [Struktur Output](#10-struktur-output)
11. [Pemecahan Masalah](#11-pemecahan-masalah)

---

## 1. Gambaran Sistem

Aplikasi ini adalah pipeline CLI yang menghasilkan video **storytelling motivasi** untuk YouTube Shorts secara otomatis. Proses dari awal sampai akhir:

```
                      ┌──────────────────────┐
                      │  my_config.json       │
                      │  (API keys & config)  │
                      └──────────┬───────────┘
                                 │
┌─ main.py ──────────────────────┼─────────────────────────────┐
│                                ▼                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  1. Auto-fill AI: pilih topic/style/audience/CTA    │   │
│   │     (via 9Router: Groq / Cerebras / SambaNova)      │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  2. Generate Script     → script.json               │   │
│   │     (LLM + scene breakdown)                         │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  3. Generate Image Prompts  → image_prompts.json    │   │
│   │     (LLM: subject, artform, device, style, dll)     │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  4. Fetch Images via Serper.dev  → images/*.jpeg    │   │
│   │     (Google Images filter "large", min 1080x1920)   │   │
│   │     (crop 9:16 di full-res, simpan work + final)    │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  5. Generate Audio  → audio/voiceover.mp3           │   │
│   │     (Kokoro TTS → fallback Edge TTS → fallback gTTS)│   │
│   │     + background music ducking                       │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  6. Compose Video  → final_video.mp4                │   │
│   │     (Ken Burns zoom + crossfade, 1080x1920 30fps)   │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  7. Generate Captions  → audio/captions.json        │   │
│   │     (Whisper: word-level timestamps, bahasa ID)     │   │
│   │   + Overlay Karaoke  → final_video_captioned.mp4    │   │
│   └──────────────────────────────────────────────────────┘   │
│                         ▼                                    │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  8. [Optional] Auto-Upload ke YouTube               │   │
│   │     → Generate title/desc/tags via LLM              │   │
│   │     → Upload via YouTube Data API v3 (resumable)    │   │
│   │     → Rotasi project GCP kalau quota habis          │   │
│   └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Persyaratan Sistem

### Minimum

| Komponen | Versi/Keterangan |
|----------|-----------------|
| **OS** | Windows 10/11 (path sudah hardcoded untuk Windows) |
| **Python** | 3.11+ (venv menggunakan 3.11.0) |
| **RAM** | Minimal 8GB (Whisper model "small" butuh ~2GB) |
| **Disk** | ~10GB (termasuk PyTorch + Whisper model) |
| **FFmpeg** | Harus terinstall dan di PATH |
| **ImageMagick** | 7.1.2+ (path: `C:\Program Files\ImageMagick-*\magick.exe`) |

### Dependensi Python Utama

| Package | Fungsi |
|---------|--------|
| `openai` | LLM client (via 9Router / Groq / Cerebras / SambaNova) |
| `moviepy==1.0.3` | Video/audio composition, Ken Burns, crossfade, caption overlay |
| `pillow==12.3.0` | Image processing (resize, crop, EXIF) |
| `whisper` (openai-whisper) | Speech-to-text, word-level timestamps (model: "small") |
| `edge-tts==7.2.8` | Microsoft Edge TTS (suara Indonesia: ArdiNeural, GadisNeural) |
| `gTTS==2.5.4` | Google TTS (fallback terakhir) |
| `google-api-python-client` | YouTube Data API v3 |
| `google-auth-oauthlib` | OAuth 2.0 Google |
| `requests` | HTTP client (Serper, Kokoro TTS, dll) |
| `numpy` | Audio ducking (RMS calculation) |
| `torch==2.13.0` | PyTorch (dependency Whisper) |
| `jinja2` | (dependency, tidak langsung dipakai) |

---

## 3. Instalasi

### Langkah 1: Clone / Extract Project

```bash
cd C:\Users\lagik\Desktop
git clone <repo-url> TikTokAIVideoGenerator
cd TikTokAIVideoGenerator
```

### Langkah 2: Setup Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

### Langkah 3: Install Dependencies

> **Catatan**: Tidak ada `requirements.txt` — install manual satu per satu atau gunakan `pip freeze` output dari environment yang sudah ada.

```bash
# Core dependencies
pip install openai
pip install moviepy==1.0.3
pip install pillow
pip install openai-whisper
pip install edge-tts
pip install gTTS
pip install google-api-python-client google-auth-oauthlib google-auth
pip install requests numpy
pip install tqdm imageio-ffmpeg
pip install httpx
pip install groq
pip install jinja2
```

Jika menggunakan PyTorch dengan CUDA (opsional, lebih cepat untuk Whisper):

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Langkah 4: Install System Dependencies

#### FFmpeg

1. Download dari https://ffmpeg.org/download.html
2. Ekstrak ke `C:\ffmpeg\`
3. Tambahkan `C:\ffmpeg\bin` ke system PATH
4. Verifikasi: `ffmpeg -version`

#### ImageMagick

1. Download dari https://imagemagick.org/script/download.php
2. Install ke `C:\Program Files\ImageMagick-*`
3. Pastikan saat instalasi centang "Install legacy utilities (e.g., convert)"
4. Verifikasi: `magick -version`

### Langkah 5: Siapkan Folder assets

```bash
mkdir assets\background_music
```

Download musik instrumental royalty-free dari [Pixabay Music](https://pixabay.com/music/) atau [YouTube Audio Library](https://studio.youtube.com/) dan simpan di `assets/background_music/`.

Format yang didukung: `.mp3`, `.wav`, `.m4a`, `.aac`

---

## 4. Konfigurasi API Keys

Semua API key disimpan di `my_config.json`.

### Serper.dev (Wajib — untuk mencari gambar)

1. Daftar di https://serper.dev
2. Dapatkan API key (free tier: 2500 queries/bulan)
3. Masukkan ke `my_config.json`:

```json
"serper_api_key": "your_serper_api_key_here"
```

### 9Router (Wajib — untuk LLM/script generation)

9Router adalah proxy OpenAI-compatible yang merotasi request ke Groq, Cerebras, SambaNova, dll.

```json
"router_api_key": "sk-9router_key_here"
```

> Jika tidak pakai 9Router, bisa langsung pakai provider di `llm_providers` (lihat [Konfigurasi LLM](#5-konfigurasi-llm-providers-9router)).

### Image Fetch Configuration

```json
"image_fetch": {
    "serper_image_size_filter": "isz:l",
    "serper_num_results": 5,
    "min_width": 1080,
    "min_height": 1920
}
```

| Parameter | Opsi | Keterangan |
|-----------|------|------------|
| `serper_image_size_filter` | `isz:m` (medium), `isz:l` (large), `isz:xl` (extra large), `isz:gt,isgt:6x9` (>6MP) | Filter ukuran gambar dari Google Images |
| `serper_num_results` | angka (default 5) | Jumlah kandidat per query — makin besar makin banyak buffer untuk resolusi filtering |
| `min_width` / `min_height` | pixel (default 1080x1920) | Gambar di bawah ini akan di-skip, cari kandidat berikutnya |

---

## 5. Konfigurasi LLM Providers (9Router)

Aplikasi menggunakan `MultiProviderKeyRotator` yang membaca provider dari `my_config.json`.

### Struktur llm_providers

```json
"llm_providers": [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "api_keys": [
            "gsk_...key1",
            "gsk_...key2"
        ]
    },
    {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "llama3.1-70b",
        "api_keys": [
            "csk_...key1"
        ]
    },
    {
        "name": "sambanova",
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "api_keys": [
            "020413a3-..."
        ]
    }
]
```

### Cara Kerja Key Rotation

1. **call_with_rotation** → coba provider pertama, key pertama
2. Kalau kena **rate limit (429)** atau **quota exceeded** → rotasi ke key berikutnya dalam provider yang sama
3. Kalau semua key dalam satu provider habis → pindah ke provider berikutnya
4. Kalau semua provider gagal → raise error

### Fallback Priority

Selain `llm_providers`, rotator juga mendukung:
- `groq_api_keys` (array) — backward compatibility
- `groq_api_key` (string) — backward compatibility paling lama

> Prioritas: `llm_providers` > `groq_api_keys` > `groq_api_key`

---

## 6. ImageMagick & FFmpeg

### ImageMagick Path

Path ImageMagick sudah hardcoded di 3 file:

| File | Path |
|------|------|
| `main.py:25` | `C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe` |
| `video_composer.py:8` | Sama |
| `caption_overlay.py:10` | Sama |

Kalau versi ImageMagick berbeda, edit path di ketiga file tersebut, atau gunakan fallback otomatis di `main.py`:

```python
candidates = glob.glob(r"C:\Program Files\ImageMagick-*\magick.exe")
```

### FFmpeg

FFmpeg harus ada di system PATH. Digunakan oleh:
- **Whisper** (caption_generator.py) — transcribe audio
- **moviepy** (video_composer.py, caption_overlay.py) — render video

Verifikasi:
```bash
ffmpeg -version
```

---

## 7. Background Music

### Setup

1. Buat folder: `assets/background_music/`
2. Masukkan file musik instrumental (royalty-free)
3. Format: `.mp3`, `.wav`, `.m4a`, `.aac`

### Cara Kerja Ducking

Di `utils/music_mixer.py`:

- Musik diputar di **15% volume** saat tidak ada narasi
- Volume otomatis turun ke **5%** saat narasi berbicara (auto-ducking)
- Musik dipilih random dari folder setiap generate

### Sumber Musik Gratis

| Sumber | URL |
|--------|-----|
| Pixabay Music | https://pixabay.com/music/ |
| YouTube Audio Library | https://studio.youtube.com/ |
| Free Music Archive | https://freemusicarchive.org/ |
| Incompetech | https://incompetech.com/ |

> **PENTING**: Jangan upload video dengan musik berhak cipta ke YouTube — bisa kena copyright claim.

---

## 8. Konfigurasi YouTube Auto-Upload

### 8.1. Arsitektur Multi-Project

YouTube Data API v3 punya kuota harian ~10.000 unit per project. Satu upload video menghabiskan ~1.600 unit (maks ~6 upload/hari/project).

Aplikasi mendukung **rotation multi-project**: jika kuota project A habis, otomatis pindah ke project B, lalu C.

```
┌─ Google Cloud Project A ─┐
│  client_secret_a.json    │
│  token_a.json            │  quota: 10.000/hari
│  └─ upload 6 video       │
└──────────────────────────┘
           ↓ quota habis
┌─ Google Cloud Project B ─┐
│  client_secret_b.json    │
│  token_b.json            │  quota: 10.000/hari
│  └─ upload 6 video       │
└──────────────────────────┘
           ↓ quota habis
┌─ Google Cloud Project C ─┐
│  client_secret_c.json    │
│  token_c.json            │  quota: 10.000/hari
│  └─ upload 6 video       │
└──────────────────────────┘
```

### 8.2. One-time Setup: Google Cloud

Ulangi langkah berikut untuk SETIAP project (A, B, C):

1. **Buat Google Cloud Project**
   - Buka https://console.cloud.google.com/
   - Buat project baru (misal: "tiktok-ai-video-a")
2. **Aktifkan YouTube Data API v3**
   - APIs & Services → Library → cari "YouTube Data API v3" → Enable
3. **Buat OAuth Client ID**
   - APIs & Services → Credentials → Create Credentials → OAuth Client ID
   - Application type: **Desktop app** (bukan Web application)
   - Download JSON → simpan sebagai `secrets/project_a_client_secret.json`

### 8.3. Jalankan OAuth Flow (Sekali Per Project)

Untuk mengotorisasi akun YouTube ke project tertentu:

```bash
# Untuk project_a
python utils/youtube_auth_setup.py --project project_a

# Untuk project_b
python utils/youtube_auth_setup.py --project project_b

# Untuk project_c
python utils/youtube_auth_setup.py --project project_c
```

Ini akan:
1. Membuka browser untuk login ke Google/YouTube
2. Meminta izin akses ke channel YouTube
3. Menyimpan token ke `secrets/project_a_token.json`

> **Untuk server headless (VPS tanpa browser)**: Jalankan OAuth flow di laptop yang punya browser, lalu copy file `token.json` / `secrets/*_token.json` ke server.

### 8.4. Konfigurasi di my_config.json

```json
"youtube_upload": {
    "enabled": true,
    "privacy_status": "public",
    "category_id": "22",
    "publish_at": null,
    "rotation": {
        "enabled": true,
        "strategy": "least_used",
        "cost_per_upload": 1600,
        "quota_safety_margin": 1000
    },
    "projects": [
        {
            "name": "project_a",
            "client_secret_file": "secrets/project_a_client_secret.json",
            "token_file": "secrets/project_a_token.json",
            "daily_quota_limit": 10000,
            "active": true
        },
        {
            "name": "project_b",
            "client_secret_file": "secrets/project_b_client_secret.json",
            "token_file": "secrets/project_b_token.json",
            "daily_quota_limit": 10000,
            "active": true
        },
        {
            "name": "project_c",
            "client_secret_file": "secrets/project_c_client_secret.json",
            "token_file": "secrets/project_c_token.json",
            "daily_quota_limit": 10000,
            "active": true
        }
    ]
}
```

### 8.5. Parameter YouTube Upload

| Parameter | Opsi | Keterangan |
|-----------|------|------------|
| `enabled` | `true` / `false` | Aktifkan/nonaktifkan auto-upload |
| `privacy_status` | `public` / `private` / `unlisted` | Status privasi video |
| `category_id` | `"22"` = People & Blogs | Lihat daftar lengkap di [Google Docs](https://developers.google.com/youtube/v3/docs/videoCategories/list) |
| `publish_at` | ISO 8601 UTC atau `null` | Jadwal publish. Contoh: `"2026-07-15T09:00:00Z"`. Jika diisi, video otomatis di-private sampai waktu tsb |
| `rotation.enabled` | `true` / `false` | Aktifkan rotasi multi-project |
| `rotation.cost_per_upload` | 1600 (default) | Unit kuota per upload |
| `rotation.quota_safety_margin` | 1000 (default) | Sisa kuota minimal yang dijaga |

### 8.6. Metadata Video (Generate Otomatis)

Judul, deskripsi, dan tags di-generate otomatis oleh AI berdasarkan naskah cerita, via `utils/youtube_metadata_generator.py`. Prompt dioptimasi untuk SEO YouTube Shorts Bahasa Indonesia, termasuk hashtag.

### 8.7. Quota Tracking

Penggunaan kuota harian dicatat di `data/youtube_quota_state.json`:

```json
{
    "date": "2026-07-12",
    "usage": {
        "project_a": 1600,
        "project_b": 0,
        "project_c": 0
    }
}
```

File ini auto-reset setiap hari (berdasarkan UTC).

### 8.8. Jika Tidak Pakai Multi-Project

Hapus `rotation` dan `projects`, atau set `rotation.enabled = false`. Sistem akan fallback ke mode single-project (baca `token.json` di root).

---

## 9. Menjalankan Pipeline

### Mode Batch (Otomatis — Semua Cerita)

```bash
python main.py
# Pilih mode 1
```

Ini akan memproses SEMUA cerita di `config/motivational_topics.json` (8 cerita) × 3 gaya penceritaan = **24 video**.

Setiap cerita akan di-generate dalam 3 gaya berbeda:
| Gaya | Voice | Deskripsi |
|------|-------|-----------|
| `kisah_perjuangan` | ArdiNeural (male) | Dari sudut pandang perjuangan, personal dan jujur |
| `hikmah_reflektif` | GadisNeural (female) | Nada tenang, puitis, reflektif |
| `membangkitkan_semangat` | ArdiNeural (male) | Penuh energi, memotivasi |

### Mode Manual

```bash
python main.py
# Pilih mode 2
```

1. Masukkan nama folder
2. Pilih premis cerita dari daftar (atau input custom)
3. AI auto-generate topic/style/audience/CTA
4. Konfirmasi atau edit manual
5. Video di-generate

### Output Struktur

```
outputs/
└── 2026-07-12/
    └── merantau_demi_mengubah_nasib_kisah_perjuangan/
        ├── script.json
        ├── image_prompts.json
        ├── images/
        │   ├── 1.jpeg
        │   ├── 1_work.jpeg
        │   ├── 2.jpeg
        │   ├── 2_work.jpeg
        │   └── ...
        ├── audio/
        │   ├── voiceover_narration_only.mp3
        │   ├── voiceover.mp3
        │   └── captions.json
        ├── final_video.mp4
        └── final_video_captioned.mp4
```

---

## 10. Struktur Output

```
TikTokAIVideoGenerator/
│
├── main.py                          # Entry point CLI
├── my_config.json                   # Semua API key & konfigurasi
│
├── config/
│   └── motivational_topics.json     # 8 curated story premises
│
├── utils/
│   ├── script_generator.py          # Generate script via LLM
│   ├── image_prompt_generator.py    # Generate image prompts via LLM
│   ├── image_fetcher.py             # Fetch + crop + resize images via Serper
│   ├── audio_generator.py           # TTS (Kokoro → Edge → gTTS)
│   ├── music_mixer.py               # Background music + auto-ducking
│   ├── video_composer.py            # Ken Burns + crossfade + render
│   ├── caption_generator.py         # Whisper speech-to-text
│   ├── caption_overlay.py           # Karaoke caption overlay
│   ├── groq_key_rotator.py          # Multi-provider LLM rotation
│   ├── youtube_auth_setup.py        # OAuth 2.0 YouTube
│   ├── youtube_uploader.py          # Resumable upload + project rotation
│   ├── youtube_project_manager.py   # Quota tracking multi-project
│   ├── youtube_metadata_generator.py # AI title/desc/tags
│   └── output_path_helper.py        # Output folder structure
│
├── scripts/
│   └── migrate_existing_outputs.py  # Migrasi folder lama ke outputs/
│
├── secrets/                         # .gitignore'd
│   ├── project_a_client_secret.json
│   ├── project_a_token.json
│   ├── project_b_client_secret.json
│   ├── project_b_token.json
│   ├── project_c_client_secret.json
│   └── project_c_token.json
│
├── data/                            # .gitignore'd
│   └── youtube_quota_state.json     # Daily quota usage per project
│
├── outputs/                         # .gitignore'd — semua hasil generate
│   └── YYYY-MM-DD/
│       └── <nama_video>/
│
├── assets/
│   ├── background_music/            # Musik instrumental royalty-free
│   │   └── README.txt
│   └── fonts/
│       └── EastmanRomanTrial-Black.otf
│
└── docs/
    └── tutorial.md                  # Dokumentasi ini
```

---

## 11. Pemecahan Masalah

### 11.1. "ImageMagick tidak ditemukan"

**Sebab**: Path ImageMagick di hardcode ke versi spesifik.

**Solusi**:
1. Cek path ImageMagick yang terinstall: `where magick`
2. Edit path di `main.py:25`, `video_composer.py:8`, `caption_overlay.py:10`

Atau install ulang ImageMagick ke path default: `C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\`

### 11.2. "FFmpeg is not installed"

**Sebab**: FFmpeg tidak ada di system PATH.

**Solusi**:
1. Download FFmpeg dari https://ffmpeg.org/download.html
2. Ekstrak ke `C:\ffmpeg\`
3. Tambahkan `C:\ffmpeg\bin` ke system PATH
4. Restart terminal

### 11.3. "No image results found" dari Serper

**Sebab**: Query terlalu spesifik atau API key tidak valid.

**Solusi**:
1. Cek API key di https://serper.dev
2. Turunkan `serper_image_size_filter` ke `"isz:m"` (medium) di `my_config.json`
3. Naikkan `serper_num_results` untuk lebih banyak kandidat

### 11.4. Upload YouTube gagal "quotaExceeded"

**Sebab**: Kuota harian YouTube Data API sudah habis (~6 upload/project/hari).

**Solusi**:
1. Tambah Google Cloud Project baru (project D, E, dst)
2. Jalankan OAuth: `python utils/youtube_auth_setup.py --project project_d`
3. Tambah entry di `my_config.json` → `youtube_upload.projects[]`
4. Pipeline otomatis rotasi ke project baru

### 11.5. Kokoro TTS selalu gagal

**Sebab**: API Kokoro sedang down atau berubah endpoint.

**Solusi**: Pipeline otomatis fallback ke Edge TTS, lalu gTTS. Jika ingin paksa gTTS saja, edit `audio_generator.py`:

```python
# Comment out Kokoro, langsung ke Edge atau gTTS
def generate_audio(text, output_path, voice="af_bella", edge_voice=...):
    # Skip Kokoro, langsung Edge
    if asyncio.run(generate_audio_edge(text, output_path, voice=edge_voice)):
        return True
    # Fallback gTTS
    ...
```

### 11.6. Video terlalu besar / lambat render

**Sebab**: Work images (*_work.jpeg) beresolusi sangat tinggi.

**Solusi**: Turunkan `min_width`/`min_height` di `my_config.json` agar gambar lebih kecil, atau kurangi jumlah gambar via `MAX_IMAGES = 10` di `main.py`.

### 11.7. Token YouTube expired

**Token otomatis di-refresh** oleh `_get_authenticated_service()` di `youtube_uploader.py` selama refresh token masih valid. Jika refresh token dicabut (misal ganti password Google), jalankan ulang OAuth:

```bash
python utils/youtube_auth_setup.py --project <nama_project>
```

---

## Credits

- **LLM Providers**: Groq, Cerebras, SambaNova (via 9Router)
- **Image Search**: Serper.dev
- **TTS**: Kokoro TTS, Microsoft Edge TTS, Google TTS
- **Speech-to-Text**: OpenAI Whisper
- **Video Processing**: MoviePy + FFmpeg + ImageMagick
- **YouTube Upload**: Google YouTube Data API v3
- **Font**: EastmanRomanTrial-Black.otf
