import { useState, useEffect, useRef } from 'react';
import { X, Mail, Lock, User as UserIcon, Loader2, ShieldCheck } from 'lucide-react';
import { login, register, googleSignIn, verifyEmail, resendVerification } from '../api';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

// Mirror the backend guardrails so users get instant, friendly feedback instead
// of a round-trip 400. Requires a non-empty local part, an "@", a dotted domain
// with a 2+ char TLD, and no whitespace anywhere.
const EMAIL_RE = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[^@\s.]{2,}$/;
const MIN_PASSWORD_LENGTH = 8;

// Load the Google Identity Services script once.
function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const existing = document.getElementById('google-gsi');
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', reject);
      return;
    }
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client';
    s.id = 'google-gsi';
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

export default function AuthModal({ onClose, onSuccess, initialMode = 'login' }) {
  const [mode, setMode] = useState(initialMode); // 'login' | 'signup' | 'verify'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  // Email-verification step (shown after sign-up when the server requires it).
  const [code, setCode] = useState('');
  const [resendMsg, setResendMsg] = useState('');
  const googleBtnRef = useRef(null);

  // Render the Google Sign-In button when a client ID is configured.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled || !window.google?.accounts?.id) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (response) => {
            setError('');
            setLoading(true);
            try {
              const data = await googleSignIn(response.credential);
              onSuccess(data.user);
            } catch (err) {
              setError('Google sign-in failed. Please try again.');
            } finally {
              setLoading(false);
            }
          },
        });
        if (googleBtnRef.current) {
          window.google.accounts.id.renderButton(googleBtnRef.current, {
            theme: 'outline',
            size: 'large',
            width: 320,
            text: 'continue_with',
            shape: 'pill',
          });
        }
      })
      .catch(() => {/* script blocked — email/password still works */});
    return () => { cancelled = true; };
  }, [onSuccess]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Client-side guardrails: give instant feedback and avoid pointless requests.
    const trimmedEmail = email.trim();
    if (!EMAIL_RE.test(trimmedEmail)) {
      setError('Please enter a valid email address.');
      return;
    }
    if (mode === 'signup' && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setLoading(true);
    try {
      const data = mode === 'login'
        ? await login(trimmedEmail, password)
        : await register(trimmedEmail, password, name.trim());
      // New accounts may need to confirm an emailed code before they're usable.
      if (data.user?.verification_required) {
        setResendMsg(`We sent a 6-digit code to ${trimmedEmail}.`);
        setCode('');
        setError('');
        setMode('verify');
        return;
      }
      onSuccess(data.user);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    setError('');
    const trimmed = code.trim();
    if (!/^\d{6}$/.test(trimmed)) {
      setError('Enter the 6-digit code from your email.');
      return;
    }
    setLoading(true);
    try {
      const user = await verifyEmail(trimmed);
      onSuccess(user);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Verification failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setResendMsg('');
    try {
      await resendVerification();
      setResendMsg('A new code is on its way. Check your inbox.');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not resend the code. Please wait a moment.');
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-stone-900/40 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-white rounded-3xl shadow-soft border border-paper-300 p-8">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full text-stone-400 hover:text-stone-700 hover:bg-paper-100 transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-6">
          <h2 className="font-display text-2xl font-semibold text-stone-900">
            {mode === 'verify'
              ? 'Verify your email'
              : mode === 'login' ? 'Welcome back' : 'Create your account'}
          </h2>
          <p className="text-sm text-stone-500 mt-1">
            {mode === 'verify'
              ? 'Enter the 6-digit code we emailed you to start creating podcasts.'
              : mode === 'login'
                ? 'Sign in to access your podcast library.'
                : 'Sign up to save and organize your podcasts.'}
          </p>
        </div>

        {mode === 'verify' && (
          <form onSubmit={handleVerify} className="space-y-3">
            <div className="flex justify-center">
              <div className="w-12 h-12 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center">
                <ShieldCheck className="w-6 h-6" />
              </div>
            </div>
            {resendMsg && <p className="text-sm text-brand-700 text-center">{resendMsg}</p>}
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="Enter 6-digit code"
              className="w-full text-center tracking-[0.5em] text-lg font-semibold px-3 py-2.5 rounded-xl border border-paper-300 bg-paper-50 text-stone-800 placeholder-stone-400 placeholder:tracking-normal placeholder:text-base placeholder:font-normal focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
            />
            {error && <p className="text-sm text-red-600 text-center">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-glow transition-all disabled:opacity-60 disabled:cursor-wait"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Verify &amp; continue
            </button>
            <p className="text-sm text-stone-500 text-center">
              Didn't get the code?{' '}
              <button type="button" onClick={handleResend} className="text-brand-600 font-semibold hover:text-brand-700">
                Resend
              </button>
            </p>
          </form>
        )}

        {mode !== 'verify' && GOOGLE_CLIENT_ID && (
          <>
            <div ref={googleBtnRef} className="flex justify-center mb-4 min-h-[44px]" />
            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-paper-300" />
              <span className="text-xs text-stone-400">or</span>
              <div className="flex-1 h-px bg-paper-300" />
            </div>
          </>
        )}

        {mode !== 'verify' && (
        <>
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'signup' && (
            <div className="relative">
              <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name (optional)"
                className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-paper-300 bg-paper-50 text-stone-800 placeholder-stone-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
              />
            </div>
          )}
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-paper-300 bg-paper-50 text-stone-800 placeholder-stone-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'signup' ? 'Create a password (min 8 chars)' : 'Password'}
              className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-paper-300 bg-paper-50 text-stone-800 placeholder-stone-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
            />
          </div>

          {error && <p className="text-sm text-red-600 text-center">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-glow transition-all disabled:opacity-60 disabled:cursor-wait"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="text-sm text-stone-500 text-center mt-5">
          {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); }}
            className="text-brand-600 font-semibold hover:text-brand-700"
          >
            {mode === 'login' ? 'Sign up' : 'Sign in'}
          </button>
        </p>
        </>
        )}
      </div>
    </div>
  );
}
