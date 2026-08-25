import { useState, useEffect, useRef } from 'react';
import { Headphones, FileAudio, Sparkles, ArrowLeft, AlertCircle, Trash2, Chrome, Puzzle, LogOut, LogIn, Check, Download, Upload, Wand2, MessageCircle, Zap, Star, Bookmark, Loader2, Youtube, Github, Mail, Phone, X } from 'lucide-react';
import UploadZone from './components/UploadZone';
import PodcastPlayer from './components/PodcastPlayer';
import QAPanel from './components/QAPanel';
import AuthModal from './components/AuthModal';
import SignOutModal from './components/SignOutModal';
import SampleEpisode from './components/SampleEpisode';
import VideoShowcase from './components/VideoShowcase';
import EngineeringDeepDive from './components/EngineeringDeepDive';
import ProcessingView from './components/ProcessingView';
import ConfirmModal from './components/ConfirmModal';
import ToastContainer from './components/ToastContainer';
import PaywallModal from './components/PaywallModal';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import { uploadDocument, uploadText, uploadImage, getDocument, listDocuments, deleteDocument, getAudioUrl, createShare, getSharedPodcast, getMe, getToken, logout, setUnauthorizedHandler, getBillingConfig, createCheckout, getBillingPortal } from './api';

// Browser extension store listings — surfaced in the navbar, hero, and footer.
const CHROME_STORE_URL = 'https://chromewebstore.google.com/detail/paperpod-%E2%80%94-ai-podcast-for/oeppbenincbmdaomedjpjfegnfphdoeo';
const FIREFOX_STORE_URL = 'https://addons.mozilla.org/en-US/firefox/addon/paperpod-ai-podcast/';

// Optional muted product-demo video shown behind the generation loading screen.
// Set to a hosted .webm/.mp4 URL to enable it; null falls back to a branded
// animation so nothing 404s until the asset exists.
const PROCESSING_VIDEO_URL = '/processing-demo.mp4';

// Footer video links — point straight to YouTube so views are counted in YT
// analytics (no in-app route needed).
const FOOTER_VIDEOS = [
  { label: 'Founder intro', url: 'https://www.youtube.com/watch?v=G0jdx3Y9ZQE' },
  { label: 'Product demo', url: 'https://www.youtube.com/watch?v=3UU8Ikde_2M' },
  { label: 'Feature deep dive', url: 'https://www.youtube.com/watch?v=KqSpaN2U7qM' },
];
const GITHUB_REPO_URL = 'https://github.com/pushkal1234/PaperPod/';
const CONTACT_EMAIL = 'pushkalshuk@gmail.com';
// Support contacts surfaced in the navbar "Contact us" popover. Kept front and
// centre so users can reach a human about their experience and — importantly —
// about anything payment/billing related, for full transparency.
const CONTACT_WHATSAPP_DISPLAY = '+91 97294 61168';
const CONTACT_WHATSAPP_LINK = 'https://wa.me/919729461168';
const CONTACT_EMAIL_LINK = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('PaperPod — support / feedback')}`;


function App() {
  const [view, setView] = useState('home');
  const [documents, setDocuments] = useState([]);
  const [currentDoc, setCurrentDoc] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [deletingDocIds, setDeletingDocIds] = useState(() => new Set());
  const [sharedPodcast, setSharedPodcast] = useState(null);
  const [sharedLoading, setSharedLoading] = useState(false);
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [showSignOut, setShowSignOut] = useState(false);
  const [postAuthView, setPostAuthView] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [confirmState, setConfirmState] = useState(null);
  const [processingElapsed, setProcessingElapsed] = useState(0);
  const [processingStage, setProcessingStage] = useState(null);
  const [showContact, setShowContact] = useState(false);
  // Billing: public flags (drives whether any upgrade UI shows at all) and the
  // paywall modal state ({ reason, message } when open, null when closed).
  const [billingConfig, setBillingConfig] = useState(null);
  const [paywall, setPaywall] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);
  // Prefill for the text composer when opened via an extension/context-menu
  // handoff (?type=text&text=...). Empty by default.
  const [handoff, setHandoff] = useState({ text: '', title: '' });
  const pollRef = useRef(null);
  const elapsedRef = useRef(null);
  const toastIdRef = useRef(0);
  const contactRef = useRef(null);

  const pushToast = (message, type = 'info', duration = 5000) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
  };
  const dismissToast = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  useEffect(() => {
    // If a token expires mid-session, drop the user back to logged-out state.
    setUnauthorizedHandler(() => {
      setUser(null);
      setDocuments([]);
    });

    // Restore the session from a stored token, then load that user's library.
    if (getToken()) {
      getMe()
        .then((me) => {
          setUser(me);
          loadDocuments();
        })
        .catch(() => setUser(null))
        .finally(() => setAuthChecked(true));
    } else {
      setAuthChecked(true);
    }

    // Public billing flags — decides whether any upgrade/paywall UI shows.
    getBillingConfig()
      .then(setBillingConfig)
      .catch(() => setBillingConfig(null));

    // Handle shared podcast via ?share=TOKEN (public, no auth needed)
    const params = new URLSearchParams(window.location.search);

    // Returned from a successful Dodo checkout (?upgrade=success): the webhook is
    // the source of truth, so just refresh the user, celebrate, and clean the URL.
    if (params.get('upgrade') === 'success') {
      pushToast('Welcome to Premium! Your account has been upgraded. 🎉', 'success', 7000);
      if (getToken()) {
        // Poll a couple of times in case the webhook lands a moment after redirect.
        refreshUser();
        setTimeout(refreshUser, 3000);
      }
      params.delete('upgrade');
      const clean = window.location.pathname + (params.toString() ? `?${params}` : '');
      window.history.replaceState({}, '', clean);
    }

    // Extension "Paste text" / context-menu text handoff: prefill the composer.
    if (params.get('type') === 'text' && params.get('text')) {
      setHandoff({ text: params.get('text'), title: params.get('title') || '' });
      params.delete('type');
      params.delete('text');
      params.delete('title');
      const clean = window.location.pathname + (params.toString() ? `?${params}` : '');
      window.history.replaceState({}, '', clean);
    }

    const shareToken = params.get('share');
    if (shareToken) {
      setSharedLoading(true);
      getSharedPodcast(shareToken)
        .then((data) => {
          setSharedPodcast(data);
          setView('shared');
        })
        .catch((err) => {
          console.error('Failed to load shared podcast:', err);
          setErrorMsg('This shared podcast link is invalid or has expired.');
          setView('failed');
        })
        .finally(() => setSharedLoading(false));
    }
  }, []);

  // Close the "Contact us" popover on outside click or Escape.
  useEffect(() => {
    if (!showContact) return;
    const onPointerDown = (e) => {
      if (contactRef.current && !contactRef.current.contains(e.target)) {
        setShowContact(false);
      }
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setShowContact(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [showContact]);

  const loadDocuments = async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents || []);
    } catch (err) {
      // 401 is expected when logged out; the interceptor already clears state.
      if (err?.response?.status !== 401) console.error('Failed to load documents:', err);
    }
  };

  // Re-fetch the signed-in user's plan/usage (e.g. after returning from checkout).
  const refreshUser = async () => {
    try {
      const me = await getMe();
      setUser(me);
      return me;
    } catch {
      return null;
    }
  };

  // Whether any upgrade/paywall UI should be visible. Sourced from the public
  // /billing/config flag so the whole feature stays dark until BILLING_ENABLED.
  const billingOn = !!billingConfig?.billing_enabled;
  const isPremium = user?.plan === 'premium';

  // Detect a 402 (Payment Required) from an upload and open the paywall with the
  // backend's reason/message; otherwise show a normal error toast.
  const handleUploadError = (err, fallbackMsg) => {
    if (err?.response?.status === 402) {
      const detail = err?.response?.data?.detail;
      const reason = (detail && detail.code) || 'quota_exceeded';
      const message = (detail && detail.message) || null;
      setPaywall({ reason, message });
      return true;
    }
    pushToast(fallbackMsg, 'error');
    return false;
  };

  const openUpgrade = () => setPaywall({ reason: 'upgrade', message: null });

  const handleManageBilling = async () => {
    setPortalLoading(true);
    try {
      const { url } = await getBillingPortal();
      if (url) window.location.href = url;
      else pushToast('Could not open the billing portal. Please try again.', 'error');
    } catch {
      pushToast('Could not open the billing portal. Please try again.', 'error');
      setPortalLoading(false);
    }
  };

  const handleAuthSuccess = (loggedInUser) => {
    setUser(loggedInUser);
    setShowAuth(false);
    loadDocuments();
    // If the user opened sign-in on their way to "My Podcasts", take them there.
    if (postAuthView) {
      setView(postAuthView);
      setPostAuthView(null);
    }
  };

  // "My Podcasts" is the only auth-gated area. Anonymous users can upload and
  // listen freely; signing in is only required to open a personal library.
  const goToLibrary = () => {
    if (user) {
      loadDocuments();
      setView('library');
    } else {
      setPostAuthView('library');
      setShowAuth(true);
    }
  };

  const handleLogout = () => {
    setShowSignOut(false);
    logout();
    setUser(null);
    setDocuments([]);
    setCurrentDoc(null);
    setView('home');
  };

  const handleUpload = async (file) => {
    setIsUploading(true);
    try {
      const isImage = file.type?.startsWith('image/');
      const res = isImage ? await uploadImage(file) : await uploadDocument(file);
      setView('processing');
      startPolling(res.doc_id);
    } catch (err) {
      console.error('Upload failed:', err);
      handleUploadError(err, 'Upload failed. Please check the file and try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleUploadText = async (text, title) => {
    setIsUploading(true);
    try {
      const res = await uploadText(text, title);
      setView('processing');
      startPolling(res.doc_id);
    } catch (err) {
      console.error('Text upload failed:', err);
      handleUploadError(err, 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleUploadImage = async (file) => {
    setIsUploading(true);
    try {
      const res = await uploadImage(file);
      setView('processing');
      startPolling(res.doc_id);
    } catch (err) {
      console.error('Image upload failed:', err);
      handleUploadError(err, 'Image upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const stopElapsedTimer = () => {
    if (elapsedRef.current) {
      clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }
  };

  const startPolling = (docId) => {
    setIsPolling(true);
    setErrorMsg(null);
    // Drive the ProcessingView's staged progress with a 1s wall-clock timer.
    setProcessingElapsed(0);
    setProcessingStage(null);
    stopElapsedTimer();
    elapsedRef.current = setInterval(() => setProcessingElapsed((s) => s + 1), 1000);
    let elapsed = 0;
    const poll = async () => {
      try {
        const doc = await getDocument(docId);
        // Real backend sub-step ("reading" | "analyzing_figures" |
        // "writing_script" | "synthesizing"); drives the honest stage checklist.
        if (doc.stage) setProcessingStage(doc.stage);
        if (doc.status === 'ready') {
          setIsPolling(false);
          stopElapsedTimer();
          setCurrentDoc(doc);
          setView('player');
          loadDocuments();
          return;
        } else if (doc.status === 'failed') {
          setIsPolling(false);
          stopElapsedTimer();
          setErrorMsg(doc.error || 'Podcast generation failed. Please try again.');
          setView('failed');
          loadDocuments();
          return;
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
      // Progressive polling: fast at first, then slow down to reduce server load
      const interval = elapsed < 30000 ? 3000 : elapsed < 90000 ? 6000 : 10000;
      elapsed += interval;
      pollRef.current = setTimeout(poll, interval);
    };
    pollRef.current = setTimeout(poll, 3000);
    elapsed += 3000;
  };

  useEffect(() => {
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    };
  }, []);

  const openDoc = async (docId) => {
    try {
      const doc = await getDocument(docId);
      if (doc.status === 'ready') {
        setCurrentDoc(doc);
        setView('player');
      } else if (doc.status === 'failed') {
        setErrorMsg(doc.error || 'Podcast generation failed. Please try again.');
        setView('failed');
      } else {
        setView('processing');
        startPolling(docId);
      }
    } catch (err) {
      console.error('Failed to load document:', err);
    }
  };

  // Open the branded confirm dialog; the actual delete runs on confirm.
  const handleDelete = (doc, e) => {
    e?.preventDefault?.();
    e?.stopPropagation?.();
    setConfirmState({
      title: `Delete "${doc.filename}"?`,
      message: 'This permanently removes the podcast and its Q&A history from the server.',
      confirmLabel: 'Delete',
      danger: true,
      onConfirm: () => performDelete(doc),
    });
  };

  const performDelete = async (doc) => {
    setDeletingDocIds((prev) => new Set([...prev, doc.doc_id]));
    try {
      await deleteDocument(doc.doc_id);
      if (currentDoc?.doc_id === doc.doc_id) {
        setCurrentDoc(null);
        setView('home');
      }
      await loadDocuments();
      pushToast('Podcast deleted.', 'success');
    } catch (err) {
      console.error('Delete failed:', err);
      pushToast('Delete failed. Please try again.', 'error');
    } finally {
      setConfirmState(null);
      setDeletingDocIds((prev) => {
        const next = new Set(prev);
        next.delete(doc.doc_id);
        return next;
      });
    }
  };

  const handleShare = async (docId) => {
    try {
      const res = await createShare(docId);
      return `${window.location.origin}/?share=${res.share_token}`;
    } catch (err) {
      console.error('Share failed:', err);
      pushToast('Failed to create share link. Please try again.', 'error');
      return null;
    }
  };

  return (
    <div className="min-h-screen">
      {/* Navbar */}
      <nav className="border-b border-paper-300/70 bg-paper-50/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <button onClick={() => { setView('home'); setCurrentDoc(null); }} className="flex items-center gap-2.5 group shrink-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow">
              <Headphones className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-stone-800 tracking-tight">
              Paper<span className="text-brand-600">Pod</span>
            </span>
          </button>
          <div className="flex items-center gap-1.5 min-w-0">
            <button
              onClick={goToLibrary}
              className={`inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full border transition-all ${
                view === 'library'
                  ? 'bg-brand-50 text-brand-700 border-brand-200'
                  : 'bg-white text-stone-600 border-paper-300 hover:text-brand-700 hover:border-brand-200'
              }`}
              title="Your personal podcast library"
            >
              <FileAudio className="w-4 h-4" />
              <span className="hidden sm:inline">My Podcasts</span>
            </button>
            <a
              href={CHROME_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={`${user ? 'hidden 2xl:inline-flex' : 'hidden lg:inline-flex'} shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3.5 py-2 rounded-full bg-brand-600 text-white hover:bg-brand-700 shadow-glow transition-all`}
              title="Download PaperPod for Chrome — free forever, no credit card"
            >
              <Download className="w-4 h-4" />
              <span>Free Download</span>
              <span className="hidden lg:inline opacity-80">· Chrome</span>
            </a>
            <a
              href={FIREFOX_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={`${user ? 'hidden 2xl:inline-flex' : 'hidden lg:inline-flex'} shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3.5 py-2 rounded-full bg-white text-brand-700 border border-brand-200 hover:bg-brand-50 shadow-soft transition-all`}
              title="Download PaperPod for Firefox — free forever, no credit card"
            >
              <Puzzle className="w-4 h-4" />
              <span>Free · Firefox</span>
            </a>

            {authChecked && (user ? (
              <div className="flex items-center gap-1.5 pl-1 shrink-0">
                <div className="flex items-center gap-2 shrink-0">
                  {user.avatar_url ? (
                    <img src={user.avatar_url} alt="" className="w-8 h-8 rounded-full border border-paper-300" referrerPolicy="no-referrer" />
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-sm font-bold">
                      {(user.name || user.email || '?').trim().charAt(0).toUpperCase()}
                    </div>
                  )}
                  <span className="hidden lg:block text-sm font-medium text-stone-700 max-w-[8rem] truncate">
                    {user.name || user.email}
                  </span>
                </div>

                {/* Billing UI — hidden entirely until BILLING_ENABLED is on. */}
                {billingOn && (isPremium ? (
                  <div className="flex items-center gap-2">
                    <span className="hidden sm:inline-flex shrink-0 whitespace-nowrap items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-full bg-gradient-to-r from-brand-100 to-accent-100 text-brand-700 border border-brand-200">
                      <Star className="w-3.5 h-3.5" /> Premium
                    </span>
                    <button
                      onClick={handleManageBilling}
                      disabled={portalLoading}
                      className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full bg-white text-stone-600 border border-paper-300 hover:text-brand-700 hover:border-brand-200 transition-all disabled:opacity-60"
                      title="Manage your subscription"
                    >
                      {portalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                      <span className="hidden sm:inline">Manage</span>
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    {user?.usage?.podcasts_remaining != null && (
                      <span className="hidden lg:inline whitespace-nowrap text-xs font-medium text-stone-500" title="Free podcasts remaining">
                        {user.usage.podcasts_remaining} of {user.usage.podcasts_limit} left
                      </span>
                    )}
                    <button
                      onClick={openUpgrade}
                      className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-bold px-3.5 py-2 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-white hover:opacity-90 shadow-glow transition-all"
                      title="Upgrade to Premium"
                    >
                      <Star className="w-4 h-4" />
                      <span>Upgrade</span>
                    </button>
                  </div>
                ))}

                <button
                  onClick={() => setShowSignOut(true)}
                  className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full bg-paper-100 text-stone-500 hover:text-stone-800 border border-paper-300 transition-all"
                  title="Sign out"
                >
                  <LogOut className="w-4 h-4 -scale-x-100" />
                  <span className="hidden sm:inline">Sign out</span>
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowAuth(true)}
                className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-full bg-stone-900 text-white hover:bg-stone-800 shadow-soft transition-all"
              >
                <LogIn className="w-4 h-4" />
                <span>Sign in</span>
              </button>
            ))}
            <div className="relative" ref={contactRef}>
              <button
                onClick={() => setShowContact((v) => !v)}
                aria-haspopup="dialog"
                aria-expanded={showContact}
                className={`inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full border transition-all ${
                  showContact
                    ? 'bg-brand-50 text-brand-700 border-brand-200'
                    : 'bg-white text-stone-600 border-paper-300 hover:text-brand-700 hover:border-brand-200'
                }`}
                title="Talk to us about your experience or anything payment related"
              >
                <MessageCircle className="w-4 h-4" />
                <span className="hidden sm:inline">Contact us</span>
              </button>
              {showContact && (
                <div
                  role="dialog"
                  aria-label="Contact PaperPod support"
                  className="absolute right-0 mt-2 w-72 rounded-2xl border border-paper-300 bg-white shadow-soft p-4 z-50"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-stone-800">We'd love to hear from you</p>
                      <p className="mt-1 text-xs text-stone-500 leading-relaxed">
                        Tell us how generating podcasts feels — or reach out about anything
                        payment related. We keep billing fully transparent.
                      </p>
                    </div>
                    <button
                      onClick={() => setShowContact(false)}
                      className="shrink-0 text-stone-400 hover:text-stone-700 transition-colors"
                      title="Close"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="mt-3 space-y-2">
                    <a
                      href={CONTACT_WHATSAPP_LINK}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-3 rounded-xl border border-paper-300 bg-paper-50 px-3 py-2.5 hover:border-brand-200 hover:bg-brand-50 transition-all group"
                    >
                      <span className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
                        <Phone className="w-4 h-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold text-stone-800 group-hover:text-brand-700">WhatsApp</span>
                        <span className="block text-xs text-stone-500 truncate">{CONTACT_WHATSAPP_DISPLAY}</span>
                      </span>
                    </a>
                    <a
                      href={CONTACT_EMAIL_LINK}
                      className="flex items-center gap-3 rounded-xl border border-paper-300 bg-paper-50 px-3 py-2.5 hover:border-brand-200 hover:bg-brand-50 transition-all group"
                    >
                      <span className="w-8 h-8 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center shrink-0">
                        <Mail className="w-4 h-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold text-stone-800 group-hover:text-brand-700">Email</span>
                        <span className="block text-xs text-stone-500 truncate">{CONTACT_EMAIL}</span>
                      </span>
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>

      {showAuth && (
        <AuthModal onClose={() => setShowAuth(false)} onSuccess={handleAuthSuccess} />
      )}

      {showSignOut && (
        <SignOutModal
          userName={user?.name || user?.email}
          onClose={() => setShowSignOut(false)}
          onConfirm={handleLogout}
        />
      )}

      {confirmState && (
        <ConfirmModal
          title={confirmState.title}
          message={confirmState.message}
          confirmLabel={confirmState.confirmLabel}
          danger={confirmState.danger}
          busy={deletingDocIds.size > 0}
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState(null)}
        />
      )}

      {paywall && (
        <PaywallModal
          reason={paywall.reason}
          message={paywall.message}
          onClose={() => setPaywall(null)}
          onError={(msg) => pushToast(msg, 'error')}
          contact={{
            whatsappLink: CONTACT_WHATSAPP_LINK,
            whatsappDisplay: CONTACT_WHATSAPP_DISPLAY,
            emailLink: CONTACT_EMAIL_LINK,
            email: CONTACT_EMAIL,
          }}
        />
      )}

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* HOME VIEW */}
        {view === 'home' && (
          <div className="space-y-8 pb-24 md:pb-0">
            {/* Hero */}
            <div className="text-center pt-10 pb-6">
              <div className="inline-flex items-center gap-2 bg-white/70 text-brand-700 text-xs font-semibold px-3.5 py-1.5 rounded-full mb-6 border border-brand-200 shadow-soft">
                <Sparkles className="w-3.5 h-3.5 text-accent-500" />
                Turn reading into listening
              </div>
              <h1 className="font-display text-5xl md:text-6xl font-semibold text-stone-900 leading-[1.05] tracking-tight">
                Turn any document into a<br />
                <span className="bg-gradient-to-r from-brand-600 via-brand-500 to-accent-500 bg-clip-text text-transparent">
                  podcast conversation
                </span>
              </h1>
              <p className="text-stone-500 mt-5 max-w-xl mx-auto text-lg leading-relaxed">
                Upload a PDF, DOCX, PPTX, or TXT, paste text, or snap a photo — and get a
                natural, two-host podcast in minutes. Then ask questions and hear instant answers.
              </p>
              {/* Decorative audio waveform — echoes the brand art */}
              <div className="flex items-end justify-center gap-1 h-10 mt-7" aria-hidden="true">
                {[0.5, 0.8, 0.4, 1, 0.6, 0.9, 0.45, 0.75, 0.55, 0.95, 0.5, 0.7].map((h, i) => (
                  <span
                    key={i}
                    className="w-1.5 rounded-full bg-gradient-to-t from-brand-500 to-accent-400 animate-eq"
                    style={{ height: `${h * 100}%`, animationDelay: `${i * 0.09}s` }}
                  />
                ))}
              </div>

              {/* Trust line — free-forever emphasis (extension demoted below) */}
              <div className="flex flex-col items-center gap-3 mt-8">
                {billingOn ? (
                  <>
                    <span className="inline-flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-[0.12em] text-accent-600 bg-accent-50 border border-accent-200 px-3 py-1 rounded-full shadow-soft animate-pulse-slow">
                      <Sparkles className="w-3.5 h-3.5" />
                      Start free — no card required
                    </span>
                    <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs font-medium text-stone-500">
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> 2 free podcasts to start</span>
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> No credit card to try it</span>
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> Unlimited Podcasts on Premium — $5/mo</span>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="inline-flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-[0.12em] text-accent-600 bg-accent-50 border border-accent-200 px-3 py-1 rounded-full shadow-soft animate-pulse-slow">
                      <Sparkles className="w-3.5 h-3.5" />
                      100% Free forever
                    </span>
                    <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs font-medium text-stone-500">
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> Free lifetime access</span>
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> No credit card required</span>
                      <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-brand-600" /> No sign-up to try it</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* PRIMARY ACTION — upload is the hero CTA for the web app. */}
            <div className="max-w-2xl mx-auto w-full">
              <UploadZone onUpload={handleUpload} onUploadText={handleUploadText} onUploadImage={handleUploadImage} isUploading={isUploading} initialText={handoff.text} initialTitle={handoff.title} />
              <p className="text-center text-sm text-stone-400 mt-4">
                Want to keep your podcasts?{' '}
                <button onClick={goToLibrary} className="text-brand-600 font-semibold hover:text-brand-700">
                  Open My Podcasts
                </button>
              </p>
              {/* Secondary — browser extension, demoted beneath the primary action. */}
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 mt-4 text-xs text-stone-500">
                <span>Prefer your browser? Add the free extension:</span>
                <a href={CHROME_STORE_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:text-brand-800">
                  <Chrome className="w-3.5 h-3.5" /> Chrome
                </a>
                <span className="text-stone-300">·</span>
                <a href={FIREFOX_STORE_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:text-brand-800">
                  <Puzzle className="w-3.5 h-3.5" /> Firefox
                </a>
              </div>
            </div>

            {/* Stat strip — feature highlights (honest, non-fabricated) */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-w-4xl mx-auto">
              {[
                { icon: Zap, stat: '~60 sec', label: 'to your first podcast' },
                { icon: Headphones, stat: '2 AI hosts', label: 'natural back-and-forth' },
                { icon: MessageCircle, stat: 'Live Q&A', label: 'ask the doc anything' },
                { icon: Star, stat: '$0 for your podcasts', label: 'no credit card to try it' },
              ].map(({ icon: Icon, stat, label }, i) => (
                <div
                  key={i}
                  className="flex flex-col items-center text-center gap-1 bg-white/70 border border-paper-300 rounded-2xl px-4 py-5 shadow-soft hover:shadow-glow hover:-translate-y-0.5 transition-all"
                >
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-50 to-accent-50 flex items-center justify-center mb-1">
                    <Icon className="w-5 h-5 text-brand-600" />
                  </div>
                  <p className="font-display text-xl font-semibold text-stone-900">{stat}</p>
                  <p className="text-xs text-stone-500">{label}</p>
                </div>
              ))}
            </div>

            {/* How it works — 3 steps */}
            <div className="pt-10">
              <h2 className="font-display text-3xl font-semibold text-stone-900 text-center">
                Three steps to your podcast
              </h2>
              <p className="text-stone-500 text-center mt-2 mb-8">No setup. No sign-up. Just drop a document and press play.</p>
              <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
                {[
                  { icon: Upload, step: '01', title: 'Drop your document', body: 'Upload a PDF, DOCX, PPTX, TXT, paste text, or snap a photo — anything you want to listen to.' },
                  { icon: Wand2, step: '02', title: 'AI writes the show', body: 'Two lifelike hosts turn it into a natural, engaging conversation in about a minute.' },
                  { icon: Headphones, step: '03', title: 'Listen & ask anything', body: 'Play it anywhere and ask follow-up questions — hear instant answers from your document.' },
                ].map(({ icon: Icon, step, title, body }, i) => (
                  <div
                    key={i}
                    className="relative bg-white border border-paper-300 rounded-3xl p-6 shadow-soft hover:shadow-glow hover:-translate-y-1 transition-all duration-200"
                  >
                    <span className="absolute top-5 right-6 font-display text-4xl font-bold text-paper-200 select-none">{step}</span>
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow mb-4">
                      <Icon className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="font-display text-lg font-semibold text-stone-900">{title}</h3>
                    <p className="text-sm text-stone-500 mt-1.5 leading-relaxed">{body}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Sample episode — real audio playback + interrupt-and-ask demo */}
            <SampleEpisode onCreateClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} />

            {/* Watch PaperPod — kept at the bottom, secondary to the product itself */}
            <VideoShowcase />

            {/* Engineering & design decisions — compact dedicated card */}
            <EngineeringDeepDive />
          </div>
        )}

        {/* MY PODCASTS (LIBRARY) VIEW — the only auth-gated area */}
        {view === 'library' && (
          <div className="space-y-6 pt-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-3xl font-semibold text-stone-900">My Podcasts</h2>
                <p className="text-stone-500 mt-1">
                  {user ? `Signed in as ${user.name || user.email}` : 'Your personal library'}
                </p>
              </div>
              <button
                onClick={() => { setView('home'); setCurrentDoc(null); }}
                className="inline-flex items-center gap-2 text-sm font-semibold text-stone-500 hover:text-brand-600 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Create a new one
              </button>
            </div>

            {/* Usage/analytics dashboard — self-hides when there are 0 podcasts. */}
            <AnalyticsDashboard />

            {documents.length > 0 ? (
              <div className="grid gap-3">
                {documents.map((doc) => (
                  <div
                    key={doc.doc_id}
                    onClick={() => openDoc(doc.doc_id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') openDoc(doc.doc_id);
                    }}
                    className="flex items-center gap-4 bg-white border border-paper-300 rounded-2xl p-4 shadow-soft hover:border-brand-300 hover:shadow-glow hover:-translate-y-0.5 transition-all duration-200 text-left group w-full cursor-pointer"
                  >
                    <div className="w-11 h-11 rounded-xl bg-brand-50 group-hover:bg-brand-100 flex items-center justify-center transition-colors">
                      <FileAudio className="w-5 h-5 text-brand-600 transition-colors" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-stone-800 truncate">{doc.filename}</p>
                      <div className="mt-1">
                        {doc.status === 'ready' ? (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            Ready to play
                          </span>
                        ) : doc.status === 'failed' ? (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-500/80">
                            <AlertCircle className="w-3.5 h-3.5" strokeWidth={2} />
                            Couldn't generate
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-400">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Processing…
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => handleDelete(doc, e)}
                      disabled={deletingDocIds.has(doc.doc_id)}
                      className="ml-2 inline-flex items-center justify-center w-9 h-9 rounded-xl border border-paper-300 bg-paper-50 text-stone-400 hover:text-red-600 hover:border-red-300 hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Delete podcast"
                      aria-label={`Delete ${doc.filename}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              /* Empty state for brand-new signed-in users */
              <div className="bg-white rounded-3xl border border-paper-300 shadow-soft p-12 text-center max-w-lg mx-auto">
                <div className="flex items-end justify-center gap-1 h-12 mb-6" aria-hidden="true">
                  {[0.4, 0.7, 0.5, 0.9, 0.6].map((h, i) => (
                    <span
                      key={i}
                      className="w-2 rounded-full bg-gradient-to-t from-brand-400 to-accent-300"
                      style={{ height: `${h * 100}%` }}
                    />
                  ))}
                </div>
                <h3 className="font-display text-2xl font-semibold text-stone-900">No podcasts yet</h3>
                <p className="text-stone-500 mt-2 mb-6">
                  Podcasts you create while signed in will appear here — a private library just for you.
                </p>
                <button
                  onClick={() => { setView('home'); setCurrentDoc(null); }}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-glow transition-all"
                >
                  <Sparkles className="w-5 h-5" />
                  Create your first podcast
                </button>
              </div>
            )}
          </div>
        )}

        {/* PROCESSING VIEW */}
        {view === 'processing' && (
          <ProcessingView elapsedSeconds={processingElapsed} stage={processingStage} videoUrl={PROCESSING_VIDEO_URL} />
        )}

        {/* FAILED VIEW */}
        {view === 'failed' && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-20 h-20 rounded-full bg-red-100 flex items-center justify-center mb-8">
              <AlertCircle className="w-10 h-10 text-red-500" />
            </div>
            <h2 className="font-display text-3xl font-semibold text-stone-900 mb-2">We couldn't finish this one</h2>
            <p className="text-stone-600 max-w-lg mb-6 leading-relaxed">
              {errorMsg || 'Something went wrong while generating your podcast. Please try again.'}
            </p>
            <button
              onClick={() => { setView('home'); setErrorMsg(null); }}
              className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl font-semibold shadow-glow transition-colors"
            >
              Try Again
            </button>
          </div>
        )}

        {/* SHARED VIEW */}
        {view === 'shared' && sharedPodcast && (
          <div className="space-y-6 max-w-2xl mx-auto py-8">
            <div className="text-center">
              <div className="inline-flex items-center gap-2 bg-white/70 text-brand-700 text-xs font-semibold px-3.5 py-1.5 rounded-full mb-4 border border-brand-200 shadow-soft">
                <Sparkles className="w-3.5 h-3.5 text-accent-500" />
                Shared Podcast
              </div>
            </div>
            <PodcastPlayer
              audioUrl={getAudioUrl(sharedPodcast.audio_id)}
              title={sharedPodcast.title}
              dialogueScript={sharedPodcast.dialogue_script}
              transcriptSegments={sharedPodcast.transcript_segments}
              fallbackDuration={sharedPodcast.duration_seconds}
            />
            <div className="text-center">
              <button
                onClick={() => { setView('home'); setSharedPodcast(null); }}
                className="text-sm text-stone-500 hover:text-brand-700 transition-colors"
              >
                Back to home
              </button>
            </div>
          </div>
        )}

        {/* PLAYER VIEW */}
        {view === 'player' && currentDoc && (
          <div className="space-y-6">
            <button
              onClick={() => { setView('home'); setCurrentDoc(null); }}
              className="flex items-center gap-2 text-sm font-medium text-stone-500 hover:text-brand-700 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to home
            </button>

            <div className="grid lg:grid-cols-2 gap-6">
              {/* Podcast Player */}
              <div className="space-y-4">
                <PodcastPlayer
                  audioUrl={getAudioUrl(currentDoc.audio.audio_id)}
                  title={currentDoc.filename}
                  dialogueScript={currentDoc.audio.dialogue_script}
                  transcriptSegments={currentDoc.audio.transcript_segments}
                  fallbackDuration={currentDoc.audio.duration_seconds}
                  onShare={() => handleShare(currentDoc.doc_id)}
                />
                {!user && (
                  <div className="flex items-center gap-3 rounded-2xl border border-brand-200 bg-gradient-to-r from-brand-50 to-accent-50/60 px-4 py-3 shadow-soft animate-pulse-slow">
                    <div className="w-9 h-9 shrink-0 rounded-full bg-white/80 text-brand-600 flex items-center justify-center shadow-soft">
                      <Bookmark className="w-4 h-4" />
                    </div>
                    <p className="text-sm text-stone-600 leading-snug flex-1">
                      <span className="font-semibold text-stone-800">Keep this episode.</span>{' '}
                      Sign in to save it to your{' '}
                      <button onClick={goToLibrary} className="font-semibold text-brand-700 hover:text-brand-800 underline underline-offset-2 decoration-brand-300">
                        My Podcasts
                      </button>{' '}
                      library and open it anytime.
                    </p>
                  </div>
                )}
                <div className="bg-white rounded-2xl p-5 border border-paper-300 shadow-soft">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-stone-400 text-xs uppercase tracking-wide">Document</p>
                      <p className="text-stone-800 font-semibold truncate mt-0.5">{currentDoc.filename}</p>
                    </div>
                    <div>
                      <p className="text-stone-400 text-xs uppercase tracking-wide">Duration</p>
                      <p className="text-stone-800 font-semibold mt-0.5">
                        {Math.floor(currentDoc.audio.duration_seconds / 60)}m {Math.floor(currentDoc.audio.duration_seconds % 60)}s
                      </p>
                    </div>
                    <div>
                      <p className="text-stone-400 text-xs uppercase tracking-wide">Created</p>
                      <p className="text-stone-800 font-semibold mt-0.5">{new Date(currentDoc.created_at).toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-stone-400 text-xs uppercase tracking-wide">Format</p>
                      <p className="text-stone-800 font-semibold mt-0.5">Podcast · 2 Hosts</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Q&A Panel */}
              <QAPanel docId={currentDoc.doc_id} />
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-paper-300/70 mt-16 py-6 text-center text-xs text-stone-400">
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 mb-3">
          {FOOTER_VIDEOS.map(({ label, url }) => (
            <a
              key={url}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-stone-500 hover:text-brand-600 font-medium transition-colors"
            >
              <Youtube className="w-3.5 h-3.5" />
              {label}
            </a>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-4 mb-2">
          <a
            href={CHROME_STORE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-stone-500 hover:text-brand-600 font-medium transition-colors"
          >
            <Chrome className="w-3.5 h-3.5" />
            Free Download — Chrome
          </a>
          <a
            href={FIREFOX_STORE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-stone-500 hover:text-brand-600 font-medium transition-colors"
          >
            <Puzzle className="w-3.5 h-3.5" />
            Free Download — Firefox
          </a>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-4 mb-2">
          <a
            href={GITHUB_REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-stone-500 hover:text-brand-600 font-medium transition-colors"
          >
            <Github className="w-3.5 h-3.5" />
            GitHub
          </a>
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="inline-flex items-center gap-1.5 text-stone-500 hover:text-brand-600 font-medium transition-colors"
          >
            <Mail className="w-3.5 h-3.5" />
            {CONTACT_EMAIL}
          </a>
        </div>
        <p className="text-brand-600 font-semibold mb-1">Free forever · No credit card required</p>
        PaperPod · Documents to Podcasts with Real-time Q&A
      </footer>

      {/* Floating free-download pill — mobile only, home view only */}
      {view === 'home' && (
        <a
          href={CHROME_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="md:hidden fixed bottom-4 inset-x-4 z-40 flex items-center justify-center gap-2 py-3.5 rounded-full bg-brand-600 text-white font-semibold shadow-glow active:scale-[0.98] transition-transform"
        >
          <Download className="w-5 h-5" />
          Free Download — it's free forever
        </a>
      )}
    </div>
  );
}

export default App;
