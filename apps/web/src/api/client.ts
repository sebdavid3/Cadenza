import type { HealthStatusResponse } from "../types";
import { DEFAULT_TIMEOUT_MS, resolveBaseUrl } from "./config";
import { ApiError, kindForStatus } from "./errors";

export type QueryValue = string | number | boolean | null | undefined;

export interface ApiClientOptions {
  /** URL base de la API; por defecto `VITE_API_BASE_URL` o `/api`. */
  baseUrl?: string;
  /** Token Bearer vigente, o null si no hay sesión. */
  getToken?: () => string | null;
  /** Se llama cuando una petición autenticada recibe un 401 (token caducado o revocado). */
  onUnauthorized?: () => void;
  fetch?: typeof fetch;
  timeoutMs?: number;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  /** Cuerpo JSON. */
  json?: unknown;
  /** Cuerpo de formulario: `multipart/form-data` o `application/x-www-form-urlencoded`. */
  body?: FormData | URLSearchParams;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Si es false no se envía el token (rutas públicas como `/health` o `/auth/login`). */
  auth?: boolean;
  responseType?: "json" | "blob";
}

function buildQuery(query: Record<string, QueryValue> | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.append(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function readDetail(response: Response): Promise<unknown> {
  try {
    const body = (await response.json()) as { detail?: unknown } | null;
    return body?.detail ?? null;
  } catch {
    return null;
  }
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? resolveBaseUrl()).replace(/\/+$/, "");
  const defaultTimeout = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch = (input: string, init: RequestInit) => (options.fetch ?? fetch)(input, init);

  async function request<T = unknown>(path: string, req: RequestOptions = {}): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, req.timeoutMs ?? defaultTimeout);
    const forwardAbort = () => {
      controller.abort();
    };
    if (req.signal?.aborted) controller.abort();
    req.signal?.addEventListener("abort", forwardAbort, { once: true });

    const failure = () =>
      new ApiError(timedOut ? "timeout" : controller.signal.aborted ? "aborted" : "network");

    const headers = new Headers();
    const token = req.auth === false ? null : (options.getToken?.() ?? null);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let body: BodyInit | undefined;
    if (req.json !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(req.json);
    } else if (req.body) {
      // El navegador fija el Content-Type (con el boundary en multipart).
      body = req.body;
    }
    if (req.responseType !== "blob") headers.set("Accept", "application/json");

    try {
      let response: Response;
      try {
        response = await doFetch(`${baseUrl}${path}${buildQuery(req.query)}`, {
          method: req.method ?? "GET",
          headers,
          body,
          signal: controller.signal,
        });
      } catch {
        throw failure();
      }

      if (!response.ok) {
        const detail = await readDetail(response);
        if (response.status === 401 && token) options.onUnauthorized?.();
        throw new ApiError(kindForStatus(response.status), response.status, detail);
      }

      try {
        if (req.responseType === "blob") return (await response.blob()) as T;
        if (response.status === 204) return undefined as T;
        return (await response.json()) as T;
      } catch {
        throw controller.signal.aborted ? failure() : new ApiError("unexpected", response.status);
      }
    } finally {
      clearTimeout(timer);
      req.signal?.removeEventListener("abort", forwardAbort);
    }
  }

  return {
    request,
    /** `GET /health`: pública, sin token. */
    health: (signal?: AbortSignal) =>
      request<HealthStatusResponse>("/health", { auth: false, signal }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
