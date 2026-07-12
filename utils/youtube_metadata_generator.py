import json
from utils.groq_key_rotator import MultiProviderKeyRotator

_router_client = MultiProviderKeyRotator()


def generate_youtube_metadata(script_data: dict, story_title: str = "", moral: str = "") -> dict:
    """
    Generate metadata YouTube Shorts (title, description, tags) dari naskah
    cerita motivasi. Ini terpisah dari naskah TTS karena judul/deskripsi
    video punya kebutuhan berbeda (SEO, panjang, gaya bahasa) dibanding
    naskah yang dinarasikan.

    Return dict: {"title": str, "description": str, "tags": [str, ...]}
    Fallback ke nilai sederhana kalau AI gagal, supaya upload tidak
    pernah gagal hanya karena metadata generation error.
    """
    script_text = script_data.get("script", "")

    prompt = f"""
    Kamu adalah spesialis SEO & copywriting untuk YouTube Shorts kategori
    motivasi/storytelling berbahasa Indonesia. Berdasarkan naskah cerita
    berikut, buatkan metadata video dalam format JSON PERSIS seperti ini:

    {{
      "title": "judul singkat maksimal 90 karakter, menarik untuk di-klik, jujur mewakili isi cerita, boleh pakai 1 emoji relevan",
      "description": "deskripsi 2-4 kalimat yang merangkum cerita dan mengajak penonton merenung/berkomentar, diakhiri 5-8 hashtag relevan",
      "tags": ["list", "10-15", "kata kunci relevan", "tanpa tanda pagar", "bahasa indonesia dan inggris campuran secukupnya"]
    }}

    NASKAH CERITA:
    {script_text}

    Balas HANYA dengan JSON di atas, tanpa markdown, tanpa penjelasan lain.
    """

    try:
        def _call(client, model_name):
            return client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600,
                response_format={"type": "json_object"},
            )

        completion = _router_client.call_with_rotation(_call)
        response_text = completion.choices[0].message.content
        
        # Handle markdown code block dari beberapa model (Claude, dll)
        import re
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            match = re.search(r'```(?:json)?\s*\n(.*?)\n```', cleaned_text, re.DOTALL)
            if match:
                cleaned_text = match.group(1)
        
        data = json.loads(cleaned_text)

        title = str(data.get("title", "")).strip()[:100]
        description = str(data.get("description", "")).strip()
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip() for t in tags if str(t).strip()][:15]

        if title and description:
            return {"title": title, "description": description, "tags": tags}

    except Exception as e:
        print(f"⚠️ Gagal generate metadata YouTube via AI, pakai fallback: {e}")

    # Fallback minimal supaya pipeline tetap jalan
    fallback_title = (story_title or "Kisah yang Mengubah Segalanya")[:100]
    fallback_description = (
        f"{moral or 'Sebuah cerita motivasi yang menginspirasi.'}\n\n"
        "#motivasi #ceritamotivasi #katakatabijak #shorts"
    )
    return {
        "title": fallback_title,
        "description": fallback_description,
        "tags": ["motivasi", "cerita motivasi", "kata kata bijak", "shorts"],
    }