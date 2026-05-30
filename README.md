# 🎧 PaperPod

**Documents → Podcast-style conversations → Real-time voice Q&A**

Upload any document (PDF, DOCX, TXT) → AI generates a natural two-host podcast conversation → Listen & ask real-time questions with voice.

[![Demo](https://img.shields.io/badge/demo-watch%20video-blue?style=flat-square)](#demo)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](#license)

---

## ✨ Features

- **Document to Podcast** — Upload a PDF/DOCX/TXT, paste text, or snap a photo and get an engaging two-host podcast conversation
- **Dual AI Voices** — Host + Guest with natural speech synthesis
- **Real-time Q&A** — Ask questions via voice or text, get audio answers
- **No GPU Required** — Runs entirely on CPU using cloud AI APIs (free tier)
- **Privacy First** — Documents stay on your machine; only text is sent to LLM API

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + Vite + Tailwind CSS |
| **Backend** | FastAPI (Python 3.10+) |
| **LLM** | Groq Llama 3.1 8B (free tier — generous limits) |
| **STT** | Groq Whisper (free tier) |
| **TTS** | edge-tts (free, no key needed) |
| **Image OCR** | Google Gemini Vision (free tier) |
| **Retrieval** | In-memory keyword search (demo) |
| **Database** | SQLite (via SQLAlchemy async) |

---

## 🚀 Quick Start — Local Setup

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| **Python** | 3.10 or higher | [python.org](https://www.python.org/downloads/) or `brew install python` |
| **Node.js** | 18 or higher | [nodejs.org](https://nodejs.org/) or `brew install node` |
| **ffmpeg** | any | `brew install ffmpeg` (macOS) / `sudo apt install ffmpeg` (Ubuntu) / [ffmpeg.org](https://ffmpeg.org/download.html) (Windows) |
| **Git** | any | `brew install git` or [git-scm.com](https://git-scm.com/) |

### Step 1: Get free API keys

**Groq** (for LLM + STT):
1. Go to [console.groq.com/keys](https://console.groq.com/keys)
2. Sign up (free — no credit card needed)
3. Create an API key and copy it

**Google AI Studio** (for Image OCR only):
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account (free — no credit card needed)
3. Create an API key and copy it

### Step 2: Clone the repo

```bash
git clone https://github.com/pushkal1234/PaperPod.git
cd PaperPod
```

### Step 3: Set up the Backend

```bash
cd backend

# Copy the example env file and add your API keys
cp .env.example .env
# Open .env in any editor and replace the placeholders with your actual keys
# Example:
#   GROQ_API_KEY=gsk_...
#   GOOGLE_API_KEY=AIza...

# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows (Command Prompt)
# venv\Scripts\Activate.ps1     # Windows (PowerShell)

# Upgrade pip (recommended)
pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn app.main:app --reload --port 8000
```

You should see: `INFO: Application startup complete.`

### Step 4: Set up the Frontend (new terminal)

```bash
# Open a new terminal tab/window, navigate to the project
cd PaperPod/frontend

# Install Node.js dependencies
npm install

# Start the development server
npm run dev
```

You should see: `Local: http://localhost:5173/`

### Step 5: Use PaperPod

1. Open **http://localhost:5173** in your browser
2. Upload a PDF, DOCX, or TXT document
3. Wait ~2-3 minutes for podcast generation
4. Listen to your AI-generated podcast
5. Ask questions via voice or text in the Q&A panel

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| `pip install` fails with `pkg_resources` error | Run `pip install --upgrade pip setuptools wheel` first |
| Backend: `No module named 'greenlet'` | Run `pip install greenlet` |
| Backend: `Address already in use` on port 8000 | Run `lsof -ti:8000 \| xargs kill -9` then restart |
| Groq rate limit error | Wait a few seconds and retry — free tier has generous but finite limits |
| Gemini API quota error | Only used for image OCR; if hitting limits, wait and retry |
| Frontend: blank page | Make sure backend is running on port 8000 first |
| `ffmpeg not found` | Install ffmpeg: `brew install ffmpeg` (macOS) |

## Project Structure

```
PaperPod/
├── backend/
│   ├── .env.example              # Environment config (copy to .env)
│   ├── requirements.txt           # Python dependencies
│   └── app/
│       ├── main.py               # FastAPI entry point
│       ├── config.py             # Settings & configuration
│       ├── database.py           # SQLAlchemy models (documents ↔ audio_files 1:1)
│       ├── routes/
│       │   ├── documents.py      # Upload, list, status endpoints
│       │   ├── audio.py          # Stream podcast MP3
│       │   └── qa.py             # Q&A: voice/text question → audio answer
│       └── services/
│           ├── document_service.py   # PDF/DOCX/TXT extraction + chunking
│           ├── vector_service.py     # In-memory chunk store + keyword retrieval
│           ├── llm_service.py        # Groq LLM (podcast script + Q&A)
│           ├── tts_service.py        # edge-tts (Host + Guest voices)
│           ├── stt_service.py        # Groq Whisper speech-to-text
│           └── image_service.py      # Google Gemini Vision OCR (camera upload)
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Main app (upload → processing → player)
│   │   ├── api.js                # API client (axios)
│   │   ├── components/
│   │   │   ├── UploadZone.jsx    # File upload + text paste + camera capture
│   │   │   ├── PodcastPlayer.jsx # Audio player + transcript view
│   │   │   └── QAPanel.jsx       # Voice/text Q&A chat interface
│   │   └── hooks/
│   │       └── useAudioRecorder.js  # MediaRecorder hook for mic input
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
├── .gitignore
└── README.md
```

## AI Models & Architecture

```mermaid
flowchart LR
    subgraph GROQ["☁️ Groq (Free Tier)"]
        LLM["🧠 Llama 3.1 8B\n─────────────────\n• Podcast script generation\n• Q&A answering\n• Fast & reliable"]
        STT["🎤 Whisper\n─────────────────\n• Speech-to-text\n• Voice question transcription\n• Multi-language support"]
    end

    subgraph TTS["🔊 edge-tts (Free, No Key)"]
        HOST["Host: AriaNeural"]
        GUEST["Guest: GuyNeural"]
    end

    subgraph OCR["📷 Google AI Studio (Free)"]
        VISION["Gemini Vision\n─────────────────\n• Image OCR\n• Camera upload"]
    end

    subgraph PIPELINE["⚙️ How They Connect"]
        DOC["📄 Document"] --> LLM
        CAM["📷 Camera"] --> VISION --> LLM
        LLM -->|dialogue script| HOST
        LLM -->|dialogue script| GUEST
        HOST -->|podcast .mp3| PLAY["🎧 Player"]
        GUEST -->|podcast .mp3| PLAY
        PLAY -->|user speaks| STT
        STT -->|question text| LLM
        LLM -->|answer text| GUEST
        GUEST -->|answer .mp3| PLAY
    end

    style GROQ fill:#E8F8F5,stroke:#1ABC9C,stroke-width:2px
    style TTS fill:#FFF3E0,stroke:#FF9800,stroke-width:2px
    style OCR fill:#E3F2FD,stroke:#2196F3,stroke-width:2px
    style PIPELINE fill:#F4ECF7,stroke:#8E44AD,stroke-width:2px
```

| Model | Provider | Purpose | Cost |
|-------|----------|---------|------|
| **Llama 3.1 8B** | Groq | Podcast script generation + Q&A | Free |
| **Whisper** | Groq | Speech-to-text (voice questions) | Free |
| **edge-tts** | Microsoft Azure (via edge-tts) | TTS — Host (Aria) + Guest (Guy) | Free |
| **Gemini Vision** | Google AI Studio | Image OCR (camera upload) | Free |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload` | Upload file (PDF/DOCX/TXT), starts podcast generation |
| `POST` | `/api/documents/text` | Paste text, starts podcast generation |
| `POST` | `/api/documents/image` | Upload image (camera), OCR + podcast generation |
| `GET` | `/api/documents/{doc_id}` | Get document + audio status |
| `GET` | `/api/documents/list` | List all documents |
| `GET` | `/api/audio/{audio_id}` | Stream podcast audio |
| `POST` | `/api/qa/ask` | Ask question (text or voice) |
| `GET` | `/api/qa/audio/{qa_id}` | Get Q&A answer audio |
| `GET` | `/api/qa/history/{doc_id}` | Q&A history for a document |
