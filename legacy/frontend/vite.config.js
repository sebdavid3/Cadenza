import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://backend:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/transcribe': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/health': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/gpu-info': {
        target: backendTarget,
        changeOrigin: true,
      },
      // Registro en vivo por SSE: la conexion queda abierta indefinidamente
      '/logs': {
        target: backendTarget,
        changeOrigin: true,
        // Sin esto el proxy cierra la corriente de eventos por inactividad
        timeout: 0,
        proxyTimeout: 0,
      },
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/transcribe': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/health': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/gpu-info': {
        target: backendTarget,
        changeOrigin: true,
      },
      // Registro en vivo por SSE: la conexion queda abierta indefinidamente
      '/logs': {
        target: backendTarget,
        changeOrigin: true,
        // Sin esto el proxy cierra la corriente de eventos por inactividad
        timeout: 0,
        proxyTimeout: 0,
      },
    }
  }
})
