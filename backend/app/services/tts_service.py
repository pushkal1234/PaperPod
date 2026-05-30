import os
import asyncio
import logging
import re

import edge_tts
from pydub import AudioSegment

from app.config import settings

logger = logging.getLogger("paperpod")

# Max concurrent TTS calls
TTS_CONCURRENCY = 6
# Hard cap on dialogue turns to prevent runaway generation
MAX_DIALOGUE_TURNS = 30


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
    """Generate speech audio using edge-tts (free, no API key)."""
    communicator = edge_tts.Communicate(text, voice)
    await communicator.save(output_path)


async def _synthesize_one(sem: asyncio.Semaphore, text: str, voice: str, clip_path: str, idx: int):
    """Synthesize a single clip with concurrency limit."""
    async with sem:
        try:
            await synthesize_speech(text, voice, clip_path)
        except Exception as e:
            logger.warning(f"[TTS] Clip {idx} failed: {e}")


async def generate_podcast_audio(script: str, doc_id: str) -> tuple[str, float, list[dict]]:
    """Convert dialogue script to a single podcast MP3 file.

    TTS calls run in parallel (up to TTS_CONCURRENCY at once) for speed.
    Returns (file_path, duration_seconds, transcript_segments).
    Each segment: {speaker, text, start_seconds, end_seconds}.
    """
    dialogue = parse_dialogue(script)
    if not dialogue:
        raise ValueError("Could not parse dialogue from script")

    if len(dialogue) > MAX_DIALOGUE_TURNS:
        logger.warning(f"[{doc_id}] Capping dialogue from {len(dialogue)} to {MAX_DIALOGUE_TURNS} turns")
        dialogue = dialogue[:MAX_DIALOGUE_TURNS]

    logger.info(f"[{doc_id}] Generating audio for {len(dialogue)} dialogue turns")

    temp_dir = os.path.join(settings.AUDIO_DIR, f"temp_{doc_id}")
    os.makedirs(temp_dir, exist_ok=True)

    sem = asyncio.Semaphore(TTS_CONCURRENCY)
    tasks = []
    clip_paths = []

    for i, entry in enumerate(dialogue):
        voice = (
            settings.TTS_VOICE_HOST
            if entry["speaker"] == "Host"
            else settings.TTS_VOICE_GUEST
        )
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp3")
        clip_paths.append(clip_path)
        tasks.append(_synthesize_one(sem, entry["text"], voice, clip_path, i))

    logger.info(f"[{doc_id}] TTS: {len(tasks)} clips, concurrency={TTS_CONCURRENCY}")
    await asyncio.gather(*tasks)

    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)
    transcript_segments: list[dict] = []

    for i, clip_path in enumerate(clip_paths):
        try:
            segment = AudioSegment.from_mp3(clip_path)
            start_seconds = len(combined) / 1000.0
            combined += segment + pause
            end_seconds = start_seconds + len(segment) / 1000.0
            entry = dialogue[i]
            transcript_segments.append({
                "speaker": entry["speaker"],
                "text": entry["text"],
                "line": f"{entry['speaker']}: {entry['text']}",
                "start_seconds": round(start_seconds, 2),
                "end_seconds": round(end_seconds, 2),
            })
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

    return output_path, duration, transcript_segments


async def synthesize_answer(text: str, doc_id: str, qa_id: str) -> str:
    """Synthesize a Q&A answer to MP3. Returns file path."""
    output_filename = f"{doc_id}_qa_{qa_id}.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    await synthesize_speech(text, settings.TTS_VOICE_GUEST, output_path)
    return output_path
