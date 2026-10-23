import { create } from "zustand";
import type { UserRead } from "../types";

/** Claves de `sessionStorage`: el token y su caducidad en el reloj local (ADR-0020). */
export const TOKEN_STORAGE_KEY = "cadenza.token";
export const EXPIRY_STORAGE_KEY = "cadenza.token.caduca";

/**
 * `restoring`: comprobando la sesión guardada; `unreachable`: hay un token guardado pero la
 * API no respondió al comprobarlo (se conserva y se puede reintentar).
 */
export type AuthStatus = "restoring" | "unreachable" | "anonymous" | "authenticated";

/** Por qué terminó la última sesión: caducó (se avisa) o la persona salió (no se recuerda ruta). */
export type SessionEndReason = "expired" | "signed-out";

interface AuthState {
  status: AuthStatus;
  token: string | null;
  user: UserRead | null;
  /** Caducidad del token en el reloj local, en ms. */
  expiresAt: number | null;
  endReason: SessionEndReason | null;
  signIn: (token: string, user: UserRead, expiresAt: number | null) => void;
  signOut: (reason?: SessionEndReason) => void;
  finishRestoring: () => void;
  markUnreachable: () => void;
  startRestoring: () => void;
  clearEndReason: () => void;
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readStoredSession(): { token: string; expiresAt: number | null } | null {
  try {
    const store = storage();
    const token = store?.getItem(TOKEN_STORAGE_KEY);
    if (!token) return null;
    const expiresAt = Number(store?.getItem(EXPIRY_STORAGE_KEY));
    return { token, expiresAt: Number.isFinite(expiresAt) && expiresAt > 0 ? expiresAt : null };
  } catch {
    return null;
  }
}

function writeStoredSession(token: string | null, expiresAt: number | null) {
  try {
    const store = storage();
    if (!store) return;
    if (token) {
      store.setItem(TOKEN_STORAGE_KEY, token);
      if (expiresAt) store.setItem(EXPIRY_STORAGE_KEY, String(expiresAt));
      else store.removeItem(EXPIRY_STORAGE_KEY);
    } else {
      store.removeItem(TOKEN_STORAGE_KEY);
      store.removeItem(EXPIRY_STORAGE_KEY);
    }
  } catch {
    // Sin almacenamiento (modo privado estricto): la sesión vive solo en memoria.
  }
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: "restoring",
  token: null,
  user: null,
  expiresAt: null,
  endReason: null,
  signIn: (token, user, expiresAt) => {
    writeStoredSession(token, expiresAt);
    set({ status: "authenticated", token, user, expiresAt, endReason: null });
  },
  signOut: (reason) => {
    writeStoredSession(null, null);
    set({
      status: "anonymous",
      token: null,
      user: null,
      expiresAt: null,
      endReason: reason ?? null,
    });
  },
  finishRestoring: () => {
    set((state) => (state.status === "restoring" ? { status: "anonymous" } : state));
  },
  markUnreachable: () => {
    set((state) => (state.status === "restoring" ? { status: "unreachable" } : state));
  },
  startRestoring: () => {
    set({ status: "restoring" });
  },
  clearEndReason: () => {
    set({ endReason: null });
  },
}));
