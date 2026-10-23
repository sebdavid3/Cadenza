export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "payload-too-large"
  | "unsupported-media-type"
  | "validation"
  | "rate-limited"
  | "server"
  | "network"
  | "timeout"
  | "aborted"
  | "unexpected";

// Mensajes propios por tipo de error. El `detail` del backend mezcla español e inglés
// y no se muestra nunca; cada vista puede afinar el mensaje según su contexto.
const MESSAGES: Record<ApiErrorKind, string> = {
  unauthorized: "Tu sesión no es válida o ha caducado. Vuelve a entrar.",
  forbidden: "No tienes permiso para hacer esto.",
  "not-found": "No se encontró lo que buscabas.",
  conflict: "Algo cambió mientras tanto. Recarga e inténtalo de nuevo.",
  "payload-too-large": "El archivo supera el tamaño máximo que admite el servidor.",
  "unsupported-media-type":
    "El servidor no acepta ese tipo de archivo. Sube una imagen PNG o JPEG.",
  validation: "Los datos enviados no son válidos.",
  "rate-limited": "Demasiados intentos. Espera unos minutos antes de volver a probar.",
  server: "El servidor tuvo un problema. Inténtalo de nuevo en un momento.",
  network: "No se pudo conectar con el servidor. Comprueba la conexión.",
  timeout: "El servidor tardó demasiado en responder.",
  aborted: "La petición se canceló.",
  unexpected: "Respuesta inesperada del servidor.",
};

export function kindForStatus(status: number): ApiErrorKind {
  switch (status) {
    case 401:
      return "unauthorized";
    case 403:
      return "forbidden";
    case 404:
      return "not-found";
    case 409:
      return "conflict";
    case 413:
      return "payload-too-large";
    case 415:
      return "unsupported-media-type";
    case 422:
      return "validation";
    case 429:
      return "rate-limited";
    default:
      return status >= 500 ? "server" : "unexpected";
  }
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** Código HTTP, o null si no hubo respuesta (red, timeout, cancelación). */
  readonly status: number | null;
  /** `detail` de la respuesta, solo para depurar: nunca se muestra en la interfaz. */
  readonly detail: unknown;

  constructor(kind: ApiErrorKind, status: number | null = null, detail: unknown = null) {
    super(MESSAGES[kind]);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

/** Mensaje presentable de cualquier error capturado. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Algo salió mal. Inténtalo de nuevo.";
}
