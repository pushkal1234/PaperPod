import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/documents/upload', formData);
  return res.data;
}

export async function getDocument(docId) {
  const res = await api.get(`/documents/${docId}`);
  return res.data;
}

export async function listDocuments() {
  const res = await api.get('/documents/list');
  return res.data;
}

export async function askQuestion(docId, { text, audioBlob }) {
  const formData = new FormData();
  formData.append('doc_id', docId);
  if (audioBlob) {
    formData.append('audio', audioBlob, 'question.wav');
  }
  if (text) {
    formData.append('question_text', text);
  }
  const res = await api.post('/qa/ask', formData);
  return res.data;
}

export async function getQAHistory(docId) {
  const res = await api.get(`/qa/history/${docId}`);
  return res.data;
}

export function getAudioUrl(audioId) {
  return `${API_BASE}/api/audio/${audioId}`;
}

export function getQAAudioUrl(qaId) {
  return `${API_BASE}/api/qa/audio/${qaId}`;
}
