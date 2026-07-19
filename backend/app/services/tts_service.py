import os
import asyncio
import logging
import random
import re
import time

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
TTS_CONCURRENCY_SMALL = settings.TTS_CONCURRENCY_SMALL
TTS_SMALL_DOC_MAX_CLIPS = settings.TTS_SMALL_DOC_MAX_CLIPS
MAX_DIALOGUE_TURNS = settings.MAX_DIALOGUE_TURNS


def _is_tts_rate_limit(err_msg: str) -> bool:
    low = err_msg.lower()
    return any(k in low for k in ["no audio", "429", "rate", "quota", "too many requests", "limit exceeded"])


def _has_speakable_content(text: str) -> bool:
    """True if the text contains anything edge-tts can actually voice.

    edge-tts returns "No audio was received" for text with no letters/digits
    (e.g. a line that is only "...", "—", or stray symbols). That error is
    INDISTINGUISHABLE from a throttle by message alone, so we check the text
    up-front: retrying punctuation-only text just burns backoff cycles and then
    fails the whole podcast, whereas a real throttle has speakable text.

    Uses str.isalnum() (Unicode-aware) so non-Latin scripts (Devanagari, CJK,
    accented Latin, etc.) still count as speakable — an ASCII-only check would
    mis-flag legitimate foreign-language lines as silence.
    """
    return any(ch.isalnum() for ch in text)


def _write_silence_mp3(output_path: str, ms: int = 350):
    """Write a short silent MP3 matching edge-tts output params (24 kHz mono)."""
    AudioSegment.silent(duration=ms, frame_rate=24000).export(
        output_path, format="mp3", bitrate="48k"
    )


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
    allow_silence_fallback: bool = False,
):
    """Generate speech audio with retry and brand-safe error wrapping.

    `rate` and `pitch` are edge-tts prosody controls (e.g. "+8%", "-2Hz") used
    to add energy/contrast and reduce the flat, monotone delivery.

    `allow_silence_fallback`: when True, a line with no speakable content (only
    punctuation/symbols) is rendered as a short silence instead of failing — this
    keeps one degenerate line from sinking an entire multi-minute podcast. Q&A
    (single-clip) callers leave it False so a bad answer surfaces as an error.
    """
    # Non-speakable text (e.g. "...", "—") makes edge-tts return "No audio was
    # received" on EVERY attempt, so don't waste the throttle-backoff budget on
    # it — handle it deterministically up-front.
    if not _has_speakable_content(text):
        if allow_silence_fallback:
            logger.warning(f"[TTS] Non-speakable clip text ({text[:40]!r}); writing silence, not retrying")
            await run_in_threadpool(_write_silence_mp3, output_path)
            return
        raise RuntimeError(TTS_SERVICE_ERROR_MSG)

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
                # Don't sleep after the final attempt — the loop is about to exit
                # and raise, so a trailing backoff is pure wasted wall-time.
                if attempt < max_retries - 1:
                    # Exponential backoff + jitter: a burst of throttled clips must
                    # NOT all retry in lockstep (thundering herd), which just
                    # re-trips the same throttle. Jitter spreads them out.
                    wait = min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0.0, 1.0)
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
        await synthesize_speech(
            text, voice, clip_path, rate=rate, pitch=pitch, allow_silence_fallback=True
        )


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

    # Adaptive concurrency: small scripts produce short clips that finish almost
    # instantly and hit edge-tts in a tight burst — the case that trips "No audio
    # received" throttling. Cap parallelism lower for them (reliability > the few
    # seconds more parallelism would save on a tiny job); long episodes, whose
    # longer clips stagger naturally, keep the full TTS_CONCURRENCY for speed.
    concurrency = TTS_CONCURRENCY
    if len(dialogue) <= TTS_SMALL_DOC_MAX_CLIPS:
        concurrency = min(TTS_CONCURRENCY, TTS_CONCURRENCY_SMALL)
    sem = asyncio.Semaphore(concurrency)
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

    logger.info(f"[{doc_id}] TTS: {len(tasks)} clips, concurrency={concurrency}")
    _t_synth = time.perf_counter()
    await asyncio.gather(*tasks)
    synth_secs = time.perf_counter() - _t_synth

    output_filename = f"{doc_id}_podcast.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    # pydub/ffmpeg are synchronous C calls — run the decode/concat/export off
    # the event loop so we don't block the async server during the merge.
    _t_merge = time.perf_counter()
    duration, transcript_segments = await run_in_threadpool(
        _merge_clips_to_mp3, clip_paths, dialogue, output_path, temp_dir
    )
    merge_secs = time.perf_counter() - _t_merge

    # Split the TTS cost so logs show whether time is spent on the edge-tts
    # network fan-out (tune via TTS_CONCURRENCY) or the local ffmpeg/pydub merge
    # (a CPU/IO concern) — otherwise the two are indistinguishable in timing.
    logger.info(
        f"[{doc_id}] TTS breakdown — synth={synth_secs:.2f}s ({len(tasks)} clips @ "
        f"concurrency={concurrency}), merge={merge_secs:.2f}s"
    )

    return output_path, duration, transcript_segments


_PAUSE_MS = 400


def _probe_duration_ms(clip_path: str) -> int:
    """Return a clip's duration in ms, reading only metadata (no full decode).

    edge-tts emits CBR MP3 (24 kHz, 48 kbit, mono), so ffprobe's header-derived
    duration is EXACT — there's no drift risk to transcript timings. This avoids
    decoding every clip to PCM (the old path spawned an ffmpeg decode per clip
    and was a large share of merge time). Falls back to a full pydub decode if
    ffprobe is unavailable or returns nothing, so timings can never break.
    """
    try:
        from pydub.utils import mediainfo
        info = mediainfo(clip_path)
        dur = info.get("duration")
        if dur:
            ms = int(round(float(dur) * 1000))
            if ms > 0:
                return ms
    except Exception as e:
        logger.warning(f"[merge] ffprobe duration failed for {os.path.basename(clip_path)} ({e}); decoding")
    # Exact fallback: full decode.
    return len(AudioSegment.from_mp3(clip_path))


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
    # 1) Build transcript timings by probing each clip's duration from metadata
    #    (exact for edge-tts CBR MP3) instead of decoding it to PCM.
    transcript_segments: list[dict] = []
    cursor_ms = 0
    for i, clip_path in enumerate(clip_paths):
        clip_ms = _probe_duration_ms(clip_path)
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

    edge-tts clips are uniform (24 kHz mono MP3, 48 kbit), so a matching silence
    clip is generated once and interleaved via the concat demuxer, then re-encoded
    to a 64k CBR MP3 with a Xing header (-write_xing 1) so mobile browsers read
    the correct duration. 64k is transparent for 24 kHz mono speech and matches
    the ~48k source (128k merely upscaled it, bloating the file for no gain), so
    this halves output size and speeds up download. ffmpeg decodes incrementally,
    so RAM stays flat.
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
         "-c:a", "libmp3lame", "-b:a", "64k", "-write_xing", "1", output_path],
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
        bitrate="64k",
        parameters=["-write_xing", "1"],
    )
    return len(combined) / 1000.0


async def synthesize_answer(text: str, doc_id: str, qa_id: str) -> str:
    """Synthesize a Q&A answer to MP3. Returns file path."""
    output_filename = f"{doc_id}_qa_{qa_id}.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)
    await synthesize_speech(text, settings.TTS_VOICE_GUEST, output_path)
    return output_path
