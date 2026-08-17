import { useState, useEffect } from 'react';
import { Headphones, FileText, Images, Wand2, AudioLines, Check, Loader2 } from 'lucide-react';

// Canonical backend pipeline order (matches the `stage` values the API reports)
// plus display metadata. `analyzing_figures` only occurs for PDFs that actually
// contain figures, so it's shown conditionally (see `sawFigures`).
const STAGE_ORDER = ['reading', 'analyzing_figures', 'writing_script', 'synthesizing'];
const STAGE_META = {
  reading: { label: 'Reading your document', icon: FileText },
  analyzing_figures: { label: 'Analyzing diagrams & figures', icon: Images },
  writing_script: { label: 'Writing the dialogue script', icon: Wand2 },
  synthesizing: { label: 'Synthesizing the audio', icon: AudioLines },
};

// Elapsed-seconds fallback, used only until the backend reports its first real
// stage (e.g. the opening moments, image OCR, or any legacy build) so the screen
// still feels alive. Maps an elapsed boundary to a canonical stage key.
const TIME_FALLBACK = [
  { until: 15, key: 'reading' },
  { until: 55, key: 'writing_script' },
  { until: Infinity, key: 'synthesizing' },
];

const EST_TOTAL_SECONDS = 90;

/**
 * Generation loading screen. Shows an approximate staged progress indicator and,
 * when a `videoUrl` is provided, plays a muted looping product demo behind it to
 * make the 1-2 minute wait engaging. Falls back to a branded animation when no
 * video asset is configured. The parent swaps to the player as soon as the job
 * is ready, so this view naturally "fades out" on completion and is skipped for
 * instant cache-hits.
 */
export default function ProcessingView({ elapsedSeconds = 0, stage = null, videoUrl = null }) {
  // If the video is missing/blocked/undecodable, fall back to the branded
  // animation instead of showing a broken black box.
  const [videoFailed, setVideoFailed] = useState(false);
  const showVideo = Boolean(videoUrl) && !videoFailed;

  // The figures step is optional (PDF-with-figures only). Once the backend
  // reports it we keep the row visible for the rest of the run; if it never
  // fires we never show it — so the checklist never claims work we didn't do.
  const [sawFigures, setSawFigures] = useState(false);
  useEffect(() => {
    if (stage === 'analyzing_figures') setSawFigures(true);
  }, [stage]);

  // Prefer the real backend stage; fall back to the time heuristic until it
  // arrives. Both resolve to a canonical STAGE_ORDER key.
  const currentKey = stage
    || (TIME_FALLBACK.find((s) => elapsedSeconds < s.until) || TIME_FALLBACK[TIME_FALLBACK.length - 1]).key;
  const currentIndex = STAGE_ORDER.indexOf(currentKey);

  // Hide the optional figures row unless it has actually occurred.
  const visibleStages = STAGE_ORDER.filter((k) => k !== 'analyzing_figures' || sawFigures);
  const pct = Math.min(95, Math.round((elapsedSeconds / EST_TOTAL_SECONDS) * 100));

  return (
    <div className="flex flex-col items-center justify-center py-16 md:py-20 text-center">
      {/* Ambient demo video (muted) OR branded animation */}
      <div className="relative mb-8 w-full max-w-xl">
        {showVideo ? (
          <video
            className="w-full rounded-3xl border border-paper-300 shadow-soft aspect-video object-cover"
            src={videoUrl}
            poster="/processing-poster.jpg"
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            disablePictureInPicture
            controls={false}
            onError={() => setVideoFailed(true)}
            aria-hidden="true"
          />
        ) : (
          <div className="mx-auto relative w-20 h-20">
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow">
              <Headphones className="w-10 h-10 text-white" />
            </div>
            <div className="absolute inset-0 w-20 h-20 rounded-full border-2 border-brand-400/40 animate-pulse-ring" />
          </div>
        )}
      </div>

      <h2 className="font-display text-3xl font-semibold text-stone-900 mb-2">Composing your podcast</h2>
      <p className="text-stone-500 max-w-md">
        This usually takes about a minute. Feel free to keep this tab open — we'll drop you
        straight into the player when it's ready.
      </p>

      {/* Progress bar */}
      <div className="w-full max-w-md mt-8" aria-hidden="true">
        <div className="h-2 rounded-full bg-paper-200 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-500 to-accent-500 transition-[width] duration-700 ease-out"
            style={{ width: `${Math.max(6, pct)}%` }}
          />
        </div>
      </div>

      {/* Stage checklist */}
      <ol className="w-full max-w-md mt-6 space-y-2.5 text-left" aria-label="Generation progress">
        {visibleStages.map((key) => {
          const meta = STAGE_META[key];
          const Icon = meta.icon;
          const canonicalIndex = STAGE_ORDER.indexOf(key);
          const done = canonicalIndex < currentIndex;
          const active = canonicalIndex === currentIndex;
          return (
            <li
              key={key}
              className={`flex items-center gap-3 rounded-2xl border px-4 py-3 transition-colors ${
                active
                  ? 'border-brand-200 bg-brand-50'
                  : done
                  ? 'border-paper-300 bg-white'
                  : 'border-paper-200 bg-white/60'
              }`}
            >
              <span
                className={`w-8 h-8 shrink-0 rounded-xl flex items-center justify-center ${
                  done
                    ? 'bg-emerald-50 text-emerald-600'
                    : active
                    ? 'bg-brand-100 text-brand-700'
                    : 'bg-paper-100 text-stone-400'
                }`}
              >
                {done ? (
                  <Check className="w-4 h-4" />
                ) : active ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </span>
              <span
                className={`text-sm font-medium ${
                  active ? 'text-brand-800' : done ? 'text-stone-600' : 'text-stone-400'
                }`}
              >
                {meta.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
