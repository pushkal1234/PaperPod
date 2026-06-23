import { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward, Volume2, Share2, Check, Download } from 'lucide-react';

const PLAYBACK_RATES = [1, 1.25, 1.5, 1.75, 2];
const POSITION_KEY_PREFIX = 'paperpod:pos:';
const RATE_KEY = 'paperpod:rate';

function buildProportionalSegments(dialogueScript, duration) {
  const lines = dialogueScript
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && (l.toLowerCase().startsWith('host:') || l.toLowerCase().startsWith('guest:')));

  if (!lines.length || !duration) return [];

  const weights = lines.map((l) => Math.max(l.length, 1));
  const total = weights.reduce((a, b) => a + b, 0);
  let acc = 0;

  return lines.map((line, i) => {
    const start = (acc / total) * duration;
    acc += weights[i];
    const end = (acc / total) * duration;
    const isHost = line.toLowerCase().startsWith('host:');
    const text = line.replace(/^(host|guest):\s*/i, '').trim();
    return {
      speaker: isHost ? 'Host' : 'Guest',
      text,
      line,
      start_seconds: start,
      end_seconds: end,
    };
  });
}

export default function PodcastPlayer({ audioUrl, title, dialogueScript, transcriptSegments, fallbackDuration, onShare }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(() => {
    const saved = parseFloat(localStorage.getItem(RATE_KEY));
    return PLAYBACK_RATES.includes(saved) ? saved : 1;
  });
  const [showTranscript, setShowTranscript] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);

  const restoredRef = useRef(false);
  const positionKey = audioUrl ? `${POSITION_KEY_PREFIX}${audioUrl}` : null;

  // Mobile Safari/Chrome often report audio.duration as Infinity/NaN/0 for
  // streamed MP3. Fall back to the duration the backend computed so the end
  // time, seek bar, and progress always work on mobile.
  const effectiveDuration =
    Number.isFinite(duration) && duration > 0
      ? duration
      : Number.isFinite(fallbackDuration) && fallbackDuration > 0
      ? fallbackDuration
      : 0;

  const segments = useMemo(() => {
    if (transcriptSegments?.length) return transcriptSegments;
    if (dialogueScript && effectiveDuration > 0) {
      return buildProportionalSegments(dialogueScript, effectiveDuration);
    }
    return [];
  }, [transcriptSegments, dialogueScript, effectiveDuration]);

  const activeIndex = useMemo(() => {
    if (!segments.length) return -1;
    const idx = segments.findIndex(
      (s) => currentTime >= s.start_seconds && currentTime < s.end_seconds
    );
    if (idx >= 0) return idx;
    if (currentTime >= segments[segments.length - 1]?.end_seconds) {
      return segments.length - 1;
    }
    return -1;
  }, [segments, currentTime]);

  const fmt = (s) => {
    if (!Number.isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const savePosition = useCallback(
    (time) => {
      if (!positionKey || !Number.isFinite(time)) return;
      // Don't persist if essentially finished or at the very start.
      if (effectiveDuration && time >= effectiveDuration - 5) {
        localStorage.removeItem(positionKey);
      } else if (time > 3) {
        localStorage.setItem(positionKey, String(Math.floor(time)));
      }
    },
    [positionKey, effectiveDuration]
  );

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => {
      if (Number.isFinite(audio.currentTime)) setCurrentTime(audio.currentTime);
    };
    const onDuration = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setDuration(audio.duration);
      }
    };
    const onProgress = () => {
      if (audio.buffered.length) {
        setBuffered(audio.buffered.end(audio.buffered.length - 1));
      }
    };
    const onPlay = () => setIsPlaying(true);
    const onPause = () => {
      setIsPlaying(false);
      savePosition(audio.currentTime);
    };
    const onEnded = () => {
      setIsPlaying(false);
      if (positionKey) localStorage.removeItem(positionKey);
    };
    // Restore saved position ONLY once the real media is loaded and seekable.
    // Doing this against the backend's fallback duration before the element is
    // ready wedges streamed audio into a stuck "seeking" state.
    const onLoadedData = () => {
      if (restoredRef.current || !positionKey) return;
      restoredRef.current = true;
      const realDur = audio.duration;
      if (!Number.isFinite(realDur) || realDur <= 0) return;
      const saved = parseFloat(localStorage.getItem(positionKey));
      if (Number.isFinite(saved) && saved > 1 && saved < realDur - 5) {
        try {
          audio.currentTime = saved;
          setCurrentTime(saved);
        } catch {
          /* not seekable yet — skip restore */
        }
      }
    };

    // Mobile browsers may not have duration at loadedmetadata (returns Infinity
    // for streamed audio). Listen on multiple events to catch it reliably.
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onDuration);
    audio.addEventListener('durationchange', onDuration);
    audio.addEventListener('canplaythrough', onDuration);
    audio.addEventListener('progress', onProgress);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('loadeddata', onLoadedData);

    // If audio is already loaded (cached), grab duration immediately
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      setDuration(audio.duration);
    }

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onDuration);
      audio.removeEventListener('durationchange', onDuration);
      audio.removeEventListener('canplaythrough', onDuration);
      audio.removeEventListener('progress', onProgress);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('loadeddata', onLoadedData);
    };
  }, [audioUrl, positionKey, savePosition]);

  // Reset transient state when the source changes.
  useEffect(() => {
    restoredRef.current = false;
    setCurrentTime(0);
    setDuration(0);
    setBuffered(0);
  }, [audioUrl]);

  // Apply playback rate to the audio element and persist the choice.
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = playbackRate;
    localStorage.setItem(RATE_KEY, String(playbackRate));
  }, [playbackRate, audioUrl]);

  // Persist position periodically and on unmount.
  useEffect(() => {
    return () => {
      if (audioRef.current) savePosition(audioRef.current.currentTime);
    };
  }, [savePosition]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  }, []);

  // Upper bound for seeking: prefer the browser's real decoded duration (so we
  // never seek past the actually-seekable range), fall back to backend value.
  const seekableMax = () => {
    const audio = audioRef.current;
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) return audio.duration;
    return effectiveDuration;
  };

  const applySeek = (target) => {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(target)) return;
    const max = seekableMax();
    const clamped = Math.max(0, max ? Math.min(target, max - 0.25) : target);
    try {
      audio.currentTime = clamped;
      setCurrentTime(clamped);
    } catch {
      /* element not ready to seek yet */
    }
  };

  const seek = useCallback(
    (seconds) => {
      const audio = audioRef.current;
      if (!audio) return;
      applySeek(audio.currentTime + seconds);
    },
    [effectiveDuration]
  );

  const seekTo = (seconds) => {
    applySeek(seconds);
    const audio = audioRef.current;
    if (audio && audio.paused) audio.play().catch(() => {});
  };

  const handleScrub = (e) => {
    applySeek(parseFloat(e.target.value));
  };

  const cyclePlaybackRate = () => {
    const idx = PLAYBACK_RATES.indexOf(playbackRate);
    setPlaybackRate(PLAYBACK_RATES[(idx + 1) % PLAYBACK_RATES.length]);
  };

  // Media Session API: lock-screen / notification controls + metadata.
  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new window.MediaMetadata({
      title: title || 'PaperPod Podcast',
      artist: 'PaperPod',
      album: 'AI-generated podcast',
    });
    const handlers = [
      ['play', () => togglePlay()],
      ['pause', () => togglePlay()],
      ['seekbackward', () => seek(-15)],
      ['seekforward', () => seek(15)],
      ['seekto', (d) => { if (d.seekTime != null) seekTo(d.seekTime); }],
    ];
    handlers.forEach(([action, fn]) => {
      try { navigator.mediaSession.setActionHandler(action, fn); } catch { /* unsupported action */ }
    });
    return () => {
      handlers.forEach(([action]) => {
        try { navigator.mediaSession.setActionHandler(action, null); } catch { /* noop */ }
      });
    };
  }, [title, togglePlay, seek]);

  // Keep Media Session play/pause + position state in sync.
  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
    if (effectiveDuration && Number.isFinite(currentTime)) {
      try {
        navigator.mediaSession.setPositionState({
          duration: effectiveDuration,
          playbackRate,
          position: Math.min(currentTime, effectiveDuration),
        });
      } catch { /* setPositionState unsupported */ }
    }
  }, [isPlaying, currentTime, effectiveDuration, playbackRate]);

  return (
    <div className="bg-gradient-to-br from-zinc-900 to-zinc-800 rounded-2xl p-6 border border-zinc-700/50">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center animate-float">
          <Volume2 className="w-6 h-6 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-zinc-100 text-lg truncate">{title}</h3>
          <p className="text-sm text-zinc-500">AI-generated podcast</p>
        </div>
        {onShare && (
          <button
            onClick={async () => {
              const link = await onShare();
              if (link) {
                try {
                  await navigator.clipboard.writeText(link);
                  setShareCopied(true);
                  setTimeout(() => setShareCopied(false), 2000);
                } catch {
                  alert(`Share link:\n${link}`);
                }
              }
            }}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all border border-zinc-700"
            title="Copy share link"
          >
            {shareCopied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Share2 className="w-3.5 h-3.5" />
                <span>Share</span>
              </>
            )}
          </button>
        )}
        {audioUrl && (
          <a
            href={audioUrl}
            download={`${title.replace(/[^a-z0-9]/gi, '_')}_podcast.mp3`}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all border border-zinc-700"
            title="Download podcast audio"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Audio</span>
          </a>
        )}
        {dialogueScript && (
          <button
            onClick={() => {
              const blob = new Blob([dialogueScript], { type: 'text/plain' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${title.replace(/[^a-z0-9]/gi, '_')}_transcript.txt`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all border border-zinc-700"
            title="Download transcript"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Transcript</span>
          </button>
        )}
      </div>

      {(() => {
        const pct = effectiveDuration ? Math.min(100, (currentTime / effectiveDuration) * 100) : 0;
        const bufPct = effectiveDuration ? Math.min(100, (buffered / effectiveDuration) * 100) : 0;
        return (
          <div className="relative w-full h-5 mb-2 flex items-center group">
            {/* Track */}
            <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-2 bg-zinc-700 rounded-full overflow-hidden">
              {/* Buffered */}
              <div className="absolute inset-y-0 left-0 bg-zinc-600 rounded-full" style={{ width: `${bufPct}%` }} />
              {/* Played */}
              <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-brand-500 to-purple-500 rounded-full" style={{ width: `${pct}%` }} />
            </div>
            {/* Thumb */}
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-white rounded-full shadow-lg ring-2 ring-brand-500/40 pointer-events-none"
              style={{ left: `${pct}%` }}
            />
            {/* Native range for accessibility, keyboard, drag & touch */}
            <input
              type="range"
              min={0}
              max={effectiveDuration || 0}
              step="any"
              value={Math.min(currentTime, effectiveDuration || 0)}
              onChange={handleScrub}
              aria-label="Seek"
              disabled={!effectiveDuration}
              className="absolute inset-0 w-full h-full m-0 cursor-pointer appearance-none bg-transparent opacity-0"
            />
          </div>
        );
      })()}

      <div className="flex justify-between text-xs text-zinc-500 mb-4">
        <span>{fmt(currentTime)}</span>
        <span>{fmt(effectiveDuration)}</span>
      </div>

      <div className="flex items-center justify-center gap-6 relative">
        <button
          onClick={() => seek(-15)}
          aria-label="Rewind 15 seconds"
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipBack className="w-5 h-5" />
        </button>

        <button
          onClick={togglePlay}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          className="w-14 h-14 rounded-full bg-brand-600 hover:bg-brand-500 flex items-center justify-center text-white shadow-lg shadow-brand-600/30 hover:shadow-brand-500/40 transition-all active:scale-95"
        >
          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
        </button>

        <button
          onClick={() => seek(15)}
          aria-label="Forward 15 seconds"
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipForward className="w-5 h-5" />
        </button>

        <button
          onClick={cyclePlaybackRate}
          aria-label="Playback speed"
          title="Playback speed"
          className="sm:absolute sm:right-0 min-w-[3rem] px-2.5 py-1 rounded-lg text-xs font-semibold bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700 transition-all border border-zinc-700"
        >
          {playbackRate}x
        </button>
      </div>

      {dialogueScript && (
        <div className="mt-6">
          <button
            onClick={() => setShowTranscript(!showTranscript)}
            className="text-sm text-brand-400 hover:text-brand-300 transition-colors"
          >
            {showTranscript ? 'Hide' : 'Show'} Transcript
          </button>
          {showTranscript && (
            <div className="mt-3 max-h-64 overflow-y-auto bg-zinc-800/50 rounded-xl p-4 text-sm border border-zinc-700/50">
              {segments.length > 0 ? (
                <p className="text-xs text-zinc-500 mb-3">Click any line to jump in the audio</p>
              ) : null}
              <div className="space-y-2">
                {segments.length > 0
                  ? segments.map((seg, i) => {
                      const isHost = seg.speaker === 'Host';
                      const isActive = i === activeIndex;
                      return (
                        <button
                          key={`${seg.start_seconds}-${i}`}
                          type="button"
                          onClick={() => seekTo(seg.start_seconds)}
                          className={`w-full text-left rounded-lg px-3 py-2 transition-all border ${
                            isActive
                              ? 'bg-brand-500/15 border-brand-500/40 ring-1 ring-brand-500/30'
                              : 'border-transparent hover:bg-zinc-700/50 hover:border-zinc-600'
                          }`}
                        >
                          <span className="text-[10px] text-zinc-500 font-mono mr-2">
                            {fmt(seg.start_seconds)}
                          </span>
                          <span className={isHost ? 'text-brand-300 font-medium' : 'text-emerald-300 font-medium'}>
                            {seg.speaker}:
                          </span>{' '}
                          <span className="text-zinc-300">{seg.text}</span>
                        </button>
                      );
                    })
                  : dialogueScript
                      .split('\n')
                      .filter((l) => l.trim())
                      .map((line, i) => {
                        const isHost = line.toLowerCase().startsWith('host:');
                        return (
                          <p key={i} className={isHost ? 'text-brand-300' : 'text-emerald-300'}>
                            {line}
                          </p>
                        );
                      })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
