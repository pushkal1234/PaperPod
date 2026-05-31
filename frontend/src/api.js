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

export async function uploadText(text, title = 'Pasted text') {
  const formData = new FormData();
  formData.append('text', text);
  formData.append('title', title);
  const res = await api.post('/documents/text', formData);
  return res.data;
}

export async function uploadImage(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/documents/image', formData);
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

export async function deleteDocument(docId) {
  const res = await api.delete(`/documents/${docId}`);
  return res.data;
}

export async function askQuestion(docId, { text, audioBlob, searchMode = 'document' }) {
  const formData = new FormData();
  formData.append('doc_id', docId);
  formData.append('search_mode', searchMode);
  if (audioBlob) {
    formData.append('audio', audioBlob, 'question.wav');
  }
  if (text) {
    formData.append('question_text', text);
  }
  const res = await api.post('/qa/ask', formData);
  return res.data;
}

export async function getHealth() {
  const res = await api.get('/health');
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

export async function createShare(docId) {
  const res = await api.post(`/share/create/${docId}`);
  return res.data;
}

export async function getSharedPodcast(token) {
  const res = await api.get(`/share/${token}`);
  return res.data;
}
