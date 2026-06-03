const API_BASE = (import.meta.env.VITE_API_BASE || runtimeApiBase()).replace(/\/$/, "");

function runtimeApiBase() {
  const isLocalFrontend =
    window.location.protocol === "file:" ||
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
  return isLocalFrontend ? "http://127.0.0.1:8000" : window.location.origin;
}

export async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: authHeaders()
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders(),
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export function authHeaders() {
  const token = localStorage.getItem("token");
  const csrf = localStorage.getItem("csrf_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(csrf ? { "X-CSRF-Token": csrf } : {})
  };
}
