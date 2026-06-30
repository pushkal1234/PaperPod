import { useState, useEffect, useRef } from 'react';
import { Headphones, FileAudio, Sparkles, ArrowLeft, RefreshCw, AlertCircle, Trash2 } from 'lucide-react';
import UploadZone from './components/UploadZone';
import PodcastPlayer from './components/PodcastPlayer';
import QAPanel from './components/QAPanel';
import { uploadDocument, uploadText, uploadImage, getDocument, listDocuments, deleteDocument, getAudioUrl, createShare, getSharedPodcast } from './api';

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
  const pollRef = useRef(null);

  useEffect(() => {
    loadDocuments();

    // Handle shared podcast via ?share=TOKEN
    const params = new URLSearchParams(window.location.search);
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

  const loadDocuments = async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents || []);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
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
      alert('Upload failed. Please try again.');
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
      alert('Upload failed. Please try again.');
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
      alert('Image upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const startPolling = (docId) => {
    setIsPolling(true);
    setErrorMsg(null);
    let elapsed = 0;
    const poll = async () => {
      try {
        const doc = await getDocument(docId);
        if (doc.status === 'ready') {
          setIsPolling(false);
          setCurrentDoc(doc);
          setView('player');
          loadDocuments();
          return;
        } else if (doc.status === 'failed') {
          setIsPolling(false);
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

  const handleDelete = async (doc, e) => {
    e?.preventDefault?.();
    e?.stopPropagation?.();

    const ok = window.confirm(`Delete "${doc.filename}"?\n\nThis will remove the podcast and Q&A history from the server.`);
    if (!ok) return;

    setDeletingDocIds((prev) => new Set([...prev, doc.doc_id]));
    try {
      await deleteDocument(doc.doc_id);
      if (currentDoc?.doc_id === doc.doc_id) {
        setCurrentDoc(null);
        setView('home');
      }
      await loadDocuments();
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Delete failed. Please try again.');
    } finally {
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
      alert('Failed to create share link. Please try again.');
      return null;
    }
  };

  return (
    <div className="min-h-screen">
      {/* Navbar */}
      <nav className="border-b border-paper-300/70 bg-paper-50/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <button onClick={() => { setView('home'); setCurrentDoc(null); }} className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow">
              <Headphones className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-stone-800 tracking-tight">
              Paper<span className="text-brand-600">Pod</span>
            </span>
          </button>
          <p className="text-xs text-stone-400 font-medium hidden sm:block">Documents → Podcasts → Conversations</p>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* HOME VIEW */}
        {view === 'home' && (
          <div className="space-y-8">
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
                Upload a PDF, DOCX, or TXT, paste text, or snap a photo — and get a
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
            </div>

            {/* Upload */}
            <UploadZone onUpload={handleUpload} onUploadText={handleUploadText} onUploadImage={handleUploadImage} isUploading={isUploading} />

            {/* Previous Documents */}
            {documents.length > 0 && (
              <div>
                <h2 className="font-display text-2xl font-semibold text-stone-800 mb-4">Your Podcasts</h2>
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
                        <p className="text-xs text-stone-400 mt-0.5">
                          {doc.status === 'ready' ? 'Ready to play' : doc.status === 'failed' ? '❌ Failed' : '⏳ Processing...'}
                        </p>
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
              </div>
            )}
          </div>
        )}

        {/* PROCESSING VIEW */}
        {view === 'processing' && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="relative mb-8">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center shadow-glow">
                <Headphones className="w-10 h-10 text-white" />
              </div>
              <div className="absolute inset-0 w-20 h-20 rounded-full border-2 border-brand-400/40 animate-pulse-ring" />
            </div>
            <h2 className="font-display text-3xl font-semibold text-stone-900 mb-2">Composing your podcast</h2>
            <p className="text-stone-500 max-w-md">
              Our AI is reading your document, writing a dialogue script, and synthesizing audio.
              This may take 1-3 minutes...
            </p>
            <div className="flex items-center gap-2 mt-6 text-brand-600">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-sm font-medium">Checking status...</span>
            </div>
          </div>
        )}

        {/* FAILED VIEW */}
        {view === 'failed' && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-20 h-20 rounded-full bg-red-100 flex items-center justify-center mb-8">
              <AlertCircle className="w-10 h-10 text-red-500" />
            </div>
            <h2 className="font-display text-3xl font-semibold text-stone-900 mb-2">Generation Failed</h2>
            <p className="text-stone-500 max-w-md mb-2">
              Something went wrong while generating your podcast.
            </p>
            {errorMsg && (
              <p className="text-red-500/80 text-sm max-w-lg mb-6 font-mono">{errorMsg}</p>
            )}
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
              Back to documents
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
        PaperPod · Documents to Podcasts with Real-time Q&A
      </footer>
    </div>
  );
}

export default App;
