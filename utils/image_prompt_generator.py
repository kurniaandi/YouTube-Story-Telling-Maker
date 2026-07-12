import json
import re
import concurrent.futures
from pathlib import Path
from typing import List, Dict
from utils.groq_key_rotator import MultiProviderKeyRotator

_router_client = MultiProviderKeyRotator()

# Pola nama model yang biasanya adalah reasoning/CoT model (lambat & sering
# menghabiskan token budget untuk "berpikir" sebelum menjawab JSON).
# Kalau model_used cocok salah satu pola ini, kita anggap kandidat buruk untuk
# tugas "hasilkan JSON terstruktur cepat", dan langsung skip ke percobaan berikutnya.
REASONING_MODEL_PATTERNS = [
    r"-r1", r"reasoning", r"thinking", r"distill", r"-o1", r"-o3", r"qwq",
]

# Timeout per percobaan (detik). Kalau model reasoning kelamaan mikir,
# request akan dibatalkan (di sisi tunggu kita) daripada nge-hang tanpa batas.
CALL_TIMEOUT_SECONDS = 90


def load_api_keys() -> dict:
    """Load API keys from config.json in root folder"""
    try:
        root_dir = Path(__file__).resolve().parent.parent
        config_path = root_dir / "my_config.json"
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError("my_config.json not found in root folder")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format in my_config.json")


def _is_reasoning_model(model_name: str) -> bool:
    """Cek apakah nama model mengindikasikan model reasoning/CoT yang lambat."""
    if not model_name:
        return False
    name_lower = model_name.lower()
    return any(re.search(pat, name_lower) for pat in REASONING_MODEL_PATTERNS)


def _extract_json_from_text(text: str) -> dict:
    """
    Robustly extract the outermost JSON object from text.
    Strips BOM/invisible characters first, then only tries the first (outermost)
    JSON object. Returns clean dict or raises ValueError.
    """
    # Step 1: Strip whitespace, BOM, zero-width chars, and other non-printable
    # characters from the beginning of the string
    text = text.strip()
    text = text.lstrip('\ufeff\u200b\u200c\u200d\ufffe\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f')

    # Step 1b: Kalau model reasoning "bocor" trace berpikirnya, biasanya dibungkus
    # tag <think>...</think> sebelum JSON asli. Buang bagian itu kalau ada.
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Step 2: Strip markdown code block
    if text.startswith("```"):
        match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Step 3: Find the first '{' (outermost JSON object)
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")

    # Step 4: Match balanced braces from the first '{' only
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]

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
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Failed to parse outer JSON structure: {e}"
                    )

    raise ValueError("No complete JSON object found in response")


def _build_prompt(script_text: str, scenes: list, num_scenes: int,
                   min_prompts: int, max_prompts: int, reinforce: bool = False) -> str:
    """Bangun prompt instruksi. Kalau reinforce=True, tambahkan penekanan ekstra
    soal jumlah prompt (dipakai saat retry karena percobaan sebelumnya salah jumlah)."""

    extra_warning = ""
    if reinforce:
        extra_warning = f"""

        ⚠️ PERINGATAN PENTING: Percobaan sebelumnya GAGAL karena jumlah prompt
        yang dihasilkan TIDAK SESUAI. Kamu WAJIB menghasilkan prompt sebanyak
        {min_prompts} SAMPAI {max_prompts} — TIDAK KURANG, TIDAK LEBIH.
        Hitung ulang jumlah objek di dalam array "prompts" sebelum menjawab.
        Jika jumlah scene ada {num_scenes}, maka kamu HARUS membuat 2-3 prompt
        untuk SETIAP scene (variasikan angle/shot), bukan hanya 1 prompt per scene.
        JANGAN gunakan proses berpikir panjang / chain-of-thought — langsung
        tulis JSON jawaban akhir saja, tanpa tag <think> atau penjelasan apa pun.
        """

    return f"""
        Kamu adalah asisten kreatif yang membuat prompt gambar untuk model AI image
        generation, khusus untuk VIDEO STORYTELLING MOTIVASI (bukan video review produk).
        Buat {min_prompts}-{max_prompts} prompt gambar berdasarkan {num_scenes} scene
        dan naskah berikut:

        NASKAH CERITA:
        {script_text}

        SCENE-SCENE:
        {json.dumps(scenes, indent=2)}

        Gunakan format respons berikut secara PERSIS:
        {{
          "prompts": [
            {{
              "subject": "seorang pemuda duduk sendirian menatap laptop dengan ekspresi lelah dan kecewa",
              "artform": ["cinematic photography"],
              "phototype": ["medium close-up"],
              "scene_details": {{
                "place": ["ruang kerja sederhana malam hari"],
                "lighting": ["cahaya lampu meja hangat, bayangan dramatis"],
                "composition": ["rule of thirds, fokus pada ekspresi wajah"]
              }},
              "background": ["shallow depth of field, sedikit blur"],
              "additional_details": {{
                "wearing": "kaos polos sederhana",
                "holding": "cangkir kopi yang sudah dingin"
              }},
              "photography_style": ["cinematic realism", "mood emosional"],
              "device": ["Sony Alpha 1"],
              "artist": []
            }},
            // ULANGI HINGGA {max_prompts} PROMPT
          ]
        }}

        Aturan:
        1. Buat tepat {min_prompts}-{max_prompts} prompt. Untuk {num_scenes} scene,
           berarti setiap scene HARUS diwakili oleh 2-3 prompt berbeda (variasi shot),
           bukan hanya 1 prompt per scene.
        2. Pertahankan struktur JSON secara ketat.
        3. Pastikan semua prompt mengikuti skema metadata di atas.
        4. Tidak ada markdown, hanya JSON murni.
        5. JANGAN tampilkan proses berpikir/reasoning apa pun (tidak ada tag
           <think>, tidak ada penjelasan) — langsung jawab dengan JSON final.

        PENTING - KONSISTENSI KARAKTER & EMOSI (khusus storytelling motivasi):
        1. Jika cerita berpusat pada satu tokoh utama, deskripsi fisik dasar tokoh
           tersebut (jenis kelamin, perkiraan usia, ciri pakaian umum) HARUS
           konsisten di setiap prompt yang menampilkan tokoh itu, supaya terlihat
           seperti orang yang sama dari scene ke scene.
        2. Setiap prompt harus mencerminkan EMOSI dan TAHAP CERITA scene tersebut
           (hook, konflik, titik balik, atau resolusi) melalui ekspresi wajah,
           bahasa tubuh, pencahayaan, dan warna suasana (mis. gelap/redup untuk
           keputusasaan, hangat/terang untuk harapan dan kebangkitan).
        3. Hindari elemen visual yang menjurus ke branding atau nama produk
           tertentu — fokus sepenuhnya pada suasana, ekspresi manusia, dan
           lingkungan yang mendukung narasi.
        4. Variasikan jenis shot (wide shot untuk suasana/tempat, close-up untuk
            emosi wajah, medium shot untuk aksi) agar video tidak terasa monoton.
        {extra_warning}

        **CRITICAL:** Balas HANYA dengan JSON murni. Jangan pakai ```markdown code block```, jangan ada teks sebelum/sesudah, jangan ada tag <think>.
        """


def _call_with_timeout(prompt_text: str, temperature: float, timeout_seconds: int):
    """
    Jalankan call_with_rotation dengan batas waktu. Kalau lewat timeout,
    raise TimeoutError supaya bisa langsung retry ke model lain, bukan
    menunggu tanpa batas (mengatasi kasus 'stuck lama' karena reasoning model).
    """

    def _call(client, model_name):
        return client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that outputs ONLY valid JSON. "
                               "No markdown, no explanation, no code fences, no <think> tags, "
                               "no chain-of-thought reasoning shown in the output."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            temperature=temperature,
            max_tokens=12000,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_router_client.call_with_rotation, _call)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Request melebihi batas waktu {timeout_seconds} detik (kemungkinan model reasoning yang lambat)"
            )


def generate_image_prompts(script_data: Dict, max_attempts: int = 4) -> List[Dict]:
    """
    Generate image prompts using AI (via 9Router) untuk VIDEO STORYTELLING MOTIVASI
    berdasarkan naskah dan scene-scene yang sudah dibuat.
    Jumlah prompt = num_scenes * 2 sampai num_scenes * 3 (dinamis).

    Retry hingga `max_attempts` kali jika:
    - response kosong,
    - request timeout (mengindikasikan model reasoning yang lambat),
    - model yang dipakai terdeteksi sebagai reasoning model (di-skip cepat),
    - atau jumlah prompt yang dihasilkan tidak sesuai rentang MIN-MAX.
    Setiap retry akan memperkuat instruksi jumlah prompt & larangan reasoning.
    """
    scenes = script_data.get("scenes", [])
    script_text = script_data.get("script", "")
    num_scenes = len(scenes)

    if num_scenes == 0:
        raise RuntimeError("Image prompt generation failed: Script has no scenes — cannot generate image prompts")

    MIN_PROMPTS = max(num_scenes * 2, 1)
    MAX_PROMPTS = max(num_scenes * 3, MIN_PROMPTS)

    last_error = None
    attempted_models = []

    for attempt in range(1, max_attempts + 1):
        reinforce = attempt > 1
        temperature = 0.7 if attempt == 1 else 0.3
        prompt_text = _build_prompt(
            script_text, scenes, num_scenes, MIN_PROMPTS, MAX_PROMPTS, reinforce=reinforce
        )

        try:
            print(f"   🔄 [Percobaan {attempt}/{max_attempts}] Mengirim request "
                  f"(timeout {CALL_TIMEOUT_SECONDS}s)...")
            completion = _call_with_timeout(prompt_text, temperature, CALL_TIMEOUT_SECONDS)
            response_text = completion.choices[0].message.content
            model_used = getattr(completion, 'model', 'unknown')
            attempted_models.append(model_used)

            if _is_reasoning_model(model_used):
                print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Model '{model_used}' "
                      f"terdeteksi sebagai reasoning model (lambat/boros token). "
                      f"Sebaiknya di-exclude dari combo 9Router. Melanjutkan validasi hasilnya dulu...")

            if not response_text:
                print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Model '{model_used}' "
                      f"mengembalikan response kosong.")
                last_error = f"Model '{model_used}' returned empty response"
                continue

            # Extract JSON dari response (otomatis buang tag <think>...</think> kalau ada)
            response = _extract_json_from_text(response_text)

            prompts = response.get("prompts")
            if not isinstance(prompts, list):
                print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Model '{model_used}' "
                      f"tidak mengembalikan field 'prompts' berupa list.")
                last_error = f"Expected 'prompts' key to be a list, got {type(prompts).__name__}"
                continue

            if not (MIN_PROMPTS <= len(prompts) <= MAX_PROMPTS):
                print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Model '{model_used}' "
                      f"menghasilkan {len(prompts)} prompt (expected {MIN_PROMPTS}-{MAX_PROMPTS}). Retry...")
                last_error = (
                    f"Invalid response format. Got {len(prompts)} prompts. "
                    f"Expected between {MIN_PROMPTS}-{MAX_PROMPTS} prompts."
                )
                continue

            required_keys = {"subject", "artform", "phototype", "scene_details"}
            missing = None
            for i, p in enumerate(prompts):
                if not all(key in p for key in required_keys):
                    missing = f"Prompt {i+1} missing required keys: {required_keys}"
                    break

            if missing:
                print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Model '{model_used}' "
                      f"menghasilkan prompt dengan struktur tidak lengkap. Retry...")
                last_error = missing
                continue

            # Sukses
            if attempt > 1:
                print(f"   ✅ Berhasil pada percobaan ke-{attempt} dengan model '{model_used}'.")
            return prompts

        except TimeoutError as e:
            print(f"   ⏱️ [Percobaan {attempt}/{max_attempts}] {e}. Melanjutkan ke percobaan berikutnya...")
            last_error = str(e)
            continue
        except ValueError as e:
            print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Gagal parsing JSON: {e}")
            last_error = str(e)
            continue
        except Exception as e:
            print(f"   ⚠️ [Percobaan {attempt}/{max_attempts}] Error tak terduga: {e}")
            last_error = str(e)
            continue

    # Semua percobaan gagal
    models_tried = ", ".join(attempted_models) if attempted_models else "tidak ada model yang berhasil dipanggil"
    reasoning_models_hit = [m for m in attempted_models if _is_reasoning_model(m)]
    hint = ""
    if reasoning_models_hit:
        hint = (f" Terdeteksi model reasoning yang lambat/tidak cocok: "
                f"{', '.join(set(reasoning_models_hit))}. "
                f"Disarankan exclude model ini dari combo 9Router Anda.")

    raise RuntimeError(
        f"Image prompt generation failed after {max_attempts} attempts. "
        f"Last error: {last_error}. Models tried: {models_tried}.{hint}"
    )


def save_image_prompts(prompts: List[Dict], output_path: Path) -> None:
    """Save the image prompts as a JSON file"""
    with open(output_path, "w") as f:
        json.dump({"prompts": prompts}, f, indent=2)
    print(f"✅ Saved {len(prompts)} image prompts to: {output_path}")

def main(script_path: Path, output_path: Path) -> None:
    """Generate and save image prompts"""
    try:
        with open(script_path, "r") as f:
            script_data = json.load(f)

        prompts = generate_image_prompts(script_data)

        save_image_prompts(prompts, output_path)

    except Exception as e:
        print(f"❌ Error: {str(e)}")