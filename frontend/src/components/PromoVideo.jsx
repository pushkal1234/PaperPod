import { useEffect, useRef, useState } from 'react';
import { Volume2, VolumeX, Play } from 'lucide-react';
import { track } from '../api';

// 21-second product promo, self-hosted from /public (≈0.9 MB, 720p).
// Plays muted and looped while on screen (browsers only allow muted autoplay)
// and pauses when scrolled away, so it costs nothing until it's seen. Visitors
// who prefer reduced motion get the poster and a play button instead.
const SRC = '/promo.mp4';
const POSTER = '/promo-poster.jpg';

export default function PromoVideo() {
  const videoRef = useRef(null);
  const [muted, setMuted] = useState(true);
  const [started, setStarted] = useState(false);
  const reduceMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || reduceMotion || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          video.play().then(() => setStarted(true)).catch(() => {});
        } else {
          video.pause();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(video);
    return () => io.disconnect();
  }, [reduceMotion]);

  const toggleSound = () => {
    const video = videoRef.current;
    if (!video) return;
    const next = !muted;
    video.muted = next;
    setMuted(next);
    if (!next) {
      // Sound on: start from the beginning so the promo is heard in full.
      video.currentTime = 0;
      video.play().then(() => setStarted(true)).catch(() => {});
      track('promo_sound_on');
    }
  };

  const playNow = () => {
    const video = videoRef.current;
    if (!video) return;
    video.play().then(() => setStarted(true)).catch(() => {});
  };

  return (
    // Same width and card style as the upload box above it (max-w-2xl,
    // rounded-2xl, paper border, soft shadow), so the two read as one column.
    <section className="mx-auto w-full max-w-2xl" aria-label="PaperPod in 20 seconds">
      <div className="relative overflow-hidden rounded-2xl border border-paper-300 bg-white shadow-soft">
        <video
          ref={videoRef}
          src={SRC}
          poster={POSTER}
          muted
          loop
          playsInline
          preload="none"
          className="block aspect-video w-full bg-paper-100 object-cover"
          aria-label="PaperPod promo: turn any document into a two-host podcast, then ask it anything"
        />
        {!started && reduceMotion && (
          <button
            type="button"
            onClick={playNow}
            className="absolute inset-0 m-auto flex h-14 w-14 items-center justify-center rounded-full bg-white/95 shadow-soft ring-1 ring-paper-300 hover:scale-105 transition"
            aria-label="Play the promo video"
          >
            <Play className="ml-0.5 h-5 w-5 fill-brand-600 text-brand-600" />
          </button>
        )}
        <button
          type="button"
          onClick={toggleSound}
          className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full bg-stone-900/80 px-3 py-1.5 text-xs font-semibold text-white backdrop-blur transition hover:bg-stone-900"
          aria-label={muted ? 'Turn sound on' : 'Turn sound off'}
        >
          {muted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          {muted ? 'Sound on' : 'Mute'}
        </button>
      </div>
    </section>
  );
}
