import { useEffect } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const TONE = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  error: 'border-red-200 bg-red-50 text-red-600',
  info: 'border-brand-200 bg-brand-50 text-brand-700',
};

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(toast.id), toast.duration ?? 5000);
    return () => clearTimeout(t);
  }, [toast, onDismiss]);

  const Icon = ICONS[toast.type] || Info;
  return (
    <div
      role="status"
      className={`pointer-events-auto flex items-start gap-2.5 w-full max-w-sm rounded-2xl border shadow-soft px-4 py-3 animate-fade-in ${
        TONE[toast.type] || TONE.info
      }`}
    >
      <Icon className="w-4 h-4 mt-0.5 shrink-0" />
      <p className="text-sm font-medium leading-snug flex-1">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 -mr-1 p-0.5 rounded-md opacity-60 hover:opacity-100 transition-opacity"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/**
 * Fixed, top-center toast stack. Replaces native alert() calls.
 * `toasts` is an array of { id, type, message, duration? }.
 */
export default function ToastContainer({ toasts, onDismiss }) {
  if (!toasts?.length) return null;
  return (
    <div className="fixed top-4 inset-x-0 z-[70] flex flex-col items-center gap-2 px-4 pointer-events-none">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
