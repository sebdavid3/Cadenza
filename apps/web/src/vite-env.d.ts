/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL base de la API. Por defecto `/api`, que el servidor de desarrollo reenvía al backend. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
