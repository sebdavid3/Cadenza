@echo off
echo ==========================================================
echo     Configuracion Local de Cadenza OMR (HOMR + GPU)
echo ==========================================================

echo [1/4] Creando entorno Conda 'homr-proto' con Python 3.11...
call conda create -n homr-proto python=3.11 -y

echo [2/4] Activando entorno homr-proto...
call conda activate homr-proto

echo [3/4] Instalando PyTorch con soporte CUDA 12.1 y dependencias backend...
call pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
call pip install -r backend\requirements-gpu.txt

echo [4/4] Instalando dependencias de Frontend...
cd frontend
call npm install
cd ..

echo ==========================================================
echo     Verificando Aceleracion por Hardware (GPU / CUDA)
echo ==========================================================
python backend\check_gpu.py

echo.
echo >> Instalacion completada.
echo >> Para iniciar ejecuta: run-local.bat
pause
