import { useState, useRef, useEffect, useCallback } from 'react';
import { Play, Pause, Hand, Loader2, MessageCircle, Headphones, Sparkles } from 'lucide-react';

const SAMPLE_SRC = '/sample-podcast.mp3';

// Canned Q&A that demonstrates the "interrupt the show and ask" flow without a
// backend call. On-topic for the sample (Stanford CS229 ML notes).
const DEMO_QUESTION = 'Hold on — can you explain what gradient descent actually does?';
const DEMO_ANSWER =
  "Great question. Gradient descent nudges the model's parameters step by step in the " +
  "direction that reduces error the most — like walking downhill to find the lowest point " +
  "of a valley. The learning rate decides how big each step is: too big and you overshoot, " +
  "too small and it crawls.";

// A refined, tapered waveform: many thin bars shaped by layered sine waves so it
// reads as a real audio waveform (taller in the middle, gently fading at the ends).
const BAR_COUNT = 60;
const BARS = Array.from({ length: BAR_COUNT }, (_, i) => {
  const t = i / (BAR_COUNT - 1);
  const wave = 0.5 + 0.3 * Math.sin(t * Math.PI * 7) + 0.16 * Math.sin(t * Math.PI * 15 + 1.2);
  const taper = 0.45 + 0.55 * Math.sin(t * Math.PI); // fuller in the center
  return Math.max(0.18, Math.min(1, wave * taper));
});

function fmt(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function SampleEpisode({ onCreateClick }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  // Q&A interrupt demo: 'idle' | 'question' | 'thinking' | 'answer'
  const [qa, setQa] = useState('idle');
  const timers = useRef([]);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  useEffect(() => () => clearTimers(), []);

  const togglePlay = useCallback(() => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      a.play().then(() => setIsPlaying(true)).catch(() => {});
    } else {
      a.pause();
      setIsPlaying(false);
    }
  }, []);

  const seek = (e) => {
    const a = audioRef.current;
    if (!a || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    a.currentTime = frac * duration;
    setCurrent(a.currentTime);
  };

  // Start the interrupt demo: pause playback and reveal the scripted exchange.
  const raiseHand = () => {
    const a = audioRef.current;
    if (a && !a.paused) {
      a.pause();
      setIsPlaying(false);
    }
    clearTimers();
    setQa('question');
    timers.current.push(setTimeout(() => setQa('thinking'), 700));
    timers.current.push(setTimeout(() => setQa('answer'), 1900));
  };

  const resume = () => {
    clearTimers();
    setQa('idle');
    const a = audioRef.current;
    if (a) a.play().then(() => setIsPlaying(true)).catch(() => {});
  };

  const progress = duration ? (current / duration) * 100 : 0;

  return (
    <div className="pt-6 max-w-3xl mx-auto w-full">
      <div className="relative overflow-hidden rounded-3xl border border-paper-300 bg-gradient-to-br from-white to-paper-50 shadow-soft p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 mb-5">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-11 h-11 shrink-0 rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow">
              <Headphones className="w-5 h-5 text-white" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-stone-800 leading-tight truncate">
                Sample episode · Stanford CS229 (ML notes)
              </p>
              <p className="text-xs text-stone-400">A real PaperPod podcast — press play to listen</p>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-brand-700 bg-brand-50 border border-brand-200 px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
            Live demo
          </span>
        </div>

        {/* Player */}
        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            aria-label={isPlaying ? 'Pause sample' : 'Play sample'}
            className="w-14 h-14 shrink-0 rounded-full bg-brand-600 text-white flex items-center justify-center shadow-glow hover:bg-brand-700 hover:scale-105 active:scale-95 transition-all"
          >
            {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
          </button>

          <div className="flex-1 min-w-0">
            {/* Waveform — click anywhere to seek. Bars fill with brand color up
                to the playhead; only bars near the playhead subtly pulse. */}
            <div
              onClick={seek}
              role="slider"
              aria-label="Seek"
              aria-valuenow={Math.round(progress)}
              className="group relative flex items-center justify-between h-11 cursor-pointer"
            >
              {BARS.map((h, i) => {
                const headIndex = (progress / 100) * (BARS.length - 1);
                const played = i <= headIndex;
                const nearHead = isPlaying && Math.abs(i - headIndex) < 2.5;
                return (
                  <span
                    key={i}
                    className={`w-[3px] rounded-full origin-center transition-colors duration-200 ${
                      played
                        ? `bg-gradient-to-t from-brand-600 to-accent-400 ${nearHead ? 'animate-eq' : ''}`
                        : 'bg-brand-200/70'
                    }`}
                    style={{ height: `${h * 100}%`, animationDelay: `${(i % 8) * 0.07}s` }}
                  />
                );
              })}
            </div>
            <div className="flex justify-between text-xs text-stone-400 mt-2 tabular-nums">
              <span>{fmt(current)}</span>
              <span>{fmt(duration)}</span>
            </div>
          </div>
        </div>

        {/* Interrupt & ask */}
        <div className="mt-6 rounded-2xl border border-dashed border-brand-200 bg-brand-50/40 p-4">
          {qa === 'idle' ? (
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-2.5 flex-1">
                <div className="w-9 h-9 shrink-0 rounded-full bg-accent-100 text-accent-600 flex items-center justify-center">
                  <Hand className="w-4 h-4" />
                </div>
                <p className="text-sm text-stone-600 leading-snug">
                  <span className="font-semibold text-stone-800">Interrupt the hosts anytime.</span>{' '}
                  Pause the show and ask the document a question — hear the answer in the same voices.
                </p>
              </div>
              <button
                onClick={raiseHand}
                className="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-full bg-accent-500 text-white text-sm font-semibold hover:bg-accent-600 shadow-soft hover:-translate-y-0.5 transition-all"
              >
                <Hand className="w-4 h-4" />
                Raise hand & ask
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {/* User question */}
              <div className="flex items-end gap-2.5 flex-row-reverse animate-fade-in">
                <div className="w-8 h-8 shrink-0 rounded-full bg-accent-100 text-accent-700 flex items-center justify-center text-xs font-bold">
                  You
                </div>
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed shadow-soft bg-accent-500 text-white">
                  {DEMO_QUESTION}
                </div>
              </div>

              {/* Thinking / answer */}
              {qa === 'thinking' && (
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 shrink-0 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center">
                    <MessageCircle className="w-4 h-4" />
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md px-4 py-2.5 text-sm bg-white border border-paper-300 text-stone-500 shadow-soft">
                    <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
                    Answering from the document…
                  </div>
                </div>
              )}

              {qa === 'answer' && (
                <>
                  <div className="flex items-end gap-2.5 animate-fade-in">
                    <div className="w-8 h-8 shrink-0 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-bold">
                      L
                    </div>
                    <div className="max-w-[85%] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm leading-relaxed shadow-soft bg-white border border-paper-300 text-stone-700">
                      {DEMO_ANSWER}
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3 pt-1">
                    <p className="text-xs text-stone-400">In the app, this answer is spoken aloud in the host's voice.</p>
                    <button
                      onClick={resume}
                      className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 shadow-soft transition-all"
                    >
                      <Play className="w-4 h-4" />
                      Resume episode
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* CTA */}
        <div className="mt-6 text-center">
          <button
            onClick={onCreateClick}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-glow hover:-translate-y-0.5 transition-all"
          >
            <Sparkles className="w-5 h-5" />
            Create yours — free
          </button>
        </div>

        <audio
          ref={audioRef}
          src={SAMPLE_SRC}
          preload="metadata"
          onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
          onEnded={() => { setIsPlaying(false); setCurrent(0); }}
          onPause={() => setIsPlaying(false)}
          onPlay={() => setIsPlaying(true)}
        />
      </div>
    </div>
  );
}
