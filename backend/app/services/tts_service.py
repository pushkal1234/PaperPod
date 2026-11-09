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
    fallback_voice: str | None = None,
    limiter: "_AdaptiveLimiter | None" = None,
):
    """Generate speech audio with retry and brand-safe error wrapping.

    `rate` and `pitch` are edge-tts prosody controls (e.g. "+8%", "-2Hz") used
    to add energy/contrast and reduce the flat, monotone delivery.

    `allow_silence_fallback`: when True, a line with no speakable content (only
    punctuation/symbols) is rendered as a short silence instead of failing — this
    keeps one degenerate line from sinking an entire multi-minute podcast. Q&A
    (single-clip) callers leave it False so a bad answer surfaces as an error.

    `fallback_voice`: a safety-net voice (the English multilingual default) used
    only when the primary voice fails for a NON-throttle reason (e.g. a bad/removed
    native voice). The multilingual English voices can still read foreign text, so
    the podcast completes in English rather than failing outright. We never fall
    back on a rate-limit — the same service would throttle the fallback voice too.

    `limiter`: a podcast's _AdaptiveLimiter. Each request to Edge holds one of its
    slots only while in flight (the backoff sleep does not), so retries also obey
    a lowered cap, and every throttled attempt is reported to it. Q&A leaves it
    unset and caps its calls itself.
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

    async def _attempt(use_voice: str) -> tuple[str, Exception | None] | None:
        """Try one voice with retries. Returns None on success, else
        (kind, error) where kind is 'rate' (throttled) or 'service' (other)."""
        last_error = None
        for attempt in range(max_retries):
            try:
                communicator = edge_tts.Communicate(text, use_voice, rate=rate, pitch=pitch)
                if limiter is None:
                    await communicator.save(output_path)
                else:
                    async with limiter:
                        await communicator.save(output_path)
                return None
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if _is_tts_rate_limit(err_msg):
                    if limiter is not None:
                        limiter.on_throttle()
                    # Don't sleep after the final attempt — the loop is about to
                    # exit, so a trailing backoff is pure wasted wall-time.
                    if attempt < max_retries - 1:
                        # Exponential backoff + jitter: a burst of throttled clips
                        # must NOT retry in lockstep (thundering herd), which just
                        # re-trips the same throttle. Jitter spreads them out.
                        wait = min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0.0, 1.0)
                        tag = f"[{limiter.label}] " if limiter is not None and limiter.label else ""
                        logger.warning(f"{tag}[TTS] Retry {attempt + 1}/{max_retries} for clip after {wait:.1f}s: {err_msg[:80]}")
                        await asyncio.sleep(wait)
                else:
                    # Non-throttle (e.g. bad voice): retrying the same voice won't
                    # help, so stop here and let the caller try the fallback voice.
                    logger.error(f"[TTS] Voice {use_voice!r} error: {err_msg[:120]}")
                    return ("service", e)
        if last_error and _is_tts_rate_limit(str(last_error)):
            return ("rate", last_error)
        return ("service", last_error)

    result = await _attempt(voice)
    if result is None:
        return

    kind, err = result
    # English safety net: only for voice/content failures, never for throttling.
    if kind == "service" and fallback_voice and fallback_voice != voice:
        logger.warning(
            f"[TTS] Primary voice {voice!r} failed; falling back to English voice "
            f"{fallback_voice!r} so the podcast still completes"
        )
        result = await _attempt(fallback_voice)
        if result is None:
            return
        kind, err = result

    if kind == "rate":
        raise RuntimeError(TTS_RATE_LIMIT_MSG)
    raise RuntimeError(TTS_SERVICE_ERROR_MSG)


class _AdaptiveLimiter:
    """Concurrency cap for one podcast's edge-tts calls that backs off when Edge
    throttles ("No audio was received").

    A fixed cap kept all 8 workers firing while one clip backed off, so the
    throttle window never cleared and a clip could exhaust its retries. Halving on
    every throttle overreacted the other way: a single blip that recovered on its
    first retry cut a 25-clip podcast from 5 to 2 for good (~90s slower). So:

    - a throttle steps the cap down by ONE; one or two more within
      ``burst_seconds`` are the same blip and don't step it again;
    - ``storm_hits`` throttles inside that window, or a step-down within
      ``sustained_seconds`` of the previous one, mean real throttling, so the cap
      HALVES instead (a storm still backs off within a fraction of a second);
    - every ``recover_after`` consecutive successful clips raise it by one again,
      back up to ``maximum``. It never goes below ``minimum``.

    A slot is held per request to Edge, not per clip, so a clip sleeping in
    backoff frees its slot. Lowering the cap never interrupts requests already in
    flight; it only holds back new ones (first tries and retries alike).
    """

    def __init__(
        self, maximum: int, minimum: int = 2, recover_after: int = 3,
        burst_seconds: float = 3.0, sustained_seconds: float = 15.0, storm_hits: int = 3,
        label: str | None = None,
    ):
        # Shown in throttle/retry logs (the podcast's doc id), so overlapping
        # podcasts can be told apart in the logs.
        self.label = label
        self.maximum = maximum
        self.minimum = min(minimum, maximum)
        self.limit = maximum
        self.lowest = maximum
        self.throttles = 0
        self._recover_after = recover_after
        self._burst_seconds = burst_seconds
        self._sustained_seconds = sustained_seconds
        self._storm_hits = storm_hits
        self._last_drop: float | None = None
        self._burst_hits = 0
        self._streak = 0
        self._active = 0
        self._cond = asyncio.Condition()

    async def __aenter__(self):
        async with self._cond:
            await self._cond.wait_for(lambda: self._active < self.limit)
            self._active += 1

    async def __aexit__(self, *exc):
        async with self._cond:
            self._active -= 1
            self._cond.notify_all()

    def on_throttle(self) -> None:
        self.throttles += 1
        self._streak = 0
        now = time.monotonic()
        since_drop = None if self._last_drop is None else now - self._last_drop
        if since_drop is not None and since_drop < self._burst_seconds:
            self._burst_hits += 1
            if self._burst_hits < self._storm_hits:
                return  # same blip as the last step-down
            halve = True  # many throttles at once: a storm, not a blip
        else:
            halve = since_drop is not None and since_drop < self._sustained_seconds
        self._last_drop = now
        self._burst_hits = 0
        new_limit = max(self.minimum, self.limit // 2 if halve else self.limit - 1)
        if new_limit < self.limit:
            self.limit = new_limit
            self.lowest = min(self.lowest, new_limit)
            tag = f"[{self.label}] " if self.label else ""
            logger.warning(f"{tag}[TTS] Edge throttling — lowering podcast concurrency to {new_limit}")

    async def on_success(self) -> None:
        async with self._cond:
            self._streak += 1
            if self._streak >= self._recover_after and self.limit < self.maximum:
                self.limit += 1
                self._streak = 0
                self._cond.notify_all()


async def _synthesize_one(
    limiter: _AdaptiveLimiter,
    text: str,
    voice: str,
    clip_path: str,
    idx: int,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    fallback_voice: str | None = None,
):
    """Synthesize a single clip under the podcast's limiter. Propagates errors."""
    await synthesize_speech(
        text, voice, clip_path, rate=rate, pitch=pitch,
        allow_silence_fallback=True, fallback_voice=fallback_voice,
        limiter=limiter,
    )
    await limiter.on_success()


async def generate_podcast_audio(
    script: str, doc_id: str, host_voice: str | None = None, guest_voice: str | None = None
) -> tuple[str, float, list[dict]]:
    """Convert dialogue script to a single podcast MP3 file.

    TTS calls run in parallel (up to TTS_CONCURRENCY at once) for speed.
    Returns (file_path, duration_seconds, transcript_segments).
    Each segment: {speaker, text, start_seconds, end_seconds}.

    ``host_voice``/``guest_voice`` override the default English casting so a
    non-English script is read by native-accent voices (see app.languages). When
    omitted they fall back to the configured English voices.
    """
    host_voice = host_voice or settings.TTS_VOICE_HOST
    guest_voice = guest_voice or settings.TTS_VOICE_GUEST
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
    limiter = _AdaptiveLimiter(concurrency, label=doc_id)
    jobs = []
    clip_paths = []

    # English safety net per speaker: if a native voice fails for a non-throttle
    # reason, the clip is re-rendered with the multilingual English default (which
    # can still read foreign text) so the podcast always completes.
    for i, entry in enumerate(dialogue):
        is_host = entry["speaker"] == "Host"
        voice = host_voice if is_host else guest_voice
        fallback = settings.TTS_VOICE_HOST if is_host else settings.TTS_VOICE_GUEST
        rate = settings.TTS_RATE_HOST if is_host else settings.TTS_RATE_GUEST
        pitch = settings.TTS_PITCH_HOST if is_host else settings.TTS_PITCH_GUEST
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp3")
        clip_paths.append(clip_path)
        jobs.append((entry["text"], voice, clip_path, rate, pitch, fallback))

    logger.info(f"[{doc_id}] TTS: {len(jobs)} clips, concurrency={concurrency}")
    _t_synth = time.perf_counter()
    results = await asyncio.gather(
        *(
            _synthesize_one(limiter, text, voice, path, i, rate=rate, pitch=pitch, fallback_voice=fallback)
            for i, (text, voice, path, rate, pitch, fallback) in enumerate(jobs)
        ),
        return_exceptions=True,
    )
    failed = [i for i, r in enumerate(results) if isinstance(r, BaseException)]
    try:
        if failed:
            await _retry_throttled_clips(doc_id, jobs, results, failed, limiter)
    except BaseException:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
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
        f"[{doc_id}] TTS breakdown — synth={synth_secs:.2f}s ({len(jobs)} clips @ "
        f"concurrency={concurrency}, throttles={limiter.throttles}, lowest={limiter.lowest}, "
        f"second-pass={len(failed)}), merge={merge_secs:.2f}s"
    )

    return output_path, duration, transcript_segments


async def _retry_throttled_clips(
    doc_id: str, jobs: list[tuple], results: list, failed: list[int], limiter: _AdaptiveLimiter
):
    """Second pass for podcast clips that were still throttled after their own
    retries: wait for Edge's rate window to clear, then redo them under the
    podcast's limiter (which is at or near its floor after throttling and climbs
    back as clips succeed — one-at-a-time would take ~30 min if a long storm
    failed every clip).

    The clips that succeeded are kept, so one stubborn clip no longer throws away
    an entire episode (a 165-clip podcast once failed on a single clip). Any
    non-throttle failure is raised as before; so is a clip still throttled here.
    """
    for i in failed:
        err = results[i]
        if not (isinstance(err, RuntimeError) and str(err) == TTS_RATE_LIMIT_MSG):
            raise err
    wait = settings.TTS_PODCAST_RETRY_DELAY + random.uniform(0.0, 2.0)
    logger.warning(
        f"[{doc_id}] TTS: {len(failed)}/{len(jobs)} clips still throttled; "
        f"retrying them in {wait:.1f}s at concurrency {limiter.limit}"
    )
    await asyncio.sleep(wait)
    retried = await asyncio.gather(
        *(
            _synthesize_one(limiter, *jobs[i][:3], i, rate=jobs[i][3], pitch=jobs[i][4], fallback_voice=jobs[i][5])
            for i in failed
        ),
        return_exceptions=True,
    )
    for err in retried:
        if isinstance(err, BaseException):
            raise err
    logger.info(f"[{doc_id}] TTS: second pass recovered {len(failed)} clip(s)")


_PAUSE_MS = 400
# Clip-length probes (ffprobe processes) run this many at a time during a merge.
_PROBE_WORKERS = 8


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
    #    (exact for edge-tts CBR MP3) instead of decoding it to PCM. Each probe
    #    is a separate ffprobe process, so they run _PROBE_WORKERS at a time
    #    (one after another cost ~12s of a 279-clip merge). Same probe per clip,
    #    results kept in clip order, so the timings are identical.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, min(_PROBE_WORKERS, len(clip_paths)))) as pool:
        clip_durations_ms = list(pool.map(_probe_duration_ms, clip_paths))
    transcript_segments: list[dict] = []
    cursor_ms = 0
    for i, clip_path in enumerate(clip_paths):
        clip_ms = clip_durations_ms[i]
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


# One edge-tts call streams audio back at roughly real-time speed, so a long
# answer voiced in a single call is slow (a 3.9K-char answer took ~190s). Long
# answers are split at sentence boundaries and the pieces synthesized in parallel,
# then stitched like podcast clips.
_ANSWER_CHUNK_CHARS = 500
_SENTENCE_BREAK = re.compile(r"(?<=[.!?؟।])\s+|(?<=[。！？])|\n+")


def _split_answer_for_tts(text: str, max_chars: int = _ANSWER_CHUNK_CHARS) -> list[str]:
    """Group sentences into chunks of at most ~max_chars (a single longer
    sentence stays whole)."""
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_BREAK.split(text.strip()):
        sentence = (sentence or "").strip()
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks


async def synthesize_answer(text: str, doc_id: str, qa_id: str, voice: str | None = None) -> str:
    """Synthesize a Q&A answer to MP3. Returns file path.

    ``voice`` selects a native-accent voice for a non-English answer; the English
    multilingual default is the safety net if that voice fails.
    """
    voice = voice or settings.TTS_VOICE_GUEST
    output_filename = f"{doc_id}_qa_{qa_id}.mp3"
    output_path = os.path.join(settings.AUDIO_DIR, output_filename)

    chunks = _split_answer_for_tts(text)
    if len(chunks) <= 1:
        await _voice_answer_clips([(text, output_path)], voice, allow_silence=False, doc_id=doc_id)
        return output_path

    temp_dir = os.path.join(settings.AUDIO_DIR, f"temp_qa_{qa_id}")
    os.makedirs(temp_dir, exist_ok=True)
    clip_paths = [os.path.join(temp_dir, f"clip_{i:04d}.mp3") for i in range(len(chunks))]
    try:
        await _voice_answer_clips(list(zip(chunks, clip_paths)), voice, allow_silence=True, doc_id=doc_id)
    except Exception:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    # Reuses the podcast merge (ffmpeg concat + cleanup); the transcript it
    # builds is not needed for an answer.
    dialogue = [{"speaker": "Guest", "text": chunk} for chunk in chunks]
    await run_in_threadpool(_merge_clips_to_mp3, clip_paths, dialogue, output_path, temp_dir)
    logger.info(f"[QA][{doc_id}] TTS: {len(chunks)} chunks (shared cap={settings.TTS_QA_CONCURRENCY}), voice={voice}")
    return output_path


# One semaphore for ALL answer audio in this process (created on first use so it
# binds to the server's event loop), capping total Q&A edge-tts calls at
# TTS_QA_CONCURRENCY however many answers are being voiced at once.
_qa_tts_sem: asyncio.Semaphore | None = None


def _get_qa_tts_sem() -> asyncio.Semaphore:
    global _qa_tts_sem
    if _qa_tts_sem is None:
        _qa_tts_sem = asyncio.Semaphore(settings.TTS_QA_CONCURRENCY)
    return _qa_tts_sem


async def _voice_clip(text: str, voice: str, path: str, allow_silence: bool):
    async with _get_qa_tts_sem():
        await synthesize_speech(
            text, voice, path, allow_silence_fallback=allow_silence,
            fallback_voice=settings.TTS_VOICE_GUEST,
        )


async def _voice_answer_clips(
    clips: list[tuple[str, str]], voice: str, allow_silence: bool, doc_id: str
):
    """Voice (text, path) clips in parallel under the shared Q&A cap.

    Each clip already gets synthesize_speech's own retries. Clips that still end
    throttled get ONE more pass after a cooldown, one at a time, so a short
    edge-tts rate window costs a few seconds instead of the whole answer's audio
    (the clips that succeeded are kept). Any other failure is raised as-is.
    """
    results = await asyncio.gather(
        *(_voice_clip(text, voice, path, allow_silence) for text, path in clips),
        return_exceptions=True,
    )
    failed = [(clip, r) for clip, r in zip(clips, results) if isinstance(r, BaseException)]
    if not failed:
        return
    for _, err in failed:
        if not (isinstance(err, RuntimeError) and str(err) == TTS_RATE_LIMIT_MSG):
            raise err

    wait = settings.TTS_QA_RETRY_DELAY + random.uniform(0.0, 2.0)
    logger.warning(
        f"[QA][{doc_id}] TTS: {len(failed)}/{len(clips)} clips throttled; "
        f"retrying them one at a time in {wait:.1f}s"
    )
    await asyncio.sleep(wait)
    for (text, path), _ in failed:
        await _voice_clip(text, voice, path, allow_silence)
