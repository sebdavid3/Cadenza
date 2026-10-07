/** Cliente HTTP de la API de Cadenza con autenticación JWT (#45, #47, ADR-0012). */

import type {
  EditEvent,
  EditEventCreate,
  SessionDetail,
  TokenResponse,
  TranscribeResponse,
  UserProfile,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const TOKEN_KEY = "cadenza_access_token";

let inMemoryToken: string | null = null;

function getStorage(): Storage | null {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      return window.sessionStorage;
    }
    if (typeof globalThis !== "undefined" && (globalThis as unknown as { sessionStorage?: Storage }).sessionStorage) {
      return (globalThis as unknown as { sessionStorage: Storage }).sessionStorage;
    }
  } catch {
    return null;
  }
  return null;
}

export function getToken(): string | null {
  const storage = getStorage();
  if (storage) {
    try {
      return storage.getItem(TOKEN_KEY);
    } catch {
      return inMemoryToken;
    }
  }
  return inMemoryToken;
}

export function setToken(token: string | null): void {
  inMemoryToken = token;
  const storage = getStorage();
  if (storage) {
    try {
      if (token) {
        storage.setItem(TOKEN_KEY, token);
      } else {
        storage.removeItem(TOKEN_KEY);
      }
    } catch {
      // Ignorar fallos de cuota o permisos en storage
    }
  }
}

export function clearToken(): void {
  setToken(null);
}

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

function notifyUnauthorized(): void {
  clearToken();
  unauthorizedListeners.forEach((listener) => {
    try {
      listener();
    } catch {
      // Ignorar errores de listeners
    }
  });
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    notifyUnauthorized();
    const detail = await response.text();
    throw new Error(`API 401: ${detail}`);
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);

  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API ${response.status}: ${detail}`);
  }

  const tokenResponse = (await response.json()) as TokenResponse;
  setToken(tokenResponse.access_token);
  return tokenResponse;
}

export function fetchMe(): Promise<UserProfile> {
  return request<UserProfile>("/auth/me");
}

export function logout(): void {
  notifyUnauthorized();
}

export function transcribe(file: File): Promise<TranscribeResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<TranscribeResponse>("/transcribe", { method: "POST", body: form });
}

export function fetchSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${sessionId}`);
}

export function appendEdit(
  sessionId: string,
  payload: EditEventCreate,
): Promise<EditEvent> {
  return request<EditEvent>(`/sessions/${sessionId}/edits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
