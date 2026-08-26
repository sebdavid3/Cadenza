#!/usr/bin/env bash

# Función para terminar procesos al presionar Ctrl+C
cleanup() {
    echo ""
    echo ">> Deteniendo servidores Backend y Frontend..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo "=========================================================="
echo "          Iniciando Cadenza OMR en Modo Local             "
echo "=========================================================="

# Activar entorno conda si está disponible
if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)"
    conda activate homr-proto 2>/dev/null || echo "Aviso: No se pudo activar homr-proto automáticamente. Usando Python del sistema."
fi

# 1. Iniciar Backend FastAPI
echo "[*] Iniciando Backend en http://localhost:8000 ..."
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# 2. Iniciar Frontend Vite
echo "[*] Iniciando Frontend en http://localhost:5173 ..."
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
cd ..

echo "=========================================================="
echo ">> Backend corriendo en:  http://localhost:8000 (Docs: /docs)"
echo ">> Frontend corriendo en: http://localhost:5173"
echo ">> Presiona Ctrl+C para detener ambos servidores."
echo "=========================================================="

# Esperar a que los procesos hijos terminen
wait $BACKEND_PID $FRONTEND_PID
