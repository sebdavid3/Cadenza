/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";

// La API no lleva prefijo (/auth, /sessions, /health...). En desarrollo se agrupa bajo
// /api para que ninguna ruta de la interfaz coincida con una ruta reenviada al backend
// (docs/api/frontend-handoff.md §5.5); el prefijo se quita al reenviar. Solo cuenta /api
// como segmento completo: /api, /api/... o /api?...; /apidocs no se reenvía.
const API_PREFIX = /^\/api(?=[/?]|$)/;

const webRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig(({ mode }) => {
  // Las variables se leen de apps/web aunque Vite se lance desde otro directorio.
  const env = loadEnv(mode, webRoot, "");
  const target = env.CADENZA_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const proxy: Record<string, ProxyOptions> = {
    [API_PREFIX.source]: {
      target,
      changeOrigin: true,
      rewrite: (path) => {
        const rest = path.replace(API_PREFIX, "");
        return rest.startsWith("/") ? rest : `/${rest}`;
      },
    },
  };

  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      // Cada prueba empieza con las variables VITE_ del build (vi.stubEnv) sin tocar.
      unstubEnvs: true,
      // Zona fija y distinta de UTC: las pruebas de fechas comprueban la conversión a hora local.
      env: { TZ: "America/Bogota" },
    },
  };
});
