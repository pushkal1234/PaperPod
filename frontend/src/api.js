import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const TOKEN_KEY = 'paperpod:token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

// Attach the bearer token (if any) to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On an expired/invalid token, drop it and let the app fall back to logged-out.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      clearToken();
      if (onUnauthorized) onUnauthorized();
    }
    return Promise.reject(error);
  }
);

// ── Auth ──
export async function register(email, password, name) {
  const res = await api.post('/auth/register', { email, password, name });
  if (res.data?.token) setToken(res.data.token);
  return res.data;
}

export async function login(email, password) {
  const res = await api.post('/auth/login', { email, password });
  if (res.data?.token) setToken(res.data.token);
  return res.data;
}

export async function googleSignIn(idToken) {
  const res = await api.post('/auth/google', { id_token: idToken });
  if (res.data?.token) setToken(res.data.token);
  return res.data;
}

export async function getMe() {
  const res = await api.get('/auth/me');
  return res.data;
}

export function logout() {
  clearToken();
}

export async function submitFeedback({ rating, comment, source = 'signout' }) {
  const res = await api.post('/feedback', { rating, comment, source });
  return res.data;
}

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

// ── Billing (Dodo Payments) ──
// Public flags so the app knows whether to show any upgrade/paywall UI at all.
export async function getBillingConfig() {
  const res = await api.get('/billing/config');
  return res.data;
}

// Create a hosted Dodo checkout session; returns { url } to redirect to.
export async function createCheckout() {
  const res = await api.post('/billing/checkout');
  return res.data;
}

// Self-service customer portal (manage/cancel subscription); returns { url }.
export async function getBillingPortal() {
  const res = await api.get('/billing/portal');
  return res.data;
}

// ── Analytics (My Podcasts dashboard) ──
export async function getStats() {
  const res = await api.get('/documents/stats');
  return res.data;
}
