interface Claims {
  exp?: unknown;
  iat?: unknown;
}

/** Lee los claims de un JWT sin verificarlo: la firma la comprueba la API. */
function readClaims(token: string): Claims | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const claims = JSON.parse(atob(padded)) as unknown;
    return claims && typeof claims === "object" ? claims : null;
  } catch {
    return null;
  }
}

/**
 * Momento (reloj local, ms) en que caduca el token. Si trae `iat`, se cuenta su vida
 * (`exp - iat`) desde que se recibió, para no depender de que el reloj del equipo esté en hora;
 * si no, se usa `exp` tal cual. Null si el token no se puede leer.
 */
export function localExpiry(token: string, receivedAt: number = Date.now()): number | null {
  const claims = readClaims(token);
  if (!claims || typeof claims.exp !== "number") return null;
  if (typeof claims.iat === "number") return receivedAt + (claims.exp - claims.iat) * 1000;
  return claims.exp * 1000;
}

/** Milisegundos que quedan hasta `expiresAt`; 0 si ya pasó o no se conoce. */
export function msUntil(expiresAt: number | null, now: number = Date.now()): number {
  if (expiresAt === null) return 0;
  return Math.max(0, expiresAt - now);
}
