const API_BASE = "/api";

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchBlob(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

// ============ GENERATION ============
export async function generateStreaming(payload) {
  const requestId = crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2);
  const res = await fetch(`${API_BASE}/generate_streaming`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, request_id: requestId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "生成失败");
  }
  const sessionId = res.headers.get("X-Session-Id");
  const blob = await res.blob();
  return { sessionId, blob };
}

export function getGenerationStatus(sessionId) {
  return fetchJSON(`/generation_status/${sessionId}`);
}

export function downloadPodcast(sessionId) {
  return fetchBlob(`/download_podcast/${sessionId}`);
}

// ============ RECOMMENDATIONS ============
export function getRecommendations({ title, content }) {
  return fetchJSON("/recommend", {
    method: "POST",
    body: JSON.stringify({ title, content }),
  });
}

// ============ EXPLORE ============
export function getExplore(platform = "all") {
  return fetchJSON(`/explore?platform=${encodeURIComponent(platform)}`);
}

// ============ PARSE ============
export function parseArticle({ url, text }) {
  return fetchJSON("/parse", {
    method: "POST",
    body: JSON.stringify({ url, text }),
  });
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `上传失败 HTTP ${res.status}`);
  }
  return res.json();
}

// ============ GENERATE SCRIPT ============
export function generateScript({ clean_text }) {
  return fetchJSON("/generate_script", {
    method: "POST",
    body: JSON.stringify({ clean_text }),
  });
}

// ============ TTS ============
export async function generateTTS(payload) {
  const res = await fetch(`${API_BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "语音合成失败");
  }
  const blob = await res.blob();
  return { blob };
}

// ============ DRAFT ============
export function getDraft(topic) {
  return fetchJSON("/draft", {
    method: "POST",
    body: JSON.stringify({ topic }),
  });
}

// ============ SUBSCRIPTIONS ============
export function getSubscriptions() {
  return fetchJSON("/subscriptions");
}

export function addSubscription(url) {
  return fetchJSON("/subscriptions", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function deleteSubscription(id) {
  return fetch(`${API_BASE}/subscriptions?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ============ PODCASTS ============
export function getPodcasts() {
  return fetchJSON("/podcasts");
}

// ============ NOTES ============
export function getNotes() {
  return fetchJSON("/notes");
}

export function addNote({ session_id, title, content }) {
  return fetchJSON("/notes", {
    method: "POST",
    body: JSON.stringify({ session_id, title, content }),
  });
}

export function updateNote(id, { title, content }) {
  return fetchJSON(`/notes/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ title, content }),
  });
}

export function deleteNote(id) {
  return fetch(`${API_BASE}/notes?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function updateSubscription(id, { name, auto_generate }) {
  return fetchJSON(`/subscriptions/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ name, auto_generate }),
  });
}

export function generateSubscription(id) {
  return fetchJSON("/subscriptions/generate", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

// ============ FAVORITES ============
export function getFavorites() {
  return fetchJSON("/favorites");
}

export function addFavorite(session_id) {
  return fetchJSON("/favorites", {
    method: "POST",
    body: JSON.stringify({ session_id }),
  });
}

export function deleteFavorite(id) {
  return fetch(`${API_BASE}/favorites?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ============ HISTORY ============
export function getHistory() {
  return fetchJSON("/history");
}

export function addHistory({ session_id, progress, duration }) {
  return fetchJSON("/history", {
    method: "POST",
    body: JSON.stringify({ session_id, progress, duration }),
  });
}

export function deleteHistory(id) {
  return fetch(`${API_BASE}/history?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ============ COLLECTIONS ============
export function getCollections() {
  return fetchJSON("/collections");
}

export function addCollection({ name, session_ids = [] }) {
  return fetchJSON("/collections", {
    method: "POST",
    body: JSON.stringify({ name, session_ids }),
  });
}

export function updateCollection({ id, name, session_ids }) {
  return fetchJSON("/collections", {
    method: "PUT",
    body: JSON.stringify({ id, name, session_ids }),
  });
}

export function deleteCollection(id) {
  return fetch(`${API_BASE}/collections?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ============ SEARCH ============
export function search(q) {
  return fetchJSON(`/search?q=${encodeURIComponent(q)}`);
}
