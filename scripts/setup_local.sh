#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=========================================================="
echo "    Configuración Local de Cadenza OMR (HOMR + GPU)       "
echo "=========================================================="

# 1. Verificar si Conda está instalado
if ! command -v conda &> /dev/null; then
    echo "[!] Conda no está en el PATH. Intentando buscar instalación estándar..."
    CONDA_BASE_SEARCH=("$HOME/miniconda3" "$HOME/anaconda3" "/opt/conda" "$HOME/miniforge3")
    for dir in "${CONDA_BASE_SEARCH[@]}"; do
        if [ -f "$dir/etc/profile.d/conda.sh" ]; then
            source "$dir/etc/profile.d/conda.sh"
            break
        fi
    done
fi

if ! command -v conda &> /dev/null; then
    echo "[!] ERROR: Conda no está instalado. Instala Miniconda o Anaconda antes de continuar."
    exit 1
fi

echo "[1/4] Creando entorno Conda 'homr-proto' con Python 3.11..."
conda create -n homr-proto python=3.11 -y

# Activar entorno para la sesión actual del script
eval "$(conda shell.bash hook)"
conda activate homr-proto

echo "[2/4] Instalando PyTorch con aceleración CUDA 12.1..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo "[3/4] Instalando dependencias de Backend (HOMR, music21, FastAPI)..."
pip install -r backend/requirements-gpu.txt

echo "[4/4] Instalando dependencias de Frontend (React, Vite, OSMD, Tone.js)..."
cd frontend
npm install
cd ..

echo "=========================================================="
echo "    Verificando Aceleración por Hardware (GPU / CUDA)     "
echo "=========================================================="
python backend/check_gpu.py

echo ""
echo ">> ¡Instalación completada con éxito!"
echo ">> Para iniciar la aplicación localmente:"
echo "   conda activate homr-proto"
echo "   ./scripts/run-local.sh"
