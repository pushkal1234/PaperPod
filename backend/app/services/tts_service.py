import os
import asyncio
import logging
import re

import edge_tts
from fastapi.concurrency import run_in_threadpool
from pydub import AudioSegment

from app.config import settings

logger = logging.getLogger("paperpod")

TTS_RATE_LIMIT_MSG = "You've reached PaperPod's free-tier rate limit. Please try again in a few moments."
TTS_SERVICE_ERROR_MSG = "PaperPod's voice engine is temporarily busy. Please try again shortly."
TTS_CONFIG_MSG = "Text-to-speech is not configured on this server. Please contact support."

# Sourced from settings so they're tunable per-environment without a redeploy.
# TTS_CONCURRENCY: parallel edge-tts calls (speed vs throttle-risk tradeoff).
# MAX_DIALOGUE_TURNS: runaway safety cap only — set >= the LLM's largest possible
# script so legitimate long podcasts are never truncated at the TTS step.
TTS_CONCURRENCY = settings.TTS_CONCURRENCY
MAX_DIALOGUE_TURNS = settings.MAX_DIALOGUE_TURNS


def _is_tts_rate_limit(err_msg: str) -> bool:
    low = err_msg.lower()
    return any(k in low for k in ["no audio", "429", "rate", "quota", "too many requests", "limit exceeded"])


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


async def synthesize_speech(
    text: str,
    voice: str,
    output_path: str,
    max_retries: int = 3,
    rate: str = "+0%",
    pitch: str = "+0Hz",
):
    """Generate speech audio with retry and brand-safe error wrapping.

    `rate` and `pitch` are edge-tts prosody controls (e.g. "+8%", "-2Hz") used
    to add energy/contrast and reduce the flat, monotone delivery.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            communicator = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicator.save(output_path)
            return
        except Exception as e:
            last_error = e
            err_msg = str(e)
            if _is_tts_rate_limit(err_msg):
                wait = 1.5 * (attempt + 1)
                logger.warning(f"[TTS] Retry {attempt + 1}/{max_retries} for clip after {wait:.1f}s: {err_msg[:80]}")
                await asyncio.sleep(wait)
            else:
                logger.error(f"[TTS] Unrecoverable error: {err_msg[:120]}")
                raise RuntimeError(TTS_SERVICE_ERROR_MSG)
    # All retries exhausted
    if last_error and _is_tts_rate_limit(str(last_error)):
        raise RuntimeError(TTS_RATE_LIMIT_MSG)
    raise RuntimeError(TTS_SERVICE_ERROR_MSG)


async def _synthesize_one(
    sem: asyncio.Semaphore,
    text: str,
    voice: str,
    clip_path: str,
    idx: int,
    rate: str = "+0%",
    pitch: str = "+0Hz",
):
    """Synthesize a single clip with concurrency limit. Propagates errors."""
    async with sem:
        await synthesize_speech(text, voice, clip_path, rate=rate, pitch=pitch)


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
        is_host = entry["speaker"] == "Host"
        voice = settings.TTS_VOICE_HOST if is_host else settings.TTS_VOICE_GUEST
        rate = settings.TTS_RATE_HOST if is_host else settings.TTS_RATE_GUEST
        pitch = settings.TTS_PITCH_HOST if is_host else settings.TTS_PITCH_GUEST
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp3")
        clip_paths.append(clip_path)
        tasks.append(_synthesize_one(sem, entry["text"], voice, clip_path, i, rate=rate, pitch=pitch))

    logger.info(f"[{doc_id}] TTS: {len(tasks)} clips, concurrency={TTS_CONCURRENCY}")
    await asyncio.gather(*tasks)

    output_filename = f"{doc_id}_podcast.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    # pydub/ffmpeg are synchronous C calls — run the decode/concat/export off
    # the event loop so we don't block the async server during the merge.
    duration, transcript_segments = await run_in_threadpool(
        _merge_clips_to_mp3, clip_paths, dialogue, output_path, temp_dir
    )

    return output_path, duration, transcript_segments


_PAUSE_MS = 400


def _merge_clips_to_mp3(
    clip_paths: list[str],
    dialogue: list[dict],
    output_path: str,
    temp_dir: str,
) -> tuple[float, list[dict]]:
    """Blocking: concatenate clips, export MP3, build transcript, clean up temp.

    Intended to be called via run_in_threadpool since pydub/ffmpeg block.

    Memory note: the whole podcast is NOT held in RAM. Clips are stitched
    file-to-file by ffmpeg (streaming), and durations are probed one clip at a
    time. This keeps peak memory at ~a single clip instead of the entire
    uncompressed episode (which previously pushed idle RSS very high).
    """
    # 1) Build transcript timings by decoding one clip at a time, freeing each
    #    immediately so only a single clip's PCM is ever resident.
    transcript_segments: list[dict] = []
    cursor_ms = 0
    for i, clip_path in enumerate(clip_paths):
        seg = AudioSegment.from_mp3(clip_path)
        clip_ms = len(seg)
        del seg  # release this clip's PCM before decoding the next
        start_seconds = cursor_ms / 1000.0
        end_seconds = start_seconds + clip_ms / 1000.0
        entry = dialogue[i]
        transcript_segments.append({
            "speaker": entry["speaker"],
            "text": entry["text"],
            "line": f"{entry['speaker']}: {entry['text']}",
            "start_seconds": round(start_seconds, 2),
            "end_seconds": round(end_seconds, 2),
        })
        cursor_ms += clip_ms + _PAUSE_MS
    duration = cursor_ms / 1000.0

    # 2) Concatenate. Prefer the low-memory ffmpeg path; fall back to the
    #    proven (higher-memory) pydub merge if anything goes wrong so audio
    #    generation can never break on this optimization.
    try:
        _concat_clips_ffmpeg(clip_paths, output_path, temp_dir)
    except Exception as ex:
        logger.warning(f"[merge] ffmpeg concat failed ({ex}); falling back to pydub merge")
        duration = _concat_clips_pydub(clip_paths, output_path)

    # 3) Clean up temp clips + dir.
    for clip_path in clip_paths:
        try:
            os.remove(clip_path)
        except OSError:
            pass
    for leftover in ("_silence.mp3", "_concat.txt"):
        try:
            os.remove(os.path.join(temp_dir, leftover))
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    return duration, transcript_segments


def _concat_clips_ffmpeg(clip_paths: list[str], output_path: str, temp_dir: str):
    """Stitch clips + inter-clip pauses into one MP3 using ffmpeg (streaming).

    edge-tts clips are uniform (24 kHz mono MP3), so a matching silence clip is
    generated once and interleaved via the concat demuxer, then re-encoded to a
    128k CBR MP3 with a Xing header (-write_xing 1) so mobile browsers read the
    correct duration. ffmpeg decodes incrementally, so RAM stays flat.
    """
    import subprocess

    # Use whatever ffmpeg pydub is configured to use (falls back to the literal
    # "ffmpeg", resolved via PATH at run time — same as pydub's own export).
    ffmpeg = AudioSegment.converter or "ffmpeg"

    # A silence clip matching edge-tts output params (24 kHz mono, 48k).
    silence_path = os.path.join(temp_dir, "_silence.mp3")
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", str(_PAUSE_MS / 1000.0), "-c:a", "libmp3lame", "-b:a", "48k", silence_path],
        check=True, capture_output=True,
    )

    # Concat list: clip, pause, clip, pause, ...
    list_path = os.path.join(temp_dir, "_concat.txt")
    with open(list_path, "w") as f:
        for clip_path in clip_paths:
            f.write(f"file '{os.path.abspath(clip_path)}'\n")
            f.write(f"file '{os.path.abspath(silence_path)}'\n")

    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "libmp3lame", "-b:a", "128k", "-write_xing", "1", output_path],
        check=True, capture_output=True,
    )


def _concat_clips_pydub(clip_paths: list[str], output_path: str) -> float:
    """Fallback: original in-memory pydub concatenation. Returns duration (s)."""
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=_PAUSE_MS)
    for clip_path in clip_paths:
        combined += AudioSegment.from_mp3(clip_path) + pause
    combined.export(
        output_path,
        format="mp3",
        bitrate="128k",
        parameters=["-write_xing", "1"],
    )
    return len(combined) / 1000.0


async def synthesize_answer(text: str, doc_id: str, qa_id: str) -> str:
    """Synthesize a Q&A answer to MP3. Returns file path."""
    output_filename = f"{doc_id}_qa_{qa_id}.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    await synthesize_speech(text, settings.TTS_VOICE_GUEST, output_path)
    return output_path
