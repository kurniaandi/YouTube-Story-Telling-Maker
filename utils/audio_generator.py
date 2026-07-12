import json
import os
import requests
from pathlib import Path
from typing import Optional
import edge_tts
import asyncio
from gtts import gTTS

# Voice Bahasa Indonesia native untuk Edge TTS
EDGE_TTS_VOICE_MALE = "id-ID-ArdiNeural"
EDGE_TTS_VOICE_FEMALE = "id-ID-GadisNeural"
EDGE_TTS_VOICE_DEFAULT = EDGE_TTS_VOICE_MALE  # ganti ke FEMALE kalau mau suara wanita

def generate_audio_kokoro(text: str, output_path: Path, voice: str = "am_michael") -> bool:
    """
    Generate audio using Kokoro TTS API.
    Returns True if successful, False otherwise.
    """
    try:
        response = requests.post(
            "https://api.kokorotts.com/v1/audio/speech",
            json={
                "model": "kokoro", 
                "input": text,
                "voice": voice,
                "response_format": "mp3",
                "speed": 1.0
            },
            timeout=30  
        )

        # Validate the response BEFORE saving it as an mp3 file
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            print(f"⚠️ Kokoro TTS API error: status {response.status_code}, content-type {content_type}")
            print(f"⚠️ Response body: {response.text[:200]}")
            return False

        if "audio" not in content_type:
            print(f"⚠️ Kokoro TTS returned non-audio content: content-type {content_type}")
            print(f"⚠️ Response body: {response.text[:200]}")
            return False

        if len(response.content) < 1000:
            print(f"⚠️ Kokoro TTS response too small ({len(response.content)} bytes), likely an error page")
            print(f"⚠️ Response body: {response.text[:200]}")
            return False

        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✅ Audio generated using Kokoro TTS: {output_path}")
        # DEBUG: print file size and header to diagnose corrupt audio
        try:
            size = os.path.getsize(output_path)
            with open(output_path, "rb") as af:
                header = af.read(16)
            print(f"🔍 Audio file size (bytes): {size}")
            print(f"🔍 Audio file header (hex): {header.hex()}")
        except Exception as dbg_e:
            print(f"⚠️ Debug audio check failed: {type(dbg_e).__name__}: {dbg_e}")
        return True

    except Exception as e:
        print(f"⚠️ Kokoro TTS API failed: {type(e).__name__}: {e}")
        return False

async def generate_audio_edge(text: str, output_path: Path, voice: str = EDGE_TTS_VOICE_DEFAULT) -> bool:
    """
    Generate audio using Edge TTS as a fallback.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"🔊 Menggunakan voice: {voice} (Bahasa Indonesia)")
        communicate = edge_tts.Communicate(text, voice=voice)
        await communicate.save(output_path)
        print(f"✅ Audio generated using Edge TTS: {output_path}")
        # DEBUG: print file size and header to diagnose corrupt audio
        try:
            size = os.path.getsize(output_path)
            with open(output_path, "rb") as af:
                header = af.read(16)
            print(f"🔍 Audio file size (bytes): {size}")
            print(f"🔍 Audio file header (hex): {header.hex()}")
        except Exception as dbg_e:
            print(f"⚠️ Debug audio check failed: {type(dbg_e).__name__}: {dbg_e}")
        return True

    except Exception as e:
        print(f"⚠️ Edge TTS failed: {type(e).__name__}: {e}")
        return False

def generate_audio_gtts(text: str, save_path: Path, lang: str = "id") -> bool:
    """Fallback TTS menggunakan gTTS (Google Text-to-Speech)."""
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(save_path)
        if os.path.getsize(save_path) < 1000:
            print("⚠️ File audio gTTS terlalu kecil, kemungkinan gagal")
            return False
        print(f"✅ Audio berhasil dibuat dengan gTTS: {save_path}")
        return True
    except Exception as e:
        print(f"⚠️ gTTS gagal: {type(e).__name__}: {e}")
        return False


def generate_audio(text: str, output_path: Path, voice: str = "af_bella", edge_voice: str = EDGE_TTS_VOICE_DEFAULT) -> bool:
    """
    Generate audio using Kokoro TTS -> Edge TTS -> gTTS.
    edge_voice: voice yang dipakai khusus untuk Edge TTS (override).
    Returns True if successful, False otherwise.
    """
    for attempt in range(2):
        if generate_audio_kokoro(text, output_path, voice):
            return True
        print(f"Retrying Kokoro TTS... (Attempt {attempt + 1}/2)")

    print("⚠️ Kokoro TTS unavailable. Falling back to Edge TTS...")
    if asyncio.run(generate_audio_edge(text, output_path, voice=edge_voice)):
        return True

    print("⚠️ Edge TTS gagal. Falling back to gTTS...")
    if generate_audio_gtts(text, output_path, lang="id"):
        return True

    return False

def main(script_path: Path, output_dir: Path, voice_override: str | None = None, enable_background_music: bool = True) -> None:
    """
    Generate audio from script and save it to the output directory.
    Optionally mix with background music if enabled.
    
    Args:
        script_path: Path to script.json
        output_dir: Directory to save audio output
        voice_override: Override voice for Edge TTS (None = use default)
        enable_background_music: Whether to add background music with ducking (default: True)
    """
    try:
        with open(script_path, "r") as f:
            script_data = json.load(f)
        
        script_text = script_data.get("script", "")
        if not script_text:
            raise ValueError("Script text is empty")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate narasi/voiceover TTS
        audio_path_narration = output_dir / "voiceover_narration_only.mp3"
        
        # voice_override: kalau diisi, pakai voice itu untuk Edge TTS.
        # Kokoro tetap pakai default-nya; Edge TTS akan pakai override.
        if not generate_audio(script_text, audio_path_narration, edge_voice=voice_override or EDGE_TTS_VOICE_DEFAULT):
            raise RuntimeError("Failed to generate audio using both Kokoro and Edge TTS")

        print(f"✅ Narration audio saved to: {audio_path_narration}")
        
        # Mix dengan background music jika enabled
        audio_path_final = output_dir / "voiceover.mp3"
        
        if enable_background_music:
            print("\n🎵 Mixing dengan background music + auto-ducking...")
            from utils.music_mixer import mix_audio_with_ducking
            
            success = mix_audio_with_ducking(
                narration_path=audio_path_narration,
                output_path=audio_path_final,
                music_path=None,  # Auto-select random dari folder
                music_volume=0.15,  # 15% volume saat tidak ada narasi
                ducking_volume=0.05,  # 5% volume saat ada narasi
            )
            
            if not success:
                print("⚠️ Background music mixing gagal/tidak tersedia, gunakan narasi saja")
                # Copy narration-only ke final path
                import shutil
                shutil.copy(audio_path_narration, audio_path_final)
        else:
            print("ℹ️ Background music disabled, gunakan narasi saja")
            # Copy narration-only ke final path
            import shutil
            shutil.copy(audio_path_narration, audio_path_final)
        
        print(f"✅ Final audio saved to: {audio_path_final}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")