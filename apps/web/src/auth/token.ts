/** Lee el `exp` (segundos desde la época) de un JWT sin verificarlo: la firma la comprueba la API. */
export function tokenExpiresAt(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const claims = JSON.parse(atob(padded)) as { exp?: unknown };
    return typeof claims.exp === "number" ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Milisegundos que le quedan al token; 0 si ya caducó o no se puede leer. */
export function msUntilExpiry(token: string, now: number = Date.now()): number {
  const expiresAt = tokenExpiresAt(token);
  if (expiresAt === null) return 0;
  return Math.max(0, expiresAt - now);
}
