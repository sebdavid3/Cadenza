import { create } from "zustand";
import type { UserRead } from "../types";

/** Clave de `sessionStorage` donde vive el token mientras dure la pestaña (ADR-0020). */
export const TOKEN_STORAGE_KEY = "cadenza.token";

export type AuthStatus = "restoring" | "anonymous" | "authenticated";

/** Motivo por el que se cerró la sesión sin que la persona lo pidiera. */
export type SessionEndReason = "expired";

interface AuthState {
  status: AuthStatus;
  token: string | null;
  user: UserRead | null;
  endReason: SessionEndReason | null;
  signIn: (token: string, user: UserRead) => void;
  signOut: (reason?: SessionEndReason) => void;
  finishRestoring: () => void;
  clearEndReason: () => void;
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readStoredToken(): string | null {
  try {
    return storage()?.getItem(TOKEN_STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

function writeStoredToken(token: string | null) {
  try {
    const store = storage();
    if (!store) return;
    if (token) store.setItem(TOKEN_STORAGE_KEY, token);
    else store.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Sin almacenamiento (modo privado estricto): la sesión vive solo en memoria.
  }
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: "restoring",
  token: null,
  user: null,
  endReason: null,
  signIn: (token, user) => {
    writeStoredToken(token);
    set({ status: "authenticated", token, user, endReason: null });
  },
  signOut: (reason) => {
    writeStoredToken(null);
    set({ status: "anonymous", token: null, user: null, endReason: reason ?? null });
  },
  finishRestoring: () => {
    set((state) => (state.status === "restoring" ? { status: "anonymous" } : state));
  },
  clearEndReason: () => {
    set({ endReason: null });
  },
}));
