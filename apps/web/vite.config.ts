/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";

// La API no lleva prefijo (/auth, /sessions, /health...). En desarrollo se agrupa bajo
// /api para que ninguna ruta de la interfaz coincida con una ruta reenviada al backend
// (docs/api/frontend-handoff.md §5.5); el prefijo se quita al reenviar.
const API_PREFIX = "/api";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.CADENZA_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const proxy: Record<string, ProxyOptions> = {
    [API_PREFIX]: {
      target,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api(?=\/|$)/, "") || "/",
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
    },
  };
});
