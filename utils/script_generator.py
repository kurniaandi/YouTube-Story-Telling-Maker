import json
from utils.groq_key_rotator import MultiProviderKeyRotator

_router_client = MultiProviderKeyRotator()

def generate_script(topic: str, style: str, target_audience: str, cta: str) -> dict:
    """
    Generates a MOTIVATIONAL STORYTELLING video script using AI (via 9Router)
    with model random selection.

    Params (nama parameter dipertahankan sama seperti versi sebelumnya supaya
    kompatibel dengan main.py, tapi maknanya sekarang):
    - topic          -> premis/topik cerita motivasi (mis. "bangkit dari kegagalan usaha")
    - style          -> gaya penceritaan (mis. "kisah_perjuangan", "reflektif", "membangkitkan_semangat")
    - target_audience-> siapa yang dituju (mis. "anak muda yang sedang merintis usaha")
    - cta            -> pesan/hikmah penutup yang ingin ditinggalkan ke penonton (bukan CTA jualan)

    Returns a dictionary dengan struktur script & scene-scene (sama seperti sebelumnya).
    """
    try:
        prompt = f"""
        Kamu adalah seorang penulis naskah storytelling motivasi yang ahli membuat
        video pendek YouTube Shorts yang menyentuh emosi dan menginspirasi penonton.
        Video harus mengikuti struktur cerita klasik berikut:

        1. HOOK (3-5 detik pertama): buka dengan kalimat, pertanyaan, atau momen yang
           langsung menarik perhatian dan bikin penonton penasaran ingin tahu
           kelanjutan ceritanya. Jangan langsung menggurui di awal.
        2. KONFLIK / PERJUANGAN (15-25 detik): ceritakan situasi sulit, keraguan,
           atau tantangan yang dihadapi tokoh dalam cerita. Buat penonton ikut
           merasakan beratnya situasi tersebut.
        3. TITIK BALIK / KLIMAKS (15-20 detik): momen di mana tokoh mengambil
           keputusan, menemukan kekuatan, atau mengalami pergeseran sudut pandang
           yang mengubah arah ceritanya.
        4. RESOLUSI & HIKMAH (10-15 detik terakhir): tutup dengan hasil dari
           perjuangan tersebut dan sampaikan pesan/hikmah secara halus dan tulus,
           bukan seperti khotbah. Boleh diakhiri kalimat reflektif yang mengajak
           penonton merenung tentang hidup mereka sendiri.

        Buat naskah video dengan 180 hingga 200 token berdasarkan detail berikut:
        - Premis/topik cerita: {topic}
        - Gaya penceritaan: {style}
        - Target penonton: {target_audience}
        - Pesan/hikmah yang ingin disampaikan di akhir: {cta}

        Kembalikan naskah dalam format JSON dengan struktur berikut:
        {{
          "script": "Naskah lengkap untuk dinarasikan oleh TTS, ditulis sebagai cerita mengalir, bukan daftar poin",
          "scenes": [
            {{
              "scene_number": 1,
              "visual_description": "Deskripsi visual/adegan detail untuk scene ini (situasi, ekspresi, suasana, tempat)",
              "voiceover_text": "Teks yang dinarasikan pada scene ini",
              "duration_seconds": 3
            }},
            ...
          ],
          "total_duration": 45
        }}

        **INSTRUKSI KRITIS:** Naskah yang dihasilkan **HARUS** memiliki antara
        **180 dan 200 token**. Ini penting agar durasi video sekitar 45 detik.

        Pastikan:
        1. Cerita terasa personal, jujur, dan relatable — gunakan sudut pandang
           orang pertama ("aku") atau orang ketiga yang dekat, sesuai konteks cerita.
        2. **BATASAN TOKEN:** Naskah harus **TEPAT** antara 180-200 token.
           JANGAN melebihi 200 dan JANGAN kurang dari 180.
        3. Setiap scene punya visual_description dan voiceover_text yang jelas
           serta selaras dengan tahapan cerita (hook/konflik/klimaks/resolusi).
        4. Nada bicara mengalir seperti orang bercerita, bukan seperti iklan
           atau daftar tips. Hindari kesan menggurui atau memaksa.
        5. Total durasi tepat 45 detik.

        **PENEKANAN ULANG:** Pastikan naskah final **WAJIB** memiliki minimal
        180 token dan maksimal 200 token. Jumlah token **HARUS** dipatuhi.

        Ingat: **BATASAN TOKEN** (poin 2) bersifat **KRITIS** dan harus **KETAT** diikuti.

        **PENGECEKAN AKHIR:** Sebelum finalisasi, periksa **DUA KALI** apakah naskah
        pas **SEMPURNA** dalam rentang 180-200 token. Batasan ini **TIDAK BISA DITAWAR**.

        **CRITICAL:** Balas HANYA dengan JSON murni. Jangan pakai ```markdown code block```, jangan ada teks sebelum/sesudah.
        """

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
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2048,
            )

        completion = _router_client.call_with_rotation(_call)
        response_text = completion.choices[0].message.content
        model_used = getattr(completion, 'model', 'unknown')
        
        if not response_text:
            print(f"   ⚠️ Model '{model_used}' return empty, retry...")
            completion = _router_client.call_with_rotation(
                lambda c, m: c.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that outputs ONLY valid JSON. No markdown, no explanation, no code fences."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
            )
            response_text = completion.choices[0].message.content
            model_used = getattr(completion, 'model', model_used)
        
        if not response_text:
            raise RuntimeError(
                f"Model '{model_used}' does not support script generation prompt. "
                f"Please retry (model may change) or update your 9Router combo."
            )
        
        response = _extract_json_from_text(response_text)

        if not all(key in response for key in ["script", "scenes", "total_duration"]):
            raise ValueError("Invalid JSON structure from API response")

        return response

    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse API response as JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Script generation failed: {str(e)}")

def _extract_json_from_text(text: str) -> dict:
    """
    Robustly extract the outermost JSON object from text.
    Strips BOM/invisible characters first, then only tries the first (outermost)
    JSON object. Returns clean dict or raises ValueError.
    """
    import re

    # Step 1: Strip whitespace, BOM, zero-width chars, and other non-printable
    text = text.strip()
    text = text.lstrip('\ufeff\u200b\u200c\u200d\ufffe\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f')

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


def save_script(script_data: dict, output_path: str) -> None:
    """Save the script as a JSON file"""
    with open(output_path, "w") as f:
        json.dump(script_data, f, indent=2)
    print(f"✅ Script saved to: {output_path}")

def main():
    try:
        topic = input("Masukkan premis cerita motivasi: ")
        style = input("Masukkan gaya penceritaan (mis. kisah_perjuangan, reflektif, membangkitkan_semangat): ")
        target_audience = input("Masukkan target penonton: ")
        cta = input("Masukkan pesan/hikmah penutup: ")
        output_path = "script.json"

        print("\n🚀 Generating storytelling script with Llama3...")
        script_data = generate_script(topic, style, target_audience, cta)

        save_script(script_data, output_path)

        print(f"📝 Total duration: {script_data['total_duration']} seconds")
        print(f"🎬 Number of scenes: {len(script_data['scenes'])}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main()