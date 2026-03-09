import os
import re
import wave
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs


def _load_env() -> None:
    # Resolve .env relative to this file so execution cwd does not matter.
    env_path = Path(__file__).resolve().parents[4] / ".env"
    load_dotenv(env_path)


def _slugify_filename(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return slug.strip("_")


def generate_backchannels() -> None:
    _load_env()

    api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_TTS_KEY")
    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY (or ELEVENLABS_TTS_KEY) in environment")

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "13xVmcINNP7cvNio2oxh")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    backchannels = [
        "Mm-hm.",
        "Ja.",
        "Juist.",
        "Oke.",
        "Uh-huh.",
        "Ga verder.",
        "Zeker.",
        "Precies.",
        "Inderdaad.",
        "Ik snap het.",
    ]

    output_folder = Path(__file__).resolve().parent / "backchannel_audio_male"
    output_folder.mkdir(parents=True, exist_ok=True)

    client = ElevenLabs(api_key=api_key)

    print(
        f"Generating {len(backchannels)} files with ElevenLabs voice_id='{voice_id}', model_id='{model_id}'"
    )

    for text in backchannels:
        filename = f"{_slugify_filename(text)}.wav"
        file_path = output_folder / filename
        print(f"Generating: '{text}' -> {file_path}")

        try:
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id=model_id,
                text=text,
                output_format="pcm_16000",
            )

            pcm_data = bytearray()
            for chunk in audio_stream:
                if chunk:
                    pcm_data.extend(chunk)

            # ElevenLabs returns raw PCM for pcm_16000. Wrap it as mono 16-bit WAV.
            with wave.open(str(file_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(bytes(pcm_data))
        except Exception as exc:
            print(f"Error generating '{text}': {exc}")

    print("\nDone! All files generated.")


if __name__ == "__main__":
    generate_backchannels()