// Centralized pricing / positioning copy so the paywall, hero, and navbar never
// drift out of sync. IMPORTANT: these strings are DISPLAY-ONLY. The amount a
// customer is actually charged is set by the Dodo product behind
// DODO_PRODUCT_ID (backend env) — not here.
//
// Positioning: we anchor against the regular price ($9.99/mo) while charging an
// early-adopter "Founding Member" price ($5/mo). That reframes $5 as an
// exclusive deal ("you got in early"), not as a cheap product. When the founding
// window closes, either flip `FOUNDING` to false (to show $9.99 as the headline)
// AND point DODO_PRODUCT_ID at the $9.99 product so new signups are billed the
// regular price. Existing founders keep $5 via their original subscription.
export const REGULAR_MONTHLY = '$9.99';
export const FOUNDING_MONTHLY = '$5';

// Master switch for the founding-member presentation.
export const FOUNDING = true;

export const FOUNDING_LABEL = 'Founding Member';
export const FOUNDING_NOTE = 'Locked in forever — early-supporter price.';

// The price shown as the big headline number (what they pay today).
export const HEADLINE_MONTHLY = FOUNDING ? FOUNDING_MONTHLY : REGULAR_MONTHLY;

// Last day of the founding price, as 'YYYY-MM-DD', e.g. '2026-11-30'. When set
// (and not yet past), the My Podcasts upgrade card says "Founding price ends
// Nov 30". Leave null until there's a real date you'll keep: a deadline that
// keeps moving stops being believed. After it passes, the line hides itself.
export const FOUNDING_ENDS_ON = '2026-11-30';

// "Founding price ends Nov 30", or null when no future date is set.
export function foundingEndsLabel() {
  if (!FOUNDING || !FOUNDING_ENDS_ON) return null;
  const end = new Date(`${FOUNDING_ENDS_ON}T23:59:59`);
  if (Number.isNaN(end.getTime()) || end < new Date()) return null;
  return `Founding price ends ${end.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
}

export const FOUNDING_SPOTS = 100;
export const FOUNDING_CLAIMED = 92;

// Seats remaining (clamped to >= 0). Only meaningful when FOUNDING_CLAIMED is set.
export const FOUNDING_SPOTS_LEFT =
  FOUNDING_CLAIMED == null ? null : Math.max(0, FOUNDING_SPOTS - FOUNDING_CLAIMED);

// Whether to render a live "X of 100 left" counter + progress bar vs the softer
// cap-only line. True only while founding is active AND a claimed count is set.
export const SHOW_FOUNDING_COUNTER = FOUNDING && FOUNDING_CLAIMED != null;
