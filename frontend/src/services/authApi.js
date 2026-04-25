const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function normalizeAuthError(payload, fallbackMessage) {
  if (!payload) return fallbackMessage;
  if (typeof payload === 'string') return payload;

  if (payload.detail) {
    if (typeof payload.detail === 'string') return payload.detail;
    if (payload.detail.message) return payload.detail.message;
    return JSON.stringify(payload.detail);
  }

  if (payload.message) return payload.message;
  return fallbackMessage;
}

export async function registerAPI({ username, email, password }) {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, email, password }),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(normalizeAuthError(payload, 'Registration failed'));
  }
  return payload;
}

export async function loginAPI({ username, password }) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(normalizeAuthError(payload, 'Login failed'));
  }
  return payload;
}
