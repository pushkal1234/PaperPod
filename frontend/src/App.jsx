import { useState, useEffect, useRef } from 'react';
import { Headphones, FileAudio, Sparkles, ArrowLeft, RefreshCw } from 'lucide-react';
import UploadZone from './components/UploadZone';
import PodcastPlayer from './components/PodcastPlayer';
import QAPanel from './components/QAPanel';
import { uploadDocument, getDocument, listDocuments, getAudioUrl } from './api';

function App() {
  const [view, setView] = useState('home');
  const [documents, setDocuments] = useState([]);
  const [currentDoc, setCurrentDoc] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    loadDocuments();
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
      const res = await uploadDocument(file);
      setView('processing');
      startPolling(res.doc_id);
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const startPolling = (docId) => {
    setIsPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const doc = await getDocument(docId);
        if (doc.status === 'ready') {
          clearInterval(pollRef.current);
          setIsPolling(false);
          setCurrentDoc(doc);
          setView('player');
          loadDocuments();
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 3000);
  };

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const openDoc = async (docId) => {
    try {
      const doc = await getDocument(docId);
      if (doc.status === 'ready') {
        setCurrentDoc(doc);
        setView('player');
      } else {
        setView('processing');
        startPolling(docId);
      }
    } catch (err) {
      console.error('Failed to load document:', err);
    }
  };

  return (
    <div className="min-h-screen bg-[#0f0f14]">
      {/* Navbar */}
      <nav className="border-b border-zinc-800/80 bg-zinc-900/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <button onClick={() => { setView('home'); setCurrentDoc(null); }} className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center shadow-lg shadow-brand-600/20">
              <Headphones className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white tracking-tight">
              Paper<span className="text-brand-400">Pod</span>
            </span>
          </button>
          <p className="text-xs text-zinc-600 hidden sm:block">Documents → Podcasts → Conversations</p>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* HOME VIEW */}
        {view === 'home' && (
          <div className="space-y-8">
            {/* Hero */}
            <div className="text-center py-12">
              <div className="inline-flex items-center gap-2 bg-brand-500/10 text-brand-400 text-xs font-medium px-3 py-1.5 rounded-full mb-4 border border-brand-500/20">
                <Sparkles className="w-3.5 h-3.5" />
                AI-Powered Document to Podcast
              </div>
              <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight">
                Turn any document into a<br />
                <span className="bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent">
                  podcast conversation
                </span>
              </h1>
              <p className="text-zinc-500 mt-4 max-w-xl mx-auto text-lg">
                Upload a PDF, DOCX, or TXT — get a natural-sounding podcast with two AI hosts.
                Then ask questions and get instant audio answers.
              </p>
            </div>

            {/* Upload */}
            <UploadZone onUpload={handleUpload} isUploading={isUploading} />

            {/* Previous Documents */}
            {documents.length > 0 && (
              <div>
                <h2 className="text-lg font-semibold text-zinc-200 mb-4">Your Podcasts</h2>
                <div className="grid gap-3">
                  {documents.map((doc) => (
                    <button
                      key={doc.doc_id}
                      onClick={() => openDoc(doc.doc_id)}
                      className="flex items-center gap-4 bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-brand-500/30 hover:bg-zinc-800/50 transition-all text-left group w-full"
                    >
                      <div className="w-10 h-10 rounded-lg bg-zinc-800 group-hover:bg-brand-500/10 flex items-center justify-center transition-colors">
                        <FileAudio className="w-5 h-5 text-zinc-500 group-hover:text-brand-400 transition-colors" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-zinc-200 truncate">{doc.filename}</p>
                        <p className="text-xs text-zinc-600">
                          {doc.status === 'ready' ? '✅ Ready to play' : '⏳ Processing...'}
                        </p>
                      </div>
                    </button>
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
              <div className="w-20 h-20 rounded-full bg-brand-500/20 flex items-center justify-center">
                <Headphones className="w-10 h-10 text-brand-400" />
              </div>
              <div className="absolute inset-0 w-20 h-20 rounded-full border-2 border-brand-400/30 animate-pulse-ring" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">Generating Your Podcast</h2>
            <p className="text-zinc-500 max-w-md">
              Our AI is reading your document, writing a dialogue script, and synthesizing audio.
              This may take 1-3 minutes...
            </p>
            <div className="flex items-center gap-2 mt-6 text-brand-400">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-sm font-medium">Checking status...</span>
            </div>
          </div>
        )}

        {/* PLAYER VIEW */}
        {view === 'player' && currentDoc && (
          <div className="space-y-6">
            <button
              onClick={() => { setView('home'); setCurrentDoc(null); }}
              className="flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
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
                />
                <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800/50">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-zinc-500">Document</p>
                      <p className="text-zinc-200 font-medium truncate">{currentDoc.filename}</p>
                    </div>
                    <div>
                      <p className="text-zinc-500">Duration</p>
                      <p className="text-zinc-200 font-medium">
                        {Math.floor(currentDoc.audio.duration_seconds / 60)}m {Math.floor(currentDoc.audio.duration_seconds % 60)}s
                      </p>
                    </div>
                    <div>
                      <p className="text-zinc-500">Created</p>
                      <p className="text-zinc-200 font-medium">{new Date(currentDoc.created_at).toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-zinc-500">Format</p>
                      <p className="text-zinc-200 font-medium">Podcast · 2 Hosts</p>
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
      <footer className="border-t border-zinc-800/50 mt-16 py-6 text-center text-xs text-zinc-700">
        PaperPod · Documents to Podcasts with Real-time Q&A · Built with ❤️
      </footer>
    </div>
  );
}

export default App;
