import { useCallback, useState, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Clipboard, Camera, Type } from 'lucide-react';

const TABS = [
  { id: 'file', label: 'Upload File', icon: Upload },
  { id: 'text', label: 'Paste Text', icon: Type },
  { id: 'camera', label: 'Camera', icon: Camera },
];

export default function UploadZone({ onUpload, onUploadText, onUploadImage, isUploading }) {
  const [activeTab, setActiveTab] = useState('file');
  const [pastedText, setPastedText] = useState('');
  const [title, setTitle] = useState('');
  const cameraInputRef = useRef(null);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles[0]);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
    },
    maxFiles: 1,
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
    <div className="bg-zinc-900 rounded-2xl border border-zinc-700/50 overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-zinc-800">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-medium transition-all ${
                activeTab === tab.id
                  ? 'text-brand-300 bg-brand-600/10 border-b-2 border-brand-500'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'file' && (
          <div
            {...getRootProps()}
            className={`
              relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer
              transition-all duration-300 group
              ${isDragActive
                ? 'border-brand-400 bg-brand-400/10 scale-[1.02]'
                : 'border-zinc-700 hover:border-brand-500/50 hover:bg-zinc-800/50'
              }
              ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className={`
                w-14 h-14 rounded-2xl flex items-center justify-center
                ${isDragActive ? 'bg-brand-500/20' : 'bg-zinc-800 group-hover:bg-brand-500/10'}
                transition-colors duration-300
              `}>
                {isDragActive ? (
                  <FileText className="w-7 h-7 text-brand-400" />
                ) : (
                  <Upload className="w-7 h-7 text-zinc-400 group-hover:text-brand-400 transition-colors" />
                )}
              </div>
              <div>
                <p className="font-semibold text-zinc-200">
                  {isDragActive ? 'Drop your document here' : 'Upload a Document'}
                </p>
                <p className="text-sm text-zinc-500 mt-1">
                  PDF, DOCX, or TXT
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'text' && (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-brand-500"
            />
            <textarea
              placeholder="Paste your text here... (articles, notes, anything)"
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              rows={6}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-brand-500 resize-none"
            />
            <button
              onClick={handlePasteSubmit}
              disabled={isUploading || !pastedText.trim()}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all flex items-center justify-center gap-2"
            >
              <Clipboard className="w-4 h-4" />
              Create Podcast from Text
            </button>
          </div>
        )}

        {activeTab === 'camera' && (
          <div className="text-center space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-zinc-800 flex items-center justify-center mx-auto">
              <Camera className="w-7 h-7 text-zinc-400" />
            </div>
            <div>
              <p className="font-semibold text-zinc-200">Take a Photo</p>
              <p className="text-sm text-zinc-500 mt-1">
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
              className="py-2.5 px-6 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-medium rounded-xl transition-all"
            >
              Open Camera
            </button>
          </div>
        )}

        {isUploading && (
          <div className="flex items-center justify-center gap-2 text-brand-400 mt-4">
            <div className="w-4 h-4 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium">Processing your document...</span>
          </div>
        )}
      </div>
    </div>
  );
}
