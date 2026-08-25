import { useCallback, useState, useRef, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Clipboard, Camera, Type, AlertCircle } from 'lucide-react';

const TABS = [
  { id: 'file', label: 'Upload File', icon: Upload },
  { id: 'text', label: 'Paste Text', icon: Type },
  { id: 'camera', label: 'Camera', icon: Camera },
];

// Keep in sync with backend MAX_UPLOAD_MB (config.py).
const MAX_UPLOAD_MB = 25;

export default function UploadZone({ onUpload, onUploadText, onUploadImage, isUploading, initialText = '', initialTitle = '' }) {
  const [activeTab, setActiveTab] = useState(initialText ? 'text' : 'file');
  const [pastedText, setPastedText] = useState(initialText);
  const [title, setTitle] = useState(initialTitle);
  const [rejectionMsg, setRejectionMsg] = useState(null);
  const cameraInputRef = useRef(null);

  // Prefill the text composer when the app is opened via an extension /
  // context-menu handoff (e.g. ?type=text&text=...). Runs when the params
  // arrive after mount.
  useEffect(() => {
    if (initialText) {
      setPastedText(initialText);
      setTitle(initialTitle || '');
      setActiveTab('text');
    }
  }, [initialText, initialTitle]);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      setRejectionMsg(null);
      onUpload(acceptedFiles[0]);
    }
  }, [onUpload]);

  // Surface why a dropped file was refused instead of silently ignoring it.
  const onDropRejected = useCallback((rejections) => {
    const first = rejections?.[0]?.errors?.[0];
    if (!first) return;
    if (first.code === 'file-too-large') {
      setRejectionMsg(`That file is too large. Please keep uploads under ${MAX_UPLOAD_MB} MB.`);
    } else if (first.code === 'file-invalid-type') {
      setRejectionMsg('Unsupported file type. Upload a PDF, DOCX, PPTX, TXT, or image (PNG/JPG/WEBP).');
    } else if (first.code === 'too-many-files') {
      setRejectionMsg('Please upload one file at a time.');
    } else {
      setRejectionMsg(first.message || 'That file could not be accepted.');
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'text/plain': ['.txt'],
      'image/*': ['.png', '.jpg', '.jpeg', '.webp'],
    },
    maxFiles: 1,
    maxSize: MAX_UPLOAD_MB * 1024 * 1024,
    disabled: isUploading,
  });

  const handlePasteSubmit = () => {
    if (pastedText.trim()) {
      onUploadText(pastedText.trim(), title.trim() || 'Pasted text');
      setPastedText('');
      setTitle('');
    }
  };

  const handleCameraCapture = (e) => {
    const file = e.target.files[0];
    if (file) {
      onUploadImage(file);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-paper-300 shadow-soft overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-paper-200" role="tablist" aria-label="Upload method">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`upload-panel-${tab.id}`}
              id={`upload-tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-3.5 text-xs font-semibold transition-all ${
                selected
                  ? 'text-brand-700 bg-brand-50 border-b-2 border-brand-500'
                  : 'text-stone-400 hover:text-stone-600 hover:bg-paper-50'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div
        className="p-6"
        role="tabpanel"
        id={`upload-panel-${activeTab}`}
        aria-labelledby={`upload-tab-${activeTab}`}
      >
        {activeTab === 'file' && (
          <div
            {...getRootProps()}
            className={`
              relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer
              transition-all duration-300 group
              ${isDragActive
                ? 'border-brand-400 bg-brand-50 scale-[1.02]'
                : 'border-paper-400 hover:border-brand-400 hover:bg-brand-50/50'
              }
              ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className={`
                w-14 h-14 rounded-2xl flex items-center justify-center
                ${isDragActive ? 'bg-brand-100' : 'bg-brand-50 group-hover:bg-brand-100'}
                transition-colors duration-300
              `}>
                {isDragActive ? (
                  <FileText className="w-7 h-7 text-brand-600" />
                ) : (
                  <Upload className="w-7 h-7 text-brand-600 transition-colors" />
                )}
              </div>
              <div>
                <p className="font-semibold text-stone-800 text-base">
                  {isDragActive ? 'Drop your document here' : 'Upload a Document'}
                </p>
                <p className="text-sm text-stone-400 mt-1">
                  PDF, DOCX, PPTX, TXT, or Image (PNG, JPG) · up to {MAX_UPLOAD_MB} MB
                </p>
              </div>
            </div>
          </div>
        )}

        {rejectionMsg && activeTab === 'file' && (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-600"
          >
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{rejectionMsg}</span>
          </div>
        )}

        {activeTab === 'text' && (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-paper-50 border border-paper-300 rounded-xl px-4 py-2.5 text-sm text-stone-800 placeholder-stone-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-500/20 transition-all"
            />
            <textarea
              placeholder="Paste your text here... (articles, notes, anything)"
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              rows={6}
              className="w-full bg-paper-50 border border-paper-300 rounded-xl px-4 py-3 text-sm text-stone-800 placeholder-stone-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-500/20 resize-none transition-all"
            />
            <button
              onClick={handlePasteSubmit}
              disabled={isUploading || !pastedText.trim()}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl shadow-glow transition-all flex items-center justify-center gap-2"
            >
              <Clipboard className="w-4 h-4" />
              Create Podcast from Text
            </button>
          </div>
        )}

        {activeTab === 'camera' && (
          <div className="text-center space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-brand-50 flex items-center justify-center mx-auto">
              <Camera className="w-7 h-7 text-brand-600" />
            </div>
            <div>
              <p className="font-semibold text-stone-800 text-base">Take a Photo</p>
              <p className="text-sm text-stone-400 mt-1">
                Snap a photo of a document page — AI will extract text and generate a podcast
              </p>
            </div>
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleCameraCapture}
              className="hidden"
            />
            <button
              onClick={() => cameraInputRef.current?.click()}
              disabled={isUploading}
              className="py-2.5 px-6 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-semibold rounded-xl shadow-glow transition-all"
            >
              Open Camera
            </button>
          </div>
        )}

        {isUploading && (
          <div className="flex items-center justify-center gap-2 text-brand-600 mt-4">
            <div className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium">Processing your document...</span>
          </div>
        )}
      </div>
    </div>
  );
}
