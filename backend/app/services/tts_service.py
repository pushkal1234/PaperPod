import os
import uuid
import asyncio
import re

import edge_tts
from pydub import AudioSegment

from app.config import settings


def parse_dialogue(script: str) -> list[dict]:
    """Parse dialogue script into list of {speaker, text} dicts."""
    lines = script.strip().split("\n")
    dialogue = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(Host|Guest):\s*(.+)", line, re.IGNORECASE)
        if match:
            speaker = match.group(1).capitalize()
            text = match.group(2).strip()
            if text:
                dialogue.append({"speaker": speaker, "text": text})
    return dialogue


async def synthesize_speech(text: str, voice: str, output_path: str):
    """Generate speech audio using edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


async def generate_podcast_audio(script: str, doc_id: str) -> tuple[str, float]:
    """Convert dialogue script to a single podcast MP3 file.
    
    Returns (file_path, duration_seconds).
    """
    dialogue = parse_dialogue(script)
    if not dialogue:
        raise ValueError("Could not parse dialogue from script")

    temp_dir = os.path.join(settings.AUDIO_DIR, f"temp_{doc_id}")
    os.makedirs(temp_dir, exist_ok=True)

    clip_paths = []
    for i, entry in enumerate(dialogue):
        voice = (
            settings.TTS_VOICE_HOST
            if entry["speaker"] == "Host"
            else settings.TTS_VOICE_GUEST
        )
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp3")
        await synthesize_speech(entry["text"], voice, clip_path)
        clip_paths.append(clip_path)

    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)

    for clip_path in clip_paths:
        try:
            segment = AudioSegment.from_mp3(clip_path)
            combined += segment + pause
        except Exception:
            continue

    output_filename = f"{doc_id}_podcast.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    combined.export(output_path, format="mp3")

    duration = len(combined) / 1000.0

    for clip_path in clip_paths:
        try:
            os.remove(clip_path)
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    return output_path, duration


async def synthesize_answer(text: str, doc_id: str, qa_id: str) -> str:
    """Synthesize a Q&A answer to MP3. Returns file path."""
    output_filename = f"{doc_id}_qa_{qa_id}.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    await synthesize_speech(text, settings.TTS_VOICE_GUEST, output_path)
    return output_path
