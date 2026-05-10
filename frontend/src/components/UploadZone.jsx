import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText } from 'lucide-react';

export default function UploadZone({ onUpload, isUploading }) {
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

  return (
    <div
      {...getRootProps()}
      className={`
        relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer
        transition-all duration-300 group
        ${isDragActive
          ? 'border-brand-400 bg-brand-400/10 scale-[1.02]'
          : 'border-zinc-700 hover:border-brand-500/50 hover:bg-zinc-800/50'
        }
        ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-4">
        <div className={`
          w-16 h-16 rounded-2xl flex items-center justify-center
          ${isDragActive ? 'bg-brand-500/20' : 'bg-zinc-800 group-hover:bg-brand-500/10'}
          transition-colors duration-300
        `}>
          {isDragActive ? (
            <FileText className="w-8 h-8 text-brand-400" />
          ) : (
            <Upload className="w-8 h-8 text-zinc-400 group-hover:text-brand-400 transition-colors" />
          )}
        </div>
        <div>
          <p className="text-lg font-semibold text-zinc-200">
            {isDragActive ? 'Drop your document here' : 'Upload a Document'}
          </p>
          <p className="text-sm text-zinc-500 mt-1">
            PDF, DOCX, or TXT — we'll turn it into a podcast
          </p>
        </div>
        {isUploading && (
          <div className="flex items-center gap-2 text-brand-400">
            <div className="w-4 h-4 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium">Processing your document...</span>
          </div>
        )}
      </div>
    </div>
  );
}
