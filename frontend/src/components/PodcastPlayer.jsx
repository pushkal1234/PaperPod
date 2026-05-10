import { useRef, useState, useEffect } from 'react';
import { Play, Pause, SkipBack, SkipForward, Volume2 } from 'lucide-react';

export default function PodcastPlayer({ audioUrl, title, dialogueScript }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showTranscript, setShowTranscript] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onLoadedMetadata = () => setDuration(audio.duration);
    const onEnded = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.removeEventListener('ended', onEnded);
    };
  }, [audioUrl]);

  const togglePlay = () => {
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const seek = (seconds) => {
    audioRef.current.currentTime = Math.max(
      0,
      Math.min(audioRef.current.currentTime + seconds, duration)
    );
  };

  const handleSeekBar = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    audioRef.current.currentTime = pct * duration;
  };

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="bg-gradient-to-br from-zinc-900 to-zinc-800 rounded-2xl p-6 border border-zinc-700/50">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center animate-float">
          <Volume2 className="w-6 h-6 text-white" />
        </div>
        <div>
          <h3 className="font-semibold text-zinc-100 text-lg">{title}</h3>
          <p className="text-sm text-zinc-500">AI-generated podcast</p>
        </div>
      </div>

      {/* Seek bar */}
      <div
        className="w-full h-2 bg-zinc-700 rounded-full cursor-pointer mb-2 group"
        onClick={handleSeekBar}
      >
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-purple-500 rounded-full relative transition-all"
          style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
        >
          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>

      <div className="flex justify-between text-xs text-zinc-500 mb-4">
        <span>{fmt(currentTime)}</span>
        <span>{fmt(duration)}</span>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-6">
        <button
          onClick={() => seek(-15)}
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipBack className="w-5 h-5" />
        </button>

        <button
          onClick={togglePlay}
          className="w-14 h-14 rounded-full bg-brand-600 hover:bg-brand-500 flex items-center justify-center text-white shadow-lg shadow-brand-600/30 hover:shadow-brand-500/40 transition-all active:scale-95"
        >
          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
        </button>

        <button
          onClick={() => seek(15)}
          className="w-10 h-10 rounded-full flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all"
        >
          <SkipForward className="w-5 h-5" />
        </button>
      </div>

      {/* Transcript toggle */}
      {dialogueScript && (
        <div className="mt-6">
          <button
            onClick={() => setShowTranscript(!showTranscript)}
            className="text-sm text-brand-400 hover:text-brand-300 transition-colors"
          >
            {showTranscript ? 'Hide' : 'Show'} Transcript
          </button>
          {showTranscript && (
            <div className="mt-3 max-h-64 overflow-y-auto bg-zinc-800/50 rounded-xl p-4 text-sm text-zinc-300 space-y-2 border border-zinc-700/50">
              {dialogueScript.split('\n').filter(l => l.trim()).map((line, i) => {
                const isHost = line.toLowerCase().startsWith('host:');
                return (
                  <p key={i} className={isHost ? 'text-brand-300' : 'text-emerald-300'}>
                    {line}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
