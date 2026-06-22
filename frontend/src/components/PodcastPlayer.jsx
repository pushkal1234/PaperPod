import { useRef, useState, useEffect, useMemo } from 'react';
import { Play, Pause, SkipBack, SkipForward, Volume2, Share2, Check, Download } from 'lucide-react';

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

export default function PodcastPlayer({ audioUrl, title, dialogueScript, transcriptSegments, onShare }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showTranscript, setShowTranscript] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);

  const segments = useMemo(() => {
    if (transcriptSegments?.length) return transcriptSegments;
    if (dialogueScript && duration > 0) {
      return buildProportionalSegments(dialogueScript, duration);
    }
    return [];
  }, [transcriptSegments, dialogueScript, duration]);

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
    const onEnded = () => setIsPlaying(false);

    // Mobile browsers may not have duration at loadedmetadata (returns Infinity
    // for streamed audio). Listen on multiple events to catch it reliably.
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onDuration);
    audio.addEventListener('durationchange', onDuration);
    audio.addEventListener('canplaythrough', onDuration);
    audio.addEventListener('ended', onEnded);

    // If audio is already loaded (cached), grab duration immediately
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      setDuration(audio.duration);
    }

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onDuration);
      audio.removeEventListener('durationchange', onDuration);
      audio.removeEventListener('canplaythrough', onDuration);
      audio.removeEventListener('ended', onEnded);
    };
  }, [audioUrl]);

  const togglePlay = () => {
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const seek = (seconds) => {
    audioRef.current.currentTime = Math.max(
      0,
      Math.min(audioRef.current.currentTime + seconds, duration)
    );
  };

  const seekTo = (seconds) => {
    if (!audioRef.current || !Number.isFinite(seconds)) return;
    audioRef.current.currentTime = Math.max(0, Math.min(seconds, duration || seconds));
    setCurrentTime(audioRef.current.currentTime);
    if (!isPlaying) {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const handleSeekBar = (e) => {
    if (!duration || !Number.isFinite(duration)) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    audioRef.current.currentTime = pct * duration;
  };

  const fmt = (s) => {
    if (!Number.isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

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

      <div
        className="w-full h-2 bg-zinc-700 rounded-full cursor-pointer mb-2 group"
        onClick={handleSeekBar}
        onTouchStart={handleSeekBar}
        onTouchMove={handleSeekBar}
      >
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-purple-500 rounded-full relative transition-all"
          style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
        >
          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>

      <div className="flex justify-between text-xs text-zinc-500 mb-4">
        <span>{fmt(currentTime)}</span>
        <span>{fmt(duration)}</span>
      </div>

      <div className="flex items-center justify-center gap-6">
        <button
          onClick={() => seek(-15)}
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipBack className="w-5 h-5" />
        </button>

        <button
          onClick={togglePlay}
          className="w-14 h-14 rounded-full bg-brand-600 hover:bg-brand-500 flex items-center justify-center text-white shadow-lg shadow-brand-600/30 hover:shadow-brand-500/40 transition-all active:scale-95"
        >
          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
        </button>

        <button
          onClick={() => seek(15)}
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipForward className="w-5 h-5" />
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
