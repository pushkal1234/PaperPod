import { useState, useRef, useEffect } from 'react';
import { Mic, MicOff, Send, MessageCircle, Volume2, Loader2, Square, Play } from 'lucide-react';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { askQuestion, getQAAudioUrl } from '../api';

export default function QAPanel({ docId }) {
  const [messages, setMessages] = useState([]);
  const [textInput, setTextInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [playingAudioUrl, setPlayingAudioUrl] = useState(null);
  const [searchMode, setSearchMode] = useState('document');
  const [webSearchAvailable, setWebSearchAvailable] = useState(false);
  const { isRecording, startRecording, stopRecording } = useAudioRecorder();
  const messagesEndRef = useRef(null);
  const answerAudioRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const audio = answerAudioRef.current;
    if (!audio) return;

    const onEnded = () => setPlayingAudioUrl(null);

    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('ended', onEnded);
    };
  }, []);

  const handleSendText = async () => {
    if (!textInput.trim() || isLoading) return;
    const question = textInput.trim();
    setTextInput('');
    await submitQuestion({ text: question, searchMode: searchMode });
  };

  const handleVoiceToggle = async () => {
    if (isRecording) {
      const audioBlob = await stopRecording();
      if (audioBlob) {
        await submitQuestion({ audioBlob, searchMode: searchMode });
      }
    } else {
      await startRecording();
    }
  };

  const submitQuestion = async ({ text, audioBlob, searchMode = 'document' }) => {
    setIsLoading(true);
    setMessages(prev => [...prev, {
      type: 'question',
      text: text || '🎤 Voice question...',
      isVoice: !!audioBlob,
    }]);

    try {
      const res = await askQuestion(docId, { text, audioBlob, searchMode });
      if (res.web_search_available !== undefined) {
        setWebSearchAvailable(res.web_search_available);
      }
      setMessages(prev => {
        const updated = [...prev];
        if (audioBlob && updated.length > 0) {
          updated[updated.length - 1].text = res.question;
        }
        return [...updated, {
          type: 'answer',
          text: res.answer,
          audioUrl: getQAAudioUrl(res.qa_id),
          citations: res.citations || [],
          mode: res.search_mode || 'document',
        }];
      });
    } catch (err) {
      setMessages(prev => [...prev, {
        type: 'error',
        text: 'Something went wrong. Please try again.',
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const playAnswerAudio = (url) => {
    if (answerAudioRef.current) {
      if (playingAudioUrl === url) {
        // Same audio - toggle pause/play
        if (answerAudioRef.current.paused) {
          answerAudioRef.current.play();
        } else {
          answerAudioRef.current.pause();
        }
      } else {
        // Different audio - play new one
        answerAudioRef.current.src = url;
        answerAudioRef.current.play();
        setPlayingAudioUrl(url);
      }
    }
  };

  const stopAnswerAudio = () => {
    if (answerAudioRef.current) {
      answerAudioRef.current.pause();
      answerAudioRef.current.currentTime = 0;
      setPlayingAudioUrl(null);
    }
  };

  return (
    <div className="bg-zinc-900 rounded-2xl border border-zinc-700/50 flex flex-col h-[500px]">
      <audio ref={answerAudioRef} className="hidden" />

      {/* Header */}
      <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-5 h-5 text-brand-400" />
          <h3 className="font-semibold text-zinc-100">Ask About This Document</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Mode:</span>
          <button
            onClick={() => setSearchMode('document')}
            disabled={!webSearchAvailable && searchMode !== 'document'}
            className={`px-3 py-1.5 text-xs rounded-lg transition-all ${
              searchMode === 'document'
                ? 'bg-brand-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700'
            } ${!webSearchAvailable ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Doc only
          </button>
          <button
            onClick={() => setSearchMode('hybrid')}
            disabled={!webSearchAvailable}
            className={`px-3 py-1.5 text-xs rounded-lg transition-all ${
              searchMode === 'hybrid'
                ? 'bg-brand-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700'
            } ${!webSearchAvailable ? 'opacity-50 cursor-not-allowed' : ''}`}
            title={!webSearchAvailable ? 'Web search not configured' : 'Use document + web search'}
          >
            Doc + Web
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-zinc-600 mt-12">
            <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Ask anything about the document — type or use your mic</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.type === 'question' ? 'justify-end' : 'justify-start'}`}>
            <div className={`
              max-w-[80%] rounded-2xl px-4 py-3 text-sm
              ${msg.type === 'question'
                ? 'bg-brand-600 text-white rounded-br-md'
                : msg.type === 'error'
                  ? 'bg-red-900/30 text-red-300 border border-red-800/50'
                  : 'bg-zinc-800 text-zinc-200 rounded-bl-md'
              }
            `}>
              <p className="whitespace-pre-wrap">{msg.text}</p>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/50">
                  <p className="text-[10px] text-zinc-500 mb-1">Sources:</p>
                  <div className="flex flex-wrap gap-1">
                    {msg.citations.map((cit, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] bg-zinc-700/50 text-zinc-400 px-2 py-0.5 rounded"
                      >
                        {cit.title || cit.url || cit.note || `Source ${idx + 1}`}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {msg.audioUrl && (
                <div className="mt-2 flex items-center gap-2">
                  <button
                    onClick={() => playAnswerAudio(msg.audioUrl)}
                    className="flex items-center gap-1.5 text-xs text-brand-300 hover:text-brand-200 transition-colors"
                  >
                    <Volume2 className="w-3.5 h-3.5" />
                    {playingAudioUrl === msg.audioUrl ? 'Pause' : 'Play audio answer'}
                  </button>
                  {playingAudioUrl === msg.audioUrl && (
                    <button
                      onClick={stopAnswerAudio}
                      className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
                      title="Stop"
                    >
                      <Square className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 rounded-2xl rounded-bl-md px-4 py-3">
              <Loader2 className="w-5 h-5 text-brand-400 animate-spin" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="p-4 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <button
            onClick={handleVoiceToggle}
            disabled={isLoading}
            className={`
              w-10 h-10 rounded-full flex items-center justify-center transition-all shrink-0
              ${isRecording
                ? 'bg-red-500 text-white animate-pulse shadow-lg shadow-red-500/30'
                : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
              }
              ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
          </button>

          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendText()}
            placeholder={isRecording ? 'Recording...' : 'Type your question...'}
            disabled={isLoading || isRecording}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30 disabled:opacity-50 transition-all"
          />

          <button
            onClick={handleSendText}
            disabled={isLoading || !textInput.trim()}
            className="w-10 h-10 rounded-full bg-brand-600 hover:bg-brand-500 flex items-center justify-center text-white shrink-0 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        {isRecording && (
          <p className="text-xs text-red-400 mt-2 text-center animate-pulse">
            🔴 Recording... Click mic again to stop and send
          </p>
        )}
      </div>
    </div>
  );
}
