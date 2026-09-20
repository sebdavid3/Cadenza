/** Cliente HTTP de la API de Cadenza. */

import type {
  EditEvent,
  EditEventCreate,
  SessionDetail,
  TranscribeResponse,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
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
