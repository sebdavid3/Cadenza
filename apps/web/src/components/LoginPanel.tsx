import { useState } from "react";

import { fetchMe, login } from "../api/client";
import type { UserProfile } from "../types";

interface LoginPanelProps {
  onLoggedIn: (user: UserProfile) => void;
}

export function LoginPanel({ onLoggedIn }: LoginPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!username || !password) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      const user = await fetchMe();
      onLoggedIn(user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Error al iniciar sesión");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload">
      <h1>Cadenza · Iniciar sesión</h1>
      <p className="muted">Ingresa tus credenciales para acceder al editor HITL.</p>
      <form onSubmit={handleSubmit} style={{ marginTop: "1.5rem", textAlign: "left" }}>
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.25rem" }}>
            Usuario
          </label>
          <input
            type="text"
            value={username}
            disabled={busy}
            autoComplete="username"
            required
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", font: "inherit", border: "1px solid #ccc" }}
          />
        </div>
        <div style={{ marginBottom: "1.25rem" }}>
          <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.25rem" }}>
            Contraseña
          </label>
          <input
            type="password"
            value={password}
            disabled={busy}
            autoComplete="current-password"
            required
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", font: "inherit", border: "1px solid #ccc" }}
          />
        </div>
        <button
          type="submit"
          disabled={busy || !username || !password}
          style={{
            width: "100%",
            padding: "0.75rem",
            background: "#111",
            color: "#fff",
            border: "none",
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          {busy ? "Iniciando sesión…" : "Iniciar sesión"}
        </button>
      </form>
      {error && (
        <p className="error" style={{ marginTop: "1rem", fontSize: "0.9rem" }}>
          {error}
        </p>
      )}
    </div>
  );
}
