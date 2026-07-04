import { useState, useEffect, useCallback } from 'react';
import { Play, X, Film } from 'lucide-react';

// Curated homepage videos. `note` shows a tasteful "earlier design" label on the
// clips that were recorded on the previous (neon) UI, so visitors aren't thrown
// by the visual mismatch. The founder intro is evergreen — no note.
const VIDEOS = [
  {
    id: 'G0jdx3Y9ZQE',
    kind: 'Founder intro',
    title: 'Meet the founder',
    blurb: 'The story, the why, and where PaperPod is headed — straight from the person building it.',
    note: null,
    featured: true,
  },
  {
    id: '3UU8Ikde_2M',
    kind: 'Product demo',
    title: 'See it in action',
    blurb: 'Watch a document become a natural, two-voice podcast conversation in a couple of minutes.',
    note: 'Recorded on an earlier design',
    featured: false,
  },
  {
    id: 'KqSpaN2U7qM',
    kind: 'Deep dive',
    title: 'Every feature, explained',
    blurb: 'A full walkthrough of use-cases — from research papers to reports, Q&A, and sharing.',
    note: 'Recorded on an earlier design',
    featured: false,
  },
];

function thumbUrl(id) {
  return `https://i.ytimg.com/vi/${id}/maxresdefault.jpg`;
}
function thumbFallback(id) {
  return `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
}

function Thumbnail({ video, onPlay, className = '' }) {
  return (
    <button
      type="button"
      onClick={() => onPlay(video)}
      className={`group relative block w-full overflow-hidden rounded-2xl bg-stone-900 focus:outline-none focus:ring-2 focus:ring-brand-300 ${className}`}
      aria-label={`Play video: ${video.title}`}
    >
      <div className="aspect-video w-full">
        <img
          src={thumbUrl(video.id)}
          onError={(e) => {
            if (e.currentTarget.src !== thumbFallback(video.id)) {
              e.currentTarget.src = thumbFallback(video.id);
            }
          }}
          alt={video.title}
          loading="lazy"
          className="h-full w-full object-cover opacity-90 transition duration-300 group-hover:scale-[1.03] group-hover:opacity-100"
        />
      </div>
      {/* Soft wash for a refined, non-generic look */}
      <div className="absolute inset-0 bg-gradient-to-t from-stone-950/60 via-stone-950/10 to-transparent" />

      {/* Play affordance */}
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white/95 shadow-soft ring-1 ring-white/60 backdrop-blur transition duration-300 group-hover:scale-110 group-hover:bg-white">
          <Play className="ml-0.5 h-4 w-4 fill-brand-600 text-brand-600" />
        </span>
      </div>

      {/* Kind + optional "earlier design" note */}
      <div className="absolute left-2.5 top-2.5 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-700 backdrop-blur">
          {video.kind}
        </span>
        {video.note && (
          <span className="rounded-full bg-stone-900/70 px-2 py-0.5 text-[10px] font-medium text-white/90 backdrop-blur">
            {video.note}
          </span>
        )}
      </div>
    </button>
  );
}

export default function VideoShowcase() {
  const [active, setActive] = useState(null);

  const close = useCallback(() => setActive(null), []);

  useEffect(() => {
    if (!active) return;
    const onKey = (e) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    // Prevent background scroll while the lightbox is open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [active, close]);

  const featured = VIDEOS.find((v) => v.featured);
  const rest = VIDEOS.filter((v) => !v.featured);

  return (
    <section className="mx-auto max-w-3xl pt-8">
      <div className="text-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-paper-300 bg-white/70 px-3 py-1 text-[11px] font-semibold text-stone-500">
          <Film className="h-3 w-3 text-accent-500" />
          Watch PaperPod
        </span>
        <h2 className="mt-3 font-display text-xl font-semibold text-stone-900">
          See it, straight from the source
        </h2>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-stone-500">
          A quick founder intro, a live product demo, and a deep dive into everything PaperPod can do.
        </p>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {/* Featured founder video spans two columns on large screens */}
        {featured && (
          <div className="lg:col-span-2">
            <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-paper-300 bg-white p-2.5 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:shadow-glow">
              <Thumbnail video={featured} onPlay={setActive} />
              <div className="px-1.5 pb-1 pt-3">
                <h3 className="font-display text-base font-semibold text-stone-900">{featured.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-stone-500">{featured.blurb}</p>
                <button
                  type="button"
                  onClick={() => setActive(featured)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-stone-800"
                >
                  <Play className="h-3.5 w-3.5 fill-white" />
                  Watch intro
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Two demo videos stacked in the remaining column */}
        <div className="grid gap-4 lg:col-span-1">
          {rest.map((video) => (
            <div
              key={video.id}
              className="flex flex-col overflow-hidden rounded-2xl border border-paper-300 bg-white p-2 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:shadow-glow"
            >
              <Thumbnail video={video} onPlay={setActive} />
              <div className="px-1.5 pb-0.5 pt-2">
                <h3 className="font-display text-sm font-semibold text-stone-900">{video.title}</h3>
                <p className="mt-0.5 text-xs leading-relaxed text-stone-500">{video.blurb}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Lightbox player */}
      {active && (
        <div
          className="fixed inset-0 z-[110] flex items-center justify-center bg-stone-950/70 p-4 backdrop-blur-sm"
          onClick={close}
          role="dialog"
          aria-modal="true"
          aria-label={active.title}
        >
          <div
            className="relative w-full max-w-4xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={close}
              className="absolute -top-11 right-0 flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-sm font-medium text-white/90 transition-colors hover:bg-white/20"
              aria-label="Close video"
            >
              <X className="h-4 w-4" />
              Close
            </button>
            <div className="aspect-video w-full overflow-hidden rounded-2xl bg-black shadow-glow ring-1 ring-white/10">
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${active.id}?autoplay=1&rel=0&modestbranding=1`}
                title={active.title}
                className="h-full w-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
