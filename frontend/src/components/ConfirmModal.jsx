import { useEffect, useRef } from 'react';
import { AlertTriangle, X } from 'lucide-react';

/**
 * Branded confirmation dialog — replaces native window.confirm().
 * Accessible: role="dialog", Esc to cancel, backdrop click to cancel,
 * focus moves to the confirm button on open and is trapped while open.
 */
export default function ConfirmModal({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
  busy = false,
}) {
  const confirmRef = useRef(null);
  const dialogRef = useRef(null);

  useEffect(() => {
    confirmRef.current?.focus();
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !busy) {
        onCancel?.();
        return;
      }
      // Simple focus trap: keep Tab within the dialog.
      if (e.key === 'Tab') {
        const focusable = dialogRef.current?.querySelectorAll(
          'button:not([disabled]), [href], input, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable?.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onCancel, busy]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-stone-900/40 backdrop-blur-sm animate-fade-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel?.();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        className="relative w-full max-w-md bg-white rounded-3xl border border-paper-300 shadow-glow p-6"
      >
        <button
          type="button"
          onClick={() => !busy && onCancel?.()}
          aria-label="Close dialog"
          className="absolute top-4 right-4 p-1.5 rounded-lg text-stone-400 hover:text-stone-600 hover:bg-paper-100 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="flex items-start gap-4">
          <div
            className={`w-11 h-11 shrink-0 rounded-2xl flex items-center justify-center ${
              danger ? 'bg-red-50 text-red-500' : 'bg-brand-50 text-brand-600'
            }`}
          >
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 id="confirm-title" className="font-display text-lg font-semibold text-stone-900">
              {title}
            </h3>
            {message && (
              <p id="confirm-message" className="text-sm text-stone-500 mt-1.5 leading-relaxed whitespace-pre-line">
                {message}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2.5 mt-6">
          <button
            type="button"
            onClick={() => !busy && onCancel?.()}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-stone-600 bg-paper-100 border border-paper-300 hover:bg-paper-200 transition-colors disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`px-4 py-2 rounded-xl text-sm font-semibold text-white shadow-soft transition-colors disabled:opacity-60 disabled:cursor-wait ${
              danger ? 'bg-red-600 hover:bg-red-700' : 'bg-brand-600 hover:bg-brand-700'
            }`}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
