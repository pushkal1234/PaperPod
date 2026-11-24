import { useState } from 'react';
import { Clock, X, ArrowRight } from 'lucide-react';
import { FOUNDING_ENDS_ON, FOUNDING_MONTHLY, REGULAR_MONTHLY, foundingEndsShort, foundingDaysLeft } from '../pricing';

// Dismissal lasts for the CURRENT VISIT only: sessionStorage survives refreshes
// in this tab but is gone on the next visit (new tab / reopened browser). It is
// also cleared on sign-in and sign-out (see resetFoundingBannerDismissal), so the
// offer shows again after every auth change. Keyed by the deadline.
const DISMISS_KEY = `pp_founding_banner_dismissed_${FOUNDING_ENDS_ON}`;

function readDismissed() {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

// Bring the banner back (called on sign-in / sign-out).
export function resetFoundingBannerDismissal() {
  try {
    sessionStorage.removeItem(DISMISS_KEY);
  } catch {
    /* storage blocked — nothing persisted anyway */
  }
}

// Slim announcement bar above the navbar for the founding-price deadline.
// Deliberately static (not a scrolling marquee): readable at a glance and no
// WCAG pause control needed. Hides itself once the deadline passes; a dismissal
// lasts until the next visit or auth change.
export default function FoundingBanner({ onCta, ctaLabel }) {
  const [dismissed, setDismissed] = useState(readDismissed);
  const endsOn = foundingEndsShort();
  const daysLeft = foundingDaysLeft();
  if (dismissed || !endsOn || daysLeft == null) return null;

  const countdown = daysLeft === 0 ? 'Last day' : `${daysLeft} day${daysLeft === 1 ? '' : 's'} left`;

  const dismiss = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      /* storage blocked — hidden for this page view only */
    }
  };

  return (
    <div
      role="region"
      aria-label="Founding member offer"
      className="bg-gradient-to-r from-brand-700 to-accent-700 text-white animate-fade-in"
    >
      <div className="max-w-6xl mx-auto px-3 sm:px-6 py-2 flex items-center gap-2 sm:gap-3 text-xs sm:text-sm">
        <span className="hidden sm:inline-flex items-center gap-1.5 shrink-0 rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-semibold">
          <Clock className="w-3.5 h-3.5" />
          {countdown}
        </span>
        <p className="flex-1 min-w-0 leading-snug">
          <span className="font-semibold">High demand:</span> Founding
          <span className="hidden sm:inline"> Member</span> price ({FOUNDING_MONTHLY}/mo
          <span className="hidden sm:inline">, locked in forever</span>) ends{' '}
          <span className="font-semibold">{endsOn}</span>
          <span className="hidden md:inline"> — then {REGULAR_MONTHLY}/mo for new members</span>.
        </p>
        <button
          type="button"
          onClick={onCta}
          className="shrink-0 inline-flex items-center gap-1 rounded-lg bg-white text-brand-800 px-2.5 sm:px-3 py-1 font-semibold hover:bg-white/90 transition"
        >
          {ctaLabel}
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss offer"
          className="shrink-0 p-1 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
