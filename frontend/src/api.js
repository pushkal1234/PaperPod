import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
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
  const res = await api.get('/documents/');
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
  return `/api/audio/${audioId}`;
}

export function getQAAudioUrl(qaId) {
  return `/api/qa/audio/${qaId}`;
}
