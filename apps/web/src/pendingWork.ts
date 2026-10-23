/**
 * Trabajo en curso que se perdería al salir de la sesión o cerrar la pestaña. Cada parte de la
 * aplicación que lo tenga registra una comprobación que devuelve el aviso, o null si no hay
 * nada pendiente; el marco de la zona privada y la pestaña preguntan aquí sin conocerlas.
 */
type PendingWorkCheck = () => string | null;

const checks = new Set<PendingWorkCheck>();

export function registerPendingWork(check: PendingWorkCheck): () => void {
  checks.add(check);
  return () => {
    checks.delete(check);
  };
}

/** Aviso del primer trabajo pendiente, o null si se puede salir sin perder nada. */
export function pendingWorkWarning(): string | null {
  for (const check of checks) {
    const warning = check();
    if (warning) return warning;
  }
  return null;
}
