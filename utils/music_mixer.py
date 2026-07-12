"""
Background Music Mixer with Auto-Ducking for YouTube Shorts
Automatically lower background music volume when narration is speaking
"""

import random
from pathlib import Path
from typing import Optional
from moviepy.editor import AudioFileClip, CompositeAudioClip
import numpy as np


def get_random_background_music(music_folder: Path = Path("assets/background_music")) -> Optional[Path]:
    """
    Pick a random background music file from the music folder.
    Supports: .mp3, .wav, .m4a, .aac
    
    Returns None if folder doesn't exist or is empty.
    """
    if not music_folder.exists():
        print(f"⚠️ Background music folder tidak ditemukan: {music_folder}")
        print("   Buat folder 'assets/background_music/' dan isi dengan file musik royalty-free")
        return None
    
    music_files = list(music_folder.glob("*.mp3")) + \
                  list(music_folder.glob("*.wav")) + \
                  list(music_folder.glob("*.m4a")) + \
                  list(music_folder.glob("*.aac"))
    
    if not music_files:
        print(f"⚠️ Tidak ada file musik di folder: {music_folder}")
        return None
    
    selected = random.choice(music_files)
    print(f"🎵 Background music terpilih: {selected.name}")
    return selected


def mix_audio_with_ducking(
    narration_path: Path,
    output_path: Path,
    music_path: Optional[Path] = None,
    music_volume: float = 0.15,  # 15% volume saat tidak ada narasi
    ducking_volume: float = 0.05,  # 5% volume saat ada narasi (ducking)
    fade_duration: float = 0.3,  # Durasi fade in/out untuk ducking (detik)
) -> bool:
    """
    Mix narration audio with background music + auto-ducking.
    
    Args:
        narration_path: Path to voiceover/narration audio
        output_path: Path to save mixed audio output
        music_path: Path to background music (None = random from folder)
        music_volume: Background music volume saat tidak ada narasi (0.0-1.0)
        ducking_volume: Background music volume saat ada narasi (0.0-1.0)
        fade_duration: Smooth transition duration untuk ducking effect
    
    Returns:
        True if successful, False if failed or no music available
    """
    try:
        # Load narration
        narration = AudioFileClip(str(narration_path))
        narration_duration = narration.duration
        
        # Get background music
        if music_path is None:
            music_path = get_random_background_music()
        
        if music_path is None:
            print("⚠️ Background music tidak tersedia, hanya gunakan narasi")
            # Save narration as-is
            narration.write_audiofile(str(output_path), codec="libmp3lame", bitrate="192k")
            narration.close()
            return False
        
        # Load background music
        music = AudioFileClip(str(music_path))
        
        # Loop music jika lebih pendek dari narasi
        if music.duration < narration_duration:
            loops_needed = int(np.ceil(narration_duration / music.duration))
            print(f"🔁 Looping background music {loops_needed}x untuk match durasi narasi")
            music_clips = [music] * loops_needed
            from moviepy.editor import concatenate_audioclips
            music = concatenate_audioclips(music_clips)
        
        # Trim music ke durasi narasi
        music = music.subclip(0, narration_duration)
        
        # Apply ducking effect
        print("🎚️  Applying auto-ducking (music volume turun saat narasi aktif)...")
        
        # Strategi sederhana: deteksi amplitude narasi untuk trigger ducking
        # Jika amplitude narasi > threshold, set music volume rendah (ducking)
        # Jika amplitude narasi rendah/silence, set music volume normal
        
        def apply_volume_envelope(get_frame, t):
            """Apply dynamic volume based on narration amplitude"""
            # Get narration frame at time t
            narration_frame = narration.get_frame(t)
            
            # Calculate RMS (root mean square) amplitude
            if len(narration_frame.shape) > 1:
                # Stereo: average channels
                amplitude = np.sqrt(np.mean(narration_frame ** 2))
            else:
                # Mono
                amplitude = np.sqrt(np.mean(narration_frame ** 2))
            
            # Threshold untuk deteksi narasi aktif
            # Normalize amplitude (typical range 0-0.1 untuk audio)
            threshold = 0.01  # Adjust based on testing
            
            if amplitude > threshold:
                # Narasi aktif -> ducking (volume rendah)
                target_volume = ducking_volume
            else:
                # Narasi tidak aktif -> volume normal
                target_volume = music_volume
            
            # Get music frame
            music_frame = get_frame(t)
            
            # Apply volume
            return music_frame * target_volume
        
        # Apply volume envelope to music
        music_ducked = music.fl(apply_volume_envelope, keep_duration=True)
        
        # Mix narration + ducked music
        print("🎼 Mixing narration + background music...")
        final_audio = CompositeAudioClip([narration, music_ducked])
        
        # Export mixed audio
        final_audio.write_audiofile(
            str(output_path),
            codec="libmp3lame",
            bitrate="192k",
            fps=44100
        )
        
        # Cleanup
        narration.close()
        music.close()
        music_ducked.close()
        final_audio.close()
        
        print(f"✅ Mixed audio dengan background music saved: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error mixing audio: {e}")
        # Fallback: save narration only
        try:
            narration = AudioFileClip(str(narration_path))
            narration.write_audiofile(str(output_path), codec="libmp3lame", bitrate="192k")
            narration.close()
        except Exception:
            pass
        return False


def main(narration_path: Path, output_path: Path, music_path: Optional[Path] = None):
    """
    CLI entry point for testing music mixing
    """
    print("🎵 Background Music Mixer with Auto-Ducking")
    print("=" * 60)
    
    success = mix_audio_with_ducking(narration_path, output_path, music_path)
    
    if success:
        print("\n✅ Audio mixing completed successfully")
    else:
        print("\n⚠️ Audio mixing skipped or failed (using narration only)")


if __name__ == "__main__":
    # Test dengan sample audio
    narration = Path("testing/audio/voiceover.mp3")
    output = Path("testing/audio/voiceover_with_music.mp3")
    
    if narration.exists():
        main(narration, output)
    else:
        print("❌ Sample audio not found. Run main pipeline first.")
