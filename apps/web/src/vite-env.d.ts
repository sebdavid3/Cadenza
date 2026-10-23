/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL base de la API. Por defecto `/api`, que el servidor de desarrollo reenvía al backend. */
  readonly VITE_API_BASE_URL?: string;
  /** `true` si el despliegue abre el registro público (ADR-0022); si no, no se enlaza. */
  readonly VITE_REGISTRATION_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
