import { useState, useEffect } from 'react';
import { X, LogOut, Star, Heart } from 'lucide-react';
import { submitFeedback } from '../api';

// Friendly line shown once the user picks a rating.
const RATING_MESSAGES = {
  1: "Oh no — we'll work hard to do better.",
  2: 'Thanks for the honesty — we’ll keep improving.',
  3: 'Good to know — thank you for the feedback!',
  4: 'So glad you’re enjoying it — thank you!',
  5: 'You’re amazing — thank you so much!',
};

export default function SignOutModal({ userName, onClose, onConfirm }) {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);

  // Close on Escape for a proper modal feel.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const firstName = (userName || '').trim().split(' ')[0];
  const active = hover || rating;

  const handleConfirm = () => {
    if (rating) {
      try {
        localStorage.setItem('paperpod_last_rating', String(rating));
      } catch {
        /* ignore storage errors (private mode etc.) */
      }
      // Fire BEFORE onConfirm() — logout clears the token, and we want the
      // request built while the auth header is still attached. Best-effort.
      submitFeedback({ rating, source: 'signout' }).catch(() => {});
    }
    onConfirm(rating);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-stone-900/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md bg-white rounded-3xl shadow-soft border border-paper-300 p-8"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="signout-title"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full text-stone-400 hover:text-stone-700 hover:bg-paper-100 transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-6">
          <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-brand-50 flex items-center justify-center">
            <Heart className="w-7 h-7 text-brand-600" />
          </div>
          <h2 id="signout-title" className="font-display text-2xl font-semibold text-stone-900">
            {firstName ? `Leaving so soon, ${firstName}?` : 'Leaving so soon?'}
          </h2>
          <p className="text-sm text-stone-500 mt-1.5">
            We’ll miss you — your podcasts will be right here waiting when you’re back.
          </p>
        </div>

        <div className="rounded-2xl border border-paper-300 bg-paper-50 p-5 mb-6">
          <p className="text-sm font-medium text-stone-700 text-center">
            How was your experience?
          </p>
          <div className="flex items-center justify-center gap-1.5 mt-3">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                type="button"
                onClick={() => setRating(star)}
                onMouseEnter={() => setHover(star)}
                onMouseLeave={() => setHover(0)}
                className="p-1 rounded-lg transition-transform hover:scale-110 focus:outline-none focus:ring-2 focus:ring-brand-200"
                aria-label={`Rate ${star} out of 5`}
              >
                <Star
                  className={`w-7 h-7 transition-colors ${
                    star <= active
                      ? 'fill-amber-400 text-amber-400'
                      : 'fill-transparent text-stone-300'
                  }`}
                  strokeWidth={1.75}
                />
              </button>
            ))}
          </div>
          <p className="text-xs text-center mt-2 h-4 text-brand-600 font-medium">
            {active ? RATING_MESSAGES[active] : ''}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-paper-300 bg-white text-stone-600 font-semibold hover:bg-paper-100 transition-colors"
          >
            Stay signed in
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex-1 inline-flex items-center justify-center gap-2 py-2.5 rounded-xl bg-stone-900 text-white font-semibold hover:bg-stone-800 shadow-soft transition-colors"
          >
            <LogOut className="w-4 h-4 -scale-x-100" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
