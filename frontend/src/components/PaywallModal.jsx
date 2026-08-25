import { useState } from 'react';
import { X, Sparkles, Check, Infinity as InfinityIcon, FileText, MessageCircle, Loader2 } from 'lucide-react';
import { createCheckout } from '../api';

const PREMIUM_PERKS = [
  { icon: InfinityIcon, text: 'Unlimited podcasts — no lifetime cap' },
  { icon: FileText, text: 'Full-length documents & podcasts, always' },
  { icon: Sparkles, text: 'Priority support & new features first' },
];

// Shown when the backend returns HTTP 402 (quota_exceeded) or when a free user
// taps "Upgrade". Kicks off a Dodo Payments checkout and redirects the browser
// to the hosted checkout URL.
export default function PaywallModal({ reason, message, onClose, onError }) {
  const [loading, setLoading] = useState(false);

  const title =
    reason === 'quota_exceeded'
      ? "You've used your free podcasts"
      : 'Go unlimited with Premium';

  const handleUpgrade = async () => {
    setLoading(true);
    try {
      const { url } = await createCheckout();
      if (url) {
        window.location.href = url;
      } else {
        throw new Error('No checkout URL returned');
      }
    } catch (err) {
      setLoading(false);
      const detail = err?.response?.data?.detail;
      onError?.(
        (typeof detail === 'string' && detail) ||
          'Could not start checkout. Please try again in a moment.'
      );
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-stone-900/50 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Upgrade to PaperPod Premium"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-3xl bg-white shadow-glow border border-paper-300 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-stone-400 hover:text-stone-700 transition-colors"
          title="Close"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="bg-gradient-to-br from-brand-500 to-accent-500 px-7 pt-8 pb-7 text-white">
          <div className="inline-flex items-center gap-1.5 bg-white/20 text-white text-xs font-semibold px-3 py-1 rounded-full mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            PaperPod Premium
          </div>
          <h2 className="font-display text-2xl font-semibold leading-tight">{title}</h2>
          {message && <p className="mt-2 text-sm text-white/90 leading-relaxed">{message}</p>}
        </div>

        {/* Body */}
        <div className="px-7 py-6">
          <div className="flex items-baseline gap-1.5 mb-5">
            <span className="text-4xl font-bold text-stone-900">$5</span>
            <span className="text-stone-500 font-medium">/ month</span>
            <span className="ml-auto text-xs text-stone-400">Cancel anytime</span>
          </div>

          <ul className="space-y-3 mb-6">
            {PREMIUM_PERKS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3">
                <span className="w-8 h-8 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4" />
                </span>
                <span className="text-sm text-stone-700 font-medium">{text}</span>
              </li>
            ))}
          </ul>

          <button
            onClick={handleUpgrade}
            disabled={loading}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-2xl bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-glow transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Opening secure checkout…
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                Upgrade to Premium
              </>
            )}
          </button>

          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-stone-400">
            <span className="inline-flex items-center gap-1">
              <Check className="w-3.5 h-3.5 text-brand-500" /> Secure checkout
            </span>
            <span className="inline-flex items-center gap-1">
              <Check className="w-3.5 h-3.5 text-brand-500" /> Global payment methods
            </span>
          </div>

          <p className="mt-4 text-center text-xs text-stone-400 leading-relaxed">
            Billed securely by Dodo Payments (Merchant of Record). Questions about
            billing?{' '}
            <span className="inline-flex items-center gap-1 text-brand-600 font-medium">
              <MessageCircle className="w-3 h-3" /> Use “Contact us”
            </span>
          </p>

          <button
            onClick={onClose}
            className="mt-3 w-full text-center text-sm font-medium text-stone-400 hover:text-stone-600 transition-colors"
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}
